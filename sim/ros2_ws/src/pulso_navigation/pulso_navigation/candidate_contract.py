"""Serialize navigation candidates into the stable phone-facing contract."""

from __future__ import annotations

from .frontier import FrontierCandidate


def candidate_contract(
    candidates: list[FrontierCandidate],
    *,
    captured_ns: int,
    sensor_map_seq: int,
    navigation_revision: int,
    valid_until_ns: int,
    capabilities: dict[str, str],
) -> dict:
    return {
        "contract_version": "pulso.navigation.candidates.v1",
        "captured_monotonic_ns": captured_ns,
        "sensor_map_seq": sensor_map_seq,
        "navigation_revision": navigation_revision,
        "valid_until_monotonic_ns": valid_until_ns,
        "candidates": [
            {
                "type": item.kind,
                "id": item.candidate_id,
                "capability": capabilities[item.candidate_id],
                "target_revision": item.target_revision,
                "label": (
                    f"Posible persona {item.candidate_id.removeprefix('PERSON_')}"
                    if item.kind == "TARGET"
                    else f"Camino {chr(ord('A') + index)}"
                ),
                "purpose": (
                    "Centrar la cámara y obtener evidencia multimodal"
                    if item.kind == "TARGET"
                    else (
                        "Girar sin avanzar para inicializar cobertura espacial"
                        if item.rotation_only
                        else "Expandir el mapa hacia espacio desconocido alcanzable"
                    )
                ),
                "position_m": [round(item.x, 3), round(item.y, 3)],
                "path_length_m": round(item.path_length_m, 3),
                "risk": round(item.risk, 3),
                "information_gain": round(item.information_gain, 3),
                "frontier_cells": item.frontier_cells,
            }
            for index, item in enumerate(candidates)
        ],
    }
