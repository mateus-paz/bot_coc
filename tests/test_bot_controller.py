"""Testes do ciclo de vida do worker controlado pela toolbar."""

from __future__ import annotations

import threading
import time
import unittest

from services.bot_controller import BotController


def _wait_for_state(controller: BotController, expected: str, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if controller.snapshot().state == expected:
            return
        time.sleep(0.01)
    raise AssertionError(
        f'Estado esperado={expected!r}, atual={controller.snapshot().state!r}'
    )


class BotControllerTest(unittest.TestCase):
    def test_pause_aborts_worker_instead_of_resuming_it(self) -> None:
        controller = BotController()
        started = threading.Event()

        def target() -> None:
            started.set()
            while True:
                controller.checkpoint()
                time.sleep(0.01)

        self.assertTrue(controller.start(target))
        self.assertTrue(started.wait(timeout=1.0))

        self.assertTrue(controller.pause())
        self.assertEqual('stopping', controller.snapshot().state)
        self.assertFalse(controller.start(target))
        _wait_for_state(controller, 'stopped')

    def test_start_after_interruption_creates_a_new_worker(self) -> None:
        controller = BotController()
        executions: list[int] = []
        first_started = threading.Event()
        second_started = threading.Event()

        def target() -> None:
            executions.append(len(executions) + 1)
            if len(executions) == 1:
                first_started.set()
                while True:
                    controller.checkpoint()
                    time.sleep(0.01)
            second_started.set()

        self.assertTrue(controller.start(target))
        self.assertTrue(first_started.wait(timeout=1.0))
        self.assertTrue(controller.pause())
        _wait_for_state(controller, 'stopped')

        self.assertTrue(controller.start(target))
        self.assertTrue(second_started.wait(timeout=1.0))
        _wait_for_state(controller, 'stopped')
        self.assertEqual([1, 2], executions)

    def test_stop_without_active_worker_is_ignored(self) -> None:
        controller = BotController()

        self.assertFalse(controller.stop())
        self.assertEqual('idle', controller.snapshot().state)


if __name__ == '__main__':
    unittest.main()
