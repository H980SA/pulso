"""Deterministic, calibratable depth degradation independent of ROS."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DepthProfile:
    min_m: float = 0.35
    useful_max_m: float = 5.0
    hard_max_m: float = 8.0
    base_sigma_m: float = 0.004
    range_sigma_m_per_m2: float = 0.0015
    base_hole_probability: float = 0.015
    range_hole_probability: float = 0.09


def degrade_depth(
    depth_m: np.ndarray,
    rng: np.random.Generator,
    profile: DepthProfile = DepthProfile(),
) -> tuple[np.ndarray, np.ndarray]:
    """Return raw depth in millimetres and mono8 confidence.

    This provisional profile models range-dependent noise and missing samples.
    It is intentionally isolated so S25 recordings can replace the parameters
    without changing ROS topics or the Android contract.
    """

    depth = np.asarray(depth_m, dtype=np.float32)
    valid = np.isfinite(depth) & (depth >= profile.min_m) & (depth <= profile.hard_max_m)

    normalized = np.clip(depth / profile.useful_max_m, 0.0, 1.6)
    sigma = profile.base_sigma_m + profile.range_sigma_m_per_m2 * np.square(depth)
    sigma = np.where(np.isfinite(sigma), sigma, 0.0)
    noisy = depth + rng.normal(0.0, sigma, size=depth.shape).astype(np.float32)

    hole_probability = profile.base_hole_probability + profile.range_hole_probability * np.square(
        np.clip(normalized, 0.0, 1.0)
    )
    holes = rng.random(depth.shape) < hole_probability
    valid &= ~holes

    confidence = np.clip(1.0 - np.square(np.clip(normalized, 0.0, 1.0)), 0.0, 1.0)
    confidence = np.where(valid, confidence, 0.0)

    depth_mm = np.zeros(depth.shape, dtype=np.uint16)
    depth_mm[valid] = np.clip(np.rint(noisy[valid] * 1000.0), 1, 65535).astype(np.uint16)
    confidence_u8 = np.rint(confidence * 255.0).astype(np.uint8)
    return depth_mm, confidence_u8
