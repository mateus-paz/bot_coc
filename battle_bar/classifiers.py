"""Classificadores de tipo e estado para conteudos da barra."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytesseract

from battle_bar.domain import AvailabilityState, ContentState, DetectorKind, SlotContent, SlotContentType, SlotLaneHint, SlotPosition
from utils.geometry_utils import extrair_roi
from utils.template_matching import ler_imagem


def _type_from_lane(lane: SlotLaneHint) -> SlotContentType:
    mapping = {
        SlotLaneHint.TROOP_SECTION: SlotContentType.TROOP,
        SlotLaneHint.HERO_SECTION: SlotContentType.HERO,
        SlotLaneHint.SPELL_SECTION: SlotContentType.SPELL,
        SlotLaneHint.SIEGE_SECTION: SlotContentType.SIEGE_MACHINE,
    }
    return mapping.get(lane, SlotContentType.UNKNOWN)


class RuleBasedContentTypeClassifier:
    """Classifica tipo com base estrutural e, opcionalmente, por templates."""

    def __init__(self, config: dict[str, Any], *, asset_base_dir: Path | None = None) -> None:
        self.config = config
        self.asset_base_dir = asset_base_dir
        self.type_templates = self._load_type_templates()

    def _load_type_templates(self) -> dict[SlotContentType, list[np.ndarray]]:
        templates_cfg = self.config.get('type_templates', {})
        if not templates_cfg or self.asset_base_dir is None:
            return {}
        loaded: dict[SlotContentType, list[np.ndarray]] = {}
        for key, paths in templates_cfg.items():
            content_type = SlotContentType(key)
            loaded[content_type] = [ler_imagem(self.asset_base_dir / str(path)) for path in paths]
        return loaded

    def _classify_from_templates(self, roi: np.ndarray) -> tuple[SlotContentType, float] | None:
        if roi.size == 0:
            return None
        best_type = SlotContentType.UNKNOWN
        best_score = -1.0
        for content_type, templates in self.type_templates.items():
            for template in templates:
                if template.shape[0] > roi.shape[0] or template.shape[1] > roi.shape[1]:
                    continue
                result = cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED)
                _, score, _, _ = cv2.minMaxLoc(result)
                if score > best_score:
                    best_score = float(score)
                    best_type = content_type
        if best_score < float(self.config.get('template_confidence_threshold', 0.82)):
            return None
        return best_type, best_score

    def classify(self, frame: np.ndarray, slot: SlotPosition, content: SlotContent) -> SlotContent:
        roi = extrair_roi(frame, {'x': slot.bbox.x, 'y': slot.bbox.y, 'w': slot.bbox.w, 'h': slot.bbox.h})
        template_result = self._classify_from_templates(roi)
        if template_result is not None:
            content_type, score = template_result
            metadata = {**content.metadata, 'type_classifier_kind': DetectorKind.TEMPLATE_MATCHING.value}
            return replace(content, type=content_type, confidence=max(content.confidence, score), metadata=metadata)
        inferred_type = content.type if content.type != SlotContentType.UNKNOWN else _type_from_lane(slot.lane_hint)
        metadata = {**content.metadata, 'type_classifier_kind': DetectorKind.COORDINATE_RULES.value}
        return replace(content, type=inferred_type, metadata=metadata)


class RuleBasedContentStateClassifier:
    """Classifica disponibilidade e selecao com heuristicas visuais."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def _extract_state_roi(self, frame: np.ndarray, slot: SlotPosition) -> np.ndarray:
        roi_cfg = self.config.get('state_roi_inset', {})
        inset_x = int(roi_cfg.get('x', 0))
        inset_y = int(roi_cfg.get('y', 0))
        inset_w = int(roi_cfg.get('w', slot.bbox.w))
        inset_h = int(roi_cfg.get('h', slot.bbox.h))
        return extrair_roi(
            frame,
            {
                'x': slot.bbox.x + inset_x,
                'y': slot.bbox.y + inset_y,
                'w': inset_w,
                'h': inset_h,
            },
        )

    def classify(self, frame: np.ndarray, slot: SlotPosition, content: SlotContent) -> ContentState:
        roi = self._extract_state_roi(frame, slot)
        if roi.size == 0:
            return ContentState(availability=AvailabilityState.UNAVAILABLE, confidence=0.0)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        saturation = float(hsv[:, :, 1].mean())
        value = float(hsv[:, :, 2].mean())
        colored_ratio = float((hsv[:, :, 1] > int(self.config.get('available_color_pixel_saturation', 45))).mean())
        selected_ratio = float((hsv[:, :, 1] > int(self.config.get('selected_color_pixel_saturation', 90))).mean())

        available = (
            saturation >= float(self.config.get('available_saturation_threshold', 35))
            and value >= float(self.config.get('available_value_threshold', 35))
            and colored_ratio >= float(self.config.get('available_color_ratio_threshold', 0.20))
        )
        selected = selected_ratio >= float(self.config.get('selected_color_ratio_threshold', 0.35))
        availability = AvailabilityState.AVAILABLE if available else AvailabilityState.USED
        confidence = min(1.0, max(colored_ratio, selected_ratio))
        return ContentState(availability=availability, selected=selected, confidence=confidence)


