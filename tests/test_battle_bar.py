"""Testes unitarios do subsistema battle_bar."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

import cv2
import numpy as np

from battle_bar import AvailabilityState, BoundingBox, DefaultActionPlanner, DefaultBattleBarAnalyzer, SlotContentType, SlotPosition
from battle_bar.classifiers import OcrContentQuantityClassifier
from battle_bar.detectors import DarkBandSlotPositionDetector, RuleBasedSlotContentDetector
from domain.settings.entities import UserSettings
from infrastructure.vision.opencv_battle_bar_analyzer import OpenCvBattleBarAnalyzerAdapter
from utils.ocr_service import _resolve_psm_modes


def _draw_slot(frame: np.ndarray, x: int, y: int, size: int, *, fill_bgr: tuple[int, int, int] | None) -> None:
    cv2.rectangle(frame, (x, y), (x + size - 1, y + size - 1), (20, 20, 20), thickness=-1)
    if fill_bgr is None:
        return
    cv2.rectangle(frame, (x + 6, y + 6), (x + size - 7, y + size - 7), fill_bgr, thickness=-1)
    cv2.line(frame, (x + 6, y + 6), (x + size - 7, y + size - 7), (255, 255, 255), thickness=2)


def _draw_dark_bar(frame: np.ndarray, x: int, y: int, width: int, height: int, slot_count: int) -> None:
    cv2.rectangle(frame, (x, y), (x + width - 1, y + height - 1), (28, 28, 28), thickness=-1)
    slot_width = width // slot_count
    for index in range(slot_count):
        sx = x + index * slot_width + 3
        ex = x + (index + 1) * slot_width - 4
        cv2.rectangle(frame, (sx, y + 4), (ex, y + height - 5), (55, 55, 55), thickness=1)
        if index < slot_count - 1:
            separator_x = x + (index + 1) * slot_width
            cv2.line(frame, (separator_x, y + 2), (separator_x, y + height - 3), (170, 170, 170), thickness=2)


class BattleBarAnalyzerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            'enabled': True,
            'position_detector': {
                'mode': 'fixed_grid',
                'bar_roi': {'x': 20, 'y': 76, 'w': 180, 'h': 40},
                'slot_count': 4,
                'slot_width': 40,
                'slot_height': 40,
                'slot_spacing': 6,
                'sections': [
                    {'lane': 'troops', 'count': 2},
                    {'lane': 'heroes', 'count': 1},
                    {'lane': 'spells', 'count': 1},
                ],
            },
            'content_detector': {
                'mode': 'rule_based',
                'variance_threshold': 80.0,
            },
            'type_classifier': {},
            'state_classifier': {
                'available_saturation_threshold': 35,
                'available_value_threshold': 35,
                'available_color_pixel_saturation': 45,
                'available_color_ratio_threshold': 0.15,
                'selected_color_pixel_saturation': 150,
                'selected_color_ratio_threshold': 0.30,
                'state_roi_inset': {'x': 6, 'y': 6, 'w': 28, 'h': 28},
            },
            'planner': {
                'preferred_types': ['troop', 'hero', 'spell'],
            },
        }
        self.analyzer = DefaultBattleBarAnalyzer(self.config, asset_base_dir=Path('.'), template_confidence=0.82)
        self.planner = DefaultActionPlanner(self.config['planner'])

    def _build_frame(self) -> np.ndarray:
        frame = np.full((120, 240, 3), 180, dtype=np.uint8)
        cv2.rectangle(frame, (0, 0), (239, 70), (110, 160, 110), thickness=-1)
        _draw_dark_bar(frame, 18, 74, 184, 42, 4)
        _draw_slot(frame, 20, 76, 40, fill_bgr=(0, 255, 0))
        _draw_slot(frame, 66, 76, 40, fill_bgr=None)
        _draw_slot(frame, 112, 76, 40, fill_bgr=(90, 90, 90))
        _draw_slot(frame, 158, 76, 40, fill_bgr=(0, 255, 255))
        return frame

    def test_analyzer_keeps_empty_slot_without_state(self) -> None:
        snapshot = self.analyzer.analyze(self._build_frame(), frame_id='frame-1', timestamp=123.0)

        self.assertEqual(4, len(snapshot.slots))
        self.assertIsNone(snapshot.slots[1].content)
        self.assertEqual(3, snapshot.diagnostics['non_empty_slots'])
        self.assertFalse(snapshot.diagnostics['used_position_fallback'])
        self.assertGreater(snapshot.diagnostics['position_confidence'], 0.35)

    def test_analyzer_classifies_type_and_state(self) -> None:
        snapshot = self.analyzer.analyze(self._build_frame(), frame_id='frame-2', timestamp=124.0)

        self.assertEqual(SlotContentType.TROOP, snapshot.slots[0].content.type)
        self.assertEqual(AvailabilityState.AVAILABLE, snapshot.slots[0].content.state.availability)

        self.assertEqual(SlotContentType.HERO, snapshot.slots[2].content.type)
        self.assertEqual(AvailabilityState.USED, snapshot.slots[2].content.state.availability)

        self.assertEqual(SlotContentType.SPELL, snapshot.slots[3].content.type)
        self.assertEqual(AvailabilityState.AVAILABLE, snapshot.slots[3].content.state.availability)

    def test_planner_returns_only_available_non_empty_slots(self) -> None:
        snapshot = self.analyzer.analyze(self._build_frame(), frame_id='frame-3', timestamp=125.0)

        actions = self.planner.plan(snapshot)

        self.assertEqual([0, 3], [action.slot_index for action in actions])
        self.assertEqual([SlotContentType.TROOP, SlotContentType.SPELL], [action.content_type for action in actions])

    def test_detector_falls_back_when_dark_band_is_not_confident(self) -> None:
        frame = np.full((120, 240, 3), 220, dtype=np.uint8)
        dark_band_config = {
            **self.config,
            'position_detector': {
                'mode': 'dark_band',
                'bar_roi': {'x': 18, 'y': 74, 'w': 184, 'h': 42},
                'slot_count': 4,
                'slot_width': 40,
                'slot_height': 40,
                'slot_spacing': 5,
                'allow_fixed_grid_fallback': True,
                'min_bar_confidence': 0.35,
                'search_margin_x_ratio': 0.15,
                'search_margin_y_ratio': 0.40,
                'sections': self.config['position_detector']['sections'],
            },
        }
        analyzer = DefaultBattleBarAnalyzer(dark_band_config, asset_base_dir=Path('.'), template_confidence=0.82)

        snapshot = analyzer.analyze(frame, frame_id='frame-4', timestamp=126.0)

        self.assertTrue(snapshot.diagnostics['used_position_fallback'])
        self.assertLess(snapshot.diagnostics['position_confidence'], 0.40)

    def test_quantity_classifier_parser_extracts_digits_after_x(self) -> None:
        self.assertEqual(7, OcrContentQuantityClassifier._parse_quantity('x7'))
        self.assertEqual(25, OcrContentQuantityClassifier._parse_quantity('x25'))
        self.assertEqual(4, OcrContentQuantityClassifier._parse_quantity('X4'))
        self.assertEqual(12, OcrContentQuantityClassifier._parse_quantity('12'))
        self.assertIsNone(OcrContentQuantityClassifier._parse_quantity('king'))

    def test_quantity_classifier_uses_configured_backend_order(self) -> None:
        classifier = OcrContentQuantityClassifier({'preferred_backends': ['pytesseract']})

        self.assertEqual(['pytesseract'], classifier._backend_order())

    def test_resolve_psm_modes_preserves_unique_valid_values(self) -> None:
        self.assertEqual([7, 6], _resolve_psm_modes({'psm_modes': [7, '6', 7, 'x']}, default=[6]))

    def test_analyzer_writes_quantity_hint_from_quantity_classifier(self) -> None:
        quantity_classifier = Mock()
        quantity_classifier.classify.side_effect = lambda frame, slot, content: content if content.type == SlotContentType.HERO else type(content)(
            content_id=content.content_id,
            type=content.type,
            state=content.state,
            name=content.name,
            quantity_hint=7,
            confidence=content.confidence,
            metadata=content.metadata,
        )
        self.analyzer.quantity_classifier = quantity_classifier

        snapshot = self.analyzer.analyze(self._build_frame(), frame_id='frame-5', timestamp=127.0)

        self.assertEqual(7, snapshot.slots[0].content.quantity_hint)
        self.assertIsNone(snapshot.slots[2].content.quantity_hint)
        self.assertEqual(7, snapshot.slots[3].content.quantity_hint)

    def test_rebalance_outlier_slot_windows_redistributes_overwide_slot(self) -> None:
        slots = [
            SlotPosition(index=0, bbox=BoundingBox(x=0, y=0, w=76, h=100)),
            SlotPosition(index=1, bbox=BoundingBox(x=76, y=0, w=78, h=100)),
            SlotPosition(index=2, bbox=BoundingBox(x=154, y=0, w=77, h=100)),
            SlotPosition(index=3, bbox=BoundingBox(x=231, y=0, w=78, h=100)),
            SlotPosition(index=4, bbox=BoundingBox(x=309, y=0, w=109, h=100)),
            SlotPosition(index=5, bbox=BoundingBox(x=418, y=0, w=80, h=100)),
            SlotPosition(index=6, bbox=BoundingBox(x=498, y=0, w=58, h=100)),
        ]

        rebalanced = DarkBandSlotPositionDetector._rebalance_outlier_slot_windows(slots)
        widths = [slot.bbox.w for slot in rebalanced[4:7]]

        self.assertEqual(sum([109, 80, 58]), sum(widths))
        self.assertTrue(all(70 <= width <= 90 for width in widths))

    def test_detect_slot_frame_boxes_uses_card_geometry(self) -> None:
        frame = np.full((180, 520, 3), 32, dtype=np.uint8)
        bar_bbox = BoundingBox(x=40, y=60, w=420, h=90)
        for index in range(5):
            x = 40 + (index * 82)
            cv2.rectangle(frame, (x, 60), (x + 70, 146), (245, 245, 245), thickness=3)
            cv2.rectangle(frame, (x + 6, 66), (x + 64, 140), (90 + (index * 10), 150, 210), thickness=-1)

        detector = DarkBandSlotPositionDetector(self.config['position_detector'])
        boxes = detector._detect_slot_frame_boxes(frame, bar_bbox, typical_width=70, typical_height=88)

        self.assertGreaterEqual(len(boxes), 5)
        widths = [box[2] for box in boxes[:5]]
        self.assertTrue(all(60 <= width <= 78 for width in widths))

    def test_structural_grid_detects_reference_slots_and_empty_positions(self) -> None:
        adapter = OpenCvBattleBarAnalyzerAdapter(asset_base_dir=Path('.'))
        config = adapter._build_config(UserSettings())
        expected_counts = {
            '01.png': (11, 11),
            '02.png': (15, 15),
            '03.png': (12, 3),
            '04.png': (11, 10),
            '05.png': (13, 13),
        }

        for image_name, (expected_slots, expected_filled) in expected_counts.items():
            with self.subTest(image=image_name):
                frame = cv2.imread(str(Path('barras') / image_name))
                self.assertIsNotNone(frame)
                position_detector = DarkBandSlotPositionDetector(config['position_detector'])
                content_detector = RuleBasedSlotContentDetector(config['content_detector'])

                slots = position_detector.detect(frame)
                classified = content_detector.detect(frame, slots)

                self.assertEqual(expected_slots, len(slots))
                self.assertEqual(expected_filled, sum(slot.content is not None for slot in classified))
                self.assertTrue(all('structural_score' in slot.metadata for slot in slots))
                self.assertTrue(all(slot.bbox.w >= 90 for slot in slots))


if __name__ == '__main__':
    unittest.main()
