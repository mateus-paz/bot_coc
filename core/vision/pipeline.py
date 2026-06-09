"""Utilitarios de pipeline visual independentes de GUI."""

from __future__ import annotations

import numpy as np

from domain.settings.entities import RatioRegion


def extract_ratio_region(frame: np.ndarray, region: RatioRegion) -> np.ndarray:
    """Recorta uma subimagem com base em coordenadas relativas."""
    height, width = frame.shape[:2]
    x = max(0, min(width - 1, int(region.x_ratio * width)))
    y = max(0, min(height - 1, int(region.y_ratio * height)))
    w = max(1, min(width - x, int(region.w_ratio * width)))
    h = max(1, min(height - y, int(region.h_ratio * height)))
    return frame[y:y + h, x:x + w]
