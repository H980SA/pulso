"""Validate short-lived phone perception tracks for camera centering."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math

from .frontier import FrontierCandidate


@dataclass(frozen=True)
class PerceptionTrack:
    track_id: str
    label: str
    confidence: float
    bearing_deg: float
    revision: int
    received_ns: int


def parse_tracks(payload_json: str, received_ns: int) -> dict[str, PerceptionTrack] | None:
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if payload.get("contract_version") != "pulso.perception.tracks.v1":
        return None
    tracks: dict[str, PerceptionTrack] = {}
    for item in (payload.get("tracks") or [])[:8]:
        track_id = str(item.get("id") or "").strip()
        if not track_id or not track_id.replace("_", "").isalnum():
            continue
        tracks[track_id] = PerceptionTrack(
            track_id=track_id,
            label=str(item.get("label") or "person"),
            confidence=float(min(1.0, max(0.0, item.get("confidence", 0.0)))),
            bearing_deg=float(min(180.0, max(-180.0, item.get("bearing_deg", 0.0)))),
            revision=int(item.get("revision") or 0),
            received_ns=received_ns,
        )
    return tracks


def build_target_candidates(
    tracks: dict[str, PerceptionTrack],
    robot: tuple[float, float, float],
    now_ns: int,
    *,
    max_age_ns: int = 3_000_000_000,
) -> tuple[list[FrontierCandidate], dict[str, PerceptionTrack]]:
    live = {
        track_id: track
        for track_id, track in tracks.items()
        if now_ns - track.received_ns <= max_age_ns
    }
    result = []
    for track in live.values():
        bearing = robot[2] + math.radians(track.bearing_deg)
        x = robot[0] + math.cos(bearing)
        y = robot[1] + math.sin(bearing)
        result.append(
            FrontierCandidate(
                candidate_id=track.track_id,
                x=x,
                y=y,
                path=((robot[0], robot[1]), (x, y)),
                path_length_m=0.0,
                risk=max(0.04, (1.0 - track.confidence) * 0.25),
                information_gain=max(0.6, track.confidence),
                frontier_cells=0,
                kind="TARGET",
                rotation_only=True,
                target_revision=track.revision,
            )
        )
    return sorted(result, key=lambda item: -item.information_gain), live
