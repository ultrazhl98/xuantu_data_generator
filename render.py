#!/usr/bin/env python3
"""
render.py — 渲染阶段 CLI：只生成图片 + 网格 sidecar，不生成指令

用法：
    python render.py --count 100 --apps all
    python render.py --count 10 --seed 42 --video-ratio 0.3

产物：
    output/images/{i:05d}.jpg
    output/grids/{i:05d}.jsonl      每行一个 photo/video 格子
    output/grids/{i:05d}.meta.json  {app, image_path}
"""

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent))
from src.render_stage import render_batch
from src.app_config import APP_PRESETS


@click.command()
@click.option("--count", "-n", default=100, show_default=True, help="生成多少张合成图")
@click.option("--apps", default="all", show_default=True,
              help=f"使用哪些 App，逗号分隔或 'all'。可选：{','.join(APP_PRESETS.keys())}")
@click.option("--ensure-labels", default=None,
              help="保证每张图中这些 label 各出现至少一次，逗号分隔（如 cat,car）")
@click.option("--metadata", default="source_photos/metadata.json", show_default=True,
              help="metadata.json 路径")
@click.option("--output", default="output", show_default=True, help="输出目录")
@click.option("--seed", default=None, type=int, help="随机种子（用于复现）")
@click.option("--video-ratio", default=0.3, show_default=True,
              help="视频格比例：0.0=纯图模式，0~1 随机混合视频")
@click.option("--camera-ratio", default=0.3, show_default=True,
              help="拍照格出现概率：0.0=不出现，0~1 随机出现")
@click.option("--partial-ratio", default=0.1, show_default=True,
              help="部分填充网格的比例：0.0=全部填满，0~1=该比例的图随机少填")
@click.option("--photos-per-screen", default=None, type=int,
              help="每屏显示图片数（默认用 config.max_photos）")
def main(count, apps, ensure_labels, metadata, output, seed, video_ratio,
         camera_ratio, partial_ratio, photos_per_screen):
    if apps == "all":
        app_list = list(APP_PRESETS.keys())
    else:
        app_list = [a.strip() for a in apps.split(",")]
    labels = [l.strip() for l in ensure_labels.split(",")] if ensure_labels else None

    render_batch(
        metadata_path=metadata,
        output_dir=output,
        count=count,
        apps=app_list,
        ensure_labels=labels,
        photos_per_screen=photos_per_screen,
        seed=seed,
        show_progress=True,
        video_ratio=video_ratio,
        camera_ratio=camera_ratio,
        partial_ratio=partial_ratio,
    )


if __name__ == "__main__":
    main()
