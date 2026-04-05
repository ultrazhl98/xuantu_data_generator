#!/usr/bin/env python3
"""
label_photos.py — 一次性脚本：用本地 Gemma 3 模型对源图自动打标签

依赖 Ollama（本地推理引擎）：
    # 1. 安装 Ollama
    brew install ollama          # macOS
    # 或从 https://ollama.com 下载安装包

    # 2. 启动 Ollama 服务
    ollama serve                 # 后台运行，或用系统服务

    # 3. 拉取 Gemma 3 多模态模型（约 3 GB）
    ollama pull gemma3:4b

    # 4. 安装 Python 客户端
    pip install ollama

用法：
    python label_photos.py
    python label_photos.py --source source_photos/images --output source_photos/metadata.json
    python label_photos.py --append          # 跳过已有 id，只处理新图片
    python label_photos.py --model gemma3:4b # 指定模型（默认 gemma3:4b）
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

LABEL_PROMPT = (
    "请分析这张图片，返回 JSON（只返回 JSON，不要其他文字）：\n"
    "{\n"
    '  "labels": ["英文标签1", "英文标签2", ...],  // 3~6个简洁英文标签\n'
    '  "description": "一句话中文描述"              // 15字以内的中文\n'
    "}\n"
    "标签必须从以下列表中选取：cat, dog, car, landscape, food, person, flower, "
    "building, screenshot, selfie, night, beach, mountain, city, "
    "animal, sky, sunset, indoor, outdoor\n"
    "要求：labels 至少3个，description 必须用中文。"
)


def encode_image_b64(path: Path) -> str:
    """返回 base64 编码的图片数据"""
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode()


def _parse_json_response(text: str) -> dict:
    """从模型返回文本中提取 JSON"""
    text = text.strip()
    # 去除 ```json ... ``` 包裹
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue
    # 直接解析
    # 找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    return json.loads(text)


VALID_LABELS = {
    "cat", "dog", "car", "landscape", "food", "person", "flower",
    "building", "screenshot", "selfie", "night", "beach", "mountain",
    "city", "animal", "sky", "sunset", "indoor", "outdoor",
}


def label_single_ollama(model: str, image_path: Path) -> dict:
    """用 Ollama 本地模型对单张图片打标签"""
    import ollama

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
    text = response["message"]["content"]
    result = _parse_json_response(text)

    # 过滤：只保留有效标签
    raw_labels = result.get("labels", [])
    filtered = [l for l in raw_labels if l.lower() in VALID_LABELS]
    # 如果全被过滤掉了，用文件夹名兜底
    if not filtered:
        folder = image_path.parent.name
        filtered = [folder] if folder in VALID_LABELS else raw_labels[:3]
    result["labels"] = filtered
    return result


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
              help="只扫描图片，不调用模型（用于测试目录结构）")
@click.option("--model", default="gemma3:4b", show_default=True,
              help="Ollama 模型名称，需支持视觉。例：gemma3:4b, gemma3:12b, llava:7b")
def main(source, output, append, dry_run, model):
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
        click.echo("dry-run 完成，未调用模型")
        return

    # 检查 ollama 是否可用
    try:
        import ollama as _ollama_check
    except ImportError:
        click.echo("错误：请先安装 ollama Python 包：pip install ollama", err=True)
        sys.exit(1)

    click.echo(f"使用模型：{model}（确保已运行 ollama serve 并执行 ollama pull {model}）")

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
                info = label_single_ollama(model, img_path)
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
