"""Testes do icone usado no executavel Windows."""

from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image


class AppIconTest(unittest.TestCase):
    def test_source_png_is_square_and_large_enough(self) -> None:
        icon_path = Path('assets/app_icon.png')

        with Image.open(icon_path) as image:
            self.assertEqual(image.width, image.height)
            self.assertGreaterEqual(image.width, 256)

    def test_generated_ico_contains_windows_resolutions(self) -> None:
        icon_path = Path('assets/app_icon.ico')

        with Image.open(icon_path) as image:
            sizes = image.info.get('sizes', set())

        self.assertTrue(
            {(16, 16), (32, 32), (48, 48), (256, 256)}.issubset(sizes)
        )


if __name__ == '__main__':
    unittest.main()
