"""Leitura de configuracao YAML e aplicacao de perfis de execucao."""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


def carregar_yaml(caminho: Path) -> dict[str, Any]:
    """Carrega um arquivo YAML como dicionario Python."""
    with caminho.open('r', encoding='utf-8') as arquivo:
        return yaml.safe_load(arquivo)


def mesclar_dicts_profundamente(base: dict[str, Any], sobrescrita: dict[str, Any]) -> dict[str, Any]:
    """Faz merge profundo preservando a estrutura do dicionario base."""
    mesclado = deepcopy(base)
    for chave, valor in sobrescrita.items():
        if isinstance(valor, dict) and isinstance(mesclado.get(chave), dict):
            mesclado[chave] = mesclar_dicts_profundamente(mesclado[chave], valor)
        else:
            mesclado[chave] = deepcopy(valor)
    return mesclado


def aplicar_perfil_cv(cfg: dict[str, Any], perfil_selecionado: str | None) -> dict[str, Any]:
    """Aplica um perfil CV sobre a configuracao base."""
    perfis = cfg.get('cv_profiles') or {}
    perfil_ativo = perfil_selecionado or cfg.get('runtime', {}).get('cv_profile')
    if not perfil_ativo:
        return cfg
    if perfil_ativo not in perfis:
        disponiveis = ', '.join(sorted(perfis)) or '<nenhum>'
        raise ValueError(f"Perfil CV '{perfil_ativo}' nao encontrado. Disponiveis: {disponiveis}")
    mesclado = mesclar_dicts_profundamente(cfg, perfis[perfil_ativo])
    mesclado.setdefault('runtime', {})['cv_profile'] = perfil_ativo
    return mesclado


def carregar_configuracao_runtime(caminho_config: Path, perfil_selecionado: str | None = None) -> dict[str, Any]:
    """Carrega a configuracao completa pronta para uso em runtime."""
    return aplicar_perfil_cv(carregar_yaml(caminho_config), perfil_selecionado)


def resolver_diretorio_aplicacao() -> Path:
    """Retorna o diretorio base da aplicacao, inclusive quando empacotada."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resolver_diretorio_bundle() -> Path:
    """Retorna o diretorio temporario de recursos do bundle, quando existir."""
    bundle_dir = getattr(sys, '_MEIPASS', None)
    if bundle_dir:
        return Path(bundle_dir).resolve()
    return resolver_diretorio_aplicacao()


def resolver_caminho_config(caminho_config: str | Path = 'config.yaml') -> Path:
    """Resolve o config priorizando arquivo externo e, em fallback, recurso embutido."""
    caminho = Path(caminho_config)
    if caminho.is_absolute():
        return caminho
    if caminho.exists():
        return caminho.resolve()

    caminho_aplicacao = resolver_diretorio_aplicacao() / caminho
    if caminho_aplicacao.exists():
        return caminho_aplicacao.resolve()

    caminho_bundle = resolver_diretorio_bundle() / caminho
    if caminho_bundle.exists():
        return caminho_bundle.resolve()

    return caminho.resolve()


def resolver_diretorio_debug(cfg: dict[str, Any], caminho_config: Path) -> Path:
    """Resolve o diretorio de debug como caminho absoluto."""
    diretorio_debug = Path(cfg['runtime']['debug_dir'])
    if not diretorio_debug.is_absolute():
        diretorio_debug = caminho_config.parent / diretorio_debug
    return diretorio_debug
