#!/usr/bin/env python3
"""Diagnostica a battle bar a partir de uma imagem local, sem abrir a UI."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2

from core.vision.pipeline import extract_ratio_region
from domain.settings.entities import BattleBarSettings, RatioRegion, UserSettings
from infrastructure.persistence.settings_repository import AppDataSettingsRepository
from infrastructure.vision.opencv_battle_bar_analyzer import OpenCvBattleBarAnalyzerAdapter
from utils.image_utils import escrever_png, ler_imagem_bgr


def carregar_settings(caminho: Path | None) -> UserSettings:
    """Carrega settings de um JSON customizado, AppData ou defaults."""
    if caminho is not None:
        with caminho.open('r', encoding='utf-8') as handle:
            return UserSettings.from_dict(json.load(handle))
    repositorio = AppDataSettingsRepository()
    return repositorio.load() or UserSettings()


def aplicar_overrides(settings: UserSettings, args: argparse.Namespace) -> UserSettings:
    """Aplica overrides simples de linha de comando para teste rapido."""
    bottom_region = settings.bottom_region
    if args.bottom_y_ratio is not None or args.bottom_h_ratio is not None:
        bottom_region = RatioRegion(
            x_ratio=bottom_region.x_ratio,
            y_ratio=args.bottom_y_ratio if args.bottom_y_ratio is not None else bottom_region.y_ratio,
            w_ratio=bottom_region.w_ratio,
            h_ratio=args.bottom_h_ratio if args.bottom_h_ratio is not None else bottom_region.h_ratio,
        )

    battle_bar = settings.battle_bar
    if any(value is not None for value in (args.bar_x_ratio, args.bar_y_ratio, args.bar_w_ratio, args.bar_h_ratio, args.slot_count)):
        battle_bar = replace(
            battle_bar,
            bar_roi=RatioRegion(
                x_ratio=args.bar_x_ratio if args.bar_x_ratio is not None else battle_bar.bar_roi.x_ratio,
                y_ratio=args.bar_y_ratio if args.bar_y_ratio is not None else battle_bar.bar_roi.y_ratio,
                w_ratio=args.bar_w_ratio if args.bar_w_ratio is not None else battle_bar.bar_roi.w_ratio,
                h_ratio=args.bar_h_ratio if args.bar_h_ratio is not None else battle_bar.bar_roi.h_ratio,
            ),
            slot_count=args.slot_count if args.slot_count is not None else battle_bar.slot_count,
        )

    return replace(settings, bottom_region=bottom_region, battle_bar=battle_bar)


def desenhar_overlay(imagem_bgr, snapshot) -> Any:
    """Desenha bbox da barra e slots sobre a imagem original."""
    overlay = imagem_bgr.copy()
    bar_bbox = snapshot.bar_bbox
    fallback = bool(snapshot.diagnostics.get('used_position_fallback', False))
    confidence = float(snapshot.diagnostics.get('position_confidence', 0.0))
    strategy = str(snapshot.diagnostics.get('position_strategy', 'unknown'))
    bar_color = (0, 165, 255) if fallback else (0, 255, 255)

    cv2.rectangle(
        overlay,
        (bar_bbox.x, bar_bbox.y),
        (bar_bbox.x + bar_bbox.w, bar_bbox.y + bar_bbox.h),
        bar_color,
        2,
    )
    cv2.putText(
        overlay,
        f'bar confidence={confidence:.2f} strategy={strategy} fallback={fallback}',
        (bar_bbox.x, max(18, bar_bbox.y - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        bar_color,
        1,
        cv2.LINE_AA,
    )

    for slot in snapshot.slots:
        bbox = slot.bbox
        color = (150, 150, 150) if slot.content is None else (0, 200, 0)
        cv2.rectangle(overlay, (bbox.x, bbox.y), (bbox.x + bbox.w, bbox.y + bbox.h), color, 2)
        label = f'#{slot.index}'
        if slot.content is None:
            label += ':empty'
        else:
            label += f':{slot.content.type.value}:{slot.content.state.availability.value}'
            if slot.content.quantity_hint is not None:
                label += f':x{slot.content.quantity_hint}'
        cv2.putText(
            overlay,
            label,
            (bbox.x, min(overlay.shape[0] - 8, bbox.y + bbox.h + 14)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    return overlay


def construir_json(snapshot, settings: UserSettings, input_image: Path) -> dict[str, Any]:
    """Monta o resumo serializavel da execucao."""
    return {
        'input_image': str(input_image),
        'settings': settings.to_dict(),
        'diagnostics': snapshot.diagnostics,
        'bar_bbox': {
            'x': snapshot.bar_bbox.x,
            'y': snapshot.bar_bbox.y,
            'w': snapshot.bar_bbox.w,
            'h': snapshot.bar_bbox.h,
        },
        'slots': [
            {
                'index': slot.index,
                'lane': slot.lane_hint.value,
                'bbox': {
                    'x': slot.bbox.x,
                    'y': slot.bbox.y,
                    'w': slot.bbox.w,
                    'h': slot.bbox.h,
                },
                'is_empty': slot.content is None,
                'content_type': None if slot.content is None else slot.content.type.value,
                'quantity_hint': None if slot.content is None else slot.content.quantity_hint,
                'state': None if slot.content is None else slot.content.state.availability.value,
                'selected': None if slot.content is None else slot.content.state.selected,
                'metadata': {} if slot.content is None else {**slot.metadata, **slot.content.metadata},
                'slot_metadata': slot.metadata,
                'content_metadata': None if slot.content is None else slot.content.metadata,
            }
            for slot in snapshot.slots
        ],
    }


def criar_parser() -> argparse.ArgumentParser:
    """Constroi a CLI do diagnostico."""
    parser = argparse.ArgumentParser(description='Executa a classificacao da battle bar a partir de uma imagem.')
    parser.add_argument('--image', required=True, help='Caminho da imagem de entrada.')
    parser.add_argument('--out-dir', default='tmp/battle_bar_diagnostics', help='Diretorio onde os artefatos serao gravados.')
    parser.add_argument('--settings', help='JSON opcional com os settings a usar; se ausente, usa AppData/defaults.')
    parser.add_argument('--bottom-y-ratio', type=float, help='Override rapido para bottom_region.y_ratio.')
    parser.add_argument('--bottom-h-ratio', type=float, help='Override rapido para bottom_region.h_ratio.')
    parser.add_argument('--bar-x-ratio', type=float, help='Override rapido para battle_bar.bar_roi.x_ratio.')
    parser.add_argument('--bar-y-ratio', type=float, help='Override rapido para battle_bar.bar_roi.y_ratio.')
    parser.add_argument('--bar-w-ratio', type=float, help='Override rapido para battle_bar.bar_roi.w_ratio.')
    parser.add_argument('--bar-h-ratio', type=float, help='Override rapido para battle_bar.bar_roi.h_ratio.')
    parser.add_argument('--slot-count', type=int, help='Override rapido para battle_bar.slot_count.')
    return parser


def main() -> int:
    parser = criar_parser()
    args = parser.parse_args()

    imagem_path = Path(args.image)
    if not imagem_path.exists():
        print(f'[ERRO] Imagem nao encontrada: {imagem_path}')
        return 1

    settings_path = Path(args.settings) if args.settings else None
    settings = aplicar_overrides(carregar_settings(settings_path), args)
    imagem_bgr = ler_imagem_bgr(imagem_path)
    if imagem_bgr is None:
        print(f'[ERRO] Nao consegui ler a imagem: {imagem_path}')
        return 1

    analyzer = OpenCvBattleBarAnalyzerAdapter(asset_base_dir=Path('.').resolve())
    snapshot = analyzer.analyze(imagem_bgr, settings)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bottom_region = extract_ratio_region(imagem_bgr, settings.bottom_region)
    overlay = desenhar_overlay(imagem_bgr, snapshot)
    summary = construir_json(snapshot, settings, imagem_path)

    original_out = out_dir / 'original.png'
    overlay_out = out_dir / 'overlay.png'
    bottom_out = out_dir / 'bottom_region.png'
    json_out = out_dir / 'classification.json'

    if not escrever_png(original_out, imagem_bgr):
        print(f'[ERRO] Nao consegui gravar: {original_out}')
        return 1
    if not escrever_png(overlay_out, overlay):
        print(f'[ERRO] Nao consegui gravar: {overlay_out}')
        return 1
    if not escrever_png(bottom_out, bottom_region):
        print(f'[ERRO] Nao consegui gravar: {bottom_out}')
        return 1
    with json_out.open('w', encoding='utf-8') as handle:
        json.dump(summary, handle, ensure_ascii=True, indent=2)

    print(f'Imagem analisada: {imagem_path}')
    print(f'Pasta de saida: {out_dir.resolve()}')
    print(f'Confianca da barra: {float(snapshot.diagnostics.get("position_confidence", 0.0)):.2f}')
    print(f'Estrategia: {snapshot.diagnostics.get("position_strategy", "unknown")}')
    print(f'Fallback usado: {bool(snapshot.diagnostics.get("used_position_fallback", False))}')
    print(f'Slots com conteudo: {snapshot.diagnostics.get("non_empty_slots", 0)}/{snapshot.diagnostics.get("slot_count", 0)}')
    print(f'Overlay: {overlay_out}')
    print(f'JSON: {json_out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
