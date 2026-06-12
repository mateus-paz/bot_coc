"""Construcao de configuracao de runtime para o bot legado."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from config import aplicar_perfil_cv, carregar_yaml, mesclar_dicts_profundamente, resolver_diretorio_bundle
from domain.settings.entities import UserSettings
from infrastructure.persistence.settings_repository import AppDataSettingsRepository


class RuntimeConfigBuilder:
    """Traduz UserSettings para o formato esperado pelo PlayGamesAppBot atual."""

    def __init__(self, *, repository: AppDataSettingsRepository, template_path: Path | None = None) -> None:
        self.repository = repository
        self.template_path = template_path or (resolver_diretorio_bundle() / 'config.yaml')

    def build(self, settings: UserSettings) -> tuple[dict[str, Any], Path]:
        base = deepcopy(carregar_yaml(self.template_path))
        cfg = mesclar_dicts_profundamente(
            base,
            {
                'window': {
                    'title_contains': settings.window_title,
                    'title_match_mode': settings.window_match_mode,
                    'activate_before_click': settings.activate_window,
                },
                'runtime': {
                    'dry_run': False,
                    'debug_dir': str(self.repository.debug_dir),
                },
            },
        )
        cfg = aplicar_perfil_cv(cfg, settings.cv_profile)
        return cfg, self.template_path
