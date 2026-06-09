"""Detectores de posicao e presenca para a barra de batalha."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from battle_bar.domain import (
    AvailabilityState,
    BoundingBox,
    ContentState,
    DetectorKind,
    SlotContent,
    SlotContentType,
    SlotLaneHint,
    SlotPosition,
)
from services.bot_shared import ErroBot
from utils.geometry_utils import extrair_roi, resolver_roi
from utils.template_matching import encontrar_template, ler_imagem


def _lane_from_name(name: str) -> SlotLaneHint:
    normalized = str(name).strip().lower()
    mapping = {
        'troops': SlotLaneHint.TROOP_SECTION,
        'troop': SlotLaneHint.TROOP_SECTION,
        'heroes': SlotLaneHint.HERO_SECTION,
        'hero': SlotLaneHint.HERO_SECTION,
        'spells': SlotLaneHint.SPELL_SECTION,
        'spell': SlotLaneHint.SPELL_SECTION,
        'siege': SlotLaneHint.SIEGE_SECTION,
        'siege_machine': SlotLaneHint.SIEGE_SECTION,
        'siege_machines': SlotLaneHint.SIEGE_SECTION,
        'machine': SlotLaneHint.SIEGE_SECTION,
    }
    return mapping.get(normalized, SlotLaneHint.UNKNOWN)


def _content_type_from_lane(lane: SlotLaneHint) -> SlotContentType:
    mapping = {
        SlotLaneHint.TROOP_SECTION: SlotContentType.TROOP,
        SlotLaneHint.HERO_SECTION: SlotContentType.HERO,
        SlotLaneHint.SPELL_SECTION: SlotContentType.SPELL,
        SlotLaneHint.SIEGE_SECTION: SlotContentType.SIEGE_MACHINE,
    }
    return mapping.get(lane, SlotContentType.UNKNOWN)


def _build_lane_by_index(sections: list[dict[str, Any]], total_slots: int) -> dict[int, SlotLaneHint]:
    lane_by_index: dict[int, SlotLaneHint] = {}
    cursor = 0
    for section in sections:
        count = int(section['count'])
        lane = _lane_from_name(section['lane'])
        for _ in range(max(0, count)):
            if cursor >= total_slots:
                break
            lane_by_index[cursor] = lane
            cursor += 1
    return lane_by_index


class FixedGridSlotPositionDetector:
    """Gera slots a partir de uma grade configurada e de secoes estruturais."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.last_bar_bbox: BoundingBox | None = None
        self.last_confidence: float = 0.0
        self.last_strategy: str = DetectorKind.COORDINATE_RULES.value

    def detect(self, frame: np.ndarray) -> list[SlotPosition]:
        frame_h, frame_w = frame.shape[:2]
        bar_roi = self.config.get('bar_roi')
        if not isinstance(bar_roi, dict):
            raise ErroBot('battle_bar.position_detector.bar_roi deve ser um mapa de ROI.')
        bar_x, bar_y, bar_w, bar_h = resolver_roi((frame_w, frame_h), bar_roi)
        slot_w = int(self.config['slot_width'])
        slot_h = int(self.config.get('slot_height', bar_h))
        spacing = int(self.config.get('slot_spacing', 0))
        total_slots = int(self.config['slot_count'])
        if total_slots <= 0:
            raise ErroBot('battle_bar.position_detector.slot_count deve ser maior que zero.')

        sections = self.config.get('sections', [])
        lane_by_index = _build_lane_by_index(sections, total_slots)
        slots: list[SlotPosition] = []
        for index in range(total_slots):
            x = bar_x + index * (slot_w + spacing)
            bbox = BoundingBox(x=x, y=bar_y, w=slot_w, h=slot_h)
            relative_x = (x - bar_x) / max(1, bar_w)
            slots.append(
                SlotPosition(
                    index=index,
                    bbox=bbox,
                    lane_hint=lane_by_index.get(index, SlotLaneHint.UNKNOWN),
                    relative_x=relative_x,
                    metadata={'detector_kind': DetectorKind.COORDINATE_RULES.value, 'position_confidence': 0.55},
                )
            )
        self.last_bar_bbox = BoundingBox(x=bar_x, y=bar_y, w=bar_w, h=bar_h)
        self.last_confidence = 0.55
        self.last_strategy = DetectorKind.COORDINATE_RULES.value
        return slots


