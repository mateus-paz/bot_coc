"""Interfaces de extensao para analise da barra de batalha."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from battle_bar.domain import BattleBarLayout, BattleBarSnapshot, ContentState, SlotContent, SlotPosition


class SlotPositionDetector(Protocol):
    """Detecta apenas as posicoes fisicas dos slots."""

    def detect(self, frame: np.ndarray) -> list[SlotPosition]:
        """Retorna as posicoes ordenadas da barra para o frame informado."""


class SlotContentDetector(Protocol):
    """Detecta se existe conteudo em cada slot."""

    def detect(self, frame: np.ndarray, slots: list[SlotPosition]) -> list[SlotPosition]:
        """Retorna os slots com conteudo associado ou `None`."""


class ContentTypeClassifier(Protocol):
    """Classifica o tipo do conteudo presente no slot."""

    def classify(self, frame: np.ndarray, slot: SlotPosition, content: SlotContent) -> SlotContent:
        """Retorna uma copia do conteudo com o tipo preenchido."""


class ContentStateClassifier(Protocol):
    """Classifica o estado do conteudo presente no slot."""

    def classify(self, frame: np.ndarray, slot: SlotPosition, content: SlotContent) -> ContentState:
        """Retorna o estado observado do conteudo."""


class ActionPlanner(Protocol):
    """Planeja acoes a partir do snapshot da barra."""

    def plan(self, snapshot: BattleBarSnapshot) -> list:
        """Retorna uma lista de acoes ou slots acionaveis."""


class BattleBarAnalyzer(Protocol):
    """Fachada de analise completa da barra."""

    @property
    def layout(self) -> BattleBarLayout:
        """Layout estrutural conhecido pelo analisador."""

    def analyze(self, frame: np.ndarray, *, frame_id: str, timestamp: float) -> BattleBarSnapshot:
        """Executa o pipeline completo e devolve um snapshot da barra."""
