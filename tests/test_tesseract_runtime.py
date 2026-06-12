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
    resolve_tesseract_cmd,
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


if __name__ == '__main__':
    unittest.main()
