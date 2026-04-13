"""
sequential_instruction.py — 基于顺序的指令生成（纯计算，无模型调用）

支持：单张定位、行列定位、多选、最新N张、最后N张
"""

from __future__ import annotations

import random
from typing import Optional

from .renderer import SlotInfo
from .instruction_types import TrainingSample, _cn, _num, cell_from_slot


# ── 单张定位 ─────────────────────────────────────────────────────

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
        click_boxes=[slot.click_box],
        selected_grid_indices=[slot.grid_index],
        selected_cells=[cell_from_slot(slot)],
    )


# ── 行列定位 ─────────────────────────────────────────────────────

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
        click_boxes=[slot.click_box],
        selected_grid_indices=[slot.grid_index],
        selected_cells=[cell_from_slot(slot)],
    )


# ── 多选 ─────────────────────────────────────────────────────────

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
        click_boxes=[s.click_box for s in slots_subset],
        selected_grid_indices=indices,
        selected_cells=[cell_from_slot(s) for s in slots_subset],
    )


# ── 最新 N 张 ────────────────────────────────────────────────────

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
        click_boxes=[s.click_box for s in chosen],
        selected_grid_indices=[s.grid_index for s in chosen],
        selected_cells=[cell_from_slot(s) for s in chosen],
    )


# ── 最后 N 张 ────────────────────────────────────────────────────

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
        click_boxes=[s.click_box for s in chosen],
        selected_grid_indices=[s.grid_index for s in chosen],
        selected_cells=[cell_from_slot(s) for s in chosen],
    )


# ── 公开入口 ─────────────────────────────────────────────────────

def generate_sequential_samples(
    slots: list[SlotInfo],
    image_path: str,
    app: str,
    n: int = 3,
    rng: Optional[random.Random] = None,
) -> list[TrainingSample]:
    """
    从 slots 信息中生成顺序类训练样本。

    n: 最终返回的指令数（从候选池中随机抽取）
    """
    rng = rng or random.Random()
    if not slots:
        return []

    num_slots = len(slots)

    # ── 按类型分桶生成候选 ──────────────────────────────────────
    buckets: dict[str, list[TrainingSample]] = {
        "single": [],
        "row_col": [],
        "multi": [],
        "newest": [],
        "last": [],
    }

    # 单张定位
    for slot in slots:
        buckets["single"].append(_make_single_index(slot, image_path, app, rng))
        if slot.row > 0 or slot.col > 0:
            buckets["row_col"].append(_make_row_col(slot, image_path, app, rng))

    # 多选：随机选 2~3 张
    if num_slots >= 2:
        for _ in range(min(3, num_slots)):
            k = rng.randint(2, min(3, num_slots))
            chosen = sorted(rng.sample(slots, k), key=lambda s: s.grid_index)
            buckets["multi"].append(_make_multi_index(chosen, image_path, app, rng))

    # 最新/最后 N 张
    for cnt in [1, 2, 3]:
        s = _make_newest_n(slots, cnt, image_path, app, rng)
        if s:
            buckets["newest"].append(s)
        s = _make_last_n(slots, cnt, image_path, app, rng)
        if s:
            buckets["last"].append(s)

    # ── 分桶轮流抽取，保证类型均衡 ──────────────────────────────
    # 过滤空桶，桶内打乱
    active_keys = [k for k, v in buckets.items() if v]
    for k in active_keys:
        rng.shuffle(buckets[k])
    rng.shuffle(active_keys)

    results: list[TrainingSample] = []
    bucket_idx = {k: 0 for k in active_keys}
    key_pos = 0
    while len(results) < n and active_keys:
        key = active_keys[key_pos % len(active_keys)]
        idx = bucket_idx[key]
        if idx < len(buckets[key]):
            results.append(buckets[key][idx])
            bucket_idx[key] = idx + 1
            key_pos += 1
        else:
            # 该桶已用完，移除
            active_keys.remove(key)
            if not active_keys:
                break
            key_pos = key_pos % len(active_keys) if active_keys else 0

    return results
