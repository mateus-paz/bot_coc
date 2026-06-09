"""Testes unitarios do subsistema battle_bar."""

from __future__ import annotations

import unittest
from pathlib import Path

import cv2
import numpy as np

from battle_bar import AvailabilityState, DefaultActionPlanner, DefaultBattleBarAnalyzer, SlotContentType


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

        snapshot = self.analyzer.analyze(frame, frame_id='frame-4', timestamp=126.0)

        self.assertTrue(snapshot.diagnostics['used_position_fallback'])
        self.assertLess(snapshot.diagnostics['position_confidence'], 0.40)


if __name__ == '__main__':
    unittest.main()
