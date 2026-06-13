"""Testes dos estados dos controles da toolbar."""

from __future__ import annotations

import unittest

from presentation.desktop.toolbar_state import resolve_toolbar_control_state
from services.bot_controller import BotStatus


def _status(state: str, *, running: bool = False) -> BotStatus:
    return BotStatus(
        state=state,
        is_running=running,
        is_paused=state == 'paused',
        stop_requested=state == 'stopping',
        last_error=None,
    )


class ToolbarStateTest(unittest.TestCase):
    def test_idle_allows_start_and_profile_change(self) -> None:
        controls = resolve_toolbar_control_state(_status('idle'))

        self.assertTrue(controls.can_start)
        self.assertTrue(controls.can_change_profile)
        self.assertFalse(controls.can_pause)
        self.assertTrue(controls.can_stop)

    def test_running_allows_pause_and_stop(self) -> None:
        controls = resolve_toolbar_control_state(_status('running', running=True))

        self.assertFalse(controls.can_start)
        self.assertFalse(controls.can_change_profile)
        self.assertTrue(controls.can_pause)
        self.assertTrue(controls.can_stop)

    def test_stopping_locks_all_runtime_controls(self) -> None:
        controls = resolve_toolbar_control_state(_status('stopping', running=True))

        self.assertFalse(controls.can_start)
        self.assertFalse(controls.can_change_profile)
        self.assertFalse(controls.can_pause)
        self.assertTrue(controls.can_stop)


if __name__ == '__main__':
    unittest.main()
