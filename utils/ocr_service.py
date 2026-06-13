"""Rotinas de OCR e normalizacao de numeros lidos da tela."""

from __future__ import annotations

import logging
import re
from typing import Any
from io import StringIO

import cv2
import numpy as np
import csv

from utils.tesseract_runtime import run_tesseract_tsv


def normalizar_numero_ocr(token: str) -> int | None:
    """Normaliza um token OCR como `1.2M` ou `850k` para inteiro."""
    token = token.strip().upper().replace('O', '0')
    multiplicador = 1
    if token.endswith('M'):
        multiplicador = 1_000_000
        token = token[:-1]
    elif token.endswith('K'):
        multiplicador = 1_000
        token = token[:-1]
    token = re.sub(r'[^0-9.,]', '', token)
    if not token:
        return None
    if multiplicador > 1 and (',' in token or '.' in token):
        try:
            return int(float(token.replace(',', '.')) * multiplicador)
        except ValueError:
            return None
    digitos = re.sub(r'\D', '', token)
    if not digitos:
        return None
    return int(digitos) * multiplicador


def _resolve_psm_modes(config: dict[str, Any] | None, *, default: list[int]) -> list[int]:
    configured = (config or {}).get('psm_modes', default)
    if isinstance(configured, int):
        return [configured]
    if not isinstance(configured, list):
        return list(default)
    modes: list[int] = []
    for value in configured:
        try:
            mode = int(value)
        except (TypeError, ValueError):
            continue
        if mode not in modes:
            modes.append(mode)
    return modes or list(default)


def _build_pytesseract_variants(imagem_bgr: np.ndarray, config: dict[str, Any] | None) -> list[tuple[str, np.ndarray]]:
    cfg = config or {}
    cinza = cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2GRAY)
    upscale = float(cfg.get('upscale_factor', 3.0))
    if upscale != 1.0:
        cinza = cv2.resize(cinza, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC)
    blur_kernel = int(cfg.get('blur_kernel', 3))
    if blur_kernel > 1:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        cinza = cv2.GaussianBlur(cinza, (blur_kernel, blur_kernel), 0)

    variants: list[tuple[str, np.ndarray]] = [('gray', cinza)]

    _, binary = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(('otsu_binary', binary))

    _, binary_inv = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    variants.append(('otsu_binary_inv', binary_inv))

    if bool(cfg.get('use_adaptive_threshold', True)):
        adaptive = cv2.adaptiveThreshold(
            cinza,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )
        variants.append(('adaptive_binary', adaptive))
    return variants


def _run_pytesseract_with_confidence(image: np.ndarray, *, psm: int, whitelist: str) -> tuple[str, float]:
    tsv_output = run_tesseract_tsv(image, psm=psm, whitelist=whitelist)
    reader = csv.DictReader(StringIO(tsv_output), delimiter='\t')
    texts: list[str] = []
    confidences: list[float] = []
    for row in reader:
        normalized = str(row.get('text', '')).strip()
        if not normalized:
            continue
        texts.append(normalized)
        try:
            confidences.append(float(row.get('conf', '-1')))
        except (TypeError, ValueError):
            continue
    if not texts:
        return '', 0.0
    confidence_score = max(0.0, (sum(confidences) / max(1, len(confidences))) / 100.0) if confidences else 0.0
    return ' '.join(texts), confidence_score


def _score_numeric_ocr_candidate(text: str, confidence: float, config: dict[str, Any] | None = None) -> float:
    """Pontua uma leitura OCR priorizando numeros utilizaveis em vez de confianca bruta."""
    cfg = config or {}
    tokens = re.findall(r'[0-9][0-9.,]*[KkMm]?', text)
    valid_values = [normalizar_numero_ocr(token) for token in tokens]
    valid_values = [value for value in valid_values if value is not None]
    digit_lengths = [len(re.sub(r'[^0-9]', '', token)) for token in tokens]
    longest_token = max(digit_lengths, default=0)
    max_digits = cfg.get('expected_max_digits')
    min_digits = int(cfg.get('expected_min_digits', 0))
    alpha_chars = sum(1 for ch in text if ch.isalpha())
    punctuation_chars = sum(1 for ch in text if ch in ',.')
    oversize_penalty = 0.0
    if max_digits is not None:
        try:
            max_digits_int = int(max_digits)
        except (TypeError, ValueError):
            max_digits_int = 0
        if max_digits_int > 0:
            oversize_penalty = sum(max(0, length - max_digits_int) * 0.30 for length in digit_lengths)
    undersize_penalty = sum(max(0, min_digits - length) * 0.10 for length in digit_lengths) if min_digits > 0 else 0.0
    return (
        confidence
        + (longest_token * 0.20)
        + (len(valid_values) * 0.15)
        + (0.10 if len(tokens) == 1 and longest_token >= 4 else 0.0)
        - (alpha_chars * 0.08)
        - (punctuation_chars * 0.01)
        - oversize_penalty
        - undersize_penalty
    )


def extrair_texto_pytesseract(imagem_bgr: np.ndarray, config: dict[str, Any] | None = None) -> str:
    """Extrai texto via pytesseract com preprocessamento calibravel."""
    cfg = config or {}
    whitelist = str(cfg.get('whitelist', '0123456789.,KMkm '))
    psm_modes = _resolve_psm_modes(cfg, default=[6, 7, 11])
    best_text = ''
    best_score = -1.0
    for variant_name, variant in _build_pytesseract_variants(imagem_bgr, cfg):
        for psm in psm_modes:
            try:
                text, confidence = _run_pytesseract_with_confidence(variant, psm=psm, whitelist=whitelist)
            except Exception:
                continue
            parsed_count = len(re.findall(r'[0-9][0-9., ]*[KkMm]?', text))
            score = confidence + (parsed_count * 0.05)
            logging.debug(
                'pytesseract variant=%s psm=%s text=%r confidence=%.3f parsed=%s',
                variant_name,
                psm,
                text,
                confidence,
                parsed_count,
            )
            score = _score_numeric_ocr_candidate(text, confidence, cfg)
            if score > best_score:
                best_score = score
                best_text = text
    return best_text


def ler_numeros_por_ocr(
    imagem_bgr: np.ndarray,
    engine: str = 'pytesseract',
    ocr_config: dict[str, Any] | None = None,
) -> list[int]:
    """Executa OCR via pytesseract e converte os tokens numericos encontrados."""
    if engine != 'pytesseract':
        logging.warning('OCR engine=%s nao suportado no build final; usando pytesseract.', engine)
    texto = extrair_texto_pytesseract(imagem_bgr, config=ocr_config)
    tokens = re.findall(r'[0-9][0-9., ]*[KkMm]?', texto)
    valores = []
    for token in tokens:
        valor = normalizar_numero_ocr(token)
        if valor is not None:
            valores.append(valor)
    logging.info('OCR engine=%s texto=%r valores=%s', engine, texto.strip(), valores)
    return valores
