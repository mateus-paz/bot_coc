"""Protocolos para captura de frames."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from domain.window.entities import WindowInfo


class ScreenCapture(Protocol):
    """Contrato de captura de frame a partir de uma janela alvo."""

    def capture_window(self, window: WindowInfo) -> np.ndarray:
        """Captura a imagem BGR da janela informada."""

