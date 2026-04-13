#!/usr/bin/env python3
"""
generate.py — CLI 入口

用法：
    python generate.py --count 100 --apps 相册,微信
    python generate.py --count 500 --apps all --ensure-labels cat,car
    python generate.py --count 10 --seed 42 --visualize
"""

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent))
from src.generator import generate
from src.app_config import APP_PRESETS
from src.visualize import draw_visualize


@click.command()
@click.option("--count", "-n", default=100, show_default=True,
              help="生成多少张合成图")
@click.option("--apps", default="all", show_default=True,
              help=f"使用哪些 App，逗号分隔或 'all'。可选：{','.join(APP_PRESETS.keys())}")
@click.option("--ensure-labels", default=None,
              help="保证每张图中这些 label 各出现至少一次，逗号分隔（如 cat,car）")
@click.option("--metadata", default="source_photos/metadata.json", show_default=True,
              help="metadata.json 路径")
@click.option("--output", default="output", show_default=True,
              help="输出目录")
@click.option("--n-sequential", default=3, show_default=True,
              help="每张图生成的顺序类指令数")
@click.option("--n-content", default=3, show_default=True,
              help="每张图生成的内容类指令数")
@click.option("--n-video-sequential", default=2, show_default=True,
              help="每张图生成的视频顺序类指令数")
@click.option("--n-video-content", default=2, show_default=True,
              help="每张图生成的视频内容类指令数")
@click.option("--seed", default=None, type=int,
              help="随机种子（用于复现）")
@click.option("--video-ratio", default=0.3, show_default=True,
              help="视频格比例：0.0=纯图模式，0~1 随机混合视频")
@click.option("--camera-ratio", default=0.3, show_default=True,
              help="拍照格出现概率：0.0=不出现，0~1 随机出现（所有 App 均生效）")
@click.option("--model", default="gemma4:e4b", show_default=True,
              help="Ollama 模型名称，用于生成内容类指令。需支持文本对话")
@click.option("--content-workers", default=4, show_default=True,
              help="内容指令并发线程数（根据 Ollama 服务能力调整）")
@click.option("--partial-ratio", default=0.1, show_default=True,
              help="部分填充网格的比例：0.0=全部填满，0~1=该比例的图随机少填")
@click.option("--visualize", is_flag=True,
              help="为每张图额外保存一张带点击位置可视化标注的图片到 output/visualize/")
def main(count, apps, ensure_labels, metadata, output, n_sequential, n_content, n_video_sequential, n_video_content, seed, video_ratio, camera_ratio, model, content_workers, partial_ratio, visualize):
    # 解析 apps
    if apps == "all":
        app_list = list(APP_PRESETS.keys())
    else:
        app_list = [a.strip() for a in apps.split(",")]

    # 解析 ensure_labels
    labels = [l.strip() for l in ensure_labels.split(",")] if ensure_labels else None

    samples = generate(
        metadata_path=metadata,
        output_dir=output,
        count=count,
        apps=app_list,
        ensure_labels=labels,
        n_sequential=n_sequential,
        n_content=n_content,
        seed=seed,
        show_progress=True,
        video_ratio=video_ratio,
        camera_ratio=camera_ratio,
        n_video_sequential=n_video_sequential,
        n_video_content=n_video_content,
        model=model,
        max_content_workers=content_workers,
        partial_ratio=partial_ratio,
    )

    if visualize:
        draw_visualize(output, samples)


if __name__ == "__main__":
    main()
