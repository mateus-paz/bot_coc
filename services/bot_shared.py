"""Tipos e validacoes compartilhados entre os modulos do bot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Correspondencia:
    """Representa um template encontrado na tela e sua confianca."""

    x: int
    y: int
    w: int
    h: int
    confidence: float

    @property
    def centro(self) -> tuple[int, int]:
        """Retorna o ponto central do match encontrado."""
        return self.x + self.w // 2, self.y + self.h // 2


class ErroBot(RuntimeError):
    """Erro de dominio usado para falhas controladas do bot."""


def listar_passos_pre_busca(cfg: dict[str, Any]) -> list[str]:
    """Extrai e valida a lista de assets preliminares do fluxo."""
    passos = cfg.get('flow', {}).get('pre_search_steps', [])
    if passos is None:
        return []
    if not isinstance(passos, list) or not all(isinstance(passo, str) for passo in passos):
        raise ErroBot('flow.pre_search_steps deve ser uma lista de nomes de assets.')
    return passos


def listar_passos_assets(cfg: dict[str, Any], chave: str) -> list[str]:
    """Extrai e valida uma lista de assets por chave de configuracao."""
    passos = cfg.get('flow', {}).get(chave, [])
    if passos is None:
        return []
    if not isinstance(passos, list) or not all(isinstance(passo, str) for passo in passos):
        raise ErroBot(f'flow.{chave} deve ser uma lista de nomes de assets.')
    return passos
