"""Testes unitarios para resolucao do Tesseract empacotado."""

from __future__ import annotations

import tempfile
import unittest
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils.tesseract_runtime import (
    _HiddenSubprocessProxy,
    _configure_hidden_tesseract_subprocess,
    build_hidden_subprocess_kwargs,
    resolve_tesseract_cmd,
    run_tesseract_tsv,
    warm_up_tesseract_runtime,
)


class TesseractRuntimeTest(unittest.TestCase):
    def test_resolve_explicit_relative_path_against_candidate_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            target = base_dir / 'runtime' / 'tesseract' / 'tesseract.exe'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('stub', encoding='utf-8')
            cfg = {'vision': {'tesseract_cmd': 'runtime/tesseract/tesseract.exe'}}

            with patch('utils.tesseract_runtime._candidate_base_dirs', return_value=[base_dir]):
                resolved = resolve_tesseract_cmd(cfg)

        self.assertEqual(target.resolve(), resolved)

    def test_resolve_default_bundled_location(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            target = base_dir / 'runtime' / 'tesseract' / 'tesseract.exe'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('stub', encoding='utf-8')

            with patch('utils.tesseract_runtime._candidate_base_dirs', return_value=[base_dir]):
                resolved = resolve_tesseract_cmd({})

        self.assertEqual(target.resolve(), resolved)

    def test_configures_tesseract_without_console_window_on_windows(self) -> None:
        original = Mock(return_value={'stdout': object(), 'creationflags': 4})
        fake_module = SimpleNamespace(
            subprocess_args=original,
            subprocess=subprocess,
        )
        fake_pytesseract = SimpleNamespace(pytesseract=fake_module)

        with (
            patch('utils.tesseract_runtime.os.name', 'nt'),
            patch('utils.tesseract_runtime.pytesseract', fake_pytesseract),
        ):
            _configure_hidden_tesseract_subprocess()
            kwargs = fake_pytesseract.pytesseract.subprocess_args()

        self.assertEqual(4 | subprocess.CREATE_NO_WINDOW, kwargs['creationflags'])
        self.assertFalse(kwargs['shell'])
        self.assertEqual(subprocess.SW_HIDE, kwargs['startupinfo'].wShowWindow)
        self.assertTrue(kwargs['startupinfo'].dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertIsInstance(fake_pytesseract.pytesseract.subprocess, _HiddenSubprocessProxy)

    def test_popen_proxy_forces_hidden_options(self) -> None:
        wrapped = Mock()
        wrapped.Popen.return_value = object()
        proxy = _HiddenSubprocessProxy(wrapped)

        result = proxy.Popen(['tesseract.exe'], creationflags=8, shell=True)

        self.assertIs(result, wrapped.Popen.return_value)
        _, kwargs = wrapped.Popen.call_args
        self.assertEqual(8 | subprocess.CREATE_NO_WINDOW, kwargs['creationflags'])
        self.assertFalse(kwargs['shell'])
        self.assertEqual(subprocess.SW_HIDE, kwargs['startupinfo'].wShowWindow)
        self.assertTrue(kwargs['startupinfo'].dwFlags & subprocess.STARTF_USESHOWWINDOW)

    def test_build_hidden_subprocess_kwargs_sets_windows_no_console_flags(self) -> None:
        with patch('utils.tesseract_runtime.os.name', 'nt'):
            kwargs = build_hidden_subprocess_kwargs()

        self.assertIn('startupinfo', kwargs)
        self.assertTrue(kwargs['creationflags'] & subprocess.CREATE_NO_WINDOW)
        self.assertFalse(kwargs['shell'])

    def test_run_tesseract_tsv_returns_generated_tsv(self) -> None:
        completed = Mock(returncode=0, stdout='', stderr='')

        def fake_run(command, **kwargs):
            output_base = Path(command[2])
            output_base.with_suffix('.tsv').write_text('level\ttext\tconf\n5\t123\t95\n', encoding='utf-8')
            return completed

        with (
            patch('utils.tesseract_runtime.configure_tesseract_runtime', return_value=Path('C:/fake/runtime/tesseract.exe')),
            patch('utils.tesseract_runtime.subprocess.run', side_effect=fake_run),
        ):
            import numpy as np

            tsv = run_tesseract_tsv(np.full((10, 10), 255, dtype=np.uint8), psm=7, whitelist='123')

        self.assertIn('123', tsv)

    def test_warmup_runs_minimal_ocr_after_configuring_runtime(self) -> None:
        target = Path('C:/fake/runtime/tesseract.exe')
        cfg = {
            'vision': {
                'ocr_engine': 'pytesseract',
                'pytesseract': {'psm_modes': [7, 6]},
                'attack_loot_ocr': {'psm_modes': [7]},
            }
        }
        fake_ocr = Mock(return_value=[123456])

        with (
            patch('utils.tesseract_runtime.pytesseract_required', return_value=True),
            patch('utils.tesseract_runtime.pytesseract', object()),
            patch('utils.tesseract_runtime.configure_tesseract_runtime', return_value=target),
            patch('utils.ocr_service.ler_numeros_por_ocr', fake_ocr),
        ):
            resolved = warm_up_tesseract_runtime(cfg)

        self.assertEqual(target, resolved)
        self.assertEqual(2, fake_ocr.call_count)

    def test_warmup_raises_when_runtime_call_fails(self) -> None:
        cfg = {'vision': {'ocr_engine': 'pytesseract'}}
        fake_ocr = Mock(side_effect=RuntimeError('boom'))

        with (
            patch('utils.tesseract_runtime.pytesseract_required', return_value=True),
            patch('utils.tesseract_runtime.pytesseract', object()),
            patch('utils.tesseract_runtime.configure_tesseract_runtime', return_value=Path('C:/fake/runtime/tesseract.exe')),
            patch('utils.ocr_service.ler_numeros_por_ocr', fake_ocr),
        ):
            with self.assertRaisesRegex(ValueError, 'Falha ao inicializar o Tesseract OCR'):
                warm_up_tesseract_runtime(cfg)


if __name__ == '__main__':
    unittest.main()
