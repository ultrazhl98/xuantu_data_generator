"""
video_sequential_instruction.py — 基于顺序的视频指令生成（纯计算，无模型调用）

支持：单个定位、行列定位、多选、最新N个、最后N个、时长筛选
"""

from __future__ import annotations

import random
from typing import Optional

from .renderer import SlotInfo
from .instruction_types import TrainingSample, _cn, _num


def _parse_duration(d: str) -> int:
    """将 "mm:ss" 格式的时长转换为秒数"""
    parts = d.split(":")
    return int(parts[0]) * 60 + int(parts[1])


# ── 单个定位 ─────────────────────────────────────────────────────

def _make_single_video_index(slot: SlotInfo, image_path: str, app: str,
                              rng: random.Random) -> TrainingSample:
    n = _num(slot.video_index, rng)
    templates = [
        f"播放第{n}个视频",
        f"发送第{n}个视频",
        f"选择第{n}个视频",
        f"把第{n}个视频发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="video_sequential",
        click_targets=[slot.click_target],
        click_boxes=[slot.click_box],
        selected_grid_indices=[slot.video_index],
    )


# ── 行列定位 ─────────────────────────────────────────────────────

def _make_video_row_col(slot: SlotInfo, image_path: str, app: str,
                         rng: random.Random) -> TrainingSample:
    r = _num(slot.row + 1, rng)
    c = _num(slot.col + 1, rng)
    templates = [
        f"播放第{r}行第{c}列的视频",
        f"选择第{r}排第{c}个视频",
        f"第{r}行第{c}列那个视频发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="video_sequential",
        click_targets=[slot.click_target],
        click_boxes=[slot.click_box],
        selected_grid_indices=[slot.video_index],
    )


# ── 多选 ─────────────────────────────────────────────────────────

def _make_multi_video_index(slots_subset: list[SlotInfo], image_path: str, app: str,
                             rng: random.Random) -> TrainingSample:
    indices = [s.video_index for s in slots_subset]
    indices_str = "、".join(_num(i, rng) for i in indices)
    if len(indices) >= 2 and indices[-1] - indices[0] == len(indices) - 1:
        n1, n2 = _num(indices[0], rng), _num(indices[-1], rng)
        templates = [
            f"发送第{n1}到第{n2}个视频",
            f"选择第{n1}至{n2}个视频",
        ]
    else:
        templates = [
            f"选择第{indices_str}个视频",
            f"发送第{indices_str}个视频",
            f"把第{indices_str}个视频发过来",
        ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="video_sequential",
        click_targets=[s.click_target for s in slots_subset],
        click_boxes=[s.click_box for s in slots_subset],
        selected_grid_indices=indices,
    )


# ── 最新 N 个 ────────────────────────────────────────────────────

def _make_newest_n_videos(slots: list[SlotInfo], n: int, image_path: str, app: str,
                           rng: random.Random) -> Optional[TrainingSample]:
    """最新 N 个视频（video_index 最小的 N 个，因左上角最新）"""
    sorted_slots = sorted(slots, key=lambda s: s.video_index)
    chosen = sorted_slots[:n]
    if len(chosen) < n:
        return None
    num_str = _num(n, rng)
    templates = [
        f"发送最新的{num_str}个视频",
        f"选择最近{num_str}个视频",
        f"把最新的{num_str}个视频发给我",
    ]
    if n == 1:
        templates += ["发送最新的视频", "选择最近的一个视频"]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="video_sequential",
        click_targets=[s.click_target for s in chosen],
        click_boxes=[s.click_box for s in chosen],
        selected_grid_indices=[s.video_index for s in chosen],
    )


# ── 最后 N 个 ────────────────────────────────────────────────────

def _make_last_n_videos(slots: list[SlotInfo], n: int, image_path: str, app: str,
                         rng: random.Random) -> Optional[TrainingSample]:
    """最后 N 个视频（video_index 最大的 N 个）"""
    sorted_slots = sorted(slots, key=lambda s: s.video_index, reverse=True)
    chosen = sorted_slots[:n]
    if len(chosen) < n:
        return None
    num_str = _num(n, rng)
    templates = [
        f"发送最后{num_str}个视频",
        f"选择最末{num_str}个视频",
        f"把最后{num_str}个视频发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="video_sequential",
        click_targets=[s.click_target for s in chosen],
        click_boxes=[s.click_box for s in chosen],
        selected_grid_indices=[s.video_index for s in chosen],
    )


