#!/usr/bin/env python3
"""
create_test_photos.py — 生成占位测试图片（无需下载任何素材）

每个类别生成若干张带颜色和标签文字的图片，
同时自动生成 source_photos/metadata.json。

用法：
    python create_test_photos.py          # 默认生成 ~60 张
    python create_test_photos.py --n 10  # 每类生成 10 张
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

import click
from PIL import Image, ImageDraw, ImageFont


# 类别 → (中文名, 主色调列表)
CATEGORIES = {
    "cat":       ("小猫",   [(255, 165, 80),  (200, 140, 60),  (240, 200, 150)]),
    "dog":       ("小狗",   [(180, 130, 80),  (220, 180, 120), (160, 110, 60)]),
    "car":       ("汽车",   [(60,  90,  200), (200, 50,  50),  (50,  50,  50)]),
    "landscape": ("风景",   [(60,  160, 80),  (80,  180, 100), (100, 200, 120)]),
    "food":      ("美食",   [(220, 100, 60),  (240, 160, 80),  (200, 80,  40)]),
    "selfie":    ("自拍",   [(255, 200, 200), (230, 180, 180), (210, 160, 160)]),
    "building":  ("建筑",   [(120, 120, 160), (140, 140, 180), (100, 100, 140)]),
    "sunset":    ("日落",   [(255, 120, 40),  (255, 160, 60),  (200, 80,  20)]),
}


def _get_font(size: int):
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_photo(label: str, index: int, base_color: tuple, size=(400, 400)) -> Image.Image:
    """生成一张带渐变背景和文字的占位图"""
    img = Image.new("RGB", size, base_color)
    draw = ImageDraw.Draw(img)

    # 简单渐变：从 base_color 到稍深的颜色
    r, g, b = base_color
    for y in range(size[1]):
        factor = 1 - 0.3 * (y / size[1])
        draw.line([(0, y), (size[0], y)],
                  fill=(int(r * factor), int(g * factor), int(b * factor)))

    # 中央大图标（用文字模拟）
    emoji_map = {
        "cat": "🐱", "dog": "🐶", "car": "🚗",
        "landscape": "🌄", "food": "🍜", "selfie": "🤳",
        "building": "🏢", "sunset": "🌅",
    }
    icon = emoji_map.get(label, "📷")

    # 中文标签
    zh_name = CATEGORIES[label][0]
    font_big = _get_font(60)
    font_small = _get_font(36)

    # 绘制文字（居中）
    text = zh_name
    bbox = draw.textbbox((0, 0), text, font=font_big)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (size[0] - tw) // 2
    ty = (size[1] - th) // 2 - 20

    # 文字阴影
    draw.text((tx + 2, ty + 2), text, fill=(0, 0, 0, 80), font=font_big)
    draw.text((tx, ty), text, fill=(255, 255, 255), font=font_big)

    # 序号
    num_text = f"#{index + 1}"
    draw.text((10, 10), num_text, fill=(255, 255, 255, 180), font=font_small)

    return img


def random_timestamp(rng: random.Random) -> str:
    base = datetime(2023, 1, 1)
    delta = timedelta(days=rng.randint(0, 730),
                      hours=rng.randint(0, 23),
                      minutes=rng.randint(0, 59))
    return (base + delta).isoformat()


@click.command()
@click.option("--n", default=8, show_default=True, help="每个类别生成多少张图片")
@click.option("--output", default="source_photos", show_default=True)
@click.option("--seed", default=42, type=int)
def main(n, output, seed):
    rng = random.Random(seed)
    out = Path(output)
    img_dir = out / "images"

    records = []
    total = 0

    for label, (zh_name, colors) in CATEGORIES.items():
        cat_dir = img_dir / label
        cat_dir.mkdir(parents=True, exist_ok=True)

        for i in range(n):
            color = colors[i % len(colors)]
            # 颜色加一点随机扰动
            jitter = lambda c: max(0, min(255, c + rng.randint(-20, 20)))
            color = (jitter(color[0]), jitter(color[1]), jitter(color[2]))

            img = make_photo(label, i, color)
            filename = f"{label}_{i:03d}.jpg"
            img_path = cat_dir / filename
            img.save(img_path, quality=90)

            rel_path = str(img_path.relative_to(out.parent))
            records.append({
                "id": f"{label}_{i:03d}",
                "path": rel_path,
                "labels": [label],
                "description": f"第{i+1}张{zh_name}图片",
                "timestamp": random_timestamp(rng),
            })
            total += 1

    # 写 metadata.json
    meta_path = out / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"生成完成：{total} 张图片，{len(CATEGORIES)} 个类别")
    print(f"  图片目录：{img_dir}")
    print(f"  metadata：{meta_path}")
    print(f"\n下一步：")
    print(f"  python generate.py --count 20 --apps all --debug")


if __name__ == "__main__":
    main()
