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
    ollama pull gemma4:e4b

    # 4. 安装 Python 客户端
    pip install ollama

用法：
    python label_photos.py
    python label_photos.py --source source_photos/images --output source_photos/metadata.json
    python label_photos.py --append          # 跳过已有 id，只处理新图片
    python label_photos.py --model gemma4:e4b # 指定模型（默认 gemma4:e4b）
"""

import base64
import json
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import click


SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

LABEL_PROMPT = (
    "你是一个图片标注助手。请分析这张图片，为它打上中文标签，用于手机相册中的图片搜索和分类。\n"
    "\n"
    "要求：\n"
    "1. 输出 3~6 个中文标签，描述图片中的主要内容（如主体、场景、环境等）\n"
    "2. 标签要具体且准确，例如用\"金毛犬\"而非\"哺乳动物\"，用\"卧室\"而非\"房间\"\n"
    "3. 如果图片中有动物，请同时标注具体种类（如\"猫\"、\"狗\"）和上位词\"动物\"\n"
    "4. 如果图片中有人，请标注\"人物\"以及相关活动（如\"自拍\"、\"聚餐\"）\n"
    "5. 输出一句 15 字以内的中文描述\n"
    "\n"
    "只返回 JSON，不要其他文字：\n"
    '{"labels": ["标签1", "标签2", ...], "description": "一句话描述"}'
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

    # 确保 labels 非空
    labels = result.get("labels", [])
    if not labels:
        labels = ["未知"]
    result["labels"] = labels
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
@click.option("--model", default="gemma4:e4b", show_default=True,
              help="Ollama 模型名称，需支持视觉。例：gemma4:e4b, gemma3:12b, llava:7b")
@click.option("--workers", default=4, show_default=True,
              help="并发线程数（根据 GPU 显存和 Ollama 配置调整）")
def main(source, output, append, dry_run, model, workers):
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
    click.echo(f"并发线程数：{workers}")

    rng = random.Random(42)
    results: list[dict] = list(existing)
    errors = 0

    # 过滤掉已有 id 的图片，并预生成 id 和时间戳
    tasks = []
    for img_path in image_paths:
        rel_path = img_path.relative_to(source_dir.parent)
        photo_id = str(rel_path.with_suffix("")).replace("/", "_").replace("\\", "_")
        if photo_id in existing_ids:
            continue
        tasks.append({
            "img_path": img_path,
            "rel_path": rel_path,
            "photo_id": photo_id,
            "timestamp": random_timestamp(rng),
        })

    if not tasks:
        click.echo("没有需要标注的新图片")
    else:
        click.echo(f"需要标注 {len(tasks)} 张图片")
        completed = 0
        lock = threading.Lock()

        def process_one(task):
            nonlocal errors, completed
            try:
                info = label_single_ollama(model, task["img_path"])
            except Exception as e:
                click.echo(f"\n警告：{task['img_path'].name} 标注失败：{e}", err=True)
                info = {"labels": ["未知"], "description": "无法识别"}
                with lock:
                    errors += 1

            result = {
                "id": task["photo_id"],
                "path": str(task["rel_path"]),
                "labels": info.get("labels", []),
                "description": info.get("description", ""),
                "timestamp": task["timestamp"],
            }

            with lock:
                completed += 1
                click.echo(f"\r标注进度：{completed}/{len(tasks)}", nl=False)

            return result

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_one, t): t for t in tasks}
            for future in as_completed(futures):
                results.append(future.result())

        click.echo()  # 换行

    # 写入
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    click.echo(f"\n完成：{len(results)} 条记录已写入 {output_path}")
    if errors:
        click.echo(f"  其中 {errors} 张图片标注失败（已用文件夹名降级）")


if __name__ == "__main__":
    main()
