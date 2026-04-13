#!/usr/bin/env python3
"""
generate_instructions.py — 指令生成阶段 CLI

读取 output/grids/ 下的 sidecar 文件，生成训练指令并写 training_samples.jsonl。

用法：
    python generate_instructions.py
    python generate_instructions.py --n-sequential 3 --n-content 3 --seed 42
    python generate_instructions.py --output output_v2 --model gemma3:12b
"""

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent))
from src.instruction_stage import run_instruction_stage


@click.command()
@click.option("--output", default="output", show_default=True,
              help="输出目录（读取其下 grids/，写入 training_samples.jsonl）")
@click.option("--n-sequential", default=3, show_default=True,
              help="每张图生成的顺序类指令数")
@click.option("--n-content", default=3, show_default=True,
              help="每张图生成的内容类指令数")
@click.option("--n-video-sequential", default=2, show_default=True,
              help="每张图生成的视频顺序类指令数")
@click.option("--n-video-content", default=2, show_default=True,
              help="每张图生成的视频内容类指令数")
@click.option("--model", default="gemma4:e4b", show_default=True,
              help="Ollama 模型名称，用于生成内容类指令")
@click.option("--content-workers", default=4, show_default=True,
              help="内容指令并发线程数")
@click.option("--seed", default=None, type=int, help="随机种子（用于复现）")
@click.option("--samples-filename", default="training_samples.jsonl", show_default=True,
              help="输出 jsonl 文件名（相对 --output 目录）")
def main(output, n_sequential, n_content, n_video_sequential, n_video_content,
         model, content_workers, seed, samples_filename):
    run_instruction_stage(
        output_dir=output,
        n_sequential=n_sequential,
        n_content=n_content,
        n_video_sequential=n_video_sequential,
        n_video_content=n_video_content,
        model=model,
        max_content_workers=content_workers,
        seed=seed,
        show_progress=True,
        samples_filename=samples_filename,
    )


if __name__ == "__main__":
    main()
