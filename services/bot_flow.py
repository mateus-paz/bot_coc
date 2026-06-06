"""Fluxo de alto nivel de um ciclo completo do bot."""

from __future__ import annotations

import logging
import time

from services.bot_shared import ErroBot
from utils.debug_utils import salvar_debug


class BotFlowMixin:
    """Coordena o ciclo principal entre navegacao, busca, deploy e retorno."""

    def aguardar_fim_acao(self) -> None:
        """Aguarda o fim da batalha por timeout, botao ou assets de retorno."""
        self.checkpoint_controle()
        fluxo = self.cfg['flow']
        timeout = float(fluxo['action_timeout_seconds'])
        espera_minima = float(fluxo.get('post_deploy_min_seconds', 0))
        if espera_minima > 0:
            logging.info('Aguardando post_deploy_min_seconds=%s', espera_minima)
            self.dormir_interrompivel(espera_minima)
        if bool(fluxo.get('use_end_action_button', False)):
            self.clicar_asset('end_action_button', required=False, timeout=timeout)
            self.salvar_checkpoint('after_wait_action_end')
            return
        if self.battle_finished_assets:
            encontrado = self.aguardar_qualquer_asset(self.battle_finished_assets, timeout=timeout)
            if encontrado:
                logging.info('Fim do ataque detectado por asset=%s', encontrado)
                self.salvar_checkpoint('after_wait_action_end')
                return
            logging.info('Fim do ataque nao detectado por asset; seguindo apos timeout=%s', timeout)
            self.salvar_checkpoint('after_wait_action_end')
            return
        logging.info('Aguardando action_timeout_seconds=%s', timeout)
        self.dormir_interrompivel(timeout)
        self.salvar_checkpoint('after_wait_action_end')

    def retornar_inicio(self) -> None:
        """Executa o retorno para a tela principal apos o termino do ataque."""
        self.checkpoint_controle()
        if self.return_steps:
            for chave_asset in self.return_steps:
                self.clicar_asset(chave_asset, required=False, timeout=20.0)
            self.salvar_checkpoint('after_return_home')
            return
        if bool(self.cfg['flow'].get('use_return_button', False)):
            self.clicar_asset('return_button', required=False, timeout=20.0)
            self.salvar_checkpoint('after_return_home')

    def executar_um_ciclo(self) -> None:
        """Executa um ciclo completo do fluxo principal do bot."""
        self.checkpoint_controle()
        fluxo = self.cfg['flow']
        timeouts = fluxo.get('pre_search_step_timeouts', {})
        delays = fluxo.get('pre_search_step_after_delays', {})
        for chave_asset in self.pre_search_steps:
            required = chave_asset not in self.optional_pre_search_steps
            timeout = float(timeouts.get(chave_asset, 12.0))
            after_delay = float(delays.get(chave_asset, self.after_button))
            self.clicar_asset(chave_asset, required=required, timeout=timeout, after_delay=after_delay)
        saque: dict[str, int | None] | None = None
        if fluxo.get('target_mode', 'resource_filter') == 'direct_attack':
            logging.info('Modo direct_attack: entrando na vila para validar saque e atacar se aprovado.')
            self.dormir_interrompivel(float(fluxo.get('battle_screen_delay_seconds', 5)))
            if self.filtro_saque_ativo():
                saque = self.encontrar_alvo_por_saque()
        else:
            self.aguardar_asset_obrigatorio('next_button', timeout=float(fluxo['search_result_timeout_seconds']))
            self.encontrar_alvo()
            if bool(fluxo['use_confirm_action_button']):
                self.clicar_asset('confirm_action_button', required=True, timeout=12.0)
        if saque is None:
            saque = self.ler_saque_ataque()
        self.executar_deploy()
        self.aguardar_fim_acao()
        self.retornar_inicio()

    def executar_preliminar(self) -> None:
        """Executa apenas os passos preliminares de navegacao e encerra."""
        self.checkpoint_controle()
        logging.info('===== Teste preliminar: pre_search_steps =====')
        for chave_asset in self.pre_search_steps:
            self.clicar_asset(chave_asset, required=True, timeout=12.0)
        logging.info('Teste preliminar concluido.')

    def run(self) -> None:
        """Mantem o bot em execucao continua ate parar por config ou erro."""
        self.checkpoint_controle()
        if self.deploy_now:
            logging.info('===== Teste de deploy na tela atual =====')
            self.executar_deploy()
            return

        if self.preliminary_only:
            self.executar_preliminar()
            return

        parar_apos = int(self.cfg['runtime']['stop_after_cycles'])
        ciclos = 0
        while True:
            self.checkpoint_controle()
            self.aguardar_janela_alvo_ativa()
            ciclos += 1
            logging.info('===== Ciclo %s =====', ciclos)
            try:
                self.executar_um_ciclo()
            except ErroBot:
                salvar_debug(self.diretorio_debug, 'error_screen', self.capturar_tela()[1])
                raise
            if parar_apos and ciclos >= parar_apos:
                logging.info('stop_after_cycles atingido.')
                return
            self.dormir_interrompivel(self.poll)
