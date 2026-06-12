"""Gera o ICO multirresolucao usado pelo executavel Windows."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    png_path = root / 'assets' / 'app_icon.png'
    ico_path = root / 'assets' / 'app_icon.ico'
    if not png_path.exists():
        raise FileNotFoundError(f'Icone PNG nao encontrado: {png_path}')

    with Image.open(png_path) as source:
        image = source.convert('RGBA')
        if image.width != image.height:
            raise ValueError('assets/app_icon.png precisa ser quadrado.')
        if image.width < 256:
            raise ValueError('assets/app_icon.png precisa ter pelo menos 256x256 px.')
        image.save(
            ico_path,
            format='ICO',
            sizes=[
                (16, 16),
                (24, 24),
                (32, 32),
                (48, 48),
                (64, 64),
                (128, 128),
                (256, 256),
            ],
        )

    print(f'Icone gerado: {ico_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
