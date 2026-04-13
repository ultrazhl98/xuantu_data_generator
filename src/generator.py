"""
generator.py — 批量生成主流程（兼容入口）

本模块保留为向后兼容入口：一次性完成「渲染 + 写 sidecar + 生成指令 + 写 jsonl」。
新代码推荐直接使用：
  - src/render_stage.py:render_batch
  - src/instruction_stage.py:run_instruction_stage
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .render_stage import render_batch
from .instruction_stage import run_instruction_stage
from .instruction_types import TrainingSample


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
    n_video_sequential: int = 2,
    n_video_content: int = 2,
    model: str = "gemma4:e4b",
    max_content_workers: int = 4,
    partial_ratio: float = 0.1,
    camera_ratio: float = 0.3,
) -> list[TrainingSample]:
    """渲染阶段 + 指令阶段的 orchestration（等价于先跑 render.py 再跑 generate_instructions.py）。"""
    render_batch(
        metadata_path=metadata_path,
        output_dir=output_dir,
        count=count,
        apps=apps,
        ensure_labels=ensure_labels,
        photos_per_screen=photos_per_screen,
        seed=seed,
        show_progress=show_progress,
        video_ratio=video_ratio,
        partial_ratio=partial_ratio,
        camera_ratio=camera_ratio,
    )

    samples = run_instruction_stage(
        output_dir=output_dir,
        n_sequential=n_sequential,
        n_content=n_content,
        n_video_sequential=n_video_sequential,
        n_video_content=n_video_content,
        model=model,
        max_content_workers=max_content_workers,
        seed=seed,
        show_progress=show_progress,
    )

    if show_progress:
        img_dir = Path(output_dir) / "images"
        print(f"  图片：{img_dir}")

    return samples
