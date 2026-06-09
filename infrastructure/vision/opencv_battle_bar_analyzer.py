"""Adapter que reutiliza o analisador atual de battle bar."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from battle_bar import DefaultBattleBarAnalyzer
from battle_bar.domain import BattleBarSnapshot
from domain.settings.entities import UserSettings


class OpenCvBattleBarAnalyzerAdapter:
    """Converte UserSettings para a configuracao esperada pelo analyzer atual."""

    def __init__(self, *, asset_base_dir: Path, template_confidence: float = 0.82) -> None:
        self.asset_base_dir = asset_base_dir
        self.template_confidence = template_confidence

    def analyze(self, frame: np.ndarray, settings: UserSettings) -> BattleBarSnapshot:
        config = self._build_config(settings)
        analyzer = DefaultBattleBarAnalyzer(config, asset_base_dir=self.asset_base_dir, template_confidence=self.template_confidence)
        return analyzer.analyze(frame, frame_id='desktop-preview', timestamp=0.0)

    def _build_config(self, settings: UserSettings) -> dict[str, Any]:
        battle_bar = settings.battle_bar
        return {
            'enabled': battle_bar.enabled,
            'position_detector': {
                'mode': 'dark_band',
                'bar_roi': {
                    'x_ratio': battle_bar.bar_roi.x_ratio,
                    'y_ratio': battle_bar.bar_roi.y_ratio,
                    'w_ratio': battle_bar.bar_roi.w_ratio,
                    'h_ratio': battle_bar.bar_roi.h_ratio,
                },
                'slot_count': battle_bar.slot_count,
                'slot_width': battle_bar.slot_width,
                'slot_height': battle_bar.slot_height,
                'slot_spacing': battle_bar.slot_spacing,
                'allow_fixed_grid_fallback': True,
                'min_bar_confidence': 0.35,
                'bottom_search_top_ratio': 0.68,
                'bottom_search_height_ratio': 0.30,
                'sections': [{'lane': section.lane, 'count': section.count} for section in battle_bar.sections],
            },
            'content_detector': {
                'mode': 'rule_based',
                'variance_threshold': battle_bar.variance_threshold,
            },
            'type_classifier': {},
            'state_classifier': {
                'available_saturation_threshold': battle_bar.available_saturation_threshold,
                'available_value_threshold': battle_bar.available_value_threshold,
                'available_color_pixel_saturation': battle_bar.available_color_pixel_saturation,
                'available_color_ratio_threshold': battle_bar.available_color_ratio_threshold,
                'selected_color_pixel_saturation': battle_bar.selected_color_pixel_saturation,
                'selected_color_ratio_threshold': battle_bar.selected_color_ratio_threshold,
                'state_roi_inset': {
                    'x': battle_bar.state_roi_inset_x,
                    'y': battle_bar.state_roi_inset_y,
                    'w': battle_bar.state_roi_inset_w,
                    'h': battle_bar.state_roi_inset_h,
                },
            },
            'planner': {
                'preferred_types': ['troop', 'siege_machine', 'hero', 'spell'],
            },
        }
