"""Resolucao e configuracao do executavel do Tesseract em runtime."""

from __future__ import annotations

import logging
import os
import ctypes
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

try:
    import pytesseract
except Exception:  # pragma: no cover - import guard only
    pytesseract = None

from config import resolver_diretorio_aplicacao, resolver_diretorio_bundle


def _candidate_base_dirs() -> list[Path]:
    return [resolver_diretorio_aplicacao(), resolver_diretorio_bundle()]


def _to_windows_short_path(path: Path) -> Path:
    """Converte para o short path do Windows quando disponivel."""
    if os.name != 'nt':
        return path
    buffer_size = 4096
    buffer = ctypes.create_unicode_buffer(buffer_size)
    result = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, buffer_size)
    if result == 0:
        return path
    return Path(buffer.value)


def _resolve_explicit_tesseract_cmd(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    if path.is_absolute():
        return path
    for base_dir in _candidate_base_dirs():
        candidate = (base_dir / path).resolve()
        if candidate.exists():
            return candidate
    return (resolver_diretorio_aplicacao() / path).resolve()


def resolve_tesseract_cmd(cfg: dict[str, Any] | None = None) -> Path | None:
    """Resolve o caminho do tesseract.exe por config ou local padrao empacotado."""
    vision_cfg = {} if cfg is None else cfg.get('vision', {})
    explicit = _resolve_explicit_tesseract_cmd(vision_cfg.get('tesseract_cmd'))
    if explicit is not None:
        return explicit

    for base_dir in _candidate_base_dirs():
        candidate = (base_dir / 'runtime' / 'tesseract' / 'tesseract.exe').resolve()
        if candidate.exists():
            return candidate
    return None


def configure_tesseract_runtime(cfg: dict[str, Any] | None = None) -> Path | None:
    """Configura pytesseract para usar o binario resolvido, quando disponivel."""
    if pytesseract is None:
        return None
    tesseract_cmd = resolve_tesseract_cmd(cfg)
    if tesseract_cmd is None:
        return None

    tesseract_cmd = _to_windows_short_path(tesseract_cmd)
    pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)
    _configure_hidden_tesseract_subprocess()
    tessdata_dir = _to_windows_short_path(tesseract_cmd.parent / 'tessdata')
    if tessdata_dir.exists():
        os.environ['TESSDATA_PREFIX'] = str(tessdata_dir)
    logging.info('Tesseract configurado em: %s', tesseract_cmd)
    return tesseract_cmd


def _configure_hidden_tesseract_subprocess() -> None:
    """Impede o tesseract.exe de abrir uma janela de console no Windows."""
    if os.name != 'nt' or pytesseract is None:
        return
    module = pytesseract.pytesseract
    if getattr(module.subprocess, '_playgames_hidden', False) is not True:
        module.subprocess = _HiddenSubprocessProxy(module.subprocess)

    current = module.subprocess_args
    if getattr(current, '_playgames_hidden', False) is True:
        return

    def hidden_subprocess_args(include_stdout: bool = True):
        kwargs = current(include_stdout)
        _apply_hidden_process_options(kwargs)
        return kwargs

    hidden_subprocess_args._playgames_hidden = True
    module.subprocess_args = hidden_subprocess_args


def _apply_hidden_process_options(kwargs: dict[str, Any]) -> None:
    """Forca as opcoes de criacao invisivel suportadas pelo Windows."""
    startupinfo = kwargs.get('startupinfo')
    if startupinfo is None:
        startupinfo = subprocess.STARTUPINFO()
        kwargs['startupinfo'] = startupinfo
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    kwargs['creationflags'] = int(kwargs.get('creationflags', 0)) | subprocess.CREATE_NO_WINDOW
    kwargs['shell'] = False


def build_hidden_subprocess_kwargs() -> dict[str, Any]:
    """Retorna kwargs padrao para iniciar subprocessos sem console visivel no Windows."""
    kwargs: dict[str, Any] = {}
    if os.name == 'nt':
        _apply_hidden_process_options(kwargs)
    return kwargs