class TemplateAnchoredSlotPositionDetector:
    """Localiza um anchor visual e deriva a grade de slots a partir dele."""

    def __init__(self, config: dict[str, Any], *, asset_base_dir: Path, confidence: float) -> None:
        self.config = config
        self.asset_base_dir = asset_base_dir
        self.confidence = confidence
        self.grid_detector = FixedGridSlotPositionDetector(config)
        self.last_bar_bbox: BoundingBox | None = None
        self.last_confidence: float = 0.0
        self.last_strategy: str = DetectorKind.TEMPLATE_MATCHING.value

    def detect(self, frame: np.ndarray) -> list[SlotPosition]:
        anchor_asset = self.asset_base_dir / str(self.config['anchor_asset'])
        match = encontrar_template(frame, anchor_asset, self.confidence)
        if not match:
            raise ErroBot(f'Nao foi possivel localizar o anchor da battle_bar: {anchor_asset}')

        frame_h, frame_w = frame.shape[:2]
        anchor_offset = self.config.get('anchor_offset', {})
        bar_w = int(self.config['bar_roi']['w'])
        bar_h = int(self.config['bar_roi']['h'])
        bar_x = int(match.x + int(anchor_offset.get('x', 0)))
        bar_y = int(match.y + int(anchor_offset.get('y', 0)))
        synthetic_config = dict(self.config)
        synthetic_config['bar_roi'] = {
            'x': max(0, min(frame_w - 1, bar_x)),
            'y': max(0, min(frame_h - 1, bar_y)),
            'w': bar_w,
            'h': bar_h,
        }
        slots = FixedGridSlotPositionDetector(synthetic_config).detect(frame)
        detected = [
            replace(slot, metadata={**slot.metadata, 'detector_kind': DetectorKind.TEMPLATE_MATCHING.value})
            for slot in slots
        ]
        self.last_bar_bbox = self.grid_detector.last_bar_bbox
        self.last_confidence = float(match.confidence)
        self.last_strategy = DetectorKind.TEMPLATE_MATCHING.value
        return detected


