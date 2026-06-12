"""Adapter de localizacao de janela usando a implementacao atual."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

import pygetwindow as gw

from clients.window_client import ErroJanela, titulo_janela_corresponde
from domain.window.entities import WindowBounds, WindowInfo


class PyGetWindowLocator:
    """Localiza a janela do Clash of Clans pelo titulo configurado."""

    def find_target_window(self, title: str, match_mode: str, activate: bool) -> WindowInfo:
        candidates = [
            window
            for window in gw.getAllWindows()
            if titulo_janela_corresponde(window.title, title, match_mode)
        ]
        if not candidates:
            raise ErroJanela(
                f"Nenhuma janela encontrada com match_mode={match_mode!r} para: {title!r}"
            )

        window = max(candidates, key=lambda item: max(item.width, 0) * max(item.height, 0))
        window_id = int(getattr(window, '_hWnd', 0))
        if not window_id:
            raise ErroJanela('A janela encontrada nao possui um identificador nativo valido.')

        if activate and not self._is_minimized(window_id):
            try:
                window.activate()
            except Exception:
                pass

        info = self.inspect_target_window(window_id)
        if info is None:
            raise ErroJanela('A janela encontrada deixou de existir.')
        if info.bounds.width <= 0 or info.bounds.height <= 0:
            raise ErroJanela('A janela encontrada esta sem area cliente valida.')
        return info

    def inspect_target_window(self, window_id: int) -> WindowInfo | None:
        """Consulta geometria e estado da mesma janela pelo identificador nativo."""
        user32 = ctypes.windll.user32
        if not user32.IsWindow(wintypes.HWND(window_id)):
            return None

        title_length = user32.GetWindowTextLengthW(wintypes.HWND(window_id))
        title_buffer = ctypes.create_unicode_buffer(title_length + 1)
        user32.GetWindowTextW(wintypes.HWND(window_id), title_buffer, len(title_buffer))
        minimized = self._is_minimized(window_id)
        bounds = self._client_bounds(window_id)
        return WindowInfo(
            title=title_buffer.value,
            bounds=bounds,
            window_id=window_id,
            is_minimized=minimized,
        )

    @staticmethod
    def activate_target_window(window_id: int) -> bool:
        """Restaura e coloca a janela alvo em primeiro plano."""
        user32 = ctypes.windll.user32
        hwnd = wintypes.HWND(window_id)
        if not user32.IsWindow(hwnd):
            return False
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))

    @staticmethod
    def attach_owned_window(child_window_id: int, owner_window_id: int) -> None:
        """Define a toolbar como janela pertencente ao Clash no Windows."""
        gwlp_hwndparent = -8
        set_window_long_ptr = ctypes.windll.user32.SetWindowLongPtrW
        set_window_long_ptr.argtypes = (
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_ssize_t,
        )
        set_window_long_ptr.restype = ctypes.c_ssize_t
        set_window_long_ptr(
            wintypes.HWND(child_window_id),
            gwlp_hwndparent,
            owner_window_id,
        )

    @staticmethod
    def _is_minimized(window_id: int) -> bool:
        return bool(ctypes.windll.user32.IsIconic(wintypes.HWND(window_id)))

    @staticmethod
    def _client_bounds(window_id: int) -> WindowBounds:
        user32 = ctypes.windll.user32
        client_rect = wintypes.RECT()
        if not user32.GetClientRect(wintypes.HWND(window_id), ctypes.byref(client_rect)):
            return WindowBounds(left=0, top=0, width=0, height=0)

        client_origin = wintypes.POINT(client_rect.left, client_rect.top)
        if not user32.ClientToScreen(wintypes.HWND(window_id), ctypes.byref(client_origin)):
            return WindowBounds(left=0, top=0, width=0, height=0)

        return WindowBounds(
            left=int(client_origin.x),
            top=int(client_origin.y),
            width=max(0, int(client_rect.right - client_rect.left)),
            height=max(0, int(client_rect.bottom - client_rect.top)),
        )
