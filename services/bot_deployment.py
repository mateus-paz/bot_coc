"""Comportamentos responsaveis por selecionar tropas e executar deploy."""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Any

import cv2

from clients.window_client import JanelaRetangulo
from services.bot_shared import ErroBot
from utils.debug_utils import salvar_debug
from utils.deploy_utils import (
    desenhar_pontos,
    desenhar_rois,
    mascara_vermelha,
    ponto_proximo_da_mascara,
    pontos_candidatos_deploy,
    pontos_externos_borda_vermelha,
    priorizar_pontos_deploy,
)
from utils.geometry_utils import extrair_roi, gerar_pontos_aleatorios_em_faixa, resolver_ponto
from utils.input_actions import clicar_relativo, pressionar_tecla

if TYPE_CHECKING:
    from battle_bar.domain import BattleBarSnapshot, SlotPosition


class BotDeploymentMixin:
    """Concentra a logica de calculo de pontos e soltura de tropas."""

    def _coerce_slot_content_type(self, value: Any):
        """Converte strings de configuracao para o enum esperado."""
        from battle_bar.domain import SlotContentType

        try:
            return value if isinstance(value, SlotContentType) else SlotContentType(str(value))
        except ValueError as exc:
            raise ErroBot(f'deployment.scripted.slot_ref.content_type invalido: {value}') from exc

    def _coerce_slot_lane(self, value: Any):
        """Converte aliases legados de secao para o enum de lane."""
        from battle_bar.domain import SlotLaneHint

        if isinstance(value, SlotLaneHint):
            return value
        normalized = str(value).strip().lower()
        aliases = {
            'troops': SlotLaneHint.TROOP_SECTION,
            'troop': SlotLaneHint.TROOP_SECTION,
            'troop_section': SlotLaneHint.TROOP_SECTION,
            'heroes': SlotLaneHint.HERO_SECTION,
            'hero': SlotLaneHint.HERO_SECTION,
            'hero_section': SlotLaneHint.HERO_SECTION,
            'spells': SlotLaneHint.SPELL_SECTION,
            'spell': SlotLaneHint.SPELL_SECTION,
            'spell_section': SlotLaneHint.SPELL_SECTION,
            'siege': SlotLaneHint.SIEGE_SECTION,
            'siege_machine': SlotLaneHint.SIEGE_SECTION,
            'siege_section': SlotLaneHint.SIEGE_SECTION,
            'unknown': SlotLaneHint.UNKNOWN,
        }
        if normalized in aliases:
            return aliases[normalized]
        try:
            return SlotLaneHint(normalized)
        except ValueError as exc:
            raise ErroBot(f'deployment.scripted.slot_ref.lane invalido: {value}') from exc

    def _coerce_slot_availability(self, value: Any):
        """Converte strings de disponibilidade para enum."""
        from battle_bar.domain import AvailabilityState

        try:
            return value if isinstance(value, AvailabilityState) else AvailabilityState(str(value))
        except ValueError as exc:
            raise ErroBot(f'deployment.scripted.slot_ref.availability invalido: {value}') from exc

    def _slot_matches_ref(self, slot: 'SlotPosition', slot_ref: dict[str, Any]) -> bool:
        """Aplica os filtros declarativos de um slot_ref a um slot detectado."""
        if slot.content is None:
            return False
        if 'slot_index' in slot_ref and int(slot_ref['slot_index']) != slot.index:
            return False
        if 'content_type' in slot_ref and self._coerce_slot_content_type(slot_ref['content_type']) != slot.content.type:
            return False
        if 'lane' in slot_ref and self._coerce_slot_lane(slot_ref['lane']) != slot.lane_hint:
            return False
        if 'availability' in slot_ref and self._coerce_slot_availability(slot_ref['availability']) != slot.content.state.availability:
            return False
        if 'selected' in slot_ref and bool(slot_ref['selected']) != bool(slot.content.state.selected):
            return False
        if 'min_quantity' in slot_ref:
            quantity = slot.content.quantity_hint
            if quantity is None or int(quantity) < int(slot_ref['min_quantity']):
                return False
        if 'max_quantity' in slot_ref:
            quantity = slot.content.quantity_hint
            if quantity is None or int(quantity) > int(slot_ref['max_quantity']):
                return False
        if 'content_name_contains' in slot_ref:
            content_name = (slot.content.name or '').lower()
            if str(slot_ref['content_name_contains']).strip().lower() not in content_name:
                return False
        return True

    def _sort_slots_for_ref(self, slots: list['SlotPosition'], slot_ref: dict[str, Any]) -> list['SlotPosition']:
        """Ordena candidatos conforme preferencia declarativa do slot_ref."""
        prefer = str(slot_ref.get('prefer', 'left_to_right')).strip().lower()
        if prefer == 'highest_quantity':
            return sorted(
                slots,
                key=lambda slot: (slot.content.quantity_hint if slot.content and slot.content.quantity_hint is not None else -1, -slot.index),
                reverse=True,
            )
        if prefer == 'lowest_quantity':
            return sorted(
                slots,
                key=lambda slot: (
                    slot.content.quantity_hint if slot.content and slot.content.quantity_hint is not None else 10**9,
                    slot.index,
                ),
            )
        if prefer == 'right_to_left':
            return sorted(slots, key=lambda slot: slot.index, reverse=True)
        if prefer != 'left_to_right':
            raise ErroBot(f'deployment.scripted.slot_ref.prefer invalido: {prefer}')
        return sorted(slots, key=lambda slot: slot.index)

    def resolver_slot_referencia(self, snapshot: 'BattleBarSnapshot', slot_ref: dict[str, Any]) -> 'SlotPosition':
        """Resolve uma referencia declarativa para um slot detectado na battle bar."""
        if not isinstance(slot_ref, dict) or not slot_ref:
            raise ErroBot('deployment.scripted.slot_ref deve ser um mapa nao vazio.')
        candidatos = [slot for slot in snapshot.slots if self._slot_matches_ref(slot, slot_ref)]
        if not candidatos:
            raise ErroBot(f'Nenhum slot detectado corresponde a deployment.scripted.slot_ref={slot_ref!r}')

        ordenados = self._sort_slots_for_ref(candidatos, slot_ref)
        occurrence = int(slot_ref.get('occurrence', 1))
        if occurrence <= 0:
            raise ErroBot('deployment.scripted.slot_ref.occurrence deve ser >= 1.')
        if occurrence > len(ordenados):
            raise ErroBot(
                f'deployment.scripted.slot_ref.occurrence={occurrence} excede {len(ordenados)} candidato(s) para {slot_ref!r}'
            )
        return ordenados[occurrence - 1]

    def resolver_ponto_selecao_roteiro(
        self,
        dimensoes_tela: tuple[int, int],
        acao: dict[str, Any],
        snapshot: 'BattleBarSnapshot | None',
    ) -> tuple[int, int]:
        """Resolve o ponto de selecao por coordenada fixa ou por slot detectado."""
        slot_ref = acao.get('slot_ref')
        cfg_ponto = acao.get('point') or acao.get('select_point')
        if slot_ref:
            if snapshot is None:
                raise ErroBot('slot_ref exige battle_bar.enabled=true e snapshot valido.')
            slot = self.resolver_slot_referencia(snapshot, slot_ref)
            logging.info(
                'Slot resolvido para %s: index=%s type=%s lane=%s quantity=%s center=%s',
                acao.get('name', 'action'),
                slot.index,
                None if slot.content is None else slot.content.type.value,
                slot.lane_hint.value,
                None if slot.content is None else slot.content.quantity_hint,
                slot.center,
            )
            return slot.center
        if cfg_ponto:
            return resolver_ponto(dimensoes_tela, cfg_ponto)
        raise ErroBot("Acao roteirizada exige 'point', 'select_point' ou 'slot_ref'.")

    def calcular_pontos_deploy_seguro(self) -> list[tuple[int, int]]:
        """Calcula pontos seguros de deploy dentro da ROI configurada."""
        self.checkpoint_controle()
        _, tela = self.capturar_tela()
        cfg_deploy = self.cfg['deployment']
        cfg_roi = cfg_deploy['deploy_roi']
        x0 = int(cfg_roi['x'])
        y0 = int(cfg_roi['y'])
        largura = int(cfg_roi['w'])
        altura = int(cfg_roi['h'])
        roi = tela[y0:y0 + altura, x0:x0 + largura]
        if self.salvar_imagens_deploy():
            salvar_debug(self.diretorio_debug, 'deploy_roi', roi)
        mascara = mascara_vermelha(roi, self.cfg['vision']['red_mask'])
        if cfg_deploy.get('candidate_order') == 'red_boundary_outside':
            # Quando a estrategia usa borda vermelha, tentamos posicionar os cliques logo fora dela.
            candidatos = pontos_externos_borda_vermelha(mascara, cfg_deploy)
            if not candidatos:
                logging.info('Borda vermelha nao detectada; usando fallback corners_then_edges.')
                cfg_fallback = {**cfg_deploy, 'candidate_order': 'corners_then_edges'}
                candidatos = pontos_candidatos_deploy(cfg_fallback, largura=largura, altura=altura)
            pontos_seguros_roi = candidatos
        else:
            candidatos = pontos_candidatos_deploy(cfg_deploy, largura=largura, altura=altura)
            raio = int(cfg_deploy['red_avoid_radius_px'])
            pontos_seguros_roi = [(x, y) for x, y in candidatos if not ponto_proximo_da_mascara(mascara, x, y, raio)]
        pontos_seguros_roi = priorizar_pontos_deploy(pontos_seguros_roi, cfg_deploy, largura=largura, altura=altura)
        pontos_seguro_janela = [(x0 + x, y0 + y) for x, y in pontos_seguros_roi]
        if self.salvar_imagens_deploy():
            debug = desenhar_pontos(tela, pontos_seguro_janela)
            salvar_debug(self.diretorio_debug, 'deploy_points', debug)
        logging.info('Deploy points: candidatos=%s seguros=%s', len(candidatos), len(pontos_seguro_janela))
        return pontos_seguro_janela

    def listar_tropas_deploy(self) -> list[dict[str, Any]]:
        """Retorna a lista de tropas ou slots configurados para deploy."""
        cfg_deploy = self.cfg['deployment']
        return cfg_deploy.get('troops') or cfg_deploy['item_slots']

    def tropa_disponivel(self, tropa: dict[str, Any], tela) -> bool:
        """Infere se a tropa ainda esta disponivel pela coloracao do slot."""
        status_roi = tropa.get('status_roi')
        if not status_roi:
            return True
        roi = extrair_roi(tela, status_roi)
        if roi.size == 0:
            return False
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        saturacao = float(hsv[:, :, 1].mean())
        brilho = float(hsv[:, :, 2].mean())
        proporcao_cor = float((hsv[:, :, 1] > int(self.cfg['deployment'].get('available_color_pixel_saturation', 45))).mean())
        cfg_deploy = self.cfg['deployment']
        saturacao_minima = float(tropa.get('available_saturation_threshold', cfg_deploy.get('available_saturation_threshold', 35)))
        brilho_minimo = float(tropa.get('available_value_threshold', cfg_deploy.get('available_value_threshold', 35)))
        proporcao_minima = float(tropa.get('available_color_ratio_threshold', cfg_deploy.get('available_color_ratio_threshold', 0.20)))
        disponivel = saturacao >= saturacao_minima and brilho >= brilho_minimo and proporcao_cor >= proporcao_minima
        logging.info(
            'Status tropa=%s saturacao=%.1f brilho=%.1f cor=%.3f disponivel=%s',
            tropa.get('name', 'troop'),
            saturacao,
            brilho,
            proporcao_cor,
            disponivel,
        )
        return disponivel

    def selecionar_tropa(self, retangulo: JanelaRetangulo, tropa: dict[str, Any]) -> None:
        """Seleciona uma tropa por tecla e/ou clique no card configurado."""
        self.checkpoint_controle()
        nome = tropa.get('name', 'troop')
        cfg_deploy = self.cfg['deployment']
        tecla = tropa.get('key')
        if tecla:
            pressionar_tecla(str(tecla), dry_run=self.dry_run)
            self.dormir_interrompivel(float(cfg_deploy.get('delay_after_troop_select_seconds', self.between)))
        deve_clicar_card = (not tecla) or bool(tropa.get('click_after_key', cfg_deploy.get('click_after_key_select', True)))
        if deve_clicar_card:
            logging.info('Clique no card da tropa=%s em (%s,%s)', nome, tropa['x'], tropa['y'])
            clicar_relativo(retangulo, int(tropa['x']), int(tropa['y']), dry_run=self.dry_run, duration=self.duration)
            self.dormir_interrompivel(float(cfg_deploy.get('delay_after_troop_select_seconds', self.between)))

    def fazer_deploy_tropa_ate_esgotar(
        self,
        retangulo: JanelaRetangulo,
        tropa: dict[str, Any],
        pontos: list[tuple[int, int]],
        indice_inicial: int,
    ) -> int:
        """Executa batches de deploy para uma tropa ate esgotar ou atingir limite."""
        cfg_deploy = self.cfg['deployment']
        nome = tropa.get('name', 'troop')
        cliques_lote = int(tropa.get('batch_clicks', cfg_deploy.get('clicks_per_troop_pass', 10)))
        max_lotes = int(tropa.get('max_batches', cfg_deploy.get('max_batches_per_troop', 80)))
        indice = indice_inicial

        for numero_lote in range(1, max_lotes + 1):
            self.checkpoint_controle()
            _, tela = self.capturar_tela()
            if not self.tropa_disponivel(tropa, tela):
                logging.info('Tropa=%s esgotada; avancando para a proxima.', nome)
                return indice

            logging.info('Selecionando tropa=%s lote=%s/%s cliques=%s', nome, numero_lote, max_lotes, cliques_lote)
            self.selecionar_tropa(retangulo, tropa)
            for _ in range(cliques_lote):
                self.checkpoint_controle()
                x, y = pontos[indice % len(pontos)]
                indice += 1
                clicar_relativo(retangulo, x, y, dry_run=self.dry_run, duration=self.duration)
                self.dormir_interrompivel(self.between)

        logging.warning('max_batches_per_troop atingido para tropa=%s antes de detectar esgotamento.', nome)
        return indice

    def fazer_deploy_ate_esgotar_tropas(self, retangulo: JanelaRetangulo, pontos: list[tuple[int, int]]) -> None:
        """Percorre todas as tropas configuradas tentando esgota-las em sequencia."""
        tropas = self.listar_tropas_deploy()
        indice = 0

        _, tela = self.capturar_tela()
        rois = [tropa['status_roi'] for tropa in tropas if tropa.get('status_roi')]
        if rois and self.salvar_imagens_deploy():
            salvar_debug(self.diretorio_debug, 'troop_status_rois', desenhar_rois(tela, rois))

        for tropa in tropas:
            self.checkpoint_controle()
            indice = self.fazer_deploy_tropa_ate_esgotar(retangulo, tropa, pontos, indice)
        logging.info('Sequencia de deploy concluida para todas as tropas configuradas.')

    def calcular_atraso_clique_roteirizado(self) -> float:
        """Retorna o atraso aleatorio entre cliques do modo roteirizado."""
        cfg_roteiro = self.cfg['deployment'].get('scripted', {})
        cfg_atraso = cfg_roteiro.get('click_delay_range_seconds', {})
        atraso_minimo = float(cfg_atraso.get('min', 0.10))
        atraso_maximo = float(cfg_atraso.get('max', 0.30))
        if atraso_maximo < atraso_minimo:
            atraso_minimo, atraso_maximo = atraso_maximo, atraso_minimo
        return random.uniform(atraso_minimo, atraso_maximo)

    def clicar_ponto_roteiro(self, retangulo: JanelaRetangulo, x: int, y: int) -> None:
        """Clica em um ponto do roteiro respeitando o delay configurado."""
        self.checkpoint_controle()
        clicar_relativo(retangulo, x, y, dry_run=self.dry_run, duration=self.duration)
        self.dormir_interrompivel(self.calcular_atraso_clique_roteirizado())

    def montar_nome_debug_roteiro(self, sufixo: str) -> str:
        """Monta o nome do artefato de debug considerando o perfil CV ativo."""
        perfil = str(self.cfg.get('runtime', {}).get('cv_profile', 'default'))
        return f'{perfil}_{sufixo}'

    def salvar_checkpoint(self, nome: str):
        """Salva um screenshot de checkpoint do estado atual da tela."""
        if not self.salvar_checkpoints():
            return None
        _, tela = self.capturar_tela()
        saida = salvar_debug(self.diretorio_debug, self.montar_nome_debug_roteiro(nome), tela)
        logging.info('Checkpoint salvo: %s', saida)
        return saida

    def executar_deploy_roteirizado(self, retangulo: JanelaRetangulo) -> None:
        """Executa o deploy orientado por uma lista explicita de acoes."""
        cfg_roteiro = self.cfg['deployment'].get('scripted', {})
        acoes = cfg_roteiro.get('actions', [])
        if not acoes:
            raise ErroBot('deployment.mode=scripted exige deployment.scripted.actions configurado.')

        _, tela = self.capturar_tela()
        altura_tela, largura_tela = tela.shape[:2]
        pontos_debug: list[tuple[int, int]] = []
        snapshot = self.analyze_battle_bar() if self.battle_bar_analyzer is not None else None

        for acao in acoes:
            self.checkpoint_controle()
            tipo_acao = acao['type']
            if tipo_acao == 'select':
                nome = acao.get('name', 'select')
                tecla = acao.get('key')
                if tecla:
                    logging.info('Selecionando %s por tecla=%s', nome, tecla)
                    pressionar_tecla(str(tecla), dry_run=self.dry_run)
                    self.dormir_interrompivel(self.calcular_atraso_clique_roteirizado())
                if acao.get('point') or acao.get('slot_ref'):
                    x, y = self.resolver_ponto_selecao_roteiro((largura_tela, altura_tela), acao, snapshot)
                    logging.info('Selecionando %s em (%s,%s)', nome, x, y)
                    pontos_debug.append((x, y))
                    self.clicar_ponto_roteiro(retangulo, x, y)
                atraso_posterior = acao.get('after_delay_seconds')
                if atraso_posterior is not None:
                    self.dormir_interrompivel(float(atraso_posterior))
                continue

            if tipo_acao == 'scatter_line':
                quantidade = int(acao['count'])
                meia_largura_px = float(acao.get('half_width_px', 18))
                pontos = gerar_pontos_aleatorios_em_faixa(
                    (largura_tela, altura_tela),
                    cfg_inicio=acao['start'],
                    cfg_fim=acao['end'],
                    quantidade=quantidade,
                    meia_largura_px=meia_largura_px,
                )
                logging.info('Executando scatter_line com %s cliques.', len(pontos))
                pontos_debug.extend(pontos)
                for x, y in pontos:
                    self.clicar_ponto_roteiro(retangulo, x, y)
                continue

            if tipo_acao == 'click_points':
                cfg_pontos = acao.get('points', [])
                logging.info('Executando click_points com %s pontos.', len(cfg_pontos))
                for cfg_ponto in cfg_pontos:
                    x, y = resolver_ponto((largura_tela, altura_tela), cfg_ponto)
                    pontos_debug.append((x, y))
                    self.clicar_ponto_roteiro(retangulo, x, y)
                continue

            if tipo_acao == 'scatter_line_counted':
                nome = acao.get('name', 'scatter_line_counted')
                sx, sy = self.resolver_ponto_selecao_roteiro((largura_tela, altura_tela), acao, snapshot)
                quantidade = int(acao['count'])
                meia_largura_px = float(acao.get('half_width_px', 18))
                logging.info('Selecionando %s em (%s,%s) para %s cliques na linha.', nome, sx, sy, quantidade)
                pontos_debug.append((sx, sy))
                self.clicar_ponto_roteiro(retangulo, sx, sy)
                atraso_posterior = acao.get('after_delay_seconds')
                if atraso_posterior is not None:
                    self.dormir_interrompivel(float(atraso_posterior))
                pontos = gerar_pontos_aleatorios_em_faixa(
                    (largura_tela, altura_tela),
                    cfg_inicio=acao['start'],
                    cfg_fim=acao['end'],
                    quantidade=quantidade,
                    meia_largura_px=meia_largura_px,
                )
                logging.info('Executando scatter_line_counted=%s com %s cliques.', nome, len(pontos))
                pontos_debug.extend(pontos)
                for x, y in pontos:
                    self.clicar_ponto_roteiro(retangulo, x, y)
                continue

            raise ErroBot(f'deployment.scripted.actions.type invalido: {tipo_acao}')

        if pontos_debug and self.salvar_imagens_deploy():
            debug = desenhar_pontos(tela, pontos_debug)
            salvar_debug(self.diretorio_debug, self.montar_nome_debug_roteiro('scripted_deploy_points'), debug)
        logging.info('Deploy roteirizado concluido.')

    def executar_deploy(self) -> None:
        """Dispara o modo de deploy configurado para o ciclo atual."""
        self.checkpoint_controle()
        if not bool(self.cfg['deployment']['enabled']):
            logging.info('Deploy desativado.')
            return
        retangulo = self.obter_janela()
        self.salvar_checkpoint('before_deploy')
        if self.cfg['deployment'].get('mode') == 'scripted':
            self.executar_deploy_roteirizado(retangulo)
            self.salvar_checkpoint('after_deploy')
            return
        pontos = self.calcular_pontos_deploy_seguro()
        if not pontos:
            raise ErroBot('Nenhum ponto seguro de deploy detectado.')
        if bool(self.cfg['deployment'].get('deploy_until_exhausted', False)):
            self.fazer_deploy_ate_esgotar_tropas(retangulo, pontos)
            self.salvar_checkpoint('after_deploy')
            return
        cliques_padrao = int(self.cfg['deployment']['clicks_per_item'])
        indice = 0
        for tropa in self.listar_tropas_deploy():
            self.checkpoint_controle()
            nome = tropa.get('name', 'troop')
            cliques = int(tropa.get('clicks', cliques_padrao))
            logging.info('Selecionando tropa=%s cliques=%s', nome, cliques)
            clicar_relativo(retangulo, int(tropa['x']), int(tropa['y']), dry_run=self.dry_run, duration=self.duration)
            self.dormir_interrompivel(self.between)
            for _ in range(cliques):
                self.checkpoint_controle()
                x, y = pontos[indice % len(pontos)]
                indice += 1
                clicar_relativo(retangulo, x, y, dry_run=self.dry_run, duration=self.duration)
                self.dormir_interrompivel(self.between)
        self.salvar_checkpoint('after_deploy')
