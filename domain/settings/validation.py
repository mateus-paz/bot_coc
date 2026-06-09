"""Validacoes de dominio para configuracoes do usuario."""

from __future__ import annotations

from domain.settings.entities import UserSettings


def validar_user_settings(settings: UserSettings) -> None:
    """Valida coerencia minima da configuracao salva pela UI."""
    if not settings.window_title.strip():
        raise ValueError('Informe um titulo de janela para localizar o Clash of Clans.')
    if settings.window_match_mode not in {'contains', 'starts_with', 'exact'}:
        raise ValueError('Modo de comparacao de janela invalido.')
    if settings.battle_bar.slot_count <= 0:
        raise ValueError('A quantidade de slots deve ser maior que zero.')
    for value in (
        settings.bottom_region.x_ratio,
        settings.bottom_region.y_ratio,
        settings.bottom_region.w_ratio,
        settings.bottom_region.h_ratio,
        settings.battle_bar.bar_roi.x_ratio,
        settings.battle_bar.bar_roi.y_ratio,
        settings.battle_bar.bar_roi.w_ratio,
        settings.battle_bar.bar_roi.h_ratio,
    ):
        if value < 0:
            raise ValueError('Regioes relativas nao podem ser negativas.')
    if settings.bottom_region.w_ratio <= 0 or settings.bottom_region.h_ratio <= 0:
        raise ValueError('A regiao inferior precisa ter largura e altura positivas.')
    if settings.battle_bar.bar_roi.w_ratio <= 0 or settings.battle_bar.bar_roi.h_ratio <= 0:
        raise ValueError('A ROI da battle bar precisa ter largura e altura positivas.')