class OcrContentQuantityClassifier:
    """Extrai quantidade de tropas/feitiços por OCR na faixa superior do slot."""

    _DIGIT_RE = re.compile(r'(\d{1,3})')
    _X_DIGIT_RE = re.compile(r'[xX]\s*(\d{1,3})')

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._tesseract_available: bool | None = None

    def _backend_order(self) -> list[str]:
        """Retorna a ordem configurada de backends OCR para quantidade."""
        _ = self.config.get('preferred_backends', ['pytesseract'])
        return ['pytesseract']

    def classify(self, frame: np.ndarray, slot: SlotPosition, content: SlotContent) -> SlotContent:
        metadata = dict(content.metadata)
        badge_value, badge_confidence = self._read_badge_value(frame, slot)
        if badge_value is not None:
            metadata.update(
                {
                    'badge_value': badge_value,
                    'badge_confidence': max(0.0, badge_confidence),
                }
            )
        if content.type not in {SlotContentType.TROOP, SlotContentType.SPELL}:
            return replace(content, metadata=metadata)
        quantity_rois = self._extract_quantity_rois(frame, slot)
        if not quantity_rois:
            return replace(content, metadata=metadata)

        candidates: list[tuple[str, str, float]] = []
        for quantity_roi, roi_bonus in quantity_rois:
            for backend_name, text, confidence in self._run_ocr_candidates(quantity_roi):
                candidates.append((backend_name, text, confidence + roi_bonus))

        votes: dict[int, dict[str, Any]] = {}
        for backend_name, text, confidence in candidates:
            parsed = self._parse_quantity_with_context(text)
            if parsed is None:
                continue
            quantity, has_x_prefix = parsed
            entry = votes.setdefault(
                quantity,
                {'score': 0.0, 'max_confidence': 0.0, 'backend': backend_name, 'hits': 0, 'has_x_prefix': False},
            )
            bonus = 0.18 if has_x_prefix else 0.0
            entry['score'] += float(confidence) + bonus
            entry['max_confidence'] = max(float(entry['max_confidence']), float(confidence))
            entry['backend'] = backend_name
            entry['hits'] += 1
            entry['has_x_prefix'] = bool(entry['has_x_prefix'] or has_x_prefix)

        best_value: int | None = None
        best_backend = DetectorKind.OCR.value
        best_confidence = 0.0
        best_rank: tuple[float, float, int, int] | None = None
        for quantity, entry in votes.items():
            if not entry['has_x_prefix']:
                if int(entry['hits']) < 3:
                    continue
                average_score = float(entry['score']) / max(1, int(entry['hits']))
                if average_score < 0.38:
                    continue
            rank = (
                float(entry['score']),
                float(entry['max_confidence']),
                int(entry['hits']),
                len(str(quantity)),
            )
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_value = quantity
                best_backend = str(entry['backend'])
                best_confidence = float(entry['max_confidence'])

        if best_value is None:
            return replace(
                content,
                metadata={
                    **metadata,
                    'quantity_classifier_kind': DetectorKind.OCR.value,
                    'quantity_text': None,
                    'quantity_confidence': 0.0,
                },
            )

        return replace(
            content,
            quantity_hint=best_value,
            metadata={
                **metadata,
                'quantity_classifier_kind': best_backend,
                'quantity_confidence': max(0.0, best_confidence),
            },
        )

    def _extract_quantity_rois(self, frame: np.ndarray, slot: SlotPosition) -> list[tuple[np.ndarray, float]]:
        roi_cfg = self.config.get('quantity_roi', {})
        roi_specs = roi_cfg.get(
            'roi_specs',
            [
                {'x_ratio': 0.00, 'y_ratio': 0.03, 'w_ratio': 0.92, 'h_ratio': 0.24},
                {'x_ratio': 0.10, 'y_ratio': 0.03, 'w_ratio': 0.80, 'h_ratio': 0.24},
                {'x_ratio': 0.18, 'y_ratio': 0.03, 'w_ratio': 0.72, 'h_ratio': 0.24},
                {'x_ratio': 0.25, 'y_ratio': 0.03, 'w_ratio': 0.70, 'h_ratio': 0.24},
                {'x_ratio': 0.00, 'y_ratio': 0.00, 'w_ratio': 0.92, 'h_ratio': 0.24},
                {'x_ratio': 0.00, 'y_ratio': 0.00, 'w_ratio': 0.92, 'h_ratio': 0.30},
                {'x_ratio': 0.10, 'y_ratio': 0.00, 'w_ratio': 0.80, 'h_ratio': 0.30},
                {'x_ratio': 0.30, 'y_ratio': 0.00, 'w_ratio': 0.62, 'h_ratio': 0.34},
            ],
        )
        rois: list[tuple[np.ndarray, float]] = []
        seen_shapes: set[tuple[int, int, int, int]] = set()
        for roi_spec in roi_specs:
            x_ratio = float(roi_spec.get('x_ratio', 0.0))
            y_ratio = float(roi_spec.get('y_ratio', 0.0))
            w_ratio = float(roi_spec.get('w_ratio', 1.0))
            h_ratio = float(roi_spec.get('h_ratio', 0.3))
            x = slot.bbox.x + int(slot.bbox.w * x_ratio)
            y = slot.bbox.y + int(slot.bbox.h * y_ratio)
            w = max(1, int(slot.bbox.w * w_ratio))
            h = max(1, int(slot.bbox.h * h_ratio))
            key = (x, y, w, h)
            if key in seen_shapes:
                continue
            seen_shapes.add(key)
            roi = extrair_roi(frame, {'x': x, 'y': y, 'w': w, 'h': h})
            if roi.size != 0:
                roi_bonus = (x_ratio * 0.35) + ((1.0 - w_ratio) * 0.25)
                rois.append((roi, roi_bonus))
        return rois

    def _extract_badge_rois(self, frame: np.ndarray, slot: SlotPosition) -> list[np.ndarray]:
        roi_specs = self.config.get(
            'badge_roi_specs',
            [
                {'x_ratio': 0.00, 'y_ratio': 0.68, 'w_ratio': 0.42, 'h_ratio': 0.30},
                {'x_ratio': 0.00, 'y_ratio': 0.72, 'w_ratio': 0.46, 'h_ratio': 0.28},
                {'x_ratio': 0.04, 'y_ratio': 0.70, 'w_ratio': 0.40, 'h_ratio': 0.26},
            ],
        )
        rois: list[np.ndarray] = []
        seen_shapes: set[tuple[int, int, int, int]] = set()
        for roi_spec in roi_specs:
            x = slot.bbox.x + int(slot.bbox.w * float(roi_spec.get('x_ratio', 0.0)))
            y = slot.bbox.y + int(slot.bbox.h * float(roi_spec.get('y_ratio', 0.68)))
            w = max(1, int(slot.bbox.w * float(roi_spec.get('w_ratio', 0.42))))
            h = max(1, int(slot.bbox.h * float(roi_spec.get('h_ratio', 0.30))))
            key = (x, y, w, h)
            if key in seen_shapes:
                continue
            seen_shapes.add(key)
            roi = extrair_roi(frame, {'x': x, 'y': y, 'w': w, 'h': h})
            if roi.size != 0:
                rois.append(roi)
        return rois

    def _read_badge_value(self, frame: np.ndarray, slot: SlotPosition) -> tuple[int | None, float]:
        best_value: int | None = None
        best_confidence = 0.0
        for badge_roi in self._extract_badge_rois(frame, slot):
            for backend_name, text, confidence in self._run_digit_ocr_candidates(badge_roi):
                parsed = self._parse_digit_value(text)
                if parsed is None:
                    continue
                if confidence > best_confidence:
                    best_value = parsed
                    best_confidence = float(confidence)
        return best_value, best_confidence

    def _run_digit_ocr_candidates(self, roi: np.ndarray) -> list[tuple[str, str, float]]:
        processed_variants = self._build_badge_ocr_variants(roi)
        results: list[tuple[str, str, float]] = []
        for variant in processed_variants:
            for backend in self._backend_order():
                if backend == 'pytesseract':
                    results.extend(self._run_tesseract(variant, allowlist='0123456789'))
        return results

    def _run_ocr_candidates(self, roi: np.ndarray) -> list[tuple[str, str, float]]:
        processed_variants = self._build_ocr_variants(roi)
        results: list[tuple[str, str, float]] = []
        for variant in processed_variants:
            for backend in self._backend_order():
                if backend == 'pytesseract':
                    results.extend(self._run_tesseract(variant))
        return results

    def _build_ocr_variants(self, roi: np.ndarray) -> list[np.ndarray]:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        scale = int(self.config.get('upscale_factor', 4))
        resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        blurred = cv2.GaussianBlur(resized, (3, 3), 0)
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, binary_inv = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return [binary, binary_inv]

    def _build_badge_ocr_variants(self, roi: np.ndarray) -> list[np.ndarray]:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        scale = int(max(4, self.config.get('badge_upscale_factor', self.config.get('upscale_factor', 4))))
        resized = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        blurred = cv2.GaussianBlur(resized, (3, 3), 0)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(blurred)
        _, binary = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, binary_inv = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return [binary, binary_inv]

    def _run_tesseract(self, image: np.ndarray, *, allowlist: str = 'xX0123456789') -> list[tuple[str, str, float]]:
        if self._tesseract_available is False:
            return []
        psm_modes = self.config.get('tesseract_psm_modes', [7, 13, 6])
        if not isinstance(psm_modes, list) or not psm_modes:
            psm_modes = [7, 13, 6]
        outputs: list[tuple[str, str, float]] = []
        succeeded = False
        for psm in psm_modes:
            try:
                data = pytesseract.image_to_data(
                    image,
                    config=f'--psm {int(psm)} -c tessedit_char_whitelist={allowlist}',
                    output_type=pytesseract.Output.DICT,
                )
            except Exception:
                continue
            succeeded = True

            texts: list[str] = []
            confidences: list[float] = []
            for text, confidence in zip(data.get('text', []), data.get('conf', [])):
                normalized = str(text).strip()
                if not normalized:
                    continue
                texts.append(normalized)
                try:
                    confidences.append(float(confidence))
                except (TypeError, ValueError):
                    continue
            if not texts:
                continue
            confidence_score = max(0.0, (sum(confidences) / max(1, len(confidences))) / 100.0) if confidences else 0.0
            outputs.append((f'{DetectorKind.OCR.value}_psm{int(psm)}', ''.join(texts), confidence_score))
        self._tesseract_available = succeeded
        return outputs

    @classmethod
    def _parse_quantity(cls, text: str | None) -> int | None:
        parsed = cls._parse_quantity_with_context(text)
        return None if parsed is None else parsed[0]

    @classmethod
    def _parse_quantity_with_context(cls, text: str | None) -> tuple[int, bool] | None:
        if not text:
            return None
        normalized = ''.join(ch for ch in str(text) if ch.isalnum())
        x_match = cls._X_DIGIT_RE.search(normalized)
        if x_match:
            return int(x_match.group(1)), True
        if normalized.isdigit():
            return int(normalized), False
        return None

    @classmethod
    def _parse_digit_value(cls, text: str | None) -> int | None:
        if not text:
            return None
        match = cls._DIGIT_RE.search(str(text))
        if match is None:
            return None
        return int(match.group(1))
