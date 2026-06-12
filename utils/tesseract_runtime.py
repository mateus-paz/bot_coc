"""Resolucao e configuracao do executavel do Tesseract em runtime."""

from __future__ import annotations

import logging
import os
import ctypes
import subprocess
from pathlib import Path
from typing import Any

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
    if str(vision_cfg.get('ocr_engine', 'pytesseract')) == 'pytesseract':
        return True
    quantity_cfg = cfg.get('battle_bar', {}).get('quantity_classifier', {})
    backends = quantity_cfg.get('preferred_backends', [])
    if isinstance(backends, list) and 'pytesseract' in backends:
        return True
    return False


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
