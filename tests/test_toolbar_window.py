"""Smoke tests da toolbar Qt sem janela grafica real."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from domain.settings.entities import UserSettings
from domain.window.entities import WindowBounds, WindowInfo
from presentation.desktop.toolbar_window import ToolbarWindow
from services.bot_controller import BotStatus


class _GlobalHotkeyManagerFake:
    def __init__(self, app) -> None:
        self.app = app
        self.callbacks = {}
        self.unregistered = False

    def register(self, hotkey_id: int, virtual_key: int, callback) -> bool:
        self.callbacks[hotkey_id] = callback
        return True

    def unregister_all(self) -> None:
        self.unregistered = True

    def trigger(self, hotkey_id: int) -> None:
        self.callbacks[hotkey_id]()


class _SetupServiceFake:
    def __init__(self, target: WindowInfo) -> None:
        self.target = target
        self.saved_settings = None
        self.activate_calls = 0

    def save_settings(self, settings) -> None:
        self.saved_settings = settings

    def inspect_target_window(self, window_id: int):
        return self.target

    def activate_target_window(self, window_id: int) -> bool:
        self.activate_calls += 1
        return window_id == self.target.window_id

class _AutomationServiceFake:
    def __init__(self) -> None:
        self.current_status = BotStatus('idle', False, False, False, None)
        self.start_calls = 0
        self.pause_calls = 0
        self.stop_calls = 0

    def status(self):
        return self.current_status

    def start(self) -> bool:
        self.start_calls += 1
        return True

    def pause(self) -> bool:
        self.pause_calls += 1
        return True

    def stop(self) -> bool:
        self.stop_calls += 1
        return True


class ToolbarWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.target = WindowInfo(
            title='Clash of Clans',
            bounds=WindowBounds(left=0, top=0, width=1600, height=900),
            window_id=123,
        )
        self.setup_service = _SetupServiceFake(self.target)
        self.automation_service = _AutomationServiceFake()
        self.hotkeys = _GlobalHotkeyManagerFake(self.app)
        self.window = ToolbarWindow(
            setup_service=self.setup_service,
            automation_service=self.automation_service,
            settings=UserSettings(),
            target_window=self.target,
            global_hotkey_manager=self.hotkeys,
        )

    def tearDown(self) -> None:
        self.window.close()

    def test_initial_state_and_window_flags(self) -> None:
        self.assertEqual(470, self.window.width())
        self.assertTrue(self.window.start_button.isEnabled())
        self.assertFalse(self.window.pause_button.isEnabled())
        self.assertTrue(
            self.window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        )
        window_type = self.window.windowFlags() & Qt.WindowType.WindowType_Mask
        self.assertEqual(Qt.WindowType.Window, window_type)

    def test_profile_selection_is_persisted(self) -> None:
        self.window.cv_combo.setCurrentIndex(self.window.cv_combo.findData('cv_17'))

        self.assertIsNotNone(self.setup_service.saved_settings)
        self.assertEqual('cv_17', self.setup_service.saved_settings.cv_profile)

    def test_target_poll_does_not_reposition_or_hide_toolbar(self) -> None:
        self.window.show()
        self.window.move(75, 90)
        self.setup_service.target = WindowInfo(
            title=self.target.title,
            bounds=WindowBounds(left=500, top=400, width=800, height=500),
            window_id=self.target.window_id,
            is_minimized=True,
        )

        self.window._poll_target_window()

        self.assertTrue(self.window.isVisible())
        self.assertEqual((75, 90), (self.window.x(), self.window.y()))

    def test_pin_button_locks_drag_mode(self) -> None:
        self.window.pin_button.setChecked(True)

        self.assertTrue(self.window.pin_button.isChecked())
        self.assertEqual('Posicao bloqueada', self.window.pin_button.toolTip())
        self.assertFalse(self.window.pin_button.icon().isNull())

    def test_combo_popup_has_explicit_readable_colors(self) -> None:
        stylesheet = self.window.styleSheet()

        self.assertIn('QComboBox QAbstractItemView', stylesheet)
        self.assertIn('color: #171717', stylesheet)

    def test_start_activates_target_before_starting_worker(self) -> None:
        self.window._handle_start()

        self.assertGreaterEqual(self.setup_service.activate_calls, 1)

    def test_action_buttons_load_icons_and_shortcut_tooltips(self) -> None:
        self.assertFalse(self.window.start_button.icon().isNull())
        self.assertFalse(self.window.pause_button.icon().isNull())
        self.assertFalse(self.window.stop_button.icon().isNull())
        self.assertFalse(self.window.pin_button.icon().isNull())
        self.assertEqual('Pausar (F2)', self.window.pause_button.toolTip())
        self.assertEqual('Encerrar app (F3)', self.window.stop_button.toolTip())
        self.assertEqual('Iniciar (F1)', self.window.start_button.toolTip())
        self.assertEqual((34, 30), (self.window.start_button.width(), self.window.start_button.height()))
        self.assertEqual((40, 30), (self.window.pin_button.width(), self.window.pin_button.height()))

    def test_global_function_keys_trigger_start_and_pause_actions(self) -> None:
        self.hotkeys.trigger(1)
        self.automation_service.current_status = BotStatus('running', True, False, False, None)
        self.window._refresh_status()
        self.hotkeys.trigger(2)

        self.assertEqual(1, self.automation_service.start_calls)
        self.assertEqual(1, self.automation_service.pause_calls)
        self.assertEqual(0, self.automation_service.stop_calls)

    def test_disabled_pause_shortcut_does_not_trigger_action(self) -> None:
        self.hotkeys.trigger(2)

        self.assertEqual(0, self.automation_service.pause_calls)

    def test_stop_shortcut_requests_stop_and_closes_app(self) -> None:
        self.hotkeys.trigger(3)

        self.assertEqual(1, self.automation_service.stop_calls)
        self.assertFalse(self.window.isVisible())

    def test_close_unregisters_global_hotkeys(self) -> None:
        self.window.close()

        self.assertTrue(self.hotkeys.unregistered)


if __name__ == '__main__':
    unittest.main()
