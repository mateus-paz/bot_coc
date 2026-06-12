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


def _build_lane_by_detected_sequence(total_slots: int) -> dict[int, SlotLaneHint]:
    lane_by_index: dict[int, SlotLaneHint] = {}
    if total_slots < 9:
        return lane_by_index
    cursor = 0
    for _ in range(min(4, total_slots - cursor)):
        lane_by_index[cursor] = SlotLaneHint.TROOP_SECTION
        cursor += 1
    if cursor < total_slots:
        lane_by_index[cursor] = SlotLaneHint.SIEGE_SECTION
        cursor += 1
    hero_count = 4 if total_slots >= 13 else min(4, total_slots - cursor)
    for _ in range(min(hero_count, total_slots - cursor)):
        lane_by_index[cursor] = SlotLaneHint.HERO_SECTION
        cursor += 1
    while cursor < total_slots:
        lane_by_index[cursor] = SlotLaneHint.SPELL_SECTION
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
        if self.last_bar_bbox is None:
            self.last_bar_bbox = bar_bbox
        self.last_confidence = confidence
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
        remaining_gap_to_frame_bottom = frame_h - (search_y + bottom + 1)
        anchor_bottom_gap_px_max = int(self.config.get('anchor_bottom_gap_px_max', max(24, expected_h * 2)))
        if remaining_gap_to_frame_bottom <= anchor_bottom_gap_px_max:
            bottom = search_h - 1

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
        structural_slots = self._detect_structural_grid_slots(frame, bar_bbox, confidence, features)
        if structural_slots:
            return structural_slots
        band = extrair_roi(frame, {'x': bar_bbox.x, 'y': bar_bbox.y, 'w': bar_bbox.w, 'h': bar_bbox.h})
        filled_slots = self._detect_filled_slots(frame, band, bar_bbox, confidence, features)
        if filled_slots:
            return filled_slots
        return self._fallback_with_metadata(frame, confidence, {**features, 'filled_slot_mode_failed': 1.0})

    def _detect_structural_grid_slots(
        self,
        frame: np.ndarray,
        bar_bbox: BoundingBox,
        confidence: float,
        features: dict[str, float],
    ) -> list[SlotPosition]:
        frame_h, frame_w = frame.shape[:2]
        anchor_y = self._detect_bar_anchor_y(frame)
        slot_top = anchor_y + max(8, int(round(bar_bbox.h * 0.11)))
        slot_bottom = min(frame_h, bar_bbox.y + bar_bbox.h)
        if slot_bottom - slot_top < max(48, int(bar_bbox.h * 0.55)):
            return []

        search_left = max(0, bar_bbox.x - int(max(60, bar_bbox.h * 1.20)))
        search_right = min(frame_w, bar_bbox.x + bar_bbox.w)
        roi = frame[slot_top:slot_bottom, search_left:search_right]
        if roi.size == 0 or roi.shape[0] < 48 or roi.shape[1] < 120:
            return []

        pair_score, pair_width, expected_width = self._compute_structural_pair_score(roi)
        candidate_lefts = self._select_structural_slot_candidates(pair_score, pair_width, expected_width)
        min_slots = int(self.config.get('structural_min_slot_count', 3))
        if len(candidate_lefts) < min_slots:
            return []

        absolute_lefts = [search_left + left for left in candidate_lefts]
        steps = [
            absolute_lefts[index + 1] - absolute_lefts[index]
            for index in range(len(absolute_lefts) - 1)
        ]
        plausible_steps = [
            step
            for step in steps
            if expected_width * 0.72 <= step <= expected_width * 1.65
        ]
        typical_step = int(round(float(np.median(plausible_steps or [expected_width]))))
        median_score = float(np.median([pair_score[left] for left in candidate_lefts]))
        sections = self.config.get('sections', [])
        sequence_lanes = _build_lane_by_detected_sequence(len(candidate_lefts))
        lane_by_index = sequence_lanes or _build_lane_by_index(sections, len(candidate_lefts))

        slots: list[SlotPosition] = []
        for index, local_left in enumerate(candidate_lefts):
            slot_width = int(pair_width[local_left])
            bbox = BoundingBox(
                x=search_left + local_left,
                y=slot_top,
                w=slot_width,
                h=slot_bottom - slot_top,
            )
            slots.append(
                SlotPosition(
                    index=index,
                    bbox=bbox,
                    lane_hint=lane_by_index.get(index, SlotLaneHint.UNKNOWN),
                    relative_x=(bbox.x - absolute_lefts[0])
                    / max(1, (absolute_lefts[-1] + int(pair_width[candidate_lefts[-1]])) - absolute_lefts[0]),
                    metadata={
                        'detector_kind': DetectorKind.OPENCV_RULES.value,
                        'position_confidence': confidence,
                        'bar_detection_features': {
                            **features,
                            'structural_grid': 1.0,
                            'structural_anchor_y': float(anchor_y),
                            'structural_candidate_count': float(len(candidate_lefts)),
                            'structural_expected_width': float(expected_width),
                            'structural_typical_step': float(typical_step),
                            'structural_median_score': median_score,
                        },
                        'structural_score': float(pair_score[local_left]),
                        'used_fallback': False,
                    },
                )
            )

        min_x = slots[0].bbox.x
        max_x = slots[-1].bbox.x + slots[-1].bbox.w
        self.last_bar_bbox = BoundingBox(
            x=min_x,
            y=slot_top,
            w=max_x - min_x,
            h=slot_bottom - slot_top,
        )
        self.last_strategy = f'{DetectorKind.OPENCV_RULES.value}_structural_grid'
        return slots

    def _detect_bar_anchor_y(self, frame: np.ndarray) -> int:
        frame_h, frame_w = frame.shape[:2]
        bar_roi_cfg = self.config.get('bar_roi')
        if not isinstance(bar_roi_cfg, dict):
            return max(0, int(frame_h * 0.80))
        _, expected_y, _, _ = resolver_roi((frame_w, frame_h), bar_roi_cfg)
        search_top = max(0, expected_y - int(frame_h * 0.08))
        search_bottom = min(frame_h, expected_y + int(frame_h * 0.03))
        search_left = int(frame_w * 0.05)
        search_right = max(search_left + 1, int(frame_w * 0.98))
        gray = cv2.cvtColor(frame[search_top:search_bottom, search_left:search_right], cv2.COLOR_BGR2GRAY)
        if gray.size == 0:
            return expected_y
        grad_y = np.abs(cv2.Scharr(gray, cv2.CV_32F, 0, 1))
        row_score = np.mean(np.clip(grad_y, 0, 255), axis=1)
        return search_top + int(np.argmax(row_score))

    def _compute_structural_pair_score(self, roi: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        grad_x = np.abs(cv2.Scharr(blurred, cv2.CV_32F, 1, 0))
        edge_threshold = max(45.0, float(np.percentile(grad_x, 78)))
        edge_mask = (grad_x >= edge_threshold).astype(np.uint8) * 255
        close_height = max(5, int(roi.shape[0] * 0.08))
        open_height = max(11, int(roi.shape[0] * 0.16))
        vertical = cv2.morphologyEx(
            edge_mask,
            cv2.MORPH_CLOSE,
            np.ones((close_height, 1), dtype=np.uint8),
        )
        vertical = cv2.morphologyEx(
            vertical,
            cv2.MORPH_OPEN,
            np.ones((open_height, 1), dtype=np.uint8),
        )
        persistence = vertical.mean(axis=0) / 255.0
        raw_vertical = np.mean(np.clip(grad_x, 0, 255), axis=0) / 255.0
        top_height = max(12, int(roi.shape[0] * 0.22))
        top_vertical = np.mean(np.clip(grad_x[:top_height], 0, 255), axis=0) / 255.0
        boundary_signal = (
            self._normalize_signal(persistence) * 0.50
            + self._normalize_signal(raw_vertical) * 0.20
            + self._normalize_signal(top_vertical) * 0.30
        )
        boundary_signal = self._moving_average(boundary_signal, 3)

        grad_y = np.abs(cv2.Scharr(blurred, cv2.CV_32F, 0, 1))
        border_height = max(6, int(roi.shape[0] * 0.10))
        top_border = self._normalize_signal(np.max(np.clip(grad_y[:border_height], 0, 255), axis=0))
        bottom_border = self._normalize_signal(np.max(np.clip(grad_y[-border_height:], 0, 255), axis=0))

        expected_width = max(28, int(round(roi.shape[0] * 0.76)))
        min_width = max(24, int(round(roi.shape[0] * 0.69)))
        max_width = max(min_width + 1, int(round(roi.shape[0] * 0.94)))
        pair_score = np.zeros(roi.shape[1], dtype=np.float32)
        pair_width = np.full(roi.shape[1], expected_width, dtype=np.int32)
        for candidate_width in range(min_width, max_width + 1):
            window = np.ones(candidate_width, dtype=np.float32) / float(candidate_width)
            top_window = np.convolve(top_border, window, mode='same')
            bottom_window = np.convolve(bottom_border, window, mode='same')
            width_prior = max(
                0.82,
                1.0 - (abs(candidate_width - expected_width) / max(1, expected_width)),
            )
            for left in range(0, roi.shape[1] - candidate_width):
                center = left + candidate_width // 2
                score = (
                    boundary_signal[left] * 0.32
                    + boundary_signal[left + candidate_width] * 0.32
                    + top_window[center] * 0.24
                    + bottom_window[center] * 0.12
                ) * width_prior
                if score > pair_score[left]:
                    pair_score[left] = score
                    pair_width[left] = candidate_width
        return self._moving_average(pair_score, 3), pair_width, expected_width

    def _select_structural_slot_candidates(
        self,
        pair_score: np.ndarray,
        pair_width: np.ndarray,
        expected_width: int,
    ) -> list[int]:
        if pair_score.size < expected_width * 2:
            return []
        local_maxima = [
            index
            for index in range(2, len(pair_score) - expected_width - 2)
            if pair_score[index] >= float(np.max(pair_score[index - 2:index + 3]))
        ]
        local_maxima.sort(key=lambda index: float(pair_score[index]), reverse=True)
        threshold = max(
            float(self.config.get('structural_min_score', 0.32)),
            float(np.percentile(pair_score, 72)),
        )
        selected: list[int] = []
        min_distance = int(expected_width * 0.72)
        for candidate in local_maxima:
            if pair_score[candidate] < threshold:
                continue
            if candidate + int(pair_width[candidate]) >= len(pair_score):
                continue
            if any(abs(candidate - existing) < min_distance for existing in selected):
                continue
            selected.append(candidate)
        selected.sort()
        return self._select_best_structural_sequence(selected, pair_score, expected_width)

    @staticmethod
    def _select_best_structural_sequence(
        candidates: list[int],
        pair_score: np.ndarray,
        expected_width: int,
    ) -> list[int]:
        if not candidates:
            return []
        max_gap = int(expected_width * 1.80)
        sequences: list[list[int]] = [[candidates[0]]]
        for candidate in candidates[1:]:
            if candidate - sequences[-1][-1] <= max_gap:
                sequences[-1].append(candidate)
            else:
                sequences.append([candidate])
        return max(
            sequences,
            key=lambda sequence: (
                len(sequence),
                float(np.mean([pair_score[index] for index in sequence])),
            ),
        )

    def _detect_filled_slots(
        self,
        frame: np.ndarray,
        band: np.ndarray,
        bar_bbox: BoundingBox,
        confidence: float,
        features: dict[str, float],
    ) -> list[SlotPosition]:
        anchors = self._detect_slot_anchor_boxes(frame, bar_bbox)
        if len(anchors) < 3:
            return []
        return self._build_slots_from_anchors(frame, bar_bbox, anchors, confidence, features)

    def _detect_slot_anchor_boxes(self, frame: np.ndarray, bar_bbox: BoundingBox) -> list[tuple[int, int, int, int]]:
        frame_h, frame_w = frame.shape[:2]
        expand_left = int(max(60, bar_bbox.h * 1.2))
        expand_top = int(max(8, bar_bbox.h * 0.10))
        search_x0 = max(0, bar_bbox.x - expand_left)
        search_y0 = max(0, bar_bbox.y - expand_top)
        search_x1 = min(frame_w, bar_bbox.x + bar_bbox.w)
        search_y1 = frame_h

        search = frame[search_y0:search_y1, search_x0:search_x1]
        gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
        content_top = int((search.shape[0]) * float(self.config.get('filled_slot_roi_top_ratio', 0.15)))
        content_top = max(0, min(search.shape[0] - 2, content_top))
        focus = gray[content_top:, :]
        blurred = cv2.GaussianBlur(focus, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_w = int(max(45, bar_bbox.h * 0.55))
        max_w = int(max(min_w + 1, bar_bbox.h * 1.25))
        min_h = int(max(60, bar_bbox.h * 0.70))
        max_h = int(max(min_h + 1, bar_bbox.h * 1.45))
        boxes: list[tuple[int, int, int, int]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            y += content_top
            if not (min_w <= w <= max_w and min_h <= h <= max_h):
                continue
            if (w * h) < (min_w * min_h * 0.65):
                continue
            boxes.append((x + search_x0, y + search_y0, w, h))

        boxes.sort(key=lambda item: item[0])
        deduped: list[tuple[int, int, int, int]] = []
        for box in boxes:
            if deduped and abs(box[0] - deduped[-1][0]) < 12:
                prev = deduped[-1]
                if (box[2] * box[3]) > (prev[2] * prev[3]):
                    deduped[-1] = box
                continue
            deduped.append(box)
        return deduped

    def _build_slots_from_anchors(
        self,
        frame: np.ndarray,
        bar_bbox: BoundingBox,
        anchors: list[tuple[int, int, int, int]],
        confidence: float,
        features: dict[str, float],
    ) -> list[SlotPosition]:
        configured_slots = int(self.config['slot_count'])
        sections = self.config.get('sections', [])
        anchor_lefts = [box[0] for box in anchors]
        anchor_widths = [box[2] for box in anchors]
        anchor_heights = [box[3] for box in anchors]
        anchor_tops = [box[1] for box in anchors]
        typical_width = int(round(float(np.median(anchor_widths))))
        typical_height = int(round(float(np.median(anchor_heights))))
        typical_top = int(round(float(np.median(anchor_tops))))

        diffs = [anchor_lefts[index + 1] - anchor_lefts[index] for index in range(len(anchor_lefts) - 1)]
        plausible_diffs = [diff for diff in diffs if typical_width * 0.75 <= diff <= typical_width * 1.45]
        typical_step = int(round(float(np.median(plausible_diffs or [typical_width + 8]))))
        frame_boxes = self._detect_slot_frame_boxes(
            frame,
            bar_bbox,
            typical_width=typical_width,
            typical_height=typical_height,
        )
        boundary_signal = self._compute_boundary_signal(frame, bar_bbox)
        candidate_boxes = self._build_candidate_boxes_from_anchors(
            anchors=anchors,
            typical_width=typical_width,
            typical_height=typical_height,
            typical_top=typical_top,
            typical_step=typical_step,
            frame_boxes=frame_boxes,
        )
        slots: list[SlotPosition] = []
        for absolute_x, absolute_y, slot_w, slot_h in candidate_boxes:
            bbox = self._refine_slot_bbox(
                bar_bbox=bar_bbox,
                raw_bbox=BoundingBox(x=absolute_x, y=absolute_y, w=slot_w, h=slot_h),
                typical_step=typical_step,
                typical_width=typical_width,
                boundary_signal=boundary_signal,
            )
            if not self._slot_has_filled_content(frame, bbox):
                continue

            slots.append(
                SlotPosition(
                    index=len(slots),
                    bbox=bbox,
                    lane_hint=SlotLaneHint.UNKNOWN,
                    relative_x=(bbox.x - anchor_lefts[0]) / max(1, (anchor_lefts[-1] + typical_width) - anchor_lefts[0]),
                    metadata={
                        'detector_kind': DetectorKind.OPENCV_RULES.value,
                        'position_confidence': confidence,
                        'bar_detection_features': {
                            **features,
                            'anchor_count': float(len(anchors)),
                            'anchor_step': float(typical_step),
                            'anchor_width': float(typical_width),
                            'anchor_height': float(typical_height),
                            'frame_box_count': float(len(frame_boxes)),
                            'used_frame_geometry': 1.0 if frame_boxes else 0.0,
                        },
                        'used_fallback': False,
                    },
                )
            )
        if slots:
            slots = self._normalize_slot_boundaries(frame, bar_bbox, slots, boundary_signal)
            slots = self._split_wide_terminal_slot(frame, slots)
            sequence_lanes = _build_lane_by_detected_sequence(len(slots))
            if sequence_lanes:
                slots = [
                    replace(slot, lane_hint=sequence_lanes.get(index, slot.lane_hint))
                    for index, slot in enumerate(slots)
                ]
            else:
                lane_by_index = _build_lane_by_index(sections, max(configured_slots, len(slots)))
                slots = [
                    replace(slot, lane_hint=lane_by_index.get(index, slot.lane_hint))
                    for index, slot in enumerate(slots)
                ]
            min_x = min(slot.bbox.x for slot in slots)
            max_x = max(slot.bbox.x + slot.bbox.w for slot in slots)
            min_y = min(slot.bbox.y for slot in slots)
            max_y = max(slot.bbox.y + slot.bbox.h for slot in slots)
            self.last_bar_bbox = BoundingBox(x=min_x, y=min_y, w=max_x - min_x, h=max_y - min_y)
        return slots

    def _build_candidate_boxes_from_anchors(
        self,
        *,
        anchors: list[tuple[int, int, int, int]],
        typical_width: int,
        typical_height: int,
        typical_top: int,
        typical_step: int,
        frame_boxes: list[tuple[int, int, int, int]] | None = None,
    ) -> list[tuple[int, int, int, int]]:
        clustered_anchors = self._cluster_anchor_boxes(anchors, typical_width=typical_width)
        candidates: list[tuple[int, int, int, int]] = list(clustered_anchors)
        if frame_boxes:
            candidates.extend(frame_boxes)

        gap_expand_ratio = float(self.config.get('gap_expand_ratio', 1.55))
        max_fill_per_gap = int(self.config.get('max_fill_per_gap', 2))
        for left_anchor, right_anchor in zip(clustered_anchors, clustered_anchors[1:]):
            left_x = left_anchor[0]
            right_x = right_anchor[0]
            gap = right_x - left_x
            if gap <= int(typical_step * gap_expand_ratio):
                continue
            missing = int(round(gap / max(1, typical_step))) - 1
            missing = max(0, min(max_fill_per_gap, missing))
            for offset in range(1, missing + 1):
                synthetic_x = int(round(left_x + (typical_step * offset)))
                candidates.append((synthetic_x, typical_top, typical_width, typical_height))

        candidates.sort(key=lambda box: box[0])
        deduped: list[tuple[int, int, int, int]] = []
        dedupe_distance = max(10, int(typical_width * 0.28))
        for candidate in candidates:
            if deduped and abs(candidate[0] - deduped[-1][0]) <= dedupe_distance:
                prev = deduped[-1]
                prev_area = prev[2] * prev[3]
                candidate_area = candidate[2] * candidate[3]
                if candidate_area > prev_area:
                    deduped[-1] = candidate
                continue
            deduped.append(candidate)
        return deduped

    def _detect_slot_frame_boxes(
        self,
        frame: np.ndarray,
        bar_bbox: BoundingBox,
        *,
        typical_width: int,
        typical_height: int,
    ) -> list[tuple[int, int, int, int]]:
        roi = extrair_roi(frame, {'x': bar_bbox.x, 'y': bar_bbox.y, 'w': bar_bbox.w, 'h': bar_bbox.h})
        if roi.size == 0 or roi.shape[1] < 20 or roi.shape[0] < 20:
            return []

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        binary = cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            7,
        )
        kernel = np.ones((3, 3), dtype=np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

        min_w = int(max(42, typical_width * 0.72))
        max_w = int(max(min_w + 1, typical_width * 1.45))
        min_h = int(max(70, typical_height * 0.82))
        max_h = int(max(min_h + 1, typical_height * 1.12))
        max_top = int(bar_bbox.h * 0.18)
        boxes: list[tuple[int, int, int, int]] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if not (min_w <= w <= max_w and min_h <= h <= max_h):
                continue
            if y > max_top:
                continue
            area = float(w * h)
            if area < float(min_w * min_h * 0.75):
                continue
            perimeter = float(cv2.arcLength(contour, True))
            if perimeter <= 0.0:
                continue
            box_roi = binary[y:y + h, x:x + w]
            if box_roi.size == 0:
                continue
            stroke_density = float(np.count_nonzero(box_roi)) / max(area, 1.0)
            if not (0.04 <= stroke_density <= 0.48):
                continue
            edge_band = max(2, min(6, int(min(w, h) * 0.08)))
            top_density = float(np.count_nonzero(box_roi[:edge_band, :])) / max(1.0, float(edge_band * w))
            left_density = float(np.count_nonzero(box_roi[:, :edge_band])) / max(1.0, float(edge_band * h))
            right_density = float(np.count_nonzero(box_roi[:, -edge_band:])) / max(1.0, float(edge_band * h))
            if sum(density >= 0.10 for density in (top_density, left_density, right_density)) < 2:
                continue
            boxes.append((bar_bbox.x + x, bar_bbox.y + y, w, h))

        boxes.sort(key=lambda item: item[0])
        deduped: list[tuple[int, int, int, int]] = []
        dedupe_distance = max(10, int(typical_width * 0.30))
        for box in boxes:
            if deduped and abs(box[0] - deduped[-1][0]) <= dedupe_distance:
                prev = deduped[-1]
                prev_score = prev[2] * prev[3]
                candidate_score = box[2] * box[3]
                if candidate_score > prev_score:
                    deduped[-1] = box
                continue
            deduped.append(box)
        return deduped

    @staticmethod
    def _cluster_anchor_boxes(
        anchors: list[tuple[int, int, int, int]],
        *,
        typical_width: int,
    ) -> list[tuple[int, int, int, int]]:
        if not anchors:
            return []
        cluster_distance = int(max(18, typical_width * 0.72))
        clusters: list[list[tuple[int, int, int, int]]] = [[anchors[0]]]
        for anchor in anchors[1:]:
            if anchor[0] - clusters[-1][-1][0] <= cluster_distance:
                clusters[-1].append(anchor)
                continue
            clusters.append([anchor])

        merged: list[tuple[int, int, int, int]] = []
        for cluster in clusters:
            min_x = min(box[0] for box in cluster)
            min_y = min(box[1] for box in cluster)
            max_right = max(box[0] + box[2] for box in cluster)
            max_bottom = max(box[1] + box[3] for box in cluster)
            merged.append((min_x, min_y, max_right - min_x, max_bottom - min_y))
        return merged

    def _normalize_slot_boundaries(
        self,
        frame: np.ndarray,
        bar_bbox: BoundingBox,
        slots: list[SlotPosition],
        boundary_signal: np.ndarray,
    ) -> list[SlotPosition]:
        if len(slots) < 2:
            return slots

        median_width = int(round(float(np.median([slot.bbox.w for slot in slots]))))
        median_height = int(round(float(np.median([slot.bbox.h for slot in slots]))))
        median_top = int(round(float(np.median([slot.bbox.y for slot in slots]))))
        search_span = max(6, int(median_width * 0.18))
        boundary_pad = max(2, int(median_width * 0.04))
        internal_boundaries: list[int] = []
        for left_slot, right_slot in zip(slots, slots[1:]):
            midpoint = ((left_slot.bbox.x + left_slot.bbox.w) + right_slot.bbox.x) // 2
            local_midpoint = max(0, min(bar_bbox.w - 1, midpoint - bar_bbox.x))
            internal_boundaries.append(
                self._find_best_boundary(boundary_signal, target=local_midpoint, search_span=search_span)
            )

        first_slot = slots[0]
        last_slot = slots[-1]
        outer_search = max(10, int(median_width * 0.35))
        left_outer_boundary = self._find_best_boundary(
            boundary_signal,
            target=max(0, (first_slot.bbox.x - bar_bbox.x) - outer_search),
            search_span=outer_search,
        )
        right_outer_boundary = self._find_best_boundary(
            boundary_signal,
            target=min(bar_bbox.w - 1, (last_slot.bbox.x + last_slot.bbox.w - bar_bbox.x) + outer_search),
            search_span=outer_search,
        )

        normalized: list[SlotPosition] = []
        for index, slot in enumerate(slots):
            left_edge = slot.bbox.x
            right_edge = slot.bbox.x + slot.bbox.w
            top_edge = median_top
            slot_height = median_height
            if index == 0:
                left_edge = min(left_edge, bar_bbox.x + max(0, left_outer_boundary - boundary_pad))
                left_edge = self._refine_outer_content_edge(
                    frame,
                    top=top_edge,
                    height=slot_height,
                    start_x=max(0, left_edge - median_width // 3),
                    end_x=right_edge,
                    search_from_left=True,
                )
            if index > 0:
                left_edge = max(left_edge, bar_bbox.x + internal_boundaries[index - 1] + boundary_pad)
            if index == len(slots) - 1:
                right_edge = max(right_edge, bar_bbox.x + min(bar_bbox.w - 1, right_outer_boundary + boundary_pad))
                right_edge = self._refine_outer_content_edge(
                    frame,
                    top=top_edge,
                    height=slot_height,
                    start_x=left_edge,
                    end_x=min(frame.shape[1], right_edge + median_width // 3),
                    search_from_left=False,
                )
            if index < len(slots) - 1:
                right_edge = min(right_edge, bar_bbox.x + internal_boundaries[index] - boundary_pad)
            if right_edge - left_edge < max(28, int(median_width * 0.55)):
                left_edge = slot.bbox.x
                right_edge = slot.bbox.x + slot.bbox.w
            normalized.append(
                replace(
                    slot,
                    bbox=BoundingBox(x=int(left_edge), y=int(top_edge), w=int(max(1, right_edge - left_edge)), h=int(slot_height)),
                )
            )

        normalized = self._rebalance_slot_widths_by_centers(normalized)
        normalized = [replace(slot, bbox=self._trim_slot_to_content(frame, slot.bbox)) for slot in normalized]
        normalized = self._align_inter_slot_boundaries_by_color(frame, normalized)
        normalized = self._rebalance_outlier_slot_windows(normalized)
        normalized = self._rebalance_outlier_pair_widths(normalized)
        while normalized and not self._slot_has_filled_content(frame, normalized[-1].bbox):
            normalized.pop()
        return [
            replace(slot, index=index, relative_x=(slot.bbox.x - normalized[0].bbox.x) / max(1, (normalized[-1].bbox.x + normalized[-1].bbox.w) - normalized[0].bbox.x))
            for index, slot in enumerate(normalized)
        ]

    def _split_wide_terminal_slot(self, frame: np.ndarray, slots: list[SlotPosition]) -> list[SlotPosition]:
        if len(slots) < 10:
            return slots
        median_width = float(np.median([slot.bbox.w for slot in slots]))
        min_width = int(max(40, median_width * 0.58))
        candidate_start = max(0, len(slots) - 5)
        best_index = -1
        best_candidate: tuple[BoundingBox, BoundingBox, float] | None = None
        for index in range(candidate_start, len(slots)):
            slot = slots[index]
            if slot.bbox.w < int(median_width * 1.22):
                continue
            candidate = self._find_internal_split_candidate(frame, slot.bbox, min_width=min_width)
            if candidate is None:
                continue
            if best_candidate is None or candidate[2] > best_candidate[2]:
                best_index = index
                best_candidate = candidate
        if best_index < 0 or best_candidate is None:
            return slots
        left_bbox, right_bbox, _ = best_candidate
        split_slots = list(slots)
        original = split_slots[best_index]
        split_slots = split_slots[:best_index] + [
            replace(original, bbox=left_bbox),
            replace(original, bbox=right_bbox),
        ] + split_slots[best_index + 1 :]
        return [
            replace(slot, index=index, relative_x=(slot.bbox.x - split_slots[0].bbox.x) / max(1, (split_slots[-1].bbox.x + split_slots[-1].bbox.w) - split_slots[0].bbox.x))
            for index, slot in enumerate(split_slots)
        ]

    @staticmethod
    def _rebalance_slot_widths_by_centers(slots: list[SlotPosition]) -> list[SlotPosition]:
        if len(slots) < 2:
            return slots
        centers = [slot.bbox.x + (slot.bbox.w / 2.0) for slot in slots]
        boundaries: list[int] = [slots[0].bbox.x]
        for left_center, right_center in zip(centers, centers[1:]):
            boundaries.append(int(round((left_center + right_center) / 2.0)))
        boundaries.append(slots[-1].bbox.x + slots[-1].bbox.w)

        rebalanced: list[SlotPosition] = []
        for index, slot in enumerate(slots):
            left = boundaries[index]
            right = boundaries[index + 1]
            if right <= left:
                rebalanced.append(slot)
                continue
            rebalanced.append(
                replace(
                    slot,
                    bbox=BoundingBox(
                        x=left,
                        y=slot.bbox.y,
                        w=right - left,
                        h=slot.bbox.h,
                    ),
                )
            )
        return rebalanced

    @staticmethod
    def _find_internal_split_candidate(
        frame: np.ndarray,
        bbox: BoundingBox,
        *,
        min_width: int,
    ) -> tuple[BoundingBox, BoundingBox, float] | None:
        if bbox.w < (min_width * 2):
            return None
        roi = frame[bbox.y:bbox.y + bbox.h, bbox.x:bbox.x + bbox.w]
        if roi.size == 0:
            return None
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        color = ((hsv[:, :, 1] > 52) & (hsv[:, :, 2] > 88)).mean(axis=0).astype(np.float32)
        dark = ((hsv[:, :, 1] < 55) & (hsv[:, :, 2] < 120)).mean(axis=0).astype(np.float32)
        color_sm = np.convolve(color, np.ones(5, dtype=np.float32) / 5.0, mode='same')
        dark_sm = np.convolve(dark, np.ones(5, dtype=np.float32) / 5.0, mode='same')
        left_bound = max(min_width, int(bbox.w * 0.28))
        right_bound = min(bbox.w - min_width, int(bbox.w * 0.72))
        if right_bound <= left_bound:
            return None
        best_index = -1
        best_score = 0.0
        for index in range(left_bound, right_bound):
            score = float(dark_sm[index] - (color_sm[index] * 0.28))
            if score > best_score:
                best_score = score
                best_index = index
        if best_index < 0 or best_score < 0.055:
            return None
        separator_half = 2
        left_bbox = BoundingBox(x=bbox.x, y=bbox.y, w=best_index - separator_half, h=bbox.h)
        right_bbox = BoundingBox(x=bbox.x + best_index + separator_half, y=bbox.y, w=bbox.w - best_index - separator_half, h=bbox.h)
        if left_bbox.w < min_width or right_bbox.w < min_width:
            return None
        return left_bbox, right_bbox, best_score

    @staticmethod
    def _refine_outer_content_edge(
        frame: np.ndarray,
        *,
        top: int,
        height: int,
        start_x: int,
        end_x: int,
        search_from_left: bool,
    ) -> int:
        if end_x - start_x < 8:
            return start_x if search_from_left else end_x
        roi = frame[top:top + height, start_x:end_x]
        if roi.size == 0:
            return start_x if search_from_left else end_x
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        content_mask = ((hsv[:, :, 1] > 55) & (hsv[:, :, 2] > 90)).astype(np.float32)
        column_density = content_mask.mean(axis=0)
        smoothed = np.convolve(column_density, np.ones(5, dtype=np.float32) / 5.0, mode='same')
        threshold = max(0.12, float(np.percentile(smoothed, 45)))
        active_columns = np.flatnonzero(smoothed >= threshold)
        if active_columns.size == 0:
            return start_x if search_from_left else end_x
        if search_from_left:
            return int(start_x + active_columns[0])
        return int(start_x + active_columns[-1] + 1)

    @staticmethod
    def _trim_slot_to_content(frame: np.ndarray, bbox: BoundingBox) -> BoundingBox:
        roi = frame[bbox.y:bbox.y + bbox.h, bbox.x:bbox.x + bbox.w]
        if roi.size == 0 or roi.shape[1] < 12:
            return bbox
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        content_mask = ((hsv[:, :, 1] > 52) & (hsv[:, :, 2] > 88)).astype(np.float32)
        column_density = content_mask.mean(axis=0)
        smoothed = np.convolve(column_density, np.ones(5, dtype=np.float32) / 5.0, mode='same')
        threshold = max(0.16, float(np.percentile(smoothed, 35)))
        active_columns = np.flatnonzero(smoothed >= threshold)
        if active_columns.size == 0:
            return bbox
        left = int(active_columns[0])
        right = int(active_columns[-1] + 1)
        pad = 2
        left = max(0, left - pad)
        right = min(roi.shape[1], right + pad)
        if right - left < max(28, int(bbox.w * 0.55)):
            return bbox
        return BoundingBox(x=bbox.x + left, y=bbox.y, w=right - left, h=bbox.h)

    @staticmethod
    def _align_inter_slot_boundaries_by_color(frame: np.ndarray, slots: list[SlotPosition]) -> list[SlotPosition]:
        if len(slots) < 2:
            return slots
        aligned = list(slots)
        min_width = 28
        for index in range(len(aligned) - 1):
            left_slot = aligned[index]
            right_slot = aligned[index + 1]
            separation = DarkBandSlotPositionDetector._detect_separator_band(frame, left_slot.bbox, right_slot.bbox)
            if separation is None:
                continue
            separator_left, separator_right = separation
            left_right_edge = separator_left
            right_left_edge = separator_right
            if left_right_edge - left_slot.bbox.x < min_width:
                left_right_edge = left_slot.bbox.x + left_slot.bbox.w
            if (right_slot.bbox.x + right_slot.bbox.w) - right_left_edge < min_width:
                right_left_edge = right_slot.bbox.x
            aligned[index] = replace(
                left_slot,
                bbox=BoundingBox(
                    x=left_slot.bbox.x,
                    y=left_slot.bbox.y,
                    w=max(1, left_right_edge - left_slot.bbox.x),
                    h=left_slot.bbox.h,
                ),
            )
            aligned[index + 1] = replace(
                right_slot,
                bbox=BoundingBox(
                    x=right_left_edge,
                    y=right_slot.bbox.y,
                    w=max(1, (right_slot.bbox.x + right_slot.bbox.w) - right_left_edge),
                    h=right_slot.bbox.h,
                ),
            )
        return aligned

    @staticmethod
    def _detect_separator_band(
        frame: np.ndarray,
        left_bbox: BoundingBox,
        right_bbox: BoundingBox,
    ) -> tuple[int, int] | None:
        search_left = max(left_bbox.x + int(left_bbox.w * 0.55), left_bbox.x)
        search_right = min(right_bbox.x + int(right_bbox.w * 0.45), right_bbox.x + right_bbox.w)
        if search_right - search_left < 6:
            return None

        top = max(left_bbox.y, right_bbox.y) + int(min(left_bbox.h, right_bbox.h) * 0.08)
        bottom = min(left_bbox.y + left_bbox.h, right_bbox.y + right_bbox.h) - int(min(left_bbox.h, right_bbox.h) * 0.08)
        if bottom - top < 12:
            top = max(left_bbox.y, right_bbox.y)
            bottom = min(left_bbox.y + left_bbox.h, right_bbox.y + right_bbox.h)
        roi = frame[top:bottom, search_left:search_right]
        if roi.size == 0:
            return None

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        colored_density = ((hsv[:, :, 1] > 52) & (hsv[:, :, 2] > 88)).mean(axis=0).astype(np.float32)
        smoothed = np.convolve(colored_density, np.ones(5, dtype=np.float32) / 5.0, mode='same')
        low_color_threshold = min(0.38, max(0.12, float(np.percentile(smoothed, 30))))
        low_color_mask = smoothed <= low_color_threshold

        segments = DarkBandSlotPositionDetector._find_segments(low_color_mask)
        if not segments:
            valley_index = int(np.argmin(smoothed))
            band_half_width = 2
            return search_left + max(0, valley_index - band_half_width), search_left + min(len(smoothed), valley_index + band_half_width + 1)

        midpoint = ((left_bbox.x + left_bbox.w) + right_bbox.x) / 2.0
        best_segment = min(
            segments,
            key=lambda segment: abs((search_left + ((segment[0] + segment[1]) / 2.0)) - midpoint),
        )
        segment_left = search_left + int(best_segment[0])
        segment_right = search_left + int(best_segment[1]) + 1
        min_gap = 3
        if segment_right - segment_left < min_gap:
            pad = (min_gap - (segment_right - segment_left)) // 2 + 1
            segment_left = max(search_left, segment_left - pad)
            segment_right = min(search_right, segment_right + pad)
        return segment_left, segment_right

    @staticmethod
    def _rebalance_outlier_pair_widths(slots: list[SlotPosition]) -> list[SlotPosition]:
        if len(slots) < 2:
            return slots
        median_width = float(np.median([slot.bbox.w for slot in slots]))
        if median_width <= 1.0:
            return slots
        adjusted = list(slots)
        min_width = int(max(28, median_width * 0.70))
        max_width = float(median_width * 1.35)
        min_narrow = float(median_width * 0.75)
        for index in range(len(adjusted) - 1):
            left_slot = adjusted[index]
            right_slot = adjusted[index + 1]
            left_w = float(left_slot.bbox.w)
            right_w = float(right_slot.bbox.w)
            if not (
                (left_w > max_width and right_w < min_narrow)
                or (right_w > max_width and left_w < min_narrow)
            ):
                continue
            gap = max(0, right_slot.bbox.x - (left_slot.bbox.x + left_slot.bbox.w))
            span_start = left_slot.bbox.x
            span_end = right_slot.bbox.x + right_slot.bbox.w
            usable_width = span_end - span_start - gap
            if usable_width < (min_width * 2):
                continue
            if usable_width > int(median_width * 2.6):
                continue
            left_new_width = int(round(usable_width / 2.0))
            right_new_width = usable_width - left_new_width
            if left_new_width < min_width or right_new_width < min_width:
                continue
            adjusted[index] = replace(
                left_slot,
                bbox=BoundingBox(
                    x=left_slot.bbox.x,
                    y=left_slot.bbox.y,
                    w=left_new_width,
                    h=left_slot.bbox.h,
                ),
            )
            adjusted[index + 1] = replace(
                right_slot,
                bbox=BoundingBox(
                    x=span_start + left_new_width + gap,
                    y=right_slot.bbox.y,
                    w=right_new_width,
                    h=right_slot.bbox.h,
                ),
            )
        return adjusted

    @staticmethod
    def _rebalance_outlier_slot_windows(slots: list[SlotPosition]) -> list[SlotPosition]:
        if len(slots) < 3:
            return slots
        median_width = float(np.median([slot.bbox.w for slot in slots]))
        if median_width <= 1.0:
            return slots

        adjusted = list(slots)
        overwide_threshold = float(median_width * 1.32)
        narrow_threshold = float(median_width * 0.86)
        min_width = int(max(28, median_width * 0.72))
        max_window_slots = 3

        index = 0
        while index < len(adjusted) - 2:
            widths = [float(adjusted[index + offset].bbox.w) for offset in range(max_window_slots)]
            if widths[0] <= overwide_threshold or min(widths[1:]) >= narrow_threshold:
                index += 1
                continue

            window = adjusted[index:index + max_window_slots]
            span_start = window[0].bbox.x
            span_end = window[-1].bbox.x + window[-1].bbox.w
            total_span = span_end - span_start
            if total_span < (min_width * max_window_slots):
                index += 1
                continue

            target_width = int(round(total_span / max_window_slots))
            if target_width < min_width:
                index += 1
                continue

            rebuilt: list[SlotPosition] = []
            cursor = span_start
            for offset, slot in enumerate(window):
                remaining_slots = max_window_slots - offset
                remaining_span = span_end - cursor
                width = target_width if remaining_slots > 1 else remaining_span
                width = max(min_width, width)
                if remaining_slots == 1:
                    width = remaining_span
                rebuilt.append(
                    replace(
                        slot,
                        bbox=BoundingBox(
                            x=cursor,
                            y=slot.bbox.y,
                            w=width,
                            h=slot.bbox.h,
                        ),
                    )
                )
                cursor += width

            adjusted[index:index + max_window_slots] = rebuilt
            index += max_window_slots
        return adjusted

    def _compute_boundary_signal(self, frame: np.ndarray, bar_bbox: BoundingBox) -> np.ndarray:
        roi = extrair_roi(frame, {'x': bar_bbox.x, 'y': bar_bbox.y, 'w': bar_bbox.w, 'h': bar_bbox.h})
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        y0 = int(roi.shape[0] * float(self.config.get('boundary_roi_top_ratio', 0.20)))
        y1 = int(roi.shape[0] * float(self.config.get('boundary_roi_bottom_ratio', 0.92)))
        y0 = max(0, min(roi.shape[0] - 2, y0))
        y1 = max(y0 + 1, min(roi.shape[0], y1))
        focus = hsv[y0:y1, :, :]
        hue = focus[:, :, 0].astype(np.float32).mean(axis=0)
        sat = focus[:, :, 1].astype(np.float32).mean(axis=0)
        val = focus[:, :, 2].astype(np.float32).mean(axis=0)
        dh = np.abs(np.diff(hue, prepend=hue[0]))
        ds = np.abs(np.diff(sat, prepend=sat[0]))
        dv = np.abs(np.diff(val, prepend=val[0]))
        signal = (dh * 0.50) + (ds * 0.35) + (dv * 0.15)
        return self._moving_average(signal, max(3, int(bar_bbox.h * 0.10)))

    def _refine_slot_bbox(
        self,
        *,
        bar_bbox: BoundingBox,
        raw_bbox: BoundingBox,
        typical_step: int,
        typical_width: int,
        boundary_signal: np.ndarray,
    ) -> BoundingBox:
        local_left = raw_bbox.x - bar_bbox.x
        local_right = local_left + raw_bbox.w
        half_gap = max(4, int((typical_step - typical_width) * 0.5))
        search_span = max(6, int(typical_width * 0.22))

        left_boundary = self._find_best_boundary(
            boundary_signal,
            target=max(0, local_left - half_gap),
            search_span=search_span,
        )
        right_boundary = self._find_best_boundary(
            boundary_signal,
            target=min(len(boundary_signal) - 1, local_right + half_gap),
            search_span=search_span,
        )

        refined_left = max(0, min(local_left, left_boundary + 2))
        refined_right = max(refined_left + max(20, int(typical_width * 0.55)), max(local_right, right_boundary - 2))
        refined_right = min(bar_bbox.w - 1, refined_right)
        refined_width = max(1, refined_right - refined_left)
        return BoundingBox(x=bar_bbox.x + refined_left, y=raw_bbox.y, w=refined_width, h=raw_bbox.h)

    @staticmethod
    def _find_best_boundary(signal: np.ndarray, *, target: int, search_span: int) -> int:
        if signal.size == 0:
            return target
        left = max(0, int(target - search_span))
        right = min(len(signal) - 1, int(target + search_span))
        if right <= left:
            return int(target)
        window = signal[left:right + 1]
        best_local = int(np.argmax(window))
        return left + best_local

    def _slot_has_filled_content(self, frame: np.ndarray, bbox: BoundingBox) -> bool:
        inner = extrair_roi(
            frame,
            {
                'x': bbox.x + int(bbox.w * 0.12),
                'y': bbox.y + int(bbox.h * 0.12),
                'w': max(1, int(bbox.w * 0.76)),
                'h': max(1, int(bbox.h * 0.76)),
            },
        )
        if inner.size == 0:
            return False
        hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY)
        variance = float(np.var(gray))
        mean_saturation = float(hsv[:, :, 1].mean())
        mean_value = float(hsv[:, :, 2].mean())
        grayish_ratio = float(((hsv[:, :, 1] < 38) & (hsv[:, :, 2] < 105)).mean())
        colored_ratio = float(((hsv[:, :, 1] > 62) & (hsv[:, :, 2] > 92)).mean())
        if grayish_ratio >= 0.42 and colored_ratio <= 0.20 and variance < 1800.0:
            return False
        if variance < 1200.0 and mean_saturation < 45.0 and mean_value < 85.0:
            return False
        if variance < float(self.config.get('filled_slot_min_variance', 1400.0)) and mean_value < float(
            self.config.get('filled_slot_low_value_threshold', 90.0)
        ):
            return False
        return True

    def _segment_slots_legacy_grid(
        self,
        frame: np.ndarray,
        bar_bbox: BoundingBox,
        confidence: float,
        features: dict[str, float],
    ) -> list[SlotPosition]:
        configured_slots = int(self.config['slot_count'])
        total_slots = configured_slots
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
        min_distance = max(8, int(bar_bbox.h * 0.35))
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
                        'bar_detection_features': {
                            **features,
                            'separator_count': float(len(separators)),
                            'estimated_slot_count': float(total_slots),
                        },
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
    def _normalize_signal(values: np.ndarray) -> np.ndarray:
        values = values.astype(np.float32)
        low = float(np.percentile(values, 5))
        high = float(np.percentile(values, 95))
        if high <= low:
            return np.zeros_like(values)
        return np.clip((values - low) / (high - low), 0.0, 1.0)

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

    @staticmethod
    def _estimate_slot_count(bar_bbox: BoundingBox, configured_slots: int) -> int:
        estimated_from_geometry = int(round(bar_bbox.w / max(1.0, float(bar_bbox.h))))
        estimated_from_geometry = max(configured_slots, estimated_from_geometry)
        estimated_from_geometry = min(max(configured_slots, 1) * 3, estimated_from_geometry)
        return max(1, estimated_from_geometry)


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
        full_roi = extrair_roi(
            frame,
            {
                'x': slot.bbox.x,
                'y': slot.bbox.y,
                'w': slot.bbox.w,
                'h': slot.bbox.h,
            },
        )
        if full_roi.size == 0:
            return False, {'variance': 0.0, 'empty_match': 1.0}
        full_hsv = cv2.cvtColor(full_roi, cv2.COLOR_BGR2HSV)
        side_inset = max(2, int(slot.bbox.w * 0.05))
        header_top = max(1, int(slot.bbox.h * 0.05))
        header_bottom = max(header_top + 1, int(slot.bbox.h * 0.22))
        header = full_hsv[header_top:header_bottom, side_inset:max(side_inset + 1, slot.bbox.w - side_inset)]
        empty_green_ratio = float(
            (
                (header[:, :, 0] >= 28)
                & (header[:, :, 0] <= 75)
                & (header[:, :, 1] > 40)
            ).mean()
        )
        empty_green_threshold = float(self.config.get('empty_green_header_ratio_threshold', 0.70))
        if empty_green_ratio >= empty_green_threshold:
            return False, {
                'variance': float(np.var(cv2.cvtColor(full_roi, cv2.COLOR_BGR2GRAY))),
                'empty_green_header_ratio': empty_green_ratio,
            }

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
        empty_low_variance_threshold = float(self.config.get('empty_low_variance_threshold', 1200.0))
        empty_saturation_threshold = float(self.config.get('empty_content_saturation_threshold', 18.0))
        empty_value_threshold = float(self.config.get('empty_content_value_threshold', 70.0))
        if variance <= empty_low_variance_threshold and mean_value <= (empty_value_threshold + 20.0):
            return False, {
                'variance': variance,
                'mean_saturation': mean_saturation,
                'mean_value': mean_value,
            }
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