# ── 时长筛选 ─────────────────────────────────────────────────────

def _make_duration_filter(slots: list[SlotInfo], image_path: str, app: str,
                           rng: random.Random) -> Optional[TrainingSample]:
    """根据时长筛选视频：最长/最短/超过阈值"""
    valid = [s for s in slots if s.duration]
    if not valid:
        return None

    durations = [(s, _parse_duration(s.duration)) for s in valid]

    strategy = rng.choice(["longest", "shortest", "threshold"])

    if strategy == "longest":
        max_sec = max(d[1] for d in durations)
        chosen = [s for s, sec in durations if sec == max_sec]
        templates = ["播放最长的视频", "发送时间最长的视频", "把最长的那个视频发给我"]

    elif strategy == "shortest":
        min_sec = min(d[1] for d in durations)
        chosen = [s for s, sec in durations if sec == min_sec]
        templates = ["播放最短的视频", "发送时间最短的视频", "把最短的那个视频发给我"]

    else:  # threshold
        all_secs = sorted(set(d[1] for d in durations))
        if len(all_secs) < 2:
            # 无法设置有效阈值，回退到最长
            max_sec = all_secs[0]
            chosen = [s for s, sec in durations if sec == max_sec]
            templates = ["播放最长的视频", "发送时间最长的视频"]
        else:
            # 选一个中间阈值，保证至少1个但不是全部匹配
            mid = all_secs[len(all_secs) // 2]
            chosen_over = [s for s, sec in durations if sec >= mid]
            chosen_under = [s for s, sec in durations if sec < mid]

            if rng.random() < 0.5 and chosen_over and len(chosen_over) < len(valid):
                chosen = chosen_over
                mins = mid // 60
                secs = mid % 60
                if mins > 0:
                    templates = [f"发送时长超过{mins}分钟的视频", f"选择超过{mins}分钟的视频"]
                else:
                    templates = [f"发送时长超过{secs}秒的视频", f"选择超过{secs}秒的视频"]
            elif chosen_under and len(chosen_under) < len(valid):
                chosen = chosen_under
                mins = mid // 60
                secs = mid % 60
                if mins > 0:
                    templates = [f"发送不到{mins}分钟的视频", f"选择时长不到{mins}分钟的视频"]
                else:
                    templates = [f"发送不到{secs}秒的视频", f"选择时长不到{secs}秒的视频"]
            else:
                max_sec = max(d[1] for d in durations)
                chosen = [s for s, sec in durations if sec == max_sec]
                templates = ["播放最长的视频", "发送时间最长的视频"]

    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="video_sequential",
        click_targets=[s.click_target for s in chosen],
        click_boxes=[s.click_box for s in chosen],
        selected_grid_indices=[s.video_index for s in chosen],
    )


# ── 公开入口 ─────────────────────────────────────────────────────

def generate_video_sequential_samples(
    slots: list[SlotInfo],
    image_path: str,
    app: str,
    n: int = 2,
    rng: Optional[random.Random] = None,
) -> list[TrainingSample]:
    """
    从视频 slots 信息中生成视频顺序类训练样本。

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
        "duration": [],
    }

    # 单个定位
    for slot in slots:
        buckets["single"].append(_make_single_video_index(slot, image_path, app, rng))
        if slot.row > 0 or slot.col > 0:
            buckets["row_col"].append(_make_video_row_col(slot, image_path, app, rng))

    # 多选：随机选 2~3 个
    if num_slots >= 2:
        for _ in range(min(3, num_slots)):
            k = rng.randint(2, min(3, num_slots))
            chosen = sorted(rng.sample(slots, k), key=lambda s: s.video_index)
            buckets["multi"].append(_make_multi_video_index(chosen, image_path, app, rng))

    # 最新/最后 N 个
    for cnt in [1, 2, 3]:
        s = _make_newest_n_videos(slots, cnt, image_path, app, rng)
        if s:
            buckets["newest"].append(s)
        s = _make_last_n_videos(slots, cnt, image_path, app, rng)
        if s:
            buckets["last"].append(s)

    # 时长筛选
    s = _make_duration_filter(slots, image_path, app, rng)
    if s:
        buckets["duration"].append(s)

    # ── 分桶轮流抽取，保证类型均衡 ──────────────────────────────
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
            active_keys.remove(key)
            if not active_keys:
                break
            key_pos = key_pos % len(active_keys) if active_keys else 0

    return results
