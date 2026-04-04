"""
source_library.py — 源图库管理

读取 metadata.json，提供按 label / timestamp 条件采样的接口。

metadata.json 格式：
[
  {
    "id": "cat_001",
    "path": "source_photos/images/cat/cat_001.jpg",   // 相对于项目根目录
    "labels": ["cat", "indoor"],
    "description": "一只橘色的猫趴在沙发上",
    "timestamp": "2024-03-15T14:22:00"
  },
  ...
]
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PhotoEntry:
    id: str
    source_path: str          # 绝对路径
    labels: list[str]
    description: str
    timestamp: datetime

    def has_label(self, label: str) -> bool:
        return label.lower() in [l.lower() for l in self.labels]

    def has_any_label(self, labels: list[str]) -> bool:
        return any(self.has_label(l) for l in labels)


class SourceLibrary:
    def __init__(self, metadata_path: str, root_dir: Optional[str] = None):
        """
        metadata_path: metadata.json 的路径
        root_dir: 图片路径的根目录（默认为 metadata.json 所在目录的父目录）
        """
        meta_path = Path(metadata_path)
        self.root_dir = Path(root_dir) if root_dir else meta_path.parent.parent

        with open(meta_path, encoding="utf-8") as f:
            raw = json.load(f)

        self.photos: list[PhotoEntry] = []
        for item in raw:
            abs_path = str(self.root_dir / item["path"])
            ts = datetime.fromisoformat(item["timestamp"]) if item.get("timestamp") else datetime.now()
            self.photos.append(PhotoEntry(
                id=item["id"],
                source_path=abs_path,
                labels=item.get("labels", []),
                description=item.get("description", ""),
                timestamp=ts,
            ))

    def all_labels(self) -> list[str]:
        """返回库中所有出现过的标签（去重）"""
        seen = set()
        result = []
        for p in self.photos:
            for l in p.labels:
                if l not in seen:
                    seen.add(l)
                    result.append(l)
        return result

    def by_label(self, label: str) -> list[PhotoEntry]:
        return [p for p in self.photos if p.has_label(label)]

    def sample(
        self,
        n: int,
        required_labels: Optional[list[str]] = None,
        shuffle: bool = True,
        timestamp_mode: str = "random",   # "random" | "newest_first" | "oldest_first"
        rng: Optional[random.Random] = None,
    ) -> list[PhotoEntry]:
        """
        采样 n 张图片。

        required_labels: 若指定，保证采样结果中每个 label 至少出现一次。
        timestamp_mode:
            - "random": 随机分配时间戳顺序
            - "newest_first": 按时间戳降序（左上角=最新）
            - "oldest_first": 按时间戳升序
        """
        rng = rng or random.Random()
        pool = list(self.photos)

        # 先把 required_labels 对应的图片各选一张放入结果
        selected: list[PhotoEntry] = []
        if required_labels:
            for label in required_labels:
                candidates = [p for p in pool if p.has_label(label) and p not in selected]
                if candidates:
                    chosen = rng.choice(candidates)
                    selected.append(chosen)

        # 从剩余 pool 补齐到 n
        remaining = [p for p in pool if p not in selected]
        need = max(0, n - len(selected))
        if need > 0:
            additional = rng.sample(remaining, min(need, len(remaining)))
            selected.extend(additional)

        # 截断或补足
        selected = selected[:n]

        # 排序
        if timestamp_mode == "newest_first":
            selected.sort(key=lambda p: p.timestamp, reverse=True)
        elif timestamp_mode == "oldest_first":
            selected.sort(key=lambda p: p.timestamp)
        elif shuffle:
            rng.shuffle(selected)

        return selected

    def __len__(self):
        return len(self.photos)
