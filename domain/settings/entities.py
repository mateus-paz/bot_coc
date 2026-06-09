"""Entidades de configuracao persistidas em AppData."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class RatioRegion:
    """ROI normalizada em relacao a largura/altura da janela."""

    x_ratio: float
    y_ratio: float
    w_ratio: float
    h_ratio: float


@dataclass(frozen=True)
class BattleBarSection:
    """Agrupamento logico esperado na barra."""

    lane: str
    count: int


@dataclass(frozen=True)
class BattleBarSettings:
    """Configuracao de deteccao da barra e de seus slots."""

    enabled: bool = True
    slot_count: int = 8
    slot_width: int = 68
    slot_height: int = 68
    slot_spacing: int = 14
    bar_roi: RatioRegion = field(default_factory=lambda: RatioRegion(0.296, 0.824, 0.648, 0.070))
    variance_threshold: float = 120.0
    sections: tuple[BattleBarSection, ...] = field(
        default_factory=lambda: (
            BattleBarSection('troops', 4),
            BattleBarSection('siege', 1),
            BattleBarSection('heroes', 2),
            BattleBarSection('spells', 1),
        )
    )
    available_saturation_threshold: float = 35.0
    available_value_threshold: float = 35.0
    available_color_pixel_saturation: int = 45
    available_color_ratio_threshold: float = 0.20
    selected_color_pixel_saturation: int = 90
    selected_color_ratio_threshold: float = 0.35
    state_roi_inset_x: int = 6
    state_roi_inset_y: int = 6
    state_roi_inset_w: int = 56
    state_roi_inset_h: int = 56


@dataclass(frozen=True)
class UserSettings:
    """Configuracao editavel somente pela UI."""

    window_title: str = 'Clash of Clans'
    window_match_mode: str = 'contains'
    activate_window: bool = True
    dry_run: bool = True
    cv_profile: str | None = None
    bottom_region: RatioRegion = field(default_factory=lambda: RatioRegion(0.0, 0.78, 1.0, 0.22))
    battle_bar: BattleBarSettings = field(default_factory=BattleBarSettings)

    def to_dict(self) -> dict[str, Any]:
        """Serializa configuracao para persistencia JSON."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'UserSettings':
        """Reconstrui a configuracao a partir de dados serializados."""
        default_settings = cls()
        bottom_region_data = data.get('bottom_region') or default_settings.bottom_region.__dict__
        bottom_region = RatioRegion(**bottom_region_data)
        battle_bar_data = data.get('battle_bar', {})
        bar_roi_data = battle_bar_data.get('bar_roi') or default_settings.battle_bar.bar_roi.__dict__
        bar_roi = RatioRegion(**bar_roi_data)
        sections = tuple(BattleBarSection(**item) for item in battle_bar_data.get('sections', []))
        default_battle_bar = default_settings.battle_bar
        battle_bar = BattleBarSettings(
            enabled=bool(battle_bar_data.get('enabled', True)),
            slot_count=int(battle_bar_data.get('slot_count', 8)),
            slot_width=int(battle_bar_data.get('slot_width', 68)),
            slot_height=int(battle_bar_data.get('slot_height', 68)),
            slot_spacing=int(battle_bar_data.get('slot_spacing', 14)),
            bar_roi=bar_roi,
            variance_threshold=float(battle_bar_data.get('variance_threshold', 120.0)),
            sections=sections or default_battle_bar.sections,
            available_saturation_threshold=float(battle_bar_data.get('available_saturation_threshold', 35.0)),
            available_value_threshold=float(battle_bar_data.get('available_value_threshold', 35.0)),
            available_color_pixel_saturation=int(battle_bar_data.get('available_color_pixel_saturation', 45)),
            available_color_ratio_threshold=float(battle_bar_data.get('available_color_ratio_threshold', 0.20)),
            selected_color_pixel_saturation=int(battle_bar_data.get('selected_color_pixel_saturation', 90)),
            selected_color_ratio_threshold=float(battle_bar_data.get('selected_color_ratio_threshold', 0.35)),
            state_roi_inset_x=int(battle_bar_data.get('state_roi_inset_x', 6)),
            state_roi_inset_y=int(battle_bar_data.get('state_roi_inset_y', 6)),
            state_roi_inset_w=int(battle_bar_data.get('state_roi_inset_w', 56)),
            state_roi_inset_h=int(battle_bar_data.get('state_roi_inset_h', 56)),
        )
        return cls(
            window_title=str(data.get('window_title', 'Clash of Clans')),
            window_match_mode=str(data.get('window_match_mode', 'contains')),
            activate_window=bool(data.get('activate_window', True)),
            dry_run=bool(data.get('dry_run', True)),
            cv_profile=data.get('cv_profile'),
            bottom_region=bottom_region,
            battle_bar=battle_bar,
        )