class _HiddenSubprocessProxy:
    """Proxy local que protege toda chamada Popen feita pelo pytesseract."""

    _playgames_hidden = True

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)

    def Popen(self, *args, **kwargs):
        _apply_hidden_process_options(kwargs)
        return self._wrapped.Popen(*args, **kwargs)


def pytesseract_required(cfg: dict[str, Any] | None = None) -> bool:
    """Indica se a configuracao atual depende do backend pytesseract."""
    if not cfg:
        return False
    vision_cfg = cfg.get('vision', {})
    return str(vision_cfg.get('ocr_engine', 'pytesseract')) == 'pytesseract'


def validate_tesseract_runtime(cfg: dict[str, Any] | None = None) -> None:
    """Falha cedo quando pytesseract e requerido, mas o binario nao foi localizado."""
    if not pytesseract_required(cfg):
        return
    if pytesseract is None:
        raise ValueError('pytesseract nao esta instalado no ambiente atual.')
    tesseract_cmd = configure_tesseract_runtime(cfg)
    if tesseract_cmd is None:
        raise ValueError(
            'Tesseract OCR nao encontrado. Coloque o binario em runtime/tesseract/tesseract.exe '
            'ou configure vision.tesseract_cmd no config.yaml.'
        )


def warm_up_tesseract_runtime(cfg: dict[str, Any] | None = None) -> Path | None:
    """Configura e aquece o mesmo pipeline de OCR usado na leitura de recursos."""
    if not pytesseract_required(cfg):
        return None
    if pytesseract is None:
        raise ValueError('pytesseract nao esta instalado no ambiente atual.')

    tesseract_cmd = configure_tesseract_runtime(cfg)
    if tesseract_cmd is None:
        raise ValueError(
            'Tesseract OCR nao encontrado. Coloque o binario em runtime/tesseract/tesseract.exe '
            'ou configure vision.tesseract_cmd no config.yaml.'
        )

    from utils.ocr_service import ler_numeros_por_ocr

    warmup_image = np.full((32, 120, 3), 255, dtype=np.uint8)
    warmup_image[6:26, 18:102] = 230
    cv_cfg = {} if cfg is None else cfg.get('vision', {})
    general_ocr_cfg = cv_cfg.get('pytesseract', {})
    attack_loot_ocr_cfg = cv_cfg.get('attack_loot_ocr', general_ocr_cfg)
    try:
        ler_numeros_por_ocr(
            warmup_image,
            engine='pytesseract',
            ocr_config=attack_loot_ocr_cfg,
        )
        ler_numeros_por_ocr(
            warmup_image,
            engine='pytesseract',
            ocr_config=general_ocr_cfg,
        )
    except Exception as exc:
        raise ValueError(f'Falha ao inicializar o Tesseract OCR: {exc}') from exc
    logging.info('Warm-up do Tesseract concluido para OCR de saque e OCR geral.')
    return tesseract_cmd


def run_tesseract_tsv(image: np.ndarray, *, psm: int, whitelist: str, cfg: dict[str, Any] | None = None) -> str:
    """Executa o tesseract.exe diretamente e retorna a saida TSV."""
    tesseract_cmd = configure_tesseract_runtime(cfg)
    if tesseract_cmd is None:
        raise RuntimeError('Tesseract OCR nao configurado.')

    with tempfile.TemporaryDirectory(prefix='playgames_tess_') as temp_dir:
        temp_path = Path(temp_dir)
        image_path = temp_path / 'ocr_input.png'
        output_base = temp_path / 'ocr_output'
        import cv2

        if not cv2.imwrite(str(image_path), image):
            raise RuntimeError('Falha ao gravar imagem temporaria para OCR.')

        command = [
            str(tesseract_cmd),
            str(image_path),
            str(output_base),
            '--psm',
            str(int(psm)),
            '-c',
            f'tessedit_char_whitelist={whitelist}',
            'tsv',
        ]
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
            encoding='utf-8',
            **build_hidden_subprocess_kwargs(),
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f'Tesseract retornou codigo {completed.returncode}: {stderr}')

        tsv_path = output_base.with_suffix('.tsv')
        if not tsv_path.exists():
            raise RuntimeError('Tesseract nao gerou arquivo TSV.')
        return tsv_path.read_text(encoding='utf-8', errors='replace')
