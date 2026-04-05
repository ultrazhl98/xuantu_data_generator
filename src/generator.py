"""
generator.py — 批量生成主流程

调用链：SourceLibrary → renderer.render_album → instruction generators
输出：output/images/*.jpg + output/training_samples.jsonl

两阶段流水线：
  Phase A（单线程）：渲染图片 + 生成顺序指令
  Phase B（并发）：  批量生成内容指令（ollama 模型调用）
"""

from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from .app_config import AppConfig, APP_PRESETS
from .source_library import SourceLibrary
from .playwright_renderer import render_album
from .sequential_instruction import generate_sequential_samples
from .content_instruction import generate_content_samples_via_model
from .instruction_types import TrainingSample


def _pick_photo_count(
    max_photos: int, cols: int, partial_ratio: float, rng: random.Random
) -> int:
    """以 partial_ratio 的概率返回少于 max_photos 的数量，模拟非满格相册。"""
    if partial_ratio <= 0 or rng.random() >= partial_ratio:
        return max_photos
    # 双峰分布：60% 少量照片（1~2行），40% 接近满格
    if rng.random() < 0.6:
        n = rng.randint(1, min(2 * cols, max_photos))
    else:
        min_n = max(1, max_photos - cols * 2)
        n = rng.randint(min_n, max_photos - 1)
    return max(1, n)


def generate(
    metadata_path: str,
    output_dir: str,
    count: int = 100,
    apps: Optional[list[str]] = None,
    ensure_labels: Optional[list[str]] = None,
    n_sequential: int = 3,
    n_content: int = 3,
    photos_per_screen: Optional[int] = None,
    seed: Optional[int] = None,
    show_progress: bool = True,
    root_dir: Optional[str] = None,
    video_ratio: float = 0.0,
    model: str = "gemma4:e4b",
    max_content_workers: int = 4,
    partial_ratio: float = 0.1,
) -> list[TrainingSample]:
    """
    批量生成训练数据。

    参数：
        metadata_path:   source_photos/metadata.json 路径
        output_dir:      输出目录（会创建 images/ 和 annotations/ 子目录）
        count:           生成多少张合成图（每张图产出 n_seq+n_content 条样本）
        apps:            使用哪些 App（默认全部4种轮流使用）
        ensure_labels:   每张图保证包含这些类别的图片各至少一张
        n_sequential:    每张合成图生成的顺序类指令数
        n_content:       每张合成图生成的内容类指令数
        photos_per_screen: 每屏显示图片数（None = 用 config.max_photos）
        seed:            随机种子（可复现）
        max_content_workers: 内容指令并发线程数
    """
    rng = random.Random(seed)
    library = SourceLibrary(metadata_path)

    if len(library) == 0:
        raise ValueError(f"metadata.json 中没有图片条目，请先运行 label_photos.py")

    selected_apps = apps or list(APP_PRESETS.keys())
    configs: list[AppConfig] = [APP_PRESETS[a] for a in selected_apps if a in APP_PRESETS]
    if not configs:
        raise ValueError(f"未找到有效的 App 配置，可用：{list(APP_PRESETS.keys())}")

    out_path = Path(output_dir)
    img_dir = out_path / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    samples_path = out_path / "training_samples.jsonl"

    all_samples: list[TrainingSample] = []

    if show_progress:
        try:
            from tqdm import tqdm
            iterator = tqdm(range(count), desc="渲染图片 + 顺序指令")
        except ImportError:
            iterator = range(count)
    else:
        iterator = range(count)

    # ── Phase A：渲染 + 顺序指令（单线程） ──────────────────────
    content_tasks: list[tuple] = []  # (img_rel_path, image_slots, app_name, n_content, model)

    for i in iterator:
        config = configs[i % len(configs)]
        base_n = photos_per_screen or config.max_photos
        n_photos = _pick_photo_count(base_n, config.cols, partial_ratio, rng)

        # 采样图片（保证 ensure_labels 中的类别各至少出现一次）
        photos = library.sample(
            n=n_photos,
            required_labels=ensure_labels,
            shuffle=True,
            rng=rng,
        )
        if not photos:
            continue

        # 决定哪些格子是视频（保证可复现）
        _ratio = video_ratio if video_ratio > 0 else 0.0
        if _ratio > 0:
            is_video_list = [rng.random() < _ratio for _ in range(len(photos))]
            durations = [
                f"{rng.randint(0, 5):02d}:{rng.randint(0, 59):02d}" if iv else None
                for iv in is_video_list
            ]
        else:
            is_video_list = [False] * len(photos)
            durations = [None] * len(photos)

        # 渲染
        img_filename = f"{i:05d}.jpg"
        img_abs_path = str(img_dir / img_filename)
        img, slots = render_album(config, photos, is_video_list=is_video_list, durations=durations)
        img.save(img_abs_path, quality=92)

        # 过滤出纯图片格用于指令生成（跳过视频格）
        image_slots = [s for s in slots if not s.is_video]

        if not image_slots:
            continue

        # 生成顺序指令（纯计算，瞬时完成）
        img_rel_path = str(Path("output/images") / img_filename)
        seq_samples = generate_sequential_samples(
            slots=image_slots,
            image_path=img_rel_path,
            app=config.name,
            n=n_sequential,
            rng=rng,
        )
        all_samples.extend(seq_samples)

        # 收集内容指令任务参数
        if n_content > 0:
            content_tasks.append((img_rel_path, image_slots, config.name, n_content, model))

    # ── Phase B：并发生成内容指令 ────────────────────────────────
    if content_tasks:
        workers = min(max_content_workers, len(content_tasks))

        if show_progress:
            print(f"\n开始并发生成内容指令（{len(content_tasks)} 张图，{workers} 线程）...")

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    generate_content_samples_via_model,
                    slots=task[1],
                    image_path=task[0],
                    app=task[2],
                    n=task[3],
                    model=task[4],
                )
                for task in content_tasks
            ]
            # 按提交顺序收集结果，保证 JSONL 输出可复现
            for future in futures:
                try:
                    all_samples.extend(future.result())
                except Exception as e:
                    print(f"警告：内容指令生成失败：{e}", file=sys.stderr)

    # 写 JSONL
    with open(samples_path, "w", encoding="utf-8") as f:
        for s in all_samples:
            record = {
                "image": s.image_path,
                "app": s.app,
                "instruction": s.instruction,
                "instruction_type": s.instruction_type,
                "click_targets": [list(t) for t in s.click_targets],
                "click_boxes": [list(b) for b in s.click_boxes],
                "selected_grid_indices": s.selected_grid_indices,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    if show_progress:
        print(f"\n完成：生成 {count} 张图，{len(all_samples)} 条训练样本")
        print(f"  图片：{img_dir}")
        print(f"  训练数据：{samples_path}")

    return all_samples
