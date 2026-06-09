"""Resolucao de caminhos mutaveis em AppData/Roaming."""

from __future__ import annotations

import os
from pathlib import Path


APP_DIR_NAME = 'PlayGamesBot'


def get_roaming_appdata_dir() -> Path:
    """Retorna a pasta base de dados do usuario para a aplicacao."""
    appdata = os.environ.get('APPDATA')
    if appdata:
        return Path(appdata) / APP_DIR_NAME
    return Path.home() / 'AppData' / 'Roaming' / APP_DIR_NAME


def ensure_app_dirs() -> dict[str, Path]:
    """Cria a arvore minima de dados locais."""
    base_dir = get_roaming_appdata_dir()
    logs_dir = base_dir / 'logs'
    debug_dir = base_dir / 'debug'
    cache_dir = base_dir / 'cache'
    for path in (base_dir, logs_dir, debug_dir, cache_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        'base_dir': base_dir,
        'logs_dir': logs_dir,
        'debug_dir': debug_dir,
        'cache_dir': cache_dir,
        'settings_path': base_dir / 'settings.json',
    }

