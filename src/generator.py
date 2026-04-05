"""
generator.py — 批量生成主流程

调用链：SourceLibrary → renderer.render_album → instruction_generator.generate_samples
输出：output/images/*.jpg + output/training_samples.jsonl
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from .app_config import AppConfig, APP_PRESETS
from .source_library import SourceLibrary
from .playwright_renderer import render_album
from .instruction_generator import generate_samples, TrainingSample


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
            iterator = tqdm(range(count), desc="生成合成图")
        except ImportError:
            iterator = range(count)
    else:
        iterator = range(count)

    for i in iterator:
        config = configs[i % len(configs)]
        n_photos = photos_per_screen or config.max_photos

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

        # 生成指令
        img_rel_path = str(Path("output/images") / img_filename)
        samples = generate_samples(
            image_path=img_rel_path,
            slots=image_slots,
            config=config,
            n_sequential=n_sequential,
            n_content=n_content,
            model=model,
            rng=rng,
        )
        all_samples.extend(samples)

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
