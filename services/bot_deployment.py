"""Comportamentos responsaveis por selecionar tropas e executar deploy."""

from __future__ import annotations

import logging
import random
import time
from typing import Any

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


class BotDeploymentMixin:
    """Concentra a logica de calculo de pontos e soltura de tropas."""

    def calcular_pontos_deploy_seguro(self) -> list[tuple[int, int]]:
        """Calcula pontos seguros de deploy dentro da ROI configurada."""
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
        nome = tropa.get('name', 'troop')
        cfg_deploy = self.cfg['deployment']
        tecla = tropa.get('key')
        if tecla:
            pressionar_tecla(str(tecla), dry_run=self.dry_run)
            time.sleep(float(cfg_deploy.get('delay_after_troop_select_seconds', self.between)))
        deve_clicar_card = (not tecla) or bool(tropa.get('click_after_key', cfg_deploy.get('click_after_key_select', True)))
        if deve_clicar_card:
            logging.info('Clique no card da tropa=%s em (%s,%s)', nome, tropa['x'], tropa['y'])
            clicar_relativo(retangulo, int(tropa['x']), int(tropa['y']), dry_run=self.dry_run, duration=self.duration)
            time.sleep(float(cfg_deploy.get('delay_after_troop_select_seconds', self.between)))

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
            _, tela = self.capturar_tela()
            if not self.tropa_disponivel(tropa, tela):
                logging.info('Tropa=%s esgotada; avancando para a proxima.', nome)
                return indice

            logging.info('Selecionando tropa=%s lote=%s/%s cliques=%s', nome, numero_lote, max_lotes, cliques_lote)
            self.selecionar_tropa(retangulo, tropa)
            for _ in range(cliques_lote):
                x, y = pontos[indice % len(pontos)]
                indice += 1
                clicar_relativo(retangulo, x, y, dry_run=self.dry_run, duration=self.duration)
                time.sleep(self.between)

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
        clicar_relativo(retangulo, x, y, dry_run=self.dry_run, duration=self.duration)
        time.sleep(self.calcular_atraso_clique_roteirizado())

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

        for acao in acoes:
            tipo_acao = acao['type']
            if tipo_acao == 'select':
                nome = acao.get('name', 'select')
                tecla = acao.get('key')
                if tecla:
                    logging.info('Selecionando %s por tecla=%s', nome, tecla)
                    pressionar_tecla(str(tecla), dry_run=self.dry_run)
                    time.sleep(self.calcular_atraso_clique_roteirizado())
                cfg_ponto = acao.get('point')
                if cfg_ponto:
                    x, y = resolver_ponto((largura_tela, altura_tela), cfg_ponto)
                    logging.info('Selecionando %s em (%s,%s)', nome, x, y)
                    pontos_debug.append((x, y))
                    self.clicar_ponto_roteiro(retangulo, x, y)
                atraso_posterior = acao.get('after_delay_seconds')
                if atraso_posterior is not None:
                    time.sleep(float(atraso_posterior))
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
                ponto_selecao = acao.get('select_point')
                if not ponto_selecao:
                    raise ErroBot('scatter_line_counted exige select_point.')
                sx, sy = resolver_ponto((largura_tela, altura_tela), ponto_selecao)
                quantidade = int(acao['count'])
                meia_largura_px = float(acao.get('half_width_px', 18))
                logging.info('Selecionando %s em (%s,%s) para %s cliques na linha.', nome, sx, sy, quantidade)
                pontos_debug.append((sx, sy))
                self.clicar_ponto_roteiro(retangulo, sx, sy)
                atraso_posterior = acao.get('after_delay_seconds')
                if atraso_posterior is not None:
                    time.sleep(float(atraso_posterior))
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
            nome = tropa.get('name', 'troop')
            cliques = int(tropa.get('clicks', cliques_padrao))
            logging.info('Selecionando tropa=%s cliques=%s', nome, cliques)
            clicar_relativo(retangulo, int(tropa['x']), int(tropa['y']), dry_run=self.dry_run, duration=self.duration)
            time.sleep(self.between)
            for _ in range(cliques):
                x, y = pontos[indice % len(pontos)]
                indice += 1
                clicar_relativo(retangulo, x, y, dry_run=self.dry_run, duration=self.duration)
                time.sleep(self.between)
        self.salvar_checkpoint('after_deploy')
