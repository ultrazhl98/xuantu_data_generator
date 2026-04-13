"""
visualize.py — 为每条指令生成带点击位置标注的可视化图片

输出到 {output_dir}/visualize/{stem}_{idx:02d}_vis.jpg
"""

from __future__ import annotations

from pathlib import Path

from .instruction_types import TrainingSample


def draw_visualize(output_dir: str, samples: list[TrainingSample]) -> None:
    from PIL import Image, ImageDraw, ImageFont

    out = Path(output_dir)
    vis_dir = out / "visualize"
    vis_dir.mkdir(parents=True, exist_ok=True)

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

        for box in s.click_boxes:
            x1, y1, x2, y2 = box
            draw.rectangle([x1, y1, x2, y2], outline=(0, 200, 0, 180), width=3)
            draw.rectangle([x1, y1, x2, y2], fill=(0, 200, 0, 40))

        for ct in s.click_targets:
            cx, cy = ct
            r = 14
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 0, 0, 200))
            r2 = 5
            draw.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], fill=(255, 255, 255, 230))

        try:
            font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 36)
        except Exception:
            font = ImageFont.load_default()
        text = s.instruction
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_h = text_bbox[3] - text_bbox[1] + 20
        draw.rectangle([0, 0, img.width, text_h + 10], fill=(0, 0, 0, 180))
        draw.text((10, 5), text, fill=(255, 255, 255, 255), font=font)

        stem = Path(img_rel).stem
        idx = image_counter.get(stem, 0)
        image_counter[stem] = idx + 1
        fname = f"{stem}_{idx:02d}_vis.jpg"
        img.save(vis_dir / fname, quality=90)

    print(f"可视化图已保存至：{vis_dir}（共 {len(samples)} 张，每条指令独立一张）")


def visualize_from_jsonl(output_dir: str, jsonl_path: str) -> None:
    """从训练 jsonl 读样本并可视化（供独立脚本或事后查看使用）。"""
    import json

    samples: list[TrainingSample] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            samples.append(TrainingSample(
                image_path=r["image"],
                app=r.get("app", ""),
                instruction=r["instruction"],
                instruction_type=r.get("instruction_type", ""),
                click_targets=[tuple(t) for t in r.get("click_targets", [])],
                click_boxes=[tuple(b) for b in r.get("click_boxes", [])],
                selected_grid_indices=r.get("selected_grid_indices", []),
                selected_cells=r.get("selected_cells", []),
            ))
    draw_visualize(output_dir, samples)
