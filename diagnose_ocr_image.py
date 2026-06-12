#!/usr/bin/env python3
"""Diagnostica OCR do Tesseract em uma imagem local ou ROI especifica."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import pytesseract

from utils.image_utils import escrever_png, ler_imagem_bgr
from utils.tesseract_runtime import configure_tesseract_runtime


def build_variants(image_bgr, *, upscale_factor: float, blur_kernel: int, use_adaptive_threshold: bool):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    if upscale_factor != 1.0:
        gray = cv2.resize(gray, None, fx=upscale_factor, fy=upscale_factor, interpolation=cv2.INTER_CUBIC)
    if blur_kernel > 1:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        gray = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)
    variants = [('gray', gray)]
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(('otsu_binary', binary))
    _, binary_inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    variants.append(('otsu_binary_inv', binary_inv))
    if use_adaptive_threshold:
        adaptive = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        variants.append(('adaptive_binary', adaptive))
    return variants


def run_psm(image, *, psm: int, whitelist: str) -> dict:
    data = pytesseract.image_to_data(
        image,
        config=f'--psm {psm} -c tessedit_char_whitelist={whitelist}',
        output_type=pytesseract.Output.DICT,
    )
    texts = []
    confidences = []
    for text, confidence in zip(data.get('text', []), data.get('conf', [])):
        normalized = str(text).strip()
        if not normalized:
            continue
        texts.append(normalized)
        try:
            confidences.append(float(confidence))
        except (TypeError, ValueError):
            continue
    return {
        'text': ' '.join(texts),
        'confidence': max(0.0, (sum(confidences) / max(1, len(confidences))) / 100.0) if confidences else 0.0,
        'tokens': texts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Diagnostica o pytesseract em uma imagem ou ROI.')
    parser.add_argument('--image', required=True)
    parser.add_argument('--out-dir', default='tmp/ocr_diagnostics')
    parser.add_argument('--x', type=int)
    parser.add_argument('--y', type=int)
    parser.add_argument('--w', type=int)
    parser.add_argument('--h', type=int)
    parser.add_argument('--psm', action='append', type=int, dest='psm_modes')
    parser.add_argument('--whitelist', default='0123456789.,KMkm xX')
    parser.add_argument('--upscale-factor', type=float, default=3.0)
    parser.add_argument('--blur-kernel', type=int, default=3)
    parser.add_argument('--no-adaptive-threshold', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_tesseract_runtime({'vision': {'ocr_engine': 'pytesseract', 'tesseract_cmd': 'runtime/tesseract/tesseract.exe'}})

    image = ler_imagem_bgr(Path(args.image))
    if image is None:
        print(f'[ERRO] Nao consegui ler: {args.image}')
        return 1

    if None not in (args.x, args.y, args.w, args.h):
        image = image[int(args.y):int(args.y) + int(args.h), int(args.x):int(args.x) + int(args.w)]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    escrever_png(out_dir / 'input.png', image)

    psm_modes = args.psm_modes or [6, 7, 11]
    results = []
    for variant_name, variant in build_variants(
        image,
        upscale_factor=args.upscale_factor,
        blur_kernel=args.blur_kernel,
        use_adaptive_threshold=not args.no_adaptive_threshold,
    ):
        escrever_png(out_dir / f'{variant_name}.png', variant)
        for psm in psm_modes:
            result = run_psm(variant, psm=psm, whitelist=args.whitelist)
            results.append({'variant': variant_name, 'psm': psm, **result})

    results.sort(key=lambda item: (item['confidence'], len(item['tokens'])), reverse=True)
    with (out_dir / 'results.json').open('w', encoding='utf-8') as handle:
        json.dump(results, handle, ensure_ascii=True, indent=2)

    print(f'Entrada: {args.image}')
    print(f'Saida: {out_dir.resolve()}')
    for item in results[:5]:
        print(
            f"variant={item['variant']} psm={item['psm']} confidence={item['confidence']:.3f} text={item['text']!r}"
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
