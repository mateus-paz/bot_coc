"""Composicao principal do bot e inicializacao do estado compartilhado."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from config import resolver_diretorio_aplicacao, resolver_diretorio_bundle
from services.bot_controller import BotController
from services.bot_deployment import BotDeploymentMixin
from services.bot_flow import BotFlowMixin
from services.bot_shared import ErroBot, listar_passos_assets, listar_passos_pre_busca
from services.bot_targeting import BotTargetingMixin
from services.bot_window_assets import BotWindowAssetsMixin
from utils.debug_utils import configurar_logging

if TYPE_CHECKING:
    from battle_bar import DefaultActionPlanner, DefaultBattleBarAnalyzer


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
        battle_calibration: bool = False,
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
        self.battle_calibration = battle_calibration
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
        self.battle_bar_analyzer = self._construir_battle_bar_analyzer()
        self.battle_bar_planner = self._construir_battle_bar_planner()
        self.validar_assets()
        logging.info('Perfil CV ativo: %s', self.cfg.get('runtime', {}).get('cv_profile', 'default'))
        logging.info('Dry-run: %s', self.dry_run)
        logging.info('Debug imagens: %s', self.modo_debug_imagens)

    def _construir_battle_bar_analyzer(self):
        """Cria o analisador da barra quando a feature estiver configurada."""
        cfg_battle_bar = self.cfg.get('battle_bar')
        if not isinstance(cfg_battle_bar, dict) or not bool(cfg_battle_bar.get('enabled', False)):
            return None
        from battle_bar import DefaultBattleBarAnalyzer

        return DefaultBattleBarAnalyzer(
            cfg_battle_bar,
            asset_base_dir=self.diretorio_base,
            template_confidence=self.confidence,
        )

    def _construir_battle_bar_planner(self):
        """Cria o planejador de acoes para os slots, quando habilitado."""
        cfg_battle_bar = self.cfg.get('battle_bar')
        if not isinstance(cfg_battle_bar, dict) or not bool(cfg_battle_bar.get('enabled', False)):
            return None
        from battle_bar import DefaultActionPlanner

        return DefaultActionPlanner(cfg_battle_bar.get('planner', {}))

    def analyze_battle_bar(self):
        """Analisa a barra de batalha na tela atual e devolve um snapshot."""
        if self.battle_bar_analyzer is None:
            raise ErroBot('battle_bar.enabled=false ou configuracao ausente.')
        _, tela = self.capturar_tela()
        return self.battle_bar_analyzer.analyze(
            tela,
            frame_id=f'battle_bar_{int(time.time() * 1000)}',
            timestamp=time.time(),
        )

    def plan_battle_bar_actions(self):
        """Gera a lista de slots acionaveis a partir do snapshot atual."""
        if self.battle_bar_planner is None:
            raise ErroBot('battle_bar.enabled=false ou configuracao ausente.')
        snapshot = self.analyze_battle_bar()
        return self.battle_bar_planner.plan(snapshot)

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
