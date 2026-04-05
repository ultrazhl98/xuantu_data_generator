#!/usr/bin/env python3
"""
download_photos.py — 下载公开图片数据集到 source_photos/images/

两个来源：
1. COCO val2017：覆盖 person/cat/dog/car/food 等日常类别
2. Open Images v7（通过 fiftyone）：补充 sunset/beach/flower/night 等类别

用法：
    python download_photos.py                        # 默认：COCO 500张 + Open Images 补充类别各50张
    python download_photos.py --coco 300             # 只调整 COCO 数量
    python download_photos.py --no-coco              # 跳过 COCO，只下 Open Images
    python download_photos.py --no-openimages        # 跳过 Open Images，只下 COCO
    python download_photos.py --coco 200 --oi-per-class 30
"""

import io
import os
import random
import shutil
import sys
import zipfile
from pathlib import Path

import click
import requests
from tqdm import tqdm

OUTPUT_DIR = Path("source_photos/images")

# ── COCO ──────────────────────────────────────────────────────────────────────

COCO_VAL_IMAGES_URL = "http://images.cocodataset.org/zips/val2017.zip"
COCO_VAL_ANNOTATIONS_URL = "http://images.cocodataset.org/annotations/annotations_trainval2017.zip"

# COCO 类别 id → 我们关心的标签（只保留这些类别的图片）
COCO_WANTED_CATS = {
    1: "person",
    17: "cat",
    18: "dog",
    3: "car",
    55: "cake",       # → food
    57: "carrot",     # → food
    58: "hot dog",    # → food
    60: "pizza",      # → food
    61: "donut",      # → food
    62: "sandwich",   # → food
    63: "orange",     # → food
    64: "broccoli",   # → food
    65: "carrot",     # → food
    72: "tv",         # → building/indoor
    75: "vase",       # → flower（间接）
    84: "book",
    86: "vase",
    # 建筑/城市场景没有直接类别，通过 supercategory outdoor 覆盖
}

# COCO supercategory 白名单（outdoor 包含 car/traffic light/stop sign 等）
COCO_WANTED_SUPERCATS = {"animal", "food", "outdoor", "person", "vehicle"}


def _download_file(url: str, dest: Path, desc: str):
    """流式下载大文件并显示进度条"""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f, tqdm(
        total=total, unit="B", unit_scale=True, desc=desc
    ) as bar:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
            bar.update(len(chunk))


def download_coco(n: int, output_dir: Path, seed: int = 42):
    """
    下载 COCO val2017 中最多 n 张图片，按类别分子目录存放。
    使用临时目录缓存 zip，避免重复下载。
    """
    cache_dir = Path(".cache/coco")
    cache_dir.mkdir(parents=True, exist_ok=True)

    ann_zip = cache_dir / "annotations_trainval2017.zip"
    img_zip = cache_dir / "val2017.zip"

    # ── 下载 annotations ──────────────────────────────────────────
    if not ann_zip.exists():
        click.echo("下载 COCO annotations...")
        _download_file(COCO_VAL_ANNOTATIONS_URL, ann_zip, "annotations.zip")
    else:
        click.echo("annotations.zip 已缓存，跳过下载")

    # 解析 instances_val2017.json
    import json
    click.echo("解析 COCO annotations...")
    with zipfile.ZipFile(ann_zip) as zf:
        with zf.open("annotations/instances_val2017.json") as f:
            data = json.load(f)

    # 建立 category_id → supercategory 映射
    cat_info = {c["id"]: c for c in data["categories"]}

    # 图片 id → 类别名（取第一个匹配的 wanted 类别）
    img_to_label: dict[int, str] = {}
    for ann in data["annotations"]:
        img_id = ann["image_id"]
        cat_id = ann["category_id"]
        cat = cat_info.get(cat_id, {})
        supercat = cat.get("supercategory", "")
        if cat_id in COCO_WANTED_CATS:
            label = COCO_WANTED_CATS[cat_id]
            # food 类统一归为 food
            if label in ("cake", "pizza", "donut", "sandwich", "hot dog",
                         "orange", "broccoli", "carrot"):
                label = "food"
            img_to_label.setdefault(img_id, label)
        elif supercat in COCO_WANTED_SUPERCATS:
            img_to_label.setdefault(img_id, supercat)

    # 图片 id → 文件名
    img_id_to_filename = {img["id"]: img["file_name"] for img in data["images"]}

    # 按标签分组，随机采样
    rng = random.Random(seed)
    label_to_imgs: dict[str, list] = {}
    for img_id, label in img_to_label.items():
        fname = img_id_to_filename.get(img_id)
        if fname:
            label_to_imgs.setdefault(label, []).append(fname)

    # 按比例采样各类别，总量不超过 n
    selected: list[tuple[str, str]] = []  # (label, filename)
    all_items = [(label, fname) for label, fnames in label_to_imgs.items()
                 for fname in fnames]
    rng.shuffle(all_items)
    selected = all_items[:n]

    click.echo(f"将从 COCO 下载 {len(selected)} 张图片（{len(label_to_imgs)} 个类别）")
    for label, cnt in sorted(
        {lbl: sum(1 for l, _ in selected if l == lbl) for lbl, _ in selected}.items(),
        key=lambda x: -x[1],
    ):
        click.echo(f"  {label}: {cnt} 张")

    # ── 下载图片 zip ──────────────────────────────────────────────
    if not img_zip.exists():
        click.echo("\n下载 COCO val2017 图片（约 800MB）...")
        _download_file(COCO_VAL_IMAGES_URL, img_zip, "val2017.zip")
    else:
        click.echo("val2017.zip 已缓存，跳过下载")

    # ── 解压选中的图片到分类子目录 ────────────────────────────────
    fname_to_label = {fname: label for label, fname in selected}
    click.echo("\n解压图片到 source_photos/images/...")
    with zipfile.ZipFile(img_zip) as zf:
        members = [m for m in zf.namelist() if Path(m).name in fname_to_label]
        for member in tqdm(members, desc="解压 COCO"):
            fname = Path(member).name
            label = fname_to_label[fname]
            dest = output_dir / label / fname
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    click.echo(f"COCO 完成：{len(members)} 张图片已整理到 {output_dir}")


