"""
instruction_types.py — 指令生成共享类型与工具函数
"""

from __future__ import annotations

import random
from dataclasses import dataclass


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class TrainingSample:
    image_path: str
    app: str
    instruction: str
    instruction_type: str          # "sequential" | "content"
    click_targets: list[tuple]     # [(cx, cy), ...]
    click_boxes: list[tuple]       # [(x1, y1, x2, y2), ...] 每个点击目标对应的 box
    selected_grid_indices: list[int]


# ── 中文数字 ─────────────────────────────────────────────────────

_CN_NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]

def _cn(n: int) -> str:
    if 1 <= n <= len(_CN_NUMS):
        return _CN_NUMS[n - 1]
    return str(n)

def _num(n: int, rng: random.Random) -> str:
    """随机用中文数字或阿拉伯数字"""
    if n <= 10 and rng.random() < 0.5:
        return _cn(n)
    return str(n)
