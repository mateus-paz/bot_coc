"""Composicao principal do bot e inicializacao do estado compartilhado."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from config import resolver_diretorio_aplicacao, resolver_diretorio_bundle
from services.bot_controller import BotController
from services.bot_deployment import BotDeploymentMixin
from services.bot_flow import BotFlowMixin
from services.bot_shared import ErroBot, listar_passos_assets, listar_passos_pre_busca
from services.bot_targeting import BotTargetingMixin
from services.bot_window_assets import BotWindowAssetsMixin
from utils.debug_utils import configurar_logging


class PlayGamesAppBot(
    BotWindowAssetsMixin,
    BotTargetingMixin,
    BotDeploymentMixin,
    BotFlowMixin,
):
    """Bot principal que combina janela, OCR, deploy e fluxo de execucao."""

    def __init__(
        self,
        cfg: dict[str, Any],
        caminho_config: Path,
        *,
        preliminary_only: bool = False,
        deploy_now: bool = False,
        controller: BotController | None = None,
    ) -> None:
        """Inicializa configuracao, caminhos, timers e dependencias de execucao."""
        self.cfg = cfg
        self.caminho_config = caminho_config
        self.controller = controller
        self.diretorio_base = caminho_config.parent
        self.diretorio_saida = resolver_diretorio_aplicacao()
        self.preliminary_only = preliminary_only
        self.deploy_now = deploy_now
        base_debug_relativa = self.diretorio_saida if self.diretorio_base == resolver_diretorio_bundle() else self.diretorio_base
        diretorio_debug = Path(cfg['runtime']['debug_dir'])
        if not diretorio_debug.is_absolute():
            diretorio_debug = base_debug_relativa / diretorio_debug
        self.diretorio_debug = diretorio_debug
        configurar_logging(diretorio_debug)
        self.modo_debug_imagens = str(cfg['runtime'].get('debug_images', 'errors_only'))
        self.dry_run = bool(cfg['runtime']['dry_run'])
        self.poll = float(cfg['runtime']['poll_interval_seconds'])
        self.require_target_focus = bool(cfg['runtime'].get('require_target_focus', False))
        self.focus_check_interval = float(cfg['runtime'].get('focus_check_interval_seconds', 15.0))
        self.ocr_engine = str(cfg['vision'].get('ocr_engine', 'pytesseract'))
        self.window_title = str(cfg['window']['title_contains'])
        self.window_title_match_mode = str(cfg['window'].get('title_match_mode', 'contains'))
        self.confidence = float(cfg['vision']['template_confidence'])
        self.confidence_by_asset = cfg['vision'].get('template_confidence_by_asset', {})
        self.search_regions = cfg['vision'].get('template_search_regions', {})
        self.duration = float(cfg['clicking']['move_duration_seconds'])
        self.between = float(cfg['clicking']['delay_between_clicks_seconds'])
        self.after_button = float(cfg['clicking']['delay_after_button_seconds'])
        self.click_fallbacks = cfg['clicking'].get('asset_fallbacks', {})
        self.pre_search_steps = listar_passos_pre_busca(cfg)
        self.optional_pre_search_steps = set(listar_passos_assets(cfg, 'optional_pre_search_steps'))
        self.battle_finished_assets = listar_passos_assets(cfg, 'battle_finished_assets')
        self.return_steps = listar_passos_assets(cfg, 'return_steps')
        self.validar_assets()
        logging.info('Perfil CV ativo: %s', self.cfg.get('runtime', {}).get('cv_profile', 'default'))
        logging.info('Dry-run: %s', self.dry_run)
        logging.info('Debug imagens: %s', self.modo_debug_imagens)

    def checkpoint_controle(self) -> None:
        """Sincroniza o fluxo com o controller, quando presente."""
        if self.controller:
            self.controller.checkpoint()

    def marcar_em_execucao(self) -> None:
        """Atualiza o estado do controller para running."""
        if self.controller:
            self.controller.mark_running()

    def dormir_interrompivel(self, segundos: float, *, passo: float = 0.10) -> None:
        """Dorme em pequenos intervalos para respeitar pause/stop."""
        restante = max(0.0, float(segundos))
        while restante > 0:
            self.checkpoint_controle()
            intervalo = min(passo, restante)
            import time

            time.sleep(intervalo)
            restante -= intervalo

    def salvar_imagens_ocr(self) -> bool:
        """Indica se deve salvar imagens de OCR rotineiras."""
        return self.modo_debug_imagens in {'standard', 'verbose'}

    def salvar_imagens_deploy(self) -> bool:
        """Indica se deve salvar imagens rotineiras de deploy."""
        return self.modo_debug_imagens in {'standard', 'verbose'}

    def salvar_checkpoints(self) -> bool:
        """Indica se deve salvar checkpoints de telas do fluxo normal."""
        return self.modo_debug_imagens == 'verbose'


__all__ = ['ErroBot', 'PlayGamesAppBot']
