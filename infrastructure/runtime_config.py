"""Construcao de configuracao de runtime para o bot legado."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from config import carregar_yaml, mesclar_dicts_profundamente, resolver_diretorio_bundle
from domain.settings.entities import UserSettings
from infrastructure.persistence.settings_repository import AppDataSettingsRepository


class RuntimeConfigBuilder:
    """Traduz UserSettings para o formato esperado pelo PlayGamesAppBot atual."""

    def __init__(self, *, repository: AppDataSettingsRepository, template_path: Path | None = None) -> None:
        self.repository = repository
        self.template_path = template_path or (resolver_diretorio_bundle() / 'config.example.yaml')

    def build(self, settings: UserSettings) -> tuple[dict[str, Any], Path]:
        base = deepcopy(carregar_yaml(self.template_path))
        cfg = mesclar_dicts_profundamente(
            base,
            {
                'window': {
                    'title_contains': settings.window_title,
                    'title_match_mode': settings.window_match_mode,
                    'activate_before_click': settings.activate_window,
                },
                'runtime': {
                    'dry_run': settings.dry_run,
                    'debug_dir': str(self.repository.debug_dir),
                },
                'battle_bar': {
                    'enabled': settings.battle_bar.enabled,
                    'position_detector': {
                        'mode': 'dark_band',
                        'bar_roi': {
                            'x_ratio': settings.battle_bar.bar_roi.x_ratio,
                            'y_ratio': settings.battle_bar.bar_roi.y_ratio,
                            'w_ratio': settings.battle_bar.bar_roi.w_ratio,
                            'h_ratio': settings.battle_bar.bar_roi.h_ratio,
                        },
                        'slot_count': settings.battle_bar.slot_count,
                        'slot_width': settings.battle_bar.slot_width,
                        'slot_height': settings.battle_bar.slot_height,
                        'slot_spacing': settings.battle_bar.slot_spacing,
                        'allow_fixed_grid_fallback': True,
                        'min_bar_confidence': 0.35,
                        'bottom_search_top_ratio': 0.68,
                        'bottom_search_height_ratio': 0.30,
                        'sections': [{'lane': section.lane, 'count': section.count} for section in settings.battle_bar.sections],
                    },
                    'content_detector': {
                        'mode': 'rule_based',
                        'variance_threshold': settings.battle_bar.variance_threshold,
                    },
                    'type_classifier': {},
                    'state_classifier': {
                        'available_saturation_threshold': settings.battle_bar.available_saturation_threshold,
                        'available_value_threshold': settings.battle_bar.available_value_threshold,
                        'available_color_pixel_saturation': settings.battle_bar.available_color_pixel_saturation,
                        'available_color_ratio_threshold': settings.battle_bar.available_color_ratio_threshold,
                        'selected_color_pixel_saturation': settings.battle_bar.selected_color_pixel_saturation,
                        'selected_color_ratio_threshold': settings.battle_bar.selected_color_ratio_threshold,
                        'state_roi_inset': {
                            'x': settings.battle_bar.state_roi_inset_x,
                            'y': settings.battle_bar.state_roi_inset_y,
                            'w': settings.battle_bar.state_roi_inset_w,
                            'h': settings.battle_bar.state_roi_inset_h,
                        },
                    },
                },
            },
        )
        if settings.cv_profile:
            cfg.setdefault('runtime', {})['cv_profile'] = settings.cv_profile
        return cfg, self.template_path
