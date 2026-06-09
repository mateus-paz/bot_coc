"""Repositorio JSON para configuracoes do usuario."""

from __future__ import annotations

import json
from pathlib import Path

from domain.settings.entities import UserSettings
from domain.settings.validation import validar_user_settings
from infrastructure.persistence.appdata_paths import ensure_app_dirs


class AppDataSettingsRepository:
    """Carrega e persiste settings em AppData/Roaming."""

    def __init__(self, settings_path: Path | None = None) -> None:
        if settings_path is None:
            self._paths = ensure_app_dirs()
            self.settings_path = self._paths['settings_path']
            return
        base_dir = settings_path.parent
        logs_dir = base_dir / 'logs'
        debug_dir = base_dir / 'debug'
        cache_dir = base_dir / 'cache'
        for path in (base_dir, logs_dir, debug_dir, cache_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._paths = {
            'base_dir': base_dir,
            'logs_dir': logs_dir,
            'debug_dir': debug_dir,
            'cache_dir': cache_dir,
            'settings_path': settings_path,
        }
        self.settings_path = settings_path

    @property
    def debug_dir(self) -> Path:
        """Retorna o diretorio de debug compartilhado pela aplicacao."""
        return self._paths['debug_dir']

    def load(self) -> UserSettings | None:
        """Lê o arquivo de configuracao, quando existir."""
        if not self.settings_path.exists():
            return None
        with self.settings_path.open('r', encoding='utf-8') as handle:
            data = json.load(handle)
        return UserSettings.from_dict(data)

    def save(self, settings: UserSettings) -> None:
        """Valida e persiste configuracao em JSON."""
        validar_user_settings(settings)
        with self.settings_path.open('w', encoding='utf-8') as handle:
            json.dump(settings.to_dict(), handle, ensure_ascii=True, indent=2)
