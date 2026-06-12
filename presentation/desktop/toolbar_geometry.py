"""Calculo de posicionamento da toolbar sobre a janela alvo."""

from __future__ import annotations

from dataclasses import dataclass

from domain.window.entities import WindowBounds


@dataclass(frozen=True)
class ToolbarGeometry:
    """Geometria absoluta da toolbar."""

    left: int
    top: int
    width: int
    height: int


def calculate_toolbar_geometry(
    target: WindowBounds,
    *,
    width_ratio: float = 0.22,
    center_x_ratio: float = 0.75,
    top_offset: int = 8,
    min_width: int = 500,
    max_width: int = 620,
    height: int = 52,
) -> ToolbarGeometry:
    """Ancora a barra na quinta de seis faixas horizontais da area cliente."""
    available_width = max(1, target.width)
    desired_width = round(available_width * width_ratio)
    width = min(max(desired_width, min_width), max_width, available_width)
    center_x = target.left + round(available_width * center_x_ratio)
    left = center_x - (width // 2)
    max_left = target.left + available_width - width
    left = min(max(left, target.left), max_left)
    top = target.top + max(0, top_offset)
    return ToolbarGeometry(left=left, top=top, width=width, height=height)
