"""Fachada de analise completa da barra de ataque."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from battle_bar.classifiers import RuleBasedContentStateClassifier, RuleBasedContentTypeClassifier
from battle_bar.detectors import DarkBandSlotPositionDetector, FixedGridSlotPositionDetector, RuleBasedSlotContentDetector, TemplateAnchoredSlotPositionDetector
from battle_bar.domain import BattleBarLayout, BattleBarSnapshot, BoundingBox, SlotLaneHint
from services.bot_shared import ErroBot
from utils.geometry_utils import resolver_roi


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


def _layout_from_config(config: dict[str, Any]) -> BattleBarLayout:
    sections = config.get('position_detector', {}).get('sections', [])
    expected_order = tuple(_lane_from_name(section['lane']) for section in sections if 'lane' in section)
    return BattleBarLayout(expected_order=expected_order, max_slots=config.get('position_detector', {}).get('slot_count'))


class DefaultBattleBarAnalyzer:
    """Pipeline padrao de deteccao, classificacao e consolidacao."""

    def __init__(self, config: dict[str, Any], *, asset_base_dir: Path, template_confidence: float = 0.82) -> None:
        self.config = config
        self.asset_base_dir = asset_base_dir
        self.template_confidence = template_confidence
        self.layout = _layout_from_config(config)
        self.position_detector = self._build_position_detector()
        self.content_detector = self._build_content_detector()
        self.type_classifier = RuleBasedContentTypeClassifier(config.get('type_classifier', {}), asset_base_dir=asset_base_dir)
        self.state_classifier = RuleBasedContentStateClassifier(config.get('state_classifier', {}))

    def _build_position_detector(self):
        cfg = self.config.get('position_detector', {})
        mode = str(cfg.get('mode', 'dark_band'))
        if mode == 'dark_band':
            return DarkBandSlotPositionDetector(cfg, fallback_detector=FixedGridSlotPositionDetector(cfg))
        if mode == 'fixed_grid':
            return FixedGridSlotPositionDetector(cfg)
        if mode == 'template_anchored':
            return TemplateAnchoredSlotPositionDetector(cfg, asset_base_dir=self.asset_base_dir, confidence=self.template_confidence)
        raise ErroBot(f'battle_bar.position_detector.mode invalido: {mode}')

    def _build_content_detector(self):
        cfg = self.config.get('content_detector', {})
        mode = str(cfg.get('mode', 'rule_based'))
        if mode == 'rule_based':
            return RuleBasedSlotContentDetector(cfg, asset_base_dir=self.asset_base_dir, confidence=self.template_confidence)
        raise ErroBot(f'battle_bar.content_detector.mode invalido: {mode}')

    def analyze(self, frame: np.ndarray, *, frame_id: str, timestamp: float) -> BattleBarSnapshot:
        slots = self.position_detector.detect(frame)
        slots = self.content_detector.detect(frame, slots)
        classified = []
        for slot in slots:
            if slot.content is None:
                classified.append(slot)
                continue
            typed = self.type_classifier.classify(frame, slot, slot.content)
            state = self.state_classifier.classify(frame, slot, typed)
            classified.append(slot.with_content(replace(typed, state=state)))

        bar_bbox = self._resolve_bar_bbox(frame)
        position_confidence = float(getattr(self.position_detector, 'last_confidence', 0.0))
        position_strategy = str(getattr(self.position_detector, 'last_strategy', 'unknown'))
        diagnostics = {
            'slot_count': len(classified),
            'non_empty_slots': sum(1 for slot in classified if slot.content is not None),
            'position_confidence': position_confidence,
            'position_strategy': position_strategy,
            'used_position_fallback': bool(getattr(self.position_detector, 'last_used_fallback', False)),
        }
        return BattleBarSnapshot(
            frame_id=frame_id,
            bar_bbox=bar_bbox,
            slots=tuple(classified),
            timestamp=timestamp,
            diagnostics=diagnostics,
        )

    def _resolve_bar_bbox(self, frame: np.ndarray) -> BoundingBox:
        detected_bbox = getattr(self.position_detector, 'last_bar_bbox', None)
        if detected_bbox is not None:
            return detected_bbox
        cfg = self.config.get('position_detector', {}).get('bar_roi')
        if not isinstance(cfg, dict):
            raise ErroBot('battle_bar.position_detector.bar_roi deve estar configurado.')
        frame_h, frame_w = frame.shape[:2]
        x, y, w, h = resolver_roi((frame_w, frame_h), cfg)
        return BoundingBox(x=x, y=y, w=w, h=h)
