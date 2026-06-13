"""Comportamentos de OCR e tomada de decisao para escolha de alvos."""

from __future__ import annotations

import logging
import time

from services.bot_shared import ErroBot
from utils.debug_utils import salvar_debug
from utils.geometry_utils import extrair_roi, resolver_roi
from utils.ocr_service import ler_numeros_por_ocr


class BotTargetingMixin:
    """Reune leitura de recursos, leitura de saque e filtros de aprovacao de alvo."""

    def _ocr_config_saque(self) -> dict:
        """Retorna a configuracao de OCR especifica para leitura de saque em batalha."""
        vision_cfg = self.cfg.get('vision', {})
        attack_loot_cfg = vision_cfg.get('attack_loot_ocr', {})
        if isinstance(attack_loot_cfg, dict) and attack_loot_cfg:
            return attack_loot_cfg
        return vision_cfg.get('pytesseract', {})

    def ler_valores_recursos(self, *, salvar_imagem_debug: bool = True) -> list[int]:
        """Le os valores da ROI principal de recurso para o filtro classico."""
        _, tela = self.capturar_tela()
        roi = extrair_roi(tela, self.cfg['vision']['resource_roi'])
        if salvar_imagem_debug and self.salvar_imagens_ocr():
            salvar_debug(self.diretorio_debug, 'resource_roi', roi)
        if not bool(self.cfg['vision']['ocr_enabled']):
            logging.info('OCR desativado.')
            return []
        return ler_numeros_por_ocr(
            roi,
            engine=self.ocr_engine,
            ocr_config=self.cfg.get('vision', {}).get('pytesseract', {}),
        )

    def ler_saque_ataque(self, *, salvar_imagens_debug: bool = True) -> dict[str, int | None]:
        """Le o saque da tela de batalha usando as ROIs configuradas."""
        if not bool(self.cfg['vision']['ocr_enabled']):
            logging.info('OCR desativado.')
            return {'gold': None, 'elixir': None, 'dark_elixir': None}

        rois_saque = self.cfg['vision'].get('attack_loot_rois', {})
        if not rois_saque:
            logging.info('vision.attack_loot_rois nao configurado; leitura de saque ignorada.')
            return {'gold': None, 'elixir': None, 'dark_elixir': None}

        _, tela = self.capturar_tela()
        saque: dict[str, int | None] = {}
        for nome_recurso in ('gold', 'elixir', 'dark_elixir'):
            cfg_roi = rois_saque.get(nome_recurso)
            if not cfg_roi:
                saque[nome_recurso] = None
                continue
            altura_tela, largura_tela = tela.shape[:2]
            x, y, w, h = resolver_roi((largura_tela, altura_tela), cfg_roi)
            roi = extrair_roi(tela, cfg_roi)
            if salvar_imagens_debug and self.salvar_imagens_ocr():
                salvar_debug(self.diretorio_debug, f'attack_loot_{nome_recurso}', roi)
            valores = ler_numeros_por_ocr(
                roi,
                engine=self.ocr_engine,
                ocr_config=self._ocr_config_saque(),
            )
            saque[nome_recurso] = valores[0] if valores else None
            logging.info(
                'Loot OCR %s roi=(x=%s,y=%s,w=%s,h=%s) valor=%s valores=%s',
                nome_recurso,
                x,
                y,
                w,
                h,
                saque[nome_recurso],
                valores,
            )

        logging.info(
            'Saque detectado ouro=%s elixir=%s elixir_negro=%s',
            saque.get('gold'),
            saque.get('elixir'),
            saque.get('dark_elixir'),
        )
        return saque

    def saque_ataque_pronto(self, saque: dict[str, int | None]) -> bool:
        """Indica se a leitura de saque ja retornou algum valor confiavel."""
        return any(valor is not None for valor in saque.values())

    def aguardar_saque_ataque_pronto(self) -> dict[str, int | None]:
        """Aguarda a tela estabilizar ate o OCR de saque retornar algum valor."""
        fluxo = self.cfg.get('flow', {})
        timeout = float(fluxo.get('attack_loot_ready_timeout_seconds', fluxo.get('battle_screen_delay_seconds', 5)))
        inicio = time.time()
        while time.time() - inicio < timeout:
            self.checkpoint_controle()
            saque = self.ler_saque_ataque(salvar_imagens_debug=False)
            if self.saque_ataque_pronto(saque):
                return saque
            self.dormir_interrompivel(self.poll)
        return self.ler_saque_ataque(salvar_imagens_debug=self.salvar_imagens_ocr())

    def alvo_atual_aprovado(self) -> bool:
        """Avalia se o alvo atual passa no threshold minimo de recursos."""
        valores = self.ler_valores_recursos()
        limite = int(self.cfg['vision']['resource_threshold'])
        aprovado = any(valor >= limite for valor in valores)
        logging.info('Criterio valores=%s threshold=%s aprovado=%s', valores, limite, aprovado)
        return aprovado

    def filtro_saque_ativo(self) -> bool:
        """Indica se o filtro por saque de batalha esta ativo no fluxo."""
        minimos = self.cfg.get('flow', {}).get('attack_loot_minimums', {})
        return isinstance(minimos, dict) and bool(minimos)

    def saque_aprovado(self, saque: dict[str, int | None]) -> bool:
        """Aplica os minimos configurados para ouro, elixir e elixir negro."""
        minimos = self.cfg.get('flow', {}).get('attack_loot_minimums', {})
        if not isinstance(minimos, dict) or not minimos:
            return True

        fluxo = self.cfg.get('flow', {})
        aprovado = True
        avaliacoes: list[str] = []
        gold_min = minimos.get('gold')
        elixir_min = minimos.get('elixir')
        if gold_min is not None and elixir_min is not None:
            gold_atual = saque.get('gold')
            elixir_atual = saque.get('elixir')
            total_minimo = int(fluxo.get('attack_loot_total_minimum', 1_000_000))
            total_atual = (
                int(gold_atual) + int(elixir_atual)
                if gold_atual is not None and elixir_atual is not None
                else None
            )
            gold_ok = gold_atual is not None and int(gold_atual) >= int(gold_min)
            elixir_ok = elixir_atual is not None and int(elixir_atual) >= int(elixir_min)
            total_ok = total_atual is not None and total_atual >= total_minimo
            combinado_ok = total_ok and (gold_ok or elixir_ok)
            avaliacoes.append(
                'gold_elixir='
                f'gold:{gold_atual}>={int(gold_min)}:{gold_ok},'
                f'elixir:{elixir_atual}>={int(elixir_min)}:{elixir_ok},'
                f'total:{total_atual}>={total_minimo}:{total_ok},'
                f'combinado:{combinado_ok}'
            )
            if not combinado_ok:
                aprovado = False

        for nome_recurso, valor_minimo in minimos.items():
            if nome_recurso in {'gold', 'elixir'} and gold_min is not None and elixir_min is not None:
                continue
            valor_atual = saque.get(nome_recurso)
            minimo_int = int(valor_minimo)
            recurso_ok = valor_atual is not None and int(valor_atual) >= minimo_int
            avaliacoes.append(f'{nome_recurso}={valor_atual}>={minimo_int}:{recurso_ok}')
            if not recurso_ok:
                aprovado = False
        logging.info('Criterio saque %s aprovado=%s', ', '.join(avaliacoes), aprovado)
        return aprovado

    def encontrar_alvo_por_saque(self) -> dict[str, int | None]:
        """Avanca entre bases ate encontrar uma que satisfaca o filtro por saque."""
        max_tentativas = int(self.cfg['runtime']['max_next_attempts_per_cycle'])
        fluxo = self.cfg.get('flow', {})
        atraso_proxima_base = float(fluxo.get('next_base_delay_seconds', fluxo.get('battle_screen_delay_seconds', 5)))
        for tentativa in range(1, max_tentativas + 1):
            self.checkpoint_controle()
            logging.info('Avaliando saque da base %s/%s', tentativa, max_tentativas)
            saque = self.aguardar_saque_ataque_pronto()
            if self.saque_aprovado(saque):
                logging.info('Base aprovada pelo filtro de saque.')
                return saque
            logging.info('Base rejeitada pelo filtro de saque. Indo para a proxima.')
            self.clicar_asset('next_button', required=True, timeout=10.0)
            logging.info('Aguardando render da proxima base por %.2fs', atraso_proxima_base)
            self.dormir_interrompivel(atraso_proxima_base)
        raise ErroBot('Limite de proximas bases atingido sem encontrar saque aprovado.')

    def encontrar_alvo(self) -> None:
        """Avanca entre alvos ate encontrar um que passe pelo filtro principal."""
        max_tentativas = int(self.cfg['runtime']['max_next_attempts_per_cycle'])
        for tentativa in range(1, max_tentativas + 1):
            self.checkpoint_controle()
            logging.info('Avaliando alvo %s/%s', tentativa, max_tentativas)
            if self.alvo_atual_aprovado():
                logging.info('Alvo aprovado.')
                return
            logging.info('Alvo rejeitado. Proximo.')
            self.clicar_asset('next_button', required=True, timeout=10.0)
        raise ErroBot('Limite de proximos atingido sem encontrar alvo aprovado.')