# ── Open Images ───────────────────────────────────────────────────────────────

# 需要补充的类别（COCO 中较少）→ Open Images class name
OI_SUPPLEMENT_CLASSES = {
    "sunset":    "Sunrise",      # OI 用 Sunrise 涵盖 sunset/sunrise
    "beach":     "Beach",
    "flower":    "Flower",
    "mountain":  "Mountain",
    "night":     "Night",
    "city":      "City",
    "landscape": "Landscape",
    "selfie":    "Selfie",
    "building":  "Building",
}


def download_openimages(classes: dict[str, str], per_class: int, output_dir: Path):
    """
    用 fiftyone 下载 Open Images v7 指定类别图片。
    fiftyone 会自动处理缓存，第二次运行不重复下载。
    """
    try:
        import fiftyone as fo
        import fiftyone.zoo as foz
    except ImportError:
        click.echo(
            "需要安装 fiftyone：pip install fiftyone\n"
            "安装后重新运行此脚本即可下载 Open Images 补充类别。",
            err=True,
        )
        return

    for local_label, oi_class in classes.items():
        dest_dir = output_dir / local_label
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 已有足够图片则跳过
        existing = list(dest_dir.glob("*.jpg")) + list(dest_dir.glob("*.png"))
        if len(existing) >= per_class:
            click.echo(f"  {local_label}: 已有 {len(existing)} 张，跳过")
            continue

        click.echo(f"  下载 Open Images [{oi_class}] → {local_label}...")
        try:
            dataset = foz.load_zoo_dataset(
                "open-images-v7",
                split="validation",
                label_types=["classifications"],
                classes=[oi_class],
                max_samples=per_class,
                dataset_name=f"oi_{oi_class.lower()}_{per_class}",
                overwrite=False,
            )
            for sample in tqdm(dataset, desc=f"  复制 {local_label}", total=len(dataset)):
                src = Path(sample.filepath)
                dst = dest_dir / src.name
                if not dst.exists():
                    shutil.copy2(src, dst)
            fo.delete_dataset(f"oi_{oi_class.lower()}_{per_class}")
        except Exception as e:
            click.echo(f"  警告：{oi_class} 下载失败：{e}", err=True)


# ── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--coco", default=500, show_default=True,
              help="从 COCO val2017 下载的图片数量")
@click.option("--no-coco", is_flag=True, help="跳过 COCO 下载")
@click.option("--no-openimages", is_flag=True, help="跳过 Open Images 下载")
@click.option("--oi-per-class", default=50, show_default=True,
              help="Open Images 每个补充类别下载的图片数")
@click.option("--output", default="source_photos/images", show_default=True,
              help="图片输出目录")
@click.option("--seed", default=42, show_default=True, help="随机种子")
def main(coco, no_coco, no_openimages, oi_per_class, output, seed):
    """
    下载 COCO val2017 + Open Images 补充类别图片到 source_photos/images/。

    下载完成后运行：
        python label_photos.py
        python generate.py --count 200 --apps all
    """
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not no_coco:
        click.echo(f"\n=== COCO val2017（{coco} 张）===")
        download_coco(n=coco, output_dir=output_dir, seed=seed)

    if not no_openimages:
        click.echo(f"\n=== Open Images 补充类别（每类 {oi_per_class} 张）===")
        download_openimages(OI_SUPPLEMENT_CLASSES, oi_per_class, output_dir)

    # 统计
    click.echo("\n=== 下载完成，图片统计 ===")
    total = 0
    for subdir in sorted(output_dir.iterdir()):
        if subdir.is_dir():
            imgs = [p for p in subdir.iterdir()
                    if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
            click.echo(f"  {subdir.name:15s}: {len(imgs):4d} 张")
            total += len(imgs)
    click.echo(f"  {'合计':15s}: {total:4d} 张")

    click.echo("\n下一步：")
    click.echo("  export ANTHROPIC_API_KEY=sk-ant-xxx")
    click.echo("  python label_photos.py")
    click.echo("  python generate.py --count 200 --apps all")


if __name__ == "__main__":
    main()
