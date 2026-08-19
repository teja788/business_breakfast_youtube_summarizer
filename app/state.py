from __future__ import annotations

import json
from pathlib import Path


EMPTY_STATE = {"processed_video_ids": []}


def load_processed_ids(state_file: Path) -> set[str]:
    ensure_state_file(state_file)
    data = json.loads(state_file.read_text(encoding="utf-8-sig"))
    ids = data.get("processed_video_ids", [])
    return {str(video_id) for video_id in ids}


def mark_processed(state_file: Path, video_id: str) -> None:
    ensure_state_file(state_file)
    data = json.loads(state_file.read_text(encoding="utf-8-sig"))
    ids = {str(existing_id) for existing_id in data.get("processed_video_ids", [])}
    ids.add(video_id)
    payload = {"processed_video_ids": sorted(ids)}
    state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_state_file(state_file: Path) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if not state_file.exists():
        state_file.write_text(json.dumps(EMPTY_STATE, indent=2), encoding="utf-8")