class DarkBandSlotPositionDetector:
    """Localiza a barra pela banda escura inferior e segmenta slots por transicoes internas."""

    def __init__(self, config: dict[str, Any], *, fallback_detector: FixedGridSlotPositionDetector | None = None) -> None:
        self.config = config
        self.fallback_detector = fallback_detector or FixedGridSlotPositionDetector(config)
        self.last_bar_bbox: BoundingBox | None = None
        self.last_confidence: float = 0.0
        self.last_strategy: str = DetectorKind.OPENCV_RULES.value
        self.last_used_fallback: bool = False

    def detect(self, frame: np.ndarray) -> list[SlotPosition]:
        self.last_bar_bbox = None
        self.last_confidence = 0.0
        self.last_strategy = DetectorKind.OPENCV_RULES.value
        self.last_used_fallback = False

        bar_bbox, confidence, features = self._detect_bar_bbox(frame)
        min_confidence = float(self.config.get('min_bar_confidence', 0.40))
        if bar_bbox is None or confidence < min_confidence:
            if bool(self.config.get('allow_fixed_grid_fallback', True)):
                slots = self.fallback_detector.detect(frame)
                self.last_bar_bbox = self.fallback_detector.last_bar_bbox
                self.last_confidence = min(0.39, self.fallback_detector.last_confidence)
                self.last_strategy = f'{DetectorKind.OPENCV_RULES.value}_fallback'
                self.last_used_fallback = True
                return [
                    replace(
                        slot,
                        metadata={
                            **slot.metadata,
                            'position_confidence': self.last_confidence,
                            'bar_detection_features': features,
                            'used_fallback': True,
                        },
                    )
                    for slot in slots
                ]
            raise ErroBot('Nao foi possivel localizar uma battle bar confiavel na faixa inferior da janela.')

        slots = self._segment_slots(frame, bar_bbox, confidence, features)
        self.last_bar_bbox = bar_bbox
        self.last_confidence = confidence
        self.last_strategy = DetectorKind.OPENCV_RULES.value
        return slots

    def _detect_bar_bbox(self, frame: np.ndarray) -> tuple[BoundingBox | None, float, dict[str, float]]:
        frame_h, frame_w = frame.shape[:2]
        bar_roi_cfg = self.config.get('bar_roi')
        if not isinstance(bar_roi_cfg, dict):
            raise ErroBot('battle_bar.position_detector.bar_roi deve ser um mapa de ROI.')
        expected_x, expected_y, expected_w, expected_h = resolver_roi((frame_w, frame_h), bar_roi_cfg)
        margin_x_ratio = float(self.config.get('search_margin_x_ratio', 0.35))
        margin_y_ratio = float(self.config.get('search_margin_y_ratio', 0.80))
        search_x = max(0, expected_x - int(expected_w * margin_x_ratio))
        search_y = max(0, expected_y - int(expected_h * margin_y_ratio))
        search_w = min(frame_w - search_x, expected_w + int(expected_w * margin_x_ratio * 2))
        search_h = min(frame_h - search_y, expected_h + int(expected_h * margin_y_ratio * 2))
        roi = frame[search_y:search_y + search_h, search_x:search_x + search_w]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        row_mean = gray.mean(axis=1)
        row_std = gray.std(axis=1)
        darkness = 1.0 - (row_mean / 255.0)
        texture = np.clip(row_std / 64.0, 0.0, 1.0)
        above_mean = np.concatenate(([row_mean[0]], row_mean[:-1]))
        contrast = np.clip((above_mean - row_mean) / 255.0, 0.0, 1.0)
        row_score = (darkness * 0.55) + ((1.0 - texture) * 0.20) + (contrast * 0.25)

        window_h = int(self.config.get('expected_bar_height_px', max(20, int(search_h * 0.22))))
        window_h = max(12, min(search_h, window_h))
        best_score = -1.0
        best_y = 0
        smoothed = self._moving_average(row_score, window_h)
        for index, value in enumerate(smoothed):
            if value > best_score:
                best_score = float(value)
                best_y = index

        bar_local_y = best_y
        threshold = max(0.18, best_score * 0.82)
        top = bar_local_y
        while top > 0 and row_score[top - 1] >= threshold:
            top -= 1
        bottom = min(search_h - 1, bar_local_y + window_h - 1)
        while bottom + 1 < search_h and row_score[bottom + 1] >= threshold:
            bottom += 1
        expected_local_y = max(0, expected_y - search_y)
        if abs(top - expected_local_y) > max(4, int(expected_h * 0.25)):
            top = int(round((top * 0.35) + (expected_local_y * 0.65)))
            bottom = min(search_h - 1, max(top + 1, top + expected_h - 1))

        band = gray[top:bottom + 1, :]
        if band.size == 0:
            return None, 0.0, {'row_score': 0.0}
        col_mean = band.mean(axis=0)
        col_darkness = 1.0 - (col_mean / 255.0)
        grad_x = cv2.Sobel(band, cv2.CV_32F, 1, 0, ksize=3)
        edge_projection = np.mean(np.abs(grad_x), axis=0)
        edge_norm = edge_projection / max(1e-6, float(edge_projection.max()))
        col_score = (col_darkness * 0.65) + (edge_norm * 0.35)
        col_score_smooth = self._moving_average(col_score, max(5, int(expected_w / 18)))
        active_threshold = max(0.16, float(np.percentile(col_score_smooth, 45)))
        active = col_score_smooth >= active_threshold
        close_kernel = np.ones(max(3, int(expected_w / 25)), dtype=np.uint8)
        active_closed = np.convolve(active.astype(np.uint8), close_kernel, mode='same') > 0
        active_indices = np.flatnonzero(active_closed)
        min_width_ratio = float(self.config.get('min_bar_width_ratio', 0.55))
        min_width = int(expected_w * min_width_ratio)
        if active_indices.size == 0:
            return None, 0.0, {'row_score': best_score}
        x0 = int(active_indices[0])
        x1 = int(active_indices[-1])
        if (x1 - x0 + 1) < min_width:
            return None, 0.0, {'row_score': best_score}
        center = (x0 + x1) / 2.0
        expected_center = (expected_x - search_x) + (expected_w / 2.0)
        center_distance = abs(center - expected_center) / max(expected_w, 1)
        center_score = max(0.0, 1.0 - center_distance)
        best_segment_score = (float(col_score_smooth[x0:x1 + 1].mean()) * 0.7) + (((x1 - x0 + 1) / max(expected_w, 1)) * 0.2) + (center_score * 0.1)
        bar_bbox = BoundingBox(x=int(search_x + x0), y=int(search_y + top), w=int(x1 - x0 + 1), h=int(bottom - top + 1))
        width_score = min(1.0, bar_bbox.w / max(min_width, 1))
        height_score = min(1.0, 1.0 - (abs(bar_bbox.h - expected_h) / max(expected_h, 1)))
        y_score = min(1.0, 1.0 - (abs(bar_bbox.y - expected_y) / max(expected_h * 2, 1)))
        confidence = min(1.0, (best_score * 0.35) + (best_segment_score * 0.30) + (width_score * 0.15) + (height_score * 0.10) + (y_score * 0.10))
        features = {
            'row_score': float(best_score),
            'segment_score': float(best_segment_score),
            'width_score': float(width_score),
            'height_score': float(height_score),
            'y_score': float(y_score),
        }
        return bar_bbox, confidence, features

    def _segment_slots(
        self,
        frame: np.ndarray,
        bar_bbox: BoundingBox,
        confidence: float,
        features: dict[str, float],
    ) -> list[SlotPosition]:
        total_slots = int(self.config['slot_count'])
        sections = self.config.get('sections', [])
        lane_by_index = _build_lane_by_index(sections, total_slots)
        band = extrair_roi(frame, {'x': bar_bbox.x, 'y': bar_bbox.y, 'w': bar_bbox.w, 'h': bar_bbox.h})
        gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        projection = np.mean(np.abs(grad_x), axis=0)
        smoothed = self._moving_average(projection, max(3, int(bar_bbox.w / 80)))
        if smoothed.size == 0:
            return self._fallback_with_metadata(frame, confidence, features)

        candidate_indices = np.argsort(smoothed)[::-1]
        min_distance = max(8, int(bar_bbox.w / max(total_slots * 2, 1)))
        separators: list[int] = []
        for idx in candidate_indices:
            if len(separators) >= max(0, total_slots - 1):
                break
            index = int(idx)
            if index <= 2 or index >= bar_bbox.w - 3:
                continue
            if all(abs(index - existing) >= min_distance for existing in separators):
                separators.append(index)
        separators.sort()
        if len(separators) < max(1, total_slots - 2):
            return self._fallback_with_metadata(frame, confidence, features)

        estimated_slot_w = float(bar_bbox.w) / max(total_slots, 1)
        aligned_left = max(0, min(separators[0] - estimated_slot_w, bar_bbox.w - estimated_slot_w))
        aligned_left = int(round(aligned_left))
        merged = []
        for index in range(total_slots):
            start = int(round(aligned_left + (index * estimated_slot_w)))
            end = int(round(aligned_left + ((index + 1) * estimated_slot_w)))
            start = max(0, min(bar_bbox.w - 2, start))
            end = max(start + 1, min(bar_bbox.w - 1, end))
            merged.append((start, end))

        slots: list[SlotPosition] = []
        for index, (start, end) in enumerate(merged):
            segment_w = max(1, end - start)
            slot_bbox = BoundingBox(
                x=bar_bbox.x + int(start),
                y=bar_bbox.y,
                w=int(segment_w),
                h=bar_bbox.h,
            )
            slots.append(
                SlotPosition(
                    index=index,
                    bbox=slot_bbox,
                    lane_hint=lane_by_index.get(index, SlotLaneHint.UNKNOWN),
                    relative_x=(slot_bbox.x - bar_bbox.x) / max(1, bar_bbox.w),
                    metadata={
                        'detector_kind': DetectorKind.OPENCV_RULES.value,
                        'position_confidence': confidence,
                        'bar_detection_features': {**features, 'separator_count': float(len(separators))},
                        'used_fallback': False,
                    },
                )
            )
        return slots

    def _fallback_with_metadata(self, frame: np.ndarray, confidence: float, features: dict[str, float]) -> list[SlotPosition]:
        slots = self.fallback_detector.detect(frame)
        self.last_bar_bbox = self.fallback_detector.last_bar_bbox
        self.last_confidence = min(confidence, 0.39)
        self.last_strategy = f'{DetectorKind.OPENCV_RULES.value}_fallback'
        self.last_used_fallback = True
        return [
            replace(
                slot,
                metadata={
                    **slot.metadata,
                    'position_confidence': self.last_confidence,
                    'bar_detection_features': features,
                    'used_fallback': True,
                },
            )
            for slot in slots
        ]

    @staticmethod
    def _moving_average(values: np.ndarray, window: int) -> np.ndarray:
        if values.size == 0:
            return values
        window = max(1, min(len(values), int(window)))
        kernel = np.ones(window, dtype=np.float32) / float(window)
        return np.convolve(values.astype(np.float32), kernel, mode='same')

    @staticmethod
    def _find_segments(mask: np.ndarray) -> list[tuple[int, int]]:
        segments: list[tuple[int, int]] = []
        start: int | None = None
        for index, value in enumerate(mask.tolist()):
            if value and start is None:
                start = index
                continue
            if not value and start is not None:
                segments.append((start, index - 1))
                start = None
        if start is not None:
            segments.append((start, len(mask) - 1))
        return segments


