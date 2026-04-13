"""
grid_sidecar.py — 渲染阶段与指令生成阶段之间的中间契约

每张渲染图对应：
  output/grids/{i:05d}.jsonl   每行一个 photo/video 格子（按 visual_slot 顺序）
  output/grids/{i:05d}.meta.json   {app, image_path}

读回后可重建最小 SlotInfo + PhotoEntry（仅 instruction 生成所需字段）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .renderer import SlotInfo
from .source_library import PhotoEntry


def _slot_to_dict(slot: SlotInfo) -> dict:
    return {
        "visual_slot": slot.visual_slot,
        "row": slot.row,
        "col": slot.col,
        "type": "video" if slot.is_video else "image",
        "grid_index": slot.grid_index,
        "video_index": slot.video_index,
        "bbox": list(slot.bbox),
        "click_target": list(slot.click_target),
        "click_box": list(slot.click_box),
        "target_type": slot.target_type,
        "duration": slot.duration,
        "photo": {
            "id": slot.photo.id,
            "source_path": slot.photo.source_path,
            "labels": list(slot.photo.labels),
            "description": slot.photo.description,
            "timestamp": slot.photo.timestamp.isoformat() if slot.photo.timestamp else None,
        },
    }


def _dict_to_slot(d: dict) -> SlotInfo:
    p = d["photo"]
    ts = datetime.fromisoformat(p["timestamp"]) if p.get("timestamp") else datetime.now()
    photo = PhotoEntry(
        id=p["id"],
        source_path=p["source_path"],
        labels=list(p.get("labels", [])),
        description=p.get("description", ""),
        timestamp=ts,
    )
    return SlotInfo(
        grid_index=d["grid_index"],
        video_index=d["video_index"],
        visual_slot=d["visual_slot"],
        row=d["row"],
        col=d["col"],
        bbox=tuple(d["bbox"]),
        click_target=tuple(d["click_target"]),
        click_box=tuple(d["click_box"]),
        target_type=d["target_type"],
        photo=photo,
        is_video=(d["type"] == "video"),
        duration=d.get("duration"),
    )


def write_grid_sidecar(
    grid_dir: Path,
    stem: str,
    app: str,
    image_path: str,
    slots: list[SlotInfo],
) -> None:
    """写 {stem}.jsonl（格子明细）和 {stem}.meta.json（app/image）。"""
    grid_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = grid_dir / f"{stem}.jsonl"
    meta_path = grid_dir / f"{stem}.meta.json"

    ordered = sorted(slots, key=lambda s: s.visual_slot)
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for slot in ordered:
            f.write(json.dumps(_slot_to_dict(slot), ensure_ascii=False) + "\n")

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"app": app, "image_path": image_path}, f, ensure_ascii=False, indent=2)


@dataclass
class GridSidecar:
    stem: str
    app: str
    image_path: str
    slots: list[SlotInfo]


def read_grid_sidecar(grid_dir: Path, stem: str) -> GridSidecar:
    jsonl_path = grid_dir / f"{stem}.jsonl"
    meta_path = grid_dir / f"{stem}.meta.json"
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    slots: list[SlotInfo] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            slots.append(_dict_to_slot(json.loads(line)))
    return GridSidecar(stem=stem, app=meta["app"], image_path=meta["image_path"], slots=slots)


def list_sidecar_stems(grid_dir: Path) -> list[str]:
    """返回所有 sidecar 的 stem（同时存在 .jsonl 和 .meta.json 的）。"""
    if not grid_dir.exists():
        return []
    stems = []
    for p in sorted(grid_dir.glob("*.jsonl")):
        stem = p.stem
        if (grid_dir / f"{stem}.meta.json").exists():
            stems.append(stem)
    return stems
