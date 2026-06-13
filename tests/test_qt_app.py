"""Testes do fluxo de inicializacao da UI desktop."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from domain.settings.entities import UserSettings
from domain.window.entities import WindowBounds, WindowInfo
from presentation.desktop.qt_app import run_desktop_app


class _SetupServiceFake:
    def __init__(self, target: WindowInfo) -> None:
        self.target = target
        self.settings = UserSettings()

    def load_settings(self) -> UserSettings:
        return self.settings

    def find_target_window(self, settings: UserSettings, *, activate: bool = False):
        return self.target


class _AutomationServiceFake:
    pass


class QtAppStartupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_startup_initializer_runs_before_toolbar_is_shown(self) -> None:
        target = WindowInfo(
            title='Clash of Clans',
            bounds=WindowBounds(left=0, top=0, width=1600, height=900),
            window_id=123,
        )
        setup_service = _SetupServiceFake(target)
        automation_service = _AutomationServiceFake()
        events: list[str] = []

        class _FakeToolbar:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs
                events.append('toolbar_created')

            def show(self) -> None:
                events.append('toolbar_shown')

        def initializer() -> None:
            events.append('initializer')

        with (
            patch('presentation.desktop.qt_app.ToolbarWindow', _FakeToolbar),
            patch.object(QApplication, 'exec', return_value=0),
        ):
            result = run_desktop_app(
                setup_service=setup_service,
                automation_service=automation_service,
                startup_initializer=initializer,
            )

        self.assertEqual(0, result)
        self.assertEqual(['initializer', 'toolbar_created', 'toolbar_shown'], events)


if __name__ == '__main__':
    unittest.main()
