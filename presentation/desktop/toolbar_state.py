"""Regras de habilitacao dos controles da toolbar."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolbarControlState:
    """Estado habilitado/desabilitado dos controles."""

    can_start: bool
    can_pause: bool
    can_stop: bool
    can_change_profile: bool


def resolve_toolbar_control_state(status) -> ToolbarControlState:
    """Traduz o estado do worker para os controles disponiveis."""
    return ToolbarControlState(
        can_start=status.state in {'idle', 'stopped', 'error'},
        can_pause=status.state == 'running',
        can_stop=status.state == 'running',
        can_change_profile=not status.is_running,
    )
