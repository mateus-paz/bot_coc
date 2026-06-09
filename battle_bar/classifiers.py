"""Classificadores de tipo e estado para conteudos da barra."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np

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
