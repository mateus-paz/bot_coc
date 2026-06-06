"""Rotinas de OCR e normalizacao de numeros lidos da tela."""

from __future__ import annotations

import logging
import re
from typing import Any

import cv2
import numpy as np

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import easyocr
except Exception:
    easyocr = None


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


leitor_easyocr: Any = None


def extrair_texto_pytesseract(imagem_bgr: np.ndarray) -> str:
    """Extrai texto via pytesseract com preprocessamento simples."""
    if pytesseract is None:
        logging.warning('pytesseract indisponivel; OCR desativado na pratica.')
        return ''
    cinza = cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2GRAY)
    cinza = cv2.resize(cinza, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    cinza = cv2.GaussianBlur(cinza, (3, 3), 0)
    _, limiar = cv2.threshold(cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    config = '--psm 6 -c tessedit_char_whitelist=0123456789.,KMkm '
    return pytesseract.image_to_string(limiar, config=config)


def extrair_texto_easyocr(imagem_bgr: np.ndarray) -> str:
    """Extrai texto via EasyOCR com cache do reader."""
    global leitor_easyocr
    if easyocr is None:
        logging.warning('easyocr indisponivel; OCR desativado na pratica.')
        return ''
    if leitor_easyocr is None:
        leitor_easyocr = easyocr.Reader(['en'], gpu=False, verbose=False)
    cinza = cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2GRAY)
    cinza = cv2.resize(cinza, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    resultado = leitor_easyocr.readtext(cinza, detail=0, paragraph=False, allowlist='0123456789.,KMkm')
    return ' '.join(str(item) for item in resultado)


def ler_numeros_por_ocr(imagem_bgr: np.ndarray, engine: str = 'pytesseract') -> list[int]:
    """Executa OCR no engine selecionado e converte os tokens numericos encontrados."""
    if engine == 'easyocr':
        texto = extrair_texto_easyocr(imagem_bgr)
    else:
        texto = extrair_texto_pytesseract(imagem_bgr)
    tokens = re.findall(r'[0-9][0-9., ]*[KkMm]?', texto)
    valores = []
    for token in tokens:
        valor = normalizar_numero_ocr(token)
        if valor is not None:
            valores.append(valor)
    logging.info('OCR engine=%s texto=%r valores=%s', engine, texto.strip(), valores)
    return valores
