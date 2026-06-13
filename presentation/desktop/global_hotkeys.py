"""Registro de hotkeys globais no Windows com filtro nativo do Qt."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter


WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
VK_F1 = 0x70
VK_F2 = 0x71
VK_F3 = 0x72


class _MSG(ctypes.Structure):
    _fields_ = [
        ('hwnd', wintypes.HWND),
        ('message', wintypes.UINT),
        ('wParam', wintypes.WPARAM),
        ('lParam', wintypes.LPARAM),
        ('time', wintypes.DWORD),
        ('pt_x', wintypes.LONG),
        ('pt_y', wintypes.LONG),
    ]


class _WindowsHotkeyEventFilter(QAbstractNativeEventFilter):
    """Converte WM_HOTKEY em callbacks Python."""

    def __init__(self, callbacks: dict[int, Callable[[], None]]) -> None:
        super().__init__()
        self._callbacks = callbacks

    def nativeEventFilter(self, event_type, message):
        if hasattr(event_type, 'data'):
            event_type = bytes(event_type.data()).decode(errors='ignore')
        elif isinstance(event_type, (bytes, bytearray)):
            event_type = bytes(event_type).decode(errors='ignore')
        else:
            event_type = str(event_type)
        if event_type not in {'windows_generic_MSG', 'windows_dispatcher_MSG'}:
            return False, 0
        msg = _MSG.from_address(int(message))
        if msg.message != WM_HOTKEY:
            return False, 0
        callback = self._callbacks.get(int(msg.wParam))
        if callback is None:
            return False, 0
        callback()
        return True, 0


class GlobalHotkeyManager:
    """Registra hotkeys globais quando a plataforma suporta."""

    def __init__(self, app) -> None:
        self._app = app
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._registered_ids: set[int] = set()
        self._filter = _WindowsHotkeyEventFilter(self._callbacks)
        self._filter_installed = False

    @property
    def is_supported(self) -> bool:
        return sys.platform == 'win32'

    def register(self, hotkey_id: int, virtual_key: int, callback: Callable[[], None]) -> bool:
        if not self.is_supported:
            return False
        user32 = ctypes.windll.user32
        if not bool(user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, virtual_key)):
            return False
        self._callbacks[hotkey_id] = callback
        self._registered_ids.add(hotkey_id)
        if not self._filter_installed:
            self._app.installNativeEventFilter(self._filter)
            self._filter_installed = True
        return True

    def unregister_all(self) -> None:
        if not self.is_supported:
            return
        user32 = ctypes.windll.user32
        for hotkey_id in tuple(self._registered_ids):
            user32.UnregisterHotKey(None, hotkey_id)
        self._registered_ids.clear()
        self._callbacks.clear()
        if self._filter_installed:
            self._app.removeNativeEventFilter(self._filter)
            self._filter_installed = False
