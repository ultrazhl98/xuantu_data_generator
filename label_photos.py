#!/usr/bin/env python3
"""
label_photos.py — 一次性脚本：调用 Claude API 对源图自动打标签

运行前请确保设置环境变量：ANTHROPIC_API_KEY

用法：
    python label_photos.py
    python label_photos.py --source source_photos/images --output source_photos/metadata.json
    python label_photos.py --append   # 跳过已有 id，只处理新图片
"""

import base64
import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import click


SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def encode_image(path: Path) -> tuple[str, str]:
    """返回 (base64_data, media_type)"""
    ext = path.suffix.lower()
    media_type = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
    }.get(ext, "image/jpeg")
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode(), media_type


def label_single(client, image_path: Path) -> dict:
    """调用 Claude API 对单张图片打标签"""
    b64, media_type = encode_image(image_path)

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64},
                },
                {
                    "type": "text",
                    "text": (
                        "请分析这张图片，返回 JSON（只返回 JSON，不要其他文字）：\n"
                        "{\n"
                        '  "labels": ["英文标签1", "英文标签2"],   // 3~6个简洁英文标签\n'
                        '  "description": "一句话中文描述"         // 15字以内\n'
                        "}\n"
                        "常用标签参考：cat, dog, car, landscape, food, person, flower, "
                        "building, screenshot, selfie, night, beach, mountain, city, "
                        "animal, sky, sunset, indoor, outdoor"
                    ),
                },
            ],
        }],
    )

    text = response.content[0].text.strip()
    # 提取 JSON（可能被 ``` 包裹）
    if "```" in text:
        text = text.split("```")[1].strip()
        if text.startswith("json"):
            text = text[4:].strip()
    return json.loads(text)


def random_timestamp(rng: random.Random) -> str:
    """生成随机时间戳（最近2年内）"""
    base = datetime(2023, 1, 1)
    delta = timedelta(days=rng.randint(0, 730), hours=rng.randint(0, 23),
                      minutes=rng.randint(0, 59))
    return (base + delta).isoformat()


@click.command()
@click.option("--source", default="source_photos/images", show_default=True,
              help="源图片根目录")
@click.option("--output", default="source_photos/metadata.json", show_default=True,
              help="输出 metadata.json 路径")
@click.option("--append", is_flag=True,
              help="追加模式：跳过已有 id，只处理新图片")
@click.option("--dry-run", is_flag=True,
              help="只扫描图片，不调用 API（用于测试目录结构）")
def main(source, output, append, dry_run):
    source_dir = Path(source)
    output_path = Path(output)

    if not source_dir.exists():
        click.echo(f"错误：源目录不存在：{source_dir}", err=True)
        sys.exit(1)

    # 收集所有图片
    image_paths = sorted([
        p for p in source_dir.rglob("*")
        if p.suffix.lower() in SUPPORTED_EXTS
    ])

    if not image_paths:
        click.echo(f"在 {source_dir} 下未找到图片", err=True)
        sys.exit(1)

    click.echo(f"找到 {len(image_paths)} 张图片")

    # 加载已有 metadata（追加模式）
    existing: list[dict] = []
    existing_ids: set[str] = set()
    if append and output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            existing = json.load(f)
        existing_ids = {item["id"] for item in existing}
        click.echo(f"已有 {len(existing)} 条记录，将跳过")

    if dry_run:
        for p in image_paths:
            rel = str(p.relative_to(source_dir.parent))
            click.echo(f"  {rel}")
        click.echo("dry-run 完成，未调用 API")
        return

    # 初始化 Anthropic client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        click.echo("错误：请设置环境变量 ANTHROPIC_API_KEY", err=True)
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    rng = random.Random(42)
    results: list[dict] = list(existing)
    errors = 0

    with click.progressbar(image_paths, label="标注图片") as bar:
        for img_path in bar:
            # 生成 id（相对于 source 父目录的路径，去掉扩展名，/ 换 _）
            rel_path = img_path.relative_to(source_dir.parent)
            photo_id = str(rel_path.with_suffix("")).replace("/", "_").replace("\\", "_")

            if photo_id in existing_ids:
                continue

            try:
                info = label_single(client, img_path)
            except Exception as e:
                click.echo(f"\n警告：{img_path.name} 标注失败：{e}", err=True)
                # 降级：用文件夹名作为 label
                folder = img_path.parent.name
                info = {"labels": [folder], "description": f"一张{folder}图片"}
                errors += 1

            results.append({
                "id": photo_id,
                "path": str(rel_path),
                "labels": info.get("labels", []),
                "description": info.get("description", ""),
                "timestamp": random_timestamp(rng),
            })

    # 写入
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    click.echo(f"\n完成：{len(results)} 条记录已写入 {output_path}")
    if errors:
        click.echo(f"  其中 {errors} 张图片标注失败（已用文件夹名降级）")


if __name__ == "__main__":
    main()
