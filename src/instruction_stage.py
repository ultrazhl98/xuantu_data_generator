"""
instruction_stage.py — 指令生成阶段：读 sidecar → 调用指令生成器 → 写 JSONL
"""

from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from .grid_sidecar import GridSidecar, list_sidecar_stems, read_grid_sidecar
from .instruction_types import TrainingSample
from .sequential_instruction import generate_sequential_samples
from .content_instruction import generate_content_samples_via_model
from .video_sequential_instruction import generate_video_sequential_samples
from .video_content_instruction import generate_video_content_samples_via_model


def sample_to_record(s: TrainingSample) -> dict:
    return {
        "image": s.image_path,
        "app": s.app,
        "instruction": s.instruction,
        "instruction_type": s.instruction_type,
        "click_targets": [list(t) for t in s.click_targets],
        "click_boxes": [list(b) for b in s.click_boxes],
        "selected_grid_indices": s.selected_grid_indices,
        "selected_cells": s.selected_cells,
    }


def generate_for_sidecar(
    sidecar: GridSidecar,
    n_sequential: int,
    n_content: int,
    n_video_sequential: int,
    n_video_content: int,
    model: str,
    rng: random.Random,
) -> tuple[list[TrainingSample], list[tuple], list[tuple]]:
    """
    对单个 sidecar 生成顺序类样本（同步），并收集内容类任务（延后并发）。

    返回 (seq_samples, content_tasks, video_content_tasks)
      content_tasks 项：(image_slots, sidecar.image_path, sidecar.app, n, model)
    """
    image_slots = [s for s in sidecar.slots if not s.is_video]
    video_slots = [s for s in sidecar.slots if s.is_video]

    seq_samples: list[TrainingSample] = []
    if image_slots and n_sequential > 0:
        seq_samples.extend(generate_sequential_samples(
            slots=image_slots, image_path=sidecar.image_path,
            app=sidecar.app, n=n_sequential, rng=rng,
        ))
    if video_slots and n_video_sequential > 0:
        seq_samples.extend(generate_video_sequential_samples(
            slots=video_slots, image_path=sidecar.image_path,
            app=sidecar.app, n=n_video_sequential, rng=rng,
        ))

    content_tasks: list[tuple] = []
    video_content_tasks: list[tuple] = []
    if image_slots and n_content > 0:
        content_tasks.append((image_slots, sidecar.image_path, sidecar.app, n_content, model))
    if video_slots and n_video_content > 0:
        video_content_tasks.append((video_slots, sidecar.image_path, sidecar.app, n_video_content, model))

    return seq_samples, content_tasks, video_content_tasks


def run_instruction_stage(
    output_dir: str,
    n_sequential: int = 3,
    n_content: int = 3,
    n_video_sequential: int = 2,
    n_video_content: int = 2,
    model: str = "gemma4:e4b",
    max_content_workers: int = 4,
    seed: Optional[int] = None,
    show_progress: bool = True,
    samples_filename: str = "training_samples.jsonl",
) -> list[TrainingSample]:
    """读取 output/grids/ 下所有 sidecar，生成指令并写 jsonl。"""
    rng = random.Random(seed)
    out_path = Path(output_dir)
    grid_dir = out_path / "grids"
    samples_path = out_path / samples_filename

    stems = list_sidecar_stems(grid_dir)
    if not stems:
        raise ValueError(f"未在 {grid_dir} 找到任何 sidecar（.jsonl + .meta.json）")

    if show_progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(stems, desc="顺序指令")
        except ImportError:
            iterator = stems
    else:
        iterator = stems

    all_samples: list[TrainingSample] = []
    all_content_tasks: list[tuple] = []
    all_video_content_tasks: list[tuple] = []

    for stem in iterator:
        sidecar = read_grid_sidecar(grid_dir, stem)
        seq_samples, content_tasks, video_content_tasks = generate_for_sidecar(
            sidecar=sidecar,
            n_sequential=n_sequential,
            n_content=n_content,
            n_video_sequential=n_video_sequential,
            n_video_content=n_video_content,
            model=model,
            rng=rng,
        )
        all_samples.extend(seq_samples)
        all_content_tasks.extend(content_tasks)
        all_video_content_tasks.extend(video_content_tasks)

    # 并发生成内容指令
    total_content = len(all_content_tasks) + len(all_video_content_tasks)
    if total_content > 0:
        workers = min(max_content_workers, total_content)
        if show_progress:
            print(f"\n开始并发生成内容指令（图片 {len(all_content_tasks)} 张 + "
                  f"视频 {len(all_video_content_tasks)} 张，{workers} 线程）...")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for task in all_content_tasks:
                futures.append(executor.submit(
                    generate_content_samples_via_model,
                    slots=task[0], image_path=task[1], app=task[2],
                    n=task[3], model=task[4],
                ))
            for task in all_video_content_tasks:
                futures.append(executor.submit(
                    generate_video_content_samples_via_model,
                    slots=task[0], image_path=task[1], app=task[2],
                    n=task[3], model=task[4],
                ))
            for future in futures:
                try:
                    all_samples.extend(future.result())
                except Exception as e:
                    print(f"警告：内容指令生成失败：{e}", file=sys.stderr)

    with open(samples_path, "w", encoding="utf-8") as f:
        for s in all_samples:
            f.write(json.dumps(sample_to_record(s), ensure_ascii=False) + "\n")

    if show_progress:
        print(f"\n完成：{len(all_samples)} 条训练样本")
        print(f"  训练数据：{samples_path}")

    return all_samples
