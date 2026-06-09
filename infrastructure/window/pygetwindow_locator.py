"""Adapter de localizacao de janela usando a implementacao atual."""

from __future__ import annotations

from clients.window_client import encontrar_janela
from domain.window.entities import WindowBounds, WindowInfo


class PyGetWindowLocator:
    """Localiza a janela do Clash of Clans pelo titulo configurado."""

    def find_target_window(self, title: str, match_mode: str, activate: bool) -> WindowInfo:
        janela = encontrar_janela(title, ativar=activate, modo_comparacao=match_mode)
        return WindowInfo(
            title=janela.titulo,
            bounds=WindowBounds(
                left=janela.esquerda,
                top=janela.topo,
                width=janela.largura,
                height=janela.altura,
            ),
        )