class RuleBasedSlotContentDetector:
    """Detecta presenca de conteudo por heuristicas visuais simples."""

    def __init__(self, config: dict[str, Any], *, asset_base_dir: Path | None = None, confidence: float = 0.82) -> None:
        self.config = config
        self.asset_base_dir = asset_base_dir
        self.confidence = confidence
        self.empty_template = self._load_empty_template()

    def _load_empty_template(self) -> np.ndarray | None:
        empty_asset = self.config.get('empty_slot_asset')
        if not empty_asset or self.asset_base_dir is None:
            return None
        return ler_imagem(self.asset_base_dir / str(empty_asset))

    def _has_content(self, frame: np.ndarray, slot: SlotPosition) -> tuple[bool, dict[str, float]]:
        inset_ratio = float(self.config.get('content_roi_inset_ratio', 0.14))
        inset_x = int(slot.bbox.w * inset_ratio)
        inset_y = int(slot.bbox.h * inset_ratio)
        roi = extrair_roi(
            frame,
            {
                'x': slot.bbox.x + inset_x,
                'y': slot.bbox.y + inset_y,
                'w': max(1, slot.bbox.w - (inset_x * 2)),
                'h': max(1, slot.bbox.h - (inset_y * 2)),
            },
        )
        if roi.size == 0:
            return False, {'variance': 0.0, 'empty_match': 1.0}
        variance = float(np.var(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)))
        variance_threshold = float(self.config.get('variance_threshold', 120.0))
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mean_saturation = float(hsv[:, :, 1].mean())
        mean_value = float(hsv[:, :, 2].mean())
        empty_saturation_threshold = float(self.config.get('empty_content_saturation_threshold', 18.0))
        empty_value_threshold = float(self.config.get('empty_content_value_threshold', 70.0))
        if mean_saturation <= empty_saturation_threshold and mean_value <= empty_value_threshold:
            return False, {
                'variance': variance,
                'mean_saturation': mean_saturation,
                'mean_value': mean_value,
            }
        if self.empty_template is not None and self.empty_template.shape[:2] == roi.shape[:2]:
            result = cv2.matchTemplate(roi, self.empty_template, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(result)
            empty_confidence = float(score)
            empty_threshold = float(self.config.get('empty_template_confidence', self.confidence))
            if empty_confidence >= empty_threshold:
                return False, {'variance': variance, 'empty_match': empty_confidence}
            return True, {'variance': variance, 'empty_match': empty_confidence}
        return variance >= variance_threshold, {'variance': variance}

    def detect(self, frame: np.ndarray, slots: list[SlotPosition]) -> list[SlotPosition]:
        detected: list[SlotPosition] = []
        for slot in slots:
            has_content, features = self._has_content(frame, slot)
            if not has_content:
                detected.append(slot.with_content(None))
                continue
            lane_type = _content_type_from_lane(slot.lane_hint)
            content = SlotContent(
                content_id=f'slot-{slot.index}',
                type=lane_type,
                name=None,
                state=ContentState(availability=AvailabilityState.UNAVAILABLE, confidence=0.0),
                confidence=float(features.get('variance', 0.0)),
                metadata={'features': features, 'detector_kind': DetectorKind.OPENCV_RULES.value},
            )
            detected.append(slot.with_content(content))
        return detected
