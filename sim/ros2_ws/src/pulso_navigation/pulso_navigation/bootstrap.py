"""Bounded rotation-only viewpoints used before SLAM exposes a frontier."""

from __future__ import annotations

import math

from .frontier import FrontierCandidate


def bootstrap_viewpoints(
    robot: tuple[float, float, float],
    sweep_step: int,
    *,
    max_sweep_steps: int = 8,
) -> list[FrontierCandidate]:
    """Propose evidence rotations without inventing traversable free space.

    IDs include the completed sweep count. Finishing a LOOK_AT therefore
    creates a material navigation revision and lets the agent decide whether
    another observation is warranted. The bounded step count prevents an
    unobservable environment from causing an endless autonomous spin.
    """
    if sweep_step < 0 or sweep_step >= max_sweep_steps:
        return []
    result = []
    for index, offset_deg in enumerate((90.0, -90.0, 180.0)):
        bearing = robot[2] + math.radians(offset_deg)
        x = robot[0] + math.cos(bearing)
        y = robot[1] + math.sin(bearing)
        result.append(
            FrontierCandidate(
                candidate_id=f"VP_INIT_S{sweep_step + 1}_{index + 1}",
                x=x,
                y=y,
                path=((robot[0], robot[1]), (x, y)),
                path_length_m=0.0,
                risk=0.08,
                information_gain=1.0,
                frontier_cells=0,
                kind="VIEWPOINT",
                rotation_only=True,
            )
        )
    return result
