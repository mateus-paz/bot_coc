"""DTOs usados entre servicos/casos de uso e interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class WindowInfoDTO:
    """Informacoes amigaveis da janela para a UI."""

    title: str
    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class PreviewResultDTO:
    """Resultado de diagnostico com imagem e mensagem."""

    message: str
    image_bgr: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SlotInfoDTO:
    """Resumo de um slot para exibir em tabela ou texto."""

    index: int
    lane: str
    content_type: str | None
    state: str | None
    is_empty: bool

