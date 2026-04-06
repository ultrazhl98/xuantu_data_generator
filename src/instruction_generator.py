"""
instruction_generator.py — 训练指令生成（门面模块）

实际实现已拆分至：
- instruction_types.py:          共享数据结构
- sequential_instruction.py:     顺序类指令（纯计算）
- content_instruction.py:        内容类指令（模型驱动）

本文件保留 generate_samples() 入口和 re-export，保持向后兼容。
"""

from __future__ import annotations

import random
import sys
from typing import Optional

from .renderer import SlotInfo
from .app_config import AppConfig

# Re-export
from .instruction_types import TrainingSample
from .sequential_instruction import generate_sequential_samples
from .content_instruction import generate_content_samples_via_model
from .video_sequential_instruction import generate_video_sequential_samples
from .video_content_instruction import generate_video_content_samples_via_model


def generate_samples(
    image_path: str,
    slots: list[SlotInfo],
    config: AppConfig,
    n_sequential: int = 3,
    n_content: int = 3,
    model: str = "gemma4:e4b",
    rng: Optional[random.Random] = None,
) -> list[TrainingSample]:
    """
    从一张合成图的 slots 信息中生成训练样本列表。

    n_sequential: 生成的顺序类指令数（每张图随机抽取）
    n_content:    生成的内容类指令数
    model:        用于生成内容类指令的 Ollama 模型名称
    """
    rng = rng or random.Random()
    if not slots:
        return []

    samples: list[TrainingSample] = []

    # ── 顺序类 ───────────────────────────────────────────────────
    samples.extend(generate_sequential_samples(
        slots=slots,
        image_path=image_path,
        app=config.name,
        n=n_sequential,
        rng=rng,
    ))

    # ── 内容类（模型驱动） ───────────────────────────────────────
    if n_content > 0:
        try:
            content_samples = generate_content_samples_via_model(
                slots=slots,
                image_path=image_path,
                app=config.name,
                n=n_content,
                model=model,
            )
            samples.extend(content_samples)
        except Exception as e:
            print(f"警告：内容指令生成失败：{e}", file=sys.stderr)

    return samples
