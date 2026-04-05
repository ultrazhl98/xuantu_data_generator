#!/usr/bin/env python3
"""
debug_prompt.py — 快速调试 label_photos.py 的 prompt

用法：
    python debug_prompt.py                              # 随机选一张图
    python debug_prompt.py source_photos/images/cat/000000106389.jpg  # 指定图片
    python debug_prompt.py --all-categories             # 每个类别各选一张
    python debug_prompt.py --model gemma4:e4b            # 指定模型
"""

import sys
import random
from pathlib import Path

import click

# 直接从 label_photos 导入，方便同步修改
from label_photos import LABEL_PROMPT, encode_image_b64, _parse_json_response, SUPPORTED_EXTS

SOURCE_DIR = Path("source_photos/images")


def run_once(model: str, image_path: Path):
    """对单张图片运行 prompt 并打印详细结果"""
    import ollama

    click.echo(f"\n{'='*60}")
    click.echo(f"图片：{image_path}")
    click.echo(f"模型：{model}")
    click.echo(f"{'='*60}")

    click.echo(f"\n--- Prompt ---\n{LABEL_PROMPT}\n")

    b64 = encode_image_b64(image_path)
    response = ollama.chat(
        model=model,
        messages=[{
            "role": "user",
            "content": LABEL_PROMPT,
            "images": [b64],
        }],
        options={"temperature": 0.1},
    )

    raw = response["message"]["content"]
    click.echo(f"--- 原始返回 ---\n{raw}\n")

    try:
        parsed = _parse_json_response(raw)
        click.echo(f"--- 解析结果 ---")
        click.echo(f"  labels:      {parsed.get('labels', [])}")
        click.echo(f"  description: {parsed.get('description', '')}")
    except Exception as e:
        click.echo(f"--- JSON 解析失败 ---\n  {e}")


@click.command()
@click.argument("image", required=False, type=click.Path(exists=True))
@click.option("--model", default="gemma4:e4b", show_default=True)
@click.option("--all-categories", is_flag=True, help="每个类别随机选一张")
def main(image, model, all_categories):
    if image:
        run_once(model, Path(image))
    elif all_categories:
        if not SOURCE_DIR.exists():
            click.echo(f"错误：{SOURCE_DIR} 不存在", err=True)
            sys.exit(1)
        for category in sorted(SOURCE_DIR.iterdir()):
            if not category.is_dir():
                continue
            imgs = [p for p in category.iterdir() if p.suffix.lower() in SUPPORTED_EXTS]
            if imgs:
                run_once(model, random.choice(imgs))
    else:
        if not SOURCE_DIR.exists():
            click.echo(f"错误：{SOURCE_DIR} 不存在", err=True)
            sys.exit(1)
        all_imgs = [p for p in SOURCE_DIR.rglob("*") if p.suffix.lower() in SUPPORTED_EXTS]
        if not all_imgs:
            click.echo("未找到图片", err=True)
            sys.exit(1)
        run_once(model, random.choice(all_imgs))


if __name__ == "__main__":
    main()
