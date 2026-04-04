"""
instruction_generator.py — 训练指令生成

支持两大类指令：
1. 顺序类：基于 grid_index / row / col / timestamp，纯逻辑生成
2. 内容类：基于 photo.labels，扫描可见 slots 后生成

每条指令生成一个 TrainingSample。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from .renderer import SlotInfo
from .app_config import AppConfig


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class TrainingSample:
    image_path: str
    app: str
    instruction: str
    instruction_type: str          # "sequential" | "content"
    click_targets: list[tuple]     # [(cx, cy), ...]
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


# ── 顺序类指令 ────────────────────────────────────────────────────

def _make_single_index(slot: SlotInfo, image_path: str, app: str,
                        rng: random.Random) -> TrainingSample:
    n = _num(slot.grid_index, rng)
    templates = [
        f"发送第{n}张图片",
        f"选择第{n}张照片",
        f"分享第{n}张图片",
        f"把第{n}张图片发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[slot.click_target],
        selected_grid_indices=[slot.grid_index],
    )


def _make_row_col(slot: SlotInfo, image_path: str, app: str,
                   rng: random.Random) -> TrainingSample:
    r = _num(slot.row + 1, rng)
    c = _num(slot.col + 1, rng)
    templates = [
        f"发送第{r}行第{c}列的图片",
        f"选择第{r}排第{c}个照片",
        f"第{r}行第{c}列那张图片发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[slot.click_target],
        selected_grid_indices=[slot.grid_index],
    )


def _make_multi_index(slots_subset: list[SlotInfo], image_path: str, app: str,
                       rng: random.Random) -> TrainingSample:
    indices = [s.grid_index for s in slots_subset]
    indices_str = "、".join(_num(i, rng) for i in indices)
    # 连续范围 or 离散
    if len(indices) >= 2 and indices[-1] - indices[0] == len(indices) - 1:
        n1, n2 = _num(indices[0], rng), _num(indices[-1], rng)
        templates = [
            f"发送第{n1}到第{n2}张图片",
            f"选择第{n1}至{n2}张照片",
        ]
    else:
        templates = [
            f"选择第{indices_str}张图片",
            f"发送第{indices_str}张照片",
            f"把第{indices_str}张图片发过来",
        ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[s.click_target for s in slots_subset],
        selected_grid_indices=indices,
    )


def _make_newest_n(slots: list[SlotInfo], n: int, image_path: str, app: str,
                    rng: random.Random) -> Optional[TrainingSample]:
    """最新 N 张（grid_index 最小的 N 张，因左上角最新）"""
    sorted_slots = sorted(slots, key=lambda s: s.grid_index)
    chosen = sorted_slots[:n]
    if len(chosen) < n:
        return None
    num_str = _num(n, rng)
    templates = [
        f"发送最新的{num_str}张图片",
        f"选择最近{num_str}张照片",
        f"把最新的{num_str}张图发给我",
    ]
    if n == 1:
        templates += ["发送最新的图片", "选择最近的一张照片"]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[s.click_target for s in chosen],
        selected_grid_indices=[s.grid_index for s in chosen],
    )


def _make_last_n(slots: list[SlotInfo], n: int, image_path: str, app: str,
                  rng: random.Random) -> Optional[TrainingSample]:
    """最后 N 张（grid_index 最大的 N 张）"""
    sorted_slots = sorted(slots, key=lambda s: s.grid_index, reverse=True)
    chosen = sorted_slots[:n]
    if len(chosen) < n:
        return None
    num_str = _num(n, rng)
    templates = [
        f"发送最后{num_str}张图片",
        f"选择最末{num_str}张照片",
        f"把最后{num_str}张图发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[s.click_target for s in chosen],
        selected_grid_indices=[s.grid_index for s in chosen],
    )


# ── 内容类指令 ────────────────────────────────────────────────────

# 标签 → 中文名称映射
_LABEL_ZH: dict[str, list[str]] = {
    "cat": ["小猫", "猫咪", "猫"],
    "dog": ["小狗", "狗狗", "狗"],
    "car": ["汽车", "车", "轿车"],
    "landscape": ["风景", "景色", "自然风光"],
    "food": ["食物", "美食", "吃的"],
    "person": ["人物", "人像"],
    "flower": ["花", "花朵"],
    "building": ["建筑", "楼", "房子"],
    "screenshot": ["截图", "屏幕截图"],
    "selfie": ["自拍", "自拍照"],
    "night": ["夜景", "夜晚"],
    "beach": ["海滩", "沙滩", "海边"],
    "mountain": ["山", "山景", "山峰"],
    "city": ["城市", "街景"],
    "animal": ["动物"],
    "sky": ["天空", "蓝天"],
    "sunset": ["日落", "夕阳", "落日"],
}

def _label_zh(label: str, rng: random.Random) -> str:
    candidates = _LABEL_ZH.get(label.lower())
    if candidates:
        return rng.choice(candidates)
    return label  # 未知标签直接用英文或原文


def _make_all_label(label: str, matching_slots: list[SlotInfo],
                     image_path: str, app: str, rng: random.Random) -> TrainingSample:
    zh = _label_zh(label, rng)
    templates = [
        f"发送{zh}的图片",
        f"选择{zh}照片",
        f"把所有{zh}的图片发给我",
        f"发送所有{zh}图片",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="content",
        click_targets=[s.click_target for s in matching_slots],
        selected_grid_indices=[s.grid_index for s in matching_slots],
    )


def _make_nth_label(label: str, n: int, nth_slot: SlotInfo,
                     image_path: str, app: str, rng: random.Random) -> TrainingSample:
    zh = _label_zh(label, rng)
    num_str = _num(n, rng)
    templates = [
        f"发送第{num_str}个{zh}的图片",
        f"选择第{num_str}张{zh}照片",
        f"第{num_str}个{zh}那张图发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="content",
        click_targets=[nth_slot.click_target],
        selected_grid_indices=[nth_slot.grid_index],
    )


def _make_multi_label(labels: list[str], matching_slots: list[SlotInfo],
                       image_path: str, app: str, rng: random.Random) -> TrainingSample:
    zh_parts = [_label_zh(l, rng) for l in labels]
    zh_str = "和".join(zh_parts)
    templates = [
        f"发送{zh_str}的图片",
        f"选择{zh_str}照片",
        f"把{zh_str}的图片都发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="content",
        click_targets=[s.click_target for s in matching_slots],
        selected_grid_indices=[s.grid_index for s in matching_slots],
    )


# ── 主生成函数 ────────────────────────────────────────────────────

def generate_samples(
    image_path: str,
    slots: list[SlotInfo],
    config: AppConfig,
    n_sequential: int = 3,
    n_content: int = 3,
    rng: Optional[random.Random] = None,
) -> list[TrainingSample]:
    """
    从一张合成图的 slots 信息中生成训练样本列表。

    n_sequential: 生成的顺序类指令数（每张图随机抽取）
    n_content:    生成的内容类指令数
    """
    rng = rng or random.Random()
    samples: list[TrainingSample] = []
    n = len(slots)
    if n == 0:
        return samples

    # ── 顺序类 ───────────────────────────────────────────────────
    sequential_candidates: list[TrainingSample] = []

    # 单张定位
    for slot in slots:
        sequential_candidates.append(_make_single_index(slot, image_path, config.name, rng))
        if slot.row > 0 or slot.col > 0:   # 行列坐标（1,1 以外才有意义说出来）
            sequential_candidates.append(_make_row_col(slot, image_path, config.name, rng))

    # 多选：随机选 2~3 张
    if n >= 2:
        for _ in range(min(3, n)):
            k = rng.randint(2, min(3, n))
            chosen = sorted(rng.sample(slots, k), key=lambda s: s.grid_index)
            sequential_candidates.append(_make_multi_index(chosen, image_path, config.name, rng))

    # 最新/最后 N 张
    for cnt in [1, 2, 3]:
        s = _make_newest_n(slots, cnt, image_path, config.name, rng)
        if s:
            sequential_candidates.append(s)
        s = _make_last_n(slots, cnt, image_path, config.name, rng)
        if s:
            sequential_candidates.append(s)

    rng.shuffle(sequential_candidates)
    samples.extend(sequential_candidates[:n_sequential])

    # ── 内容类 ───────────────────────────────────────────────────
    # 统计可见 slots 中各 label 的 slots（按 grid_index 排序）
    label_slots: dict[str, list[SlotInfo]] = {}
    for slot in sorted(slots, key=lambda s: s.grid_index):
        for label in slot.photo.labels:
            label_slots.setdefault(label, []).append(slot)

    content_candidates: list[TrainingSample] = []

    # 单 label：全部选
    for label, matching in label_slots.items():
        content_candidates.append(
            _make_all_label(label, matching, image_path, config.name, rng)
        )

    # 单 label 第 N 个
    for label, matching in label_slots.items():
        if len(matching) >= 2:
            for idx, slot in enumerate(matching, start=1):
                content_candidates.append(
                    _make_nth_label(label, idx, slot, image_path, config.name, rng)
                )

    # 多 label 组合（随机选2个 label）
    all_labels = list(label_slots.keys())
    if len(all_labels) >= 2:
        for _ in range(min(4, len(all_labels))):
            picked_labels = rng.sample(all_labels, 2)
            combined_slots = []
            seen_ids = set()
            for lbl in picked_labels:
                for s in label_slots[lbl]:
                    if s.photo.id not in seen_ids:
                        combined_slots.append(s)
                        seen_ids.add(s.photo.id)
            if combined_slots:
                content_candidates.append(
                    _make_multi_label(picked_labels, combined_slots, image_path, config.name, rng)
                )

    rng.shuffle(content_candidates)
    samples.extend(content_candidates[:n_content])

    return samples
