"""Servicos de setup e diagnostico consumidos pela UI."""

from __future__ import annotations

import cv2
import numpy as np

from application.dto import PreviewResultDTO, SlotInfoDTO, WindowInfoDTO
from battle_bar.domain import SlotPosition
from core.vision.pipeline import extract_ratio_region
from domain.settings.entities import UserSettings


class SetupService:
    """Orquestra localizacao de janela, previews e persistencia."""

    def __init__(self, *, window_locator, screen_capture, battle_bar_analyzer, settings_repository) -> None:
        self.window_locator = window_locator
        self.screen_capture = screen_capture
        self.battle_bar_analyzer = battle_bar_analyzer
        self.settings_repository = settings_repository

    def load_settings(self) -> UserSettings:
        """Carrega configuracao salva ou retorna defaults."""
        return self.settings_repository.load() or UserSettings()

    def save_settings(self, settings: UserSettings) -> None:
        """Persistencia da configuracao local."""
        self.settings_repository.save(settings)

    def detect_window(self, settings: UserSettings) -> WindowInfoDTO:
        """Localiza a janela alvo conforme configuracao atual."""
        window = self.window_locator.find_target_window(settings.window_title, settings.window_match_mode, settings.activate_window)
        bounds = window.bounds
        return WindowInfoDTO(
            title=window.title,
            left=bounds.left,
            top=bounds.top,
            width=bounds.width,
            height=bounds.height,
        )

    def capture_bottom_region_preview(self, settings: UserSettings) -> PreviewResultDTO:
        """Gera preview da regiao inferior da janela alvo."""
        window = self.window_locator.find_target_window(settings.window_title, settings.window_match_mode, settings.activate_window)
        frame = self.screen_capture.capture_window(window)
        region = extract_ratio_region(frame, settings.bottom_region)
        return PreviewResultDTO(
            message='Captura da regiao inferior concluida.',
            image_bgr=region,
            metadata={'shape': region.shape[:2]},
        )

    def detect_slots_preview(self, settings: UserSettings) -> tuple[PreviewResultDTO, list[SlotInfoDTO]]:
        """Executa deteccao dos slots e devolve overlay + lista resumida."""
        window = self.window_locator.find_target_window(settings.window_title, settings.window_match_mode, settings.activate_window)
        frame = self.screen_capture.capture_window(window)
        snapshot = self.battle_bar_analyzer.analyze(frame, settings)
        overlay = self._draw_slots_overlay(frame, snapshot)
        slots = [
            SlotInfoDTO(
                index=slot.index,
                lane=slot.lane_hint.value,
                content_type=None if slot.content is None else slot.content.type.value,
                state=None if slot.content is None else slot.content.state.availability.value,
                is_empty=slot.content is None,
            )
            for slot in snapshot.slots
        ]
        confidence = float(snapshot.diagnostics.get('position_confidence', 0.0))
        used_fallback = bool(snapshot.diagnostics.get('used_position_fallback', False))
        strategy = str(snapshot.diagnostics.get('position_strategy', 'unknown'))
        return (
            PreviewResultDTO(
                message=(
                    'Deteccao de slots concluida: '
                    f'{snapshot.diagnostics.get("non_empty_slots", 0)} slots com conteudo, '
                    f'confidence={confidence:.2f}, strategy={strategy}, fallback={used_fallback}.'
                ),
                image_bgr=overlay,
                metadata=snapshot.diagnostics,
            ),
            slots,
        )

    def _draw_slots_overlay(self, frame: np.ndarray, snapshot) -> np.ndarray:
        overlay = frame.copy()
        bar_bbox = snapshot.bar_bbox
        bar_color = (0, 180, 255) if not snapshot.diagnostics.get('used_position_fallback', False) else (0, 120, 255)
        cv2.rectangle(
            overlay,
            (bar_bbox.x, bar_bbox.y),
            (bar_bbox.x + bar_bbox.w, bar_bbox.y + bar_bbox.h),
            bar_color,
            2,
        )
        cv2.putText(
            overlay,
            (
                f"bar confidence={float(snapshot.diagnostics.get('position_confidence', 0.0)):.2f} "
                f"fallback={bool(snapshot.diagnostics.get('used_position_fallback', False))}"
            ),
            (bar_bbox.x, max(18, bar_bbox.y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            bar_color,
            1,
            cv2.LINE_AA,
        )
        for slot in snapshot.slots:
            bbox = slot.bbox
            color = (0, 200, 0) if slot.content is not None else (180, 180, 180)
            cv2.rectangle(overlay, (bbox.x, bbox.y), (bbox.x + bbox.w, bbox.y + bbox.h), color, 2)
            label = f'#{slot.index}'
            if slot.content is not None:
                label = f'{label}:{slot.content.type.value}:{slot.content.state.availability.value}'
            cv2.putText(
                overlay,
                label,
                (bbox.x, max(18, bbox.y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )
        return overlay
