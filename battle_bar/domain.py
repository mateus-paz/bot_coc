"""Modelo de dominio para analise da barra de ataque."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SlotContentType(str, Enum):
    """Tipos de conteudo possiveis em um slot."""

    TROOP = 'troop'
    HERO = 'hero'
    SPELL = 'spell'
    SIEGE_MACHINE = 'siege_machine'
    UNKNOWN = 'unknown'


class AvailabilityState(str, Enum):
    """Estado funcional do conteudo presente em um slot."""

    AVAILABLE = 'available'
    USED = 'used'
    UNAVAILABLE = 'unavailable'


class SlotLaneHint(str, Enum):
    """Secao estrutural esperada da barra."""

    TROOP_SECTION = 'troop_section'
    SIEGE_SECTION = 'siege_section'
    HERO_SECTION = 'hero_section'
    SPELL_SECTION = 'spell_section'
    UNKNOWN = 'unknown'


class DetectorKind(str, Enum):
    """Tecnologias ou familias de detector suportadas."""

    COORDINATE_RULES = 'coordinate_rules'
    TEMPLATE_MATCHING = 'template_matching'
    OCR = 'ocr'
    OPENCV_RULES = 'opencv_rules'
    YOLO = 'yolo'
    HYBRID = 'hybrid'


@dataclass(frozen=True)
class BoundingBox:
    """Retangulo alinhado ao eixo em coordenadas da tela."""

    x: int
    y: int
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        """Retorna o centro do retangulo."""
        return self.x + self.w // 2, self.y + self.h // 2


@dataclass(frozen=True)
class DetectionCandidate:
    """Resultado intermediario com metadados do backend visual."""

    label: str
    confidence: float
    bbox: BoundingBox | None = None
    source: DetectorKind = DetectorKind.HYBRID
    features: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentState:
    """Estado observavel do conteudo presente no slot."""

    availability: AvailabilityState
    selected: bool = False
    cooldown_hint: bool = False
    confidence: float = 0.0


@dataclass(frozen=True)
class SlotContent:
    """Conteudo associado a uma posicao fisica de slot."""

    content_id: str
    type: SlotContentType
    state: ContentState
    name: str | None = None
    quantity_hint: int | None = None
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SlotPosition:
    """Representa apenas a existencia fisica do slot na barra."""

    index: int
    bbox: BoundingBox
    lane_hint: SlotLaneHint = SlotLaneHint.UNKNOWN
    relative_x: float = 0.0
    content: SlotContent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> tuple[int, int]:
        """Retorna o centro do slot."""
        return self.bbox.center

    @property
    def is_empty(self) -> bool:
        """Indica se o slot nao possui conteudo associado."""
        return self.content is None

    def with_content(self, content: SlotContent | None) -> 'SlotPosition':
        """Retorna uma copia da posicao com o conteudo associado."""
        return SlotPosition(
            index=self.index,
            bbox=self.bbox,
            lane_hint=self.lane_hint,
            relative_x=self.relative_x,
            content=content,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class BattleBarLayout:
    """Regras estruturais conhecidas da barra."""

    expected_order: tuple[SlotLaneHint, ...]
    max_slots: int | None = None
    group_gaps: tuple[int, ...] = ()
    anchor_regions: dict[str, BoundingBox] = field(default_factory=dict)


@dataclass(frozen=True)
class BattleBarSnapshot:
    """Snapshot imutavel da barra de ataque em um frame."""

    frame_id: str
    bar_bbox: BoundingBox
    slots: tuple[SlotPosition, ...]
    timestamp: float
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def actionable_slots(self) -> list[SlotPosition]:
        """Retorna slots com conteudo presente."""
        return [slot for slot in self.slots if slot.content is not None]


@dataclass(frozen=True)
class ActionableSlot:
    """Projecao simplificada para o planejador de acoes."""

    slot_index: int
    content_type: SlotContentType
    state: ContentState
    tap_point: tuple[int, int]
    priority: int
    content_name: str | None = None
