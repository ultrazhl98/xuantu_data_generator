#!/usr/bin/env python3
"""
generate.py — CLI 入口

用法：
    python generate.py --count 100 --apps 相册,微信
    python generate.py --count 500 --apps all --ensure-labels cat,car
    python generate.py --count 10 --seed 42 --debug
"""

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent))
from src.generator import generate
from src.app_config import APP_PRESETS


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
@click.option("--seed", default=None, type=int,
              help="随机种子（用于复现）")
@click.option("--video-ratio", default=0.3, show_default=True,
              help="视频格比例：0.0=纯图模式，0~1 随机混合视频")
@click.option("--model", default="gemma4:e4b", show_default=True,
              help="Ollama 模型名称，用于生成内容类指令。需支持文本对话")
@click.option("--content-workers", default=4, show_default=True,
              help="内容指令并发线程数（根据 Ollama 服务能力调整）")
@click.option("--debug", is_flag=True,
              help="生成后在图上绘制 bbox 和 click_target 红点（用于调试）")
@click.option("--visualize", is_flag=True,
              help="为每张图额外保存一张带点击位置可视化标注的图片到 output/visualize/")
def main(count, apps, ensure_labels, metadata, output, n_sequential, n_content, seed, video_ratio, model, content_workers, debug, visualize):
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
        model=model,
        max_content_workers=content_workers,
    )

    if debug:
        _draw_debug_overlay(output, samples)

    if visualize:
        _draw_visualize(output, samples)


def _draw_debug_overlay(output_dir: str, samples):
    """在图上叠加 bbox 框和 click_target 红点，保存到 output/debug/"""
    from PIL import Image, ImageDraw
    import json
    from collections import defaultdict

    out = Path(output_dir)
    debug_dir = out / "debug"
    debug_dir.mkdir(exist_ok=True)

    # 按图片分组
    by_image: dict[str, list] = defaultdict(list)
    for s in samples:
        by_image[s.image_path].append(s)

    for img_rel, img_samples in list(by_image.items())[:10]:  # 最多调试10张
        img_abs = Path(output_dir).parent / img_rel if not Path(img_rel).is_absolute() else Path(img_rel)
        if not img_abs.exists():
            # 尝试相对于当前目录
            img_abs = Path(img_rel)
        if not img_abs.exists():
            continue

        img = Image.open(img_abs).convert("RGB")
        draw = ImageDraw.Draw(img)

        for s in img_samples:
            for ct in s.click_targets:
                cx, cy = ct
                r = 12
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 0, 0))

        fname = Path(img_rel).stem + "_debug.jpg"
        img.save(debug_dir / fname, quality=85)

    print(f"调试图已保存至：{debug_dir}")


def _draw_visualize(output_dir: str, samples):
    """为每条指令单独生成一张带点击位置可视化标注的图片，保存到 output/visualize/"""
    from PIL import Image, ImageDraw, ImageFont

    out = Path(output_dir)
    vis_dir = out / "visualize"
    vis_dir.mkdir(exist_ok=True)

    # 记录每张原图已出现的指令计数，用于生成不重复的文件名
    image_counter: dict[str, int] = {}

    for s in samples:
        img_rel = s.image_path
        img_abs = Path(output_dir).parent / img_rel if not Path(img_rel).is_absolute() else Path(img_rel)
        if not img_abs.exists():
            img_abs = Path(img_rel)
        if not img_abs.exists():
            continue

        img = Image.open(img_abs).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")

        # 绘制点击区域半透明框
        for box in s.click_boxes:
            x1, y1, x2, y2 = box
            draw.rectangle([x1, y1, x2, y2], outline=(0, 200, 0, 180), width=3)
            draw.rectangle([x1, y1, x2, y2], fill=(0, 200, 0, 40))

        # 绘制点击目标红点
        for ct in s.click_targets:
            cx, cy = ct
            r = 14
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 0, 0, 200))
            # 白色内圈
            r2 = 5
            draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(255, 255, 255, 230))

        # 在图片顶部绘制指令文本
        try:
            font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 36)
        except Exception:
            font = ImageFont.load_default()
        text = s.instruction
        # 半透明黑色背景条
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_h = text_bbox[3] - text_bbox[1] + 20
        draw.rectangle([0, 0, img.width, text_h + 10], fill=(0, 0, 0, 180))
        draw.text((10, 5), text, fill=(255, 255, 255, 255), font=font)

        # 生成文件名：原图名_序号_vis.jpg
        stem = Path(img_rel).stem
        idx = image_counter.get(stem, 0)
        image_counter[stem] = idx + 1
        fname = f"{stem}_{idx:02d}_vis.jpg"
        img.save(vis_dir / fname, quality=90)

    print(f"可视化图已保存至：{vis_dir}（共 {len(samples)} 张，每条指令独立一张）")


if __name__ == "__main__":
    main()
