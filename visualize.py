#!/usr/bin/env python3
"""
visualize.py — 对已有 training_samples.jsonl 生成可视化图

用法：
    python visualize.py                                    # 默认读 output/training_samples.jsonl
    python visualize.py --output output --jsonl run2.jsonl
    python visualize.py --jsonl path/to/any.jsonl          # 任意 jsonl 路径
"""

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent))
from src.visualize import visualize_from_jsonl


@click.command()
@click.option("--output", default="output", show_default=True,
              help="输出目录（可视化图会写入 {output}/visualize/）")
@click.option("--jsonl", default=None,
              help="training_samples.jsonl 路径（默认为 {output}/training_samples.jsonl）")
def main(output, jsonl):
    jsonl_path = jsonl or str(Path(output) / "training_samples.jsonl")
    if not Path(jsonl_path).exists():
        raise SystemExit(f"找不到 jsonl 文件：{jsonl_path}")
    visualize_from_jsonl(output_dir=output, jsonl_path=jsonl_path)


if __name__ == "__main__":
    main()
