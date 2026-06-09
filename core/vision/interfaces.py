"""Interfaces de localizacao de janela e analise de battle bar."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from battle_bar.domain import BattleBarSnapshot
from domain.settings.entities import UserSettings
from domain.window.entities import WindowInfo


class WindowLocator(Protocol):
    """Contrato de localizacao da janela alvo."""

    def find_target_window(self, title: str, match_mode: str, activate: bool) -> WindowInfo:
        """Encontra a janela alvo configurada."""


class BattleBarAnalyzerPort(Protocol):
    """Contrato de analise completa da barra de batalha."""

    def analyze(self, frame: np.ndarray, settings: UserSettings) -> BattleBarSnapshot:
        """Executa o pipeline e devolve um snapshot de slots."""

