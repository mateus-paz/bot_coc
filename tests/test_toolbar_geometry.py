"""Testes do posicionamento responsivo da toolbar beta."""

from __future__ import annotations

import unittest

from domain.window.entities import WindowBounds
from presentation.desktop.toolbar_geometry import calculate_toolbar_geometry


class ToolbarGeometryTest(unittest.TestCase):
    def test_positions_toolbar_center_at_fifth_sixth_region(self) -> None:
        target = WindowBounds(left=100, top=50, width=1800, height=1000)

        geometry = calculate_toolbar_geometry(target)

        toolbar_center = geometry.left + (geometry.width // 2)
        self.assertEqual(1450, toolbar_center)
        self.assertEqual(58, geometry.top)
        self.assertEqual(500, geometry.width)
        self.assertEqual(52, geometry.height)

    def test_clamps_width_to_maximum(self) -> None:
        target = WindowBounds(left=0, top=0, width=4000, height=2000)

        geometry = calculate_toolbar_geometry(target)

        self.assertEqual(620, geometry.width)

    def test_fits_inside_small_target_window(self) -> None:
        target = WindowBounds(left=200, top=100, width=320, height=240)

        geometry = calculate_toolbar_geometry(target)

        self.assertEqual(320, geometry.width)
        self.assertEqual(200, geometry.left)


if __name__ == '__main__':
    unittest.main()
