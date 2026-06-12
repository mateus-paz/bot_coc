"""Comportamentos relacionados a janela alvo, assets visuais e cliques de navegacao."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

from clients.window_client import JanelaRetangulo, capturar_janela_bgr, encontrar_janela, obter_janela_ativa, titulo_janela_corresponde
from services.bot_shared import Correspondencia, ErroBot
from utils.debug_utils import salvar_debug
from utils.geometry_utils import resolver_roi
from utils.input_actions import clicar_relativo, rolar_relativo
from utils.template_matching import encontrar_template


class BotWindowAssetsMixin:
    """Reune operacoes de janela, busca de assets e interacoes baseadas em template."""

    def obter_janela(self) -> JanelaRetangulo:
        """Localiza a janela alvo e a ativa quando permitido pela configuracao."""
        self.checkpoint_controle()
        deve_ativar = bool(self.cfg['window']['activate_before_click']) and not self.require_target_focus
        return encontrar_janela(self.window_title, ativar=deve_ativar, modo_comparacao=self.window_title_match_mode)

    def janela_alvo_esta_ativa(self) -> bool:
        """Indica se a janela atualmente focada corresponde ao alvo configurado."""
        ativa = obter_janela_ativa()
        if ativa is None:
            return False
        return titulo_janela_corresponde(ativa.titulo, self.window_title, self.window_title_match_mode)

    def aguardar_janela_alvo_ativa(self) -> None:
        """Bloqueia a execucao ate a janela alvo estar em foco, se exigido."""
        self.checkpoint_controle()
        if not self.require_target_focus:
            return
        while not self.janela_alvo_esta_ativa():
            self.checkpoint_controle()
            ativa = obter_janela_ativa()
            titulo_ativo = ativa.titulo if ativa else '<sem janela ativa>'
            logging.info(
                'Janela ativa atual=%r nao corresponde ao alvo=%r. Bot em espera por %.1fs.',
                titulo_ativo,
                self.window_title,
                self.focus_check_interval,
            )
            self.dormir_interrompivel(self.focus_check_interval)
        self.marcar_em_execucao()

    def capturar_tela(self) -> tuple[JanelaRetangulo, np.ndarray]:
        """Captura um screenshot BGR da janela alvo."""
        self.checkpoint_controle()
        self.aguardar_janela_alvo_ativa()
        retangulo = self.obter_janela()
        return retangulo, capturar_janela_bgr(retangulo)

    def normalizar_zoom_batalha(self) -> None:
        """Leva a vila ao limite de zoom-out antes de analisar ou clicar."""
        zoom_cfg = self.cfg.get('flow', {}).get('battle_zoom_out', {})
        if not bool(zoom_cfg.get('enabled', True)):
            return
        self.checkpoint_controle()
        retangulo = self.obter_janela()
        clicks = -abs(int(zoom_cfg.get('scroll_clicks', 12)))
        rolar_relativo(
            retangulo,
            clicks=clicks,
            dry_run=self.dry_run,
            duration=self.duration,
        )
        self.dormir_interrompivel(float(zoom_cfg.get('settle_seconds', 0.8)))

    def resolver_caminho_asset(self, chave: str) -> Path:
        """Resolve o caminho absoluto de um asset a partir da chave do config."""
        caminho = Path(self.cfg['assets'][chave])
        if not caminho.is_absolute():
            caminho = self.diretorio_base / caminho
        return caminho

    def obter_confianca_asset(self, chave: str) -> float:
        """Retorna a confianca configurada para um asset especifico."""
        return float(self.confidence_by_asset.get(chave, self.confidence))

    def obter_limites_regiao_busca(self, chave: str, tela: np.ndarray) -> tuple[int, int, int, int] | None:
        """Resolve a regiao de busca restrita para um asset, quando configurada."""
        regiao = self.search_regions.get(chave)
        if not regiao:
            return None
        altura_tela, largura_tela = tela.shape[:2]
        return resolver_roi((largura_tela, altura_tela), regiao)

    def encontrar_asset_na_tela(self, chave: str, tela: np.ndarray) -> Correspondencia | None:
        """Busca um asset na tela inteira ou em ROI restrita."""
        confianca = self.obter_confianca_asset(chave)
        limites = self.obter_limites_regiao_busca(chave, tela)
        if not limites:
            return encontrar_template(tela, self.resolver_caminho_asset(chave), confianca)

        x, y, w, h = limites
        recorte = tela[y:y + h, x:x + w]
        correspondencia = encontrar_template(recorte, self.resolver_caminho_asset(chave), confianca)
        if not correspondencia:
            return None
        # Ajusta o match local da ROI para o sistema de coordenadas da tela da janela.
        return Correspondencia(
            x=correspondencia.x + x,
            y=correspondencia.y + y,
            w=correspondencia.w,
            h=correspondencia.h,
            confidence=correspondencia.confidence,
        )

    def validar_assets(self) -> None:
        """Valida se todos os assets exigidos pelo fluxo atual existem e podem ser usados."""
        assets = self.cfg.get('assets', {})
        if not isinstance(assets, dict):
            raise ErroBot('assets deve ser um mapa de nome para caminho.')
        if self.filtro_saque_ativo() and not bool(self.cfg.get('vision', {}).get('ocr_enabled', False)):
            raise ErroBot('flow.attack_loot_minimums exige vision.ocr_enabled=true.')

        chaves_obrigatorias = set(self.pre_search_steps)
        chaves_obrigatorias.update(self.optional_pre_search_steps)
        cfg_battle_bar = self.cfg.get('battle_bar', {})
        if isinstance(cfg_battle_bar, dict) and bool(cfg_battle_bar.get('enabled', False)):
            self._validar_assets_battle_bar(cfg_battle_bar, assets)
        if not self.preliminary_only:
            fluxo = self.cfg.get('flow', {})
            if fluxo.get('target_mode', 'resource_filter') != 'direct_attack':
                chaves_obrigatorias.add('next_button')
                if fluxo.get('use_confirm_action_button', True):
                    chaves_obrigatorias.add('confirm_action_button')
            elif self.filtro_saque_ativo():
                chaves_obrigatorias.add('next_button')
            if fluxo.get('use_end_action_button', False):
                chaves_obrigatorias.add('end_action_button')
            chaves_obrigatorias.update(self.battle_finished_assets)
            chaves_obrigatorias.update(self.return_steps)

        for chave in sorted(chaves_obrigatorias):
            if chave not in assets:
                esperado = self.diretorio_base / 'assets' / f'{chave}.png'
                raise ErroBot(f"Asset '{chave}' citado no config.yaml mas sem entrada em assets. Caminho esperado: {esperado}")
            caminho = self.resolver_caminho_asset(chave)
            if not caminho.exists():
                raise ErroBot(f"Asset '{chave}' citado no config.yaml nao encontrado. Caminho esperado: {caminho}")

    def _validar_assets_battle_bar(self, cfg_battle_bar: dict, assets_fluxo: dict[str, str]) -> None:
        """Valida assets opcionais referenciados pelo subsistema battle_bar."""
        _ = assets_fluxo
        position_detector = cfg_battle_bar.get('position_detector', {})
        if position_detector.get('mode') == 'template_anchored':
            caminho_anchor = self.diretorio_base / str(position_detector['anchor_asset'])
            if not caminho_anchor.exists():
                raise ErroBot(f"battle_bar.position_detector.anchor_asset nao encontrado: {caminho_anchor}")

        content_detector = cfg_battle_bar.get('content_detector', {})
        empty_slot_asset = content_detector.get('empty_slot_asset')
        if empty_slot_asset:
            caminho_empty = self.diretorio_base / str(empty_slot_asset)
            if not caminho_empty.exists():
                raise ErroBot(f"battle_bar.content_detector.empty_slot_asset nao encontrado: {caminho_empty}")

        type_classifier = cfg_battle_bar.get('type_classifier', {})
        for caminhos in type_classifier.get('type_templates', {}).values():
            for caminho_relativo in caminhos:
                caminho_template = self.diretorio_base / str(caminho_relativo)
                if not caminho_template.exists():
                    raise ErroBot(f"battle_bar.type_classifier.type_templates nao encontrado: {caminho_template}")

    def aguardar_asset(self, chave: str, timeout: float) -> tuple[JanelaRetangulo, np.ndarray, Correspondencia] | None:
        """Espera um asset aparecer na tela ate o timeout configurado."""
        inicio = time.time()
        while time.time() - inicio < timeout:
            self.checkpoint_controle()
            retangulo, tela = self.capturar_tela()
            correspondencia = self.encontrar_asset_na_tela(chave, tela)
            if correspondencia:
                return retangulo, tela, correspondencia
            self.dormir_interrompivel(self.poll)
        return None

    def salvar_debug_asset_ausente(self, chave: str) -> None:
        """Salva evidencias de debug quando um asset esperado nao e encontrado."""
        try:
            _, tela = self.capturar_tela()
        except Exception as exc:
            logging.warning('Nao consegui salvar screenshot de debug para asset=%s: %s', chave, exc)
            return
        saida = salvar_debug(self.diretorio_debug, f'missing_{chave}', tela)
        logging.info('Screenshot salva porque o botao nao foi encontrado: %s', saida)

        limites = self.obter_limites_regiao_busca(chave, tela)
        if limites:
            x, y, w, h = limites
            regiao_saida = salvar_debug(self.diretorio_debug, f'missing_{chave}_search_region', tela[y:y + h, x:x + w])
            logging.info('Regiao de busca salva para asset=%s: %s', chave, regiao_saida)
            return

        regiao_saida = salvar_debug(self.diretorio_debug, f'missing_{chave}_search_region', tela)
        logging.info('Asset=%s sem template_search_region; regiao de busca corresponde a tela inteira: %s', chave, regiao_saida)

    def aguardar_asset_obrigatorio(self, chave: str, timeout: float) -> tuple[JanelaRetangulo, np.ndarray, Correspondencia]:
        """Espera um asset obrigatorio ou levanta erro com artefatos de debug."""
        encontrado = self.aguardar_asset(chave, timeout)
        if encontrado:
            return encontrado
        self.salvar_debug_asset_ausente(chave)
        raise ErroBot(f'Botao nao encontrado: {chave}')

    def aguardar_qualquer_asset(self, chaves: list[str], timeout: float) -> str | None:
        """Espera qualquer asset dentre uma lista e retorna a chave encontrada."""
        inicio = time.time()
        while time.time() - inicio < timeout:
            self.checkpoint_controle()
            _, tela = self.capturar_tela()
            for chave in chaves:
                correspondencia = self.encontrar_asset_na_tela(chave, tela)
                if correspondencia:
                    logging.info('Asset detectado=%s confianca=%.3f', chave, correspondencia.confidence)
                    return chave
            self.dormir_interrompivel(self.poll)
        return None

    def clicar_asset(
        self,
        chave: str,
        *,
        required: bool = True,
        timeout: float = 8.0,
        after_delay: float | None = None,
    ) -> bool:
        """Clica em um asset visual ou em seu fallback configurado."""
        encontrado = self.aguardar_asset(chave, timeout)
        if not encontrado:
            fallback = self.click_fallbacks.get(chave)
            if fallback:
                retangulo = self.obter_janela()
                if 'x_ratio' in fallback:
                    x = int(float(fallback['x_ratio']) * retangulo.largura)
                    y = int(float(fallback['y_ratio']) * retangulo.altura)
                else:
                    x = int(fallback['x'])
                    y = int(fallback['y'])
                logging.info('Asset=%s nao encontrado; usando fallback relativo=(%s,%s)', chave, x, y)
                clicar_relativo(retangulo, x, y, dry_run=self.dry_run, duration=self.duration)
                self.dormir_interrompivel(self.after_button if after_delay is None else after_delay)
                return True
            self.salvar_debug_asset_ausente(chave)
            mensagem = f'Botao nao encontrado: {chave}'
            if required:
                raise ErroBot(mensagem)
            logging.info(mensagem)
            return False
        retangulo, _, correspondencia = encontrado
        centro_x, centro_y = correspondencia.centro
        logging.info('Clicando asset=%s centro=(%s,%s) confianca=%.3f', chave, centro_x, centro_y, correspondencia.confidence)
        clicar_relativo(retangulo, centro_x, centro_y, dry_run=self.dry_run, duration=self.duration)
        self.dormir_interrompivel(self.after_button if after_delay is None else after_delay)
        return True
