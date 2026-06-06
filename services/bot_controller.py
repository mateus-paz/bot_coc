"""Controller thread-safe para start, pause, resume e stop do bot."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable


class BotStopRequested(RuntimeError):
    """Sinaliza encerramento solicitado pelo controller."""


@dataclass(frozen=True)
class BotStatus:
    """Snapshot imutavel do estado atual do bot."""

    state: str
    is_running: bool
    is_paused: bool
    stop_requested: bool
    last_error: str | None


class BotController:
    """Coordena o worker de background e expõe operações de controle."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._state = 'idle'
        self._paused = False
        self._stop_requested = False
        self._last_error: str | None = None

    def start(self, target: Callable[[], None]) -> bool:
        """Inicia um novo worker ou retoma um worker pausado."""
        with self._condition:
            if self._thread and self._thread.is_alive():
                if self._paused:
                    self._paused = False
                    self._state = 'running'
                    self._condition.notify_all()
                    return True
                return False

            self._paused = False
            self._stop_requested = False
            self._last_error = None
            self._state = 'running'
            self._thread = threading.Thread(target=self._run_target, args=(target,), daemon=True, name='playgames-bot-worker')
            self._thread.start()
            return True

    def _run_target(self, target: Callable[[], None]) -> None:
        """Executa o worker e atualiza o estado final."""
        try:
            target()
        except BotStopRequested:
            self.mark_stopped()
        except Exception as exc:
            self.mark_error(exc)
        else:
            self.mark_stopped()

    def pause(self) -> bool:
        """Pede pausa lógica no próximo checkpoint seguro."""
        with self._condition:
            if not (self._thread and self._thread.is_alive()) or self._paused:
                return False
            self._paused = True
            self._state = 'paused'
            self._condition.notify_all()
            return True

    def stop(self) -> bool:
        """Solicita parada e libera qualquer espera de pausa."""
        with self._condition:
            if self._stop_requested:
                return False
            self._stop_requested = True
            self._paused = False
            self._state = 'stopping'
            self._condition.notify_all()
            return True

    def wait_if_paused(self) -> None:
        """Bloqueia enquanto pausado e falha se houver parada solicitada."""
        with self._condition:
            while self._paused and not self._stop_requested:
                self._condition.wait(timeout=0.25)
            if self._stop_requested:
                raise BotStopRequested()

    def raise_if_stop_requested(self) -> None:
        """Falha imediatamente caso exista uma solicitação de stop pendente."""
        with self._condition:
            if self._stop_requested:
                raise BotStopRequested()

    def checkpoint(self) -> None:
        """Checkpoint padrão consultado pelo fluxo do bot."""
        self.wait_if_paused()
        self.raise_if_stop_requested()

    def mark_running(self) -> None:
        """Força o estado running quando o worker realmente retomou."""
        with self._condition:
            if not self._stop_requested:
                self._state = 'running'

    def mark_stopped(self) -> None:
        """Registra encerramento limpo."""
        with self._condition:
            self._paused = False
            self._stop_requested = False
            self._state = 'stopped'
            self._condition.notify_all()

    def mark_error(self, exc: Exception) -> None:
        """Registra estado de erro."""
        with self._condition:
            self._paused = False
            self._stop_requested = False
            self._last_error = str(exc)
            self._state = 'error'
            self._condition.notify_all()

    def snapshot(self) -> BotStatus:
        """Retorna um snapshot thread-safe do estado atual."""
        with self._condition:
            is_alive = bool(self._thread and self._thread.is_alive())
            return BotStatus(
                state=self._state,
                is_running=is_alive and self._state in {'running', 'paused', 'stopping'},
                is_paused=self._paused,
                stop_requested=self._stop_requested,
                last_error=self._last_error,
            )

    def join(self, timeout: float | None = None) -> None:
        """Aguarda o worker encerrar, quando existir."""
        thread = self._thread
        if thread:
            thread.join(timeout=timeout)
