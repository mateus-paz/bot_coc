"""Entidades de dominio para descoberta de janela."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowBounds:
    """Retangulo absoluto da janela alvo."""

    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class WindowInfo:
    """Informacoes essenciais da janela localizada."""

    title: str
    bounds: WindowBounds

