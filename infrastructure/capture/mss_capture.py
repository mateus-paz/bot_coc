"""Captura de janelas usando MSS como backend principal."""

from __future__ import annotations

import cv2
import mss
import numpy as np

from domain.window.entities import WindowInfo


class MSSScreenCapture:
    """Captura a regiao da janela alvo usando MSS."""

    def capture_window(self, window: WindowInfo) -> np.ndarray:
        bounds = window.bounds
        region = {
            'left': int(bounds.left),
            'top': int(bounds.top),
            'width': int(bounds.width),
            'height': int(bounds.height),
        }
        with mss.mss() as sct:
            screenshot = sct.grab(region)
        frame = np.array(screenshot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

