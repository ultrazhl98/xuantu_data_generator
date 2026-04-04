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
@click.option("--debug", is_flag=True,
              help="生成后在图上绘制 bbox 和 click_target 红点（用于调试）")
def main(count, apps, ensure_labels, metadata, output, n_sequential, n_content, seed, debug):
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
    )

    if debug:
        _draw_debug_overlay(output, samples)


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


if __name__ == "__main__":
    main()
