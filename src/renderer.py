"""
renderer.py — 全合成相册 UI 渲染器

使用 Pillow 从零绘制完整 App 界面，包括：
- 状态栏（status bar）
- 应用头部（header，按 header_style 变化）
- 图片网格（含拍照位、选择圆圈、时间戳覆盖层）
- 底部导航栏
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from PIL import Image, ImageDraw, ImageFont

from .app_config import AppConfig
from .source_library import PhotoEntry


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class SlotInfo:
    grid_index: int         # 用户视角第 N 张（1-based，只计图片，跳过拍照位和视频格）；视频格为 0
    visual_slot: int        # grid 中实际位置（0-based，含拍照位）
    row: int
    col: int
    bbox: tuple             # (x1, y1, x2, y2) 像素绝对坐标（网格单元）
    click_target: tuple     # (cx, cy) Agent 应点击的坐标
    click_box: tuple        # (x1, y1, x2, y2) 点击目标的 box：有圆圈时为圆圈 box，否则为网格 box
    target_type: str        # "selection_circle" | "photo_center"
    photo: PhotoEntry
    is_video: bool = False
    duration: Optional[str] = None  # 视频时长，格式 "mm:ss"；图片格为 None


# ── 字体辅助 ─────────────────────────────────────────────────────

def _get_font(size: int, bold: bool = False):
    """尝试加载系统字体，找不到则使用默认字体"""
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


# ── 各 UI 区域绘制 ─────────────────────────────────────────────

def _draw_status_bar(draw: ImageDraw.Draw, config: AppConfig):
    """绘制顶部状态栏（时间 + 电量图标）"""
    h = 55
    draw.rectangle([0, 0, config.image_size[0], h], fill=config.status_bar_color)
    font = _get_font(36, bold=True)
    text_color = config.header_text_color
    # 时间
    draw.text((60, 14), "9:41", fill=text_color, font=font)
    # 右侧图标（简化为文字符号）
    right_x = config.image_size[0] - 120
    draw.text((right_x, 16), "● ▌▌", fill=text_color, font=_get_font(28))


def _draw_simple_header(draw: ImageDraw.Draw, config: AppConfig):
    """相册：简单标题栏"""
    y0, y1 = 55, config.grid_start_y
    draw.rectangle([0, y0, config.image_size[0], y1], fill=config.header_bg_color)
    # 分割线
    draw.line([(0, y1 - 1), (config.image_size[0], y1 - 1)], fill=(210, 210, 210), width=1)
    font = _get_font(48, bold=True)
    draw.text((30, y0 + 18), "图片", fill=config.header_text_color, font=font)
    # 右侧"多选"按钮
    btn_font = _get_font(38)
    draw.text((config.image_size[0] - 150, y0 + 22), "多选", fill=(0, 122, 255), font=btn_font)


def _draw_dark_header(draw: ImageDraw.Draw, config: AppConfig):
    """微信：深色标题栏"""
    y0, y1 = 55, config.grid_start_y
    draw.rectangle([0, y0, config.image_size[0], y1], fill=(30, 30, 30))
    font = _get_font(44, bold=True)
    title = "图片和视频"
    w = font.getlength(title)
    draw.text(((config.image_size[0] - w) / 2, y0 + 20), title, fill=(255, 255, 255), font=font)
    # 左侧 ✕
    draw.text((30, y0 + 20), "✕", fill=(180, 180, 180), font=_get_font(44))
    # 右侧 ✓
    draw.text((config.image_size[0] - 75, y0 + 18), "✓", fill=(7, 193, 96), font=_get_font(48))


def _draw_search_header(draw: ImageDraw.Draw, config: AppConfig):
    """微博：含搜索栏的标题"""
    y0 = 55
    # 主标题行
    title_bar_h = 110
    draw.rectangle([0, y0, config.image_size[0], y0 + title_bar_h], fill=(255, 255, 255))
    draw.line([(0, y0 + title_bar_h), (config.image_size[0], y0 + title_bar_h)], fill=(220, 220, 220))
    font = _get_font(44, bold=True)
    draw.text((30, y0 + 22), "取消", fill=(0, 122, 255), font=_get_font(40))
    title = "微博相册 ▾"
    draw.text(((config.image_size[0] - font.getlength(title)) / 2, y0 + 22), title, fill=(0, 0, 0), font=font)
    draw.text((config.image_size[0] - 160, y0 + 22), "下一步", fill=(0, 122, 255), font=_get_font(40))
    # 搜索栏
    sy = y0 + title_bar_h + 10
    draw.rounded_rectangle([20, sy, config.image_size[0] - 20, sy + 80], radius=14, fill=(235, 235, 240))
    draw.text((50, sy + 18), "🔍  照片、人物、地点...", fill=(140, 140, 148), font=_get_font(34))


def _draw_tabs_header(draw: ImageDraw.Draw, config: AppConfig):
    """小红书：含 Tab 导航的标题"""
    y0 = 55
    draw.rectangle([0, y0, config.image_size[0], config.grid_start_y], fill=(255, 255, 255))
    # 标题行
    font_bold = _get_font(44, bold=True)
    draw.text((30, y0 + 20), "✕", fill=(0, 0, 0), font=_get_font(44))
    title = "相册 ▾"
    draw.text(((config.image_size[0] - font_bold.getlength(title)) / 2, y0 + 20), title,
              fill=(0, 0, 0), font=font_bold)
    draw.text((config.image_size[0] - 180, y0 + 20), "编辑相册", fill=(0, 122, 255), font=_get_font(34))
    # Tab 行
    ty = y0 + 80
    tabs = ["全部", "视频", "照片", "实况照片"]
    tab_w = config.image_size[0] // len(tabs)
    for i, tab in enumerate(tabs):
        tx = i * tab_w + tab_w // 2
        color = (255, 50, 50) if i == 0 else (140, 140, 148)
        draw.text((tx - font_bold.getlength(tab) / 2, ty + 4), tab, fill=color, font=_get_font(34))
    # 底部分割线
    draw.line([(0, config.grid_start_y - 1), (config.image_size[0], config.grid_start_y - 1)],
              fill=(220, 220, 220))


def _draw_bottom_nav(draw: ImageDraw.Draw, config: AppConfig):
    """底部导航栏"""
    y0 = config.image_size[1] - config.bottom_nav_height
    draw.rectangle([0, y0, config.image_size[0], config.image_size[1]], fill=config.header_bg_color)
    draw.line([(0, y0), (config.image_size[0], y0)], fill=(210, 210, 210))
    # Home indicator
    bar_w, bar_h = 200, 6
    bx = (config.image_size[0] - bar_w) // 2
    by = y0 + (config.bottom_nav_height - bar_h) // 2 + 10
    draw.rounded_rectangle([bx, by, bx + bar_w, by + bar_h], radius=3,
                            fill=(180, 180, 180))


def _draw_camera_slot(draw: ImageDraw.Draw, x1: int, y1: int, x2: int, y2: int,
                       config: AppConfig):
    """在指定位置绘制拍照按钮格"""
    draw.rectangle([x1, y1, x2, y2], fill=(235, 235, 240))
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    r = 40
    # 相机外框
    draw.rounded_rectangle([cx - r, cy - 28, cx + r, cy + 28], radius=8, outline=(150, 150, 150), width=3)
    # 镜头
    draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], outline=(150, 150, 150), width=3)
    # 顶部小突起
    draw.rectangle([cx - 12, cy - 35, cx + 12, cy - 28], fill=(150, 150, 150))


def _draw_selection_circle(draw: ImageDraw.Draw, x2: int, y1: int, y2: int,
                            config: AppConfig, selected: bool = False):
    """在图片右侧绘制选择圆圈，返回 (cx, cy, box)"""
    r = config.selection_circle_radius
    m = config.selection_circle_margin
    cx = x2 - m - r
    if config.selection_circle_position == "top-right":
        cy = y1 + m + r
    else:
        cy = y2 - m - r
    # 半透明白色背景（用 outline 模拟）
    draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                 outline=(255, 255, 255), width=2,
                 fill=(255, 255, 255, 180) if selected else None)
    return cx, cy, (cx - r, cy - r, cx + r, cy + r)


def _draw_video_duration(draw: ImageDraw.Draw, duration: str,
                          x1: int, y1: int, x2: int, y2: int):
    """在图片左下角绘制视频时长（纯白色文字 + 阴影，无背景框）"""
    font = _get_font(24)
    tx = x1 + 10
    ty = y2 - 30
    # 文字阴影增强可读性
    draw.text((tx + 1, ty + 1), duration, fill=(0, 0, 0, 180), font=font)
    draw.text((tx, ty), duration, fill=(255, 255, 255), font=font)


# ── 主渲染函数 ────────────────────────────────────────────────────

def render_album(
    config: AppConfig,
    photos: list[PhotoEntry],
    root_dir: str = ".",
    is_video_list: Optional[List[bool]] = None,
    durations: Optional[List[Optional[str]]] = None,
) -> tuple[Image.Image, list[SlotInfo]]:
    """
    合成一张相册截图。

    优先使用 config.background_image 中的真实截图作为 chrome 底图，
    仅替换网格区域内容。若未指定背景图，则回退到全 Pillow 绘制。

    返回：
        img      - Pillow Image 对象
        slots    - 每张图片的位置/坐标信息列表
    """
    bg_path = Path(root_dir) / config.background_image if config.background_image else None

    if bg_path and bg_path.exists():
        # ── 主路径：以真实截图为背景 ──────────────────────────────
        img = Image.open(bg_path).convert("RGB")
        # 若截图尺寸与 config 不完全一致，缩放对齐
        if img.size != config.image_size:
            img = img.resize(config.image_size, Image.LANCZOS)
        draw = ImageDraw.Draw(img, "RGBA")
    else:
        # ── Fallback：全 Pillow 绘制 chrome ──────────────────────
        img = Image.new("RGB", config.image_size, config.bg_color)
        draw = ImageDraw.Draw(img, "RGBA")

        _draw_status_bar(draw, config)

        if config.header_style == "simple":
            _draw_simple_header(draw, config)
        elif config.header_style == "dark":
            _draw_dark_header(draw, config)
        elif config.header_style == "with_search":
            _draw_search_header(draw, config)
        elif config.header_style == "with_tabs":
            _draw_tabs_header(draw, config)

        _draw_bottom_nav(draw, config)

    # 清空网格区域（用纯色覆盖，抹掉原截图中的图片内容）
    draw.rectangle(
        [0, config.grid_start_y, config.image_size[0], config.grid_end_y],
        fill=config.grid_bg_color if config.background_image else config.bg_color
    )

    # 标准化 is_video_list 和 durations
    _n = len(photos)
    _is_video = list(is_video_list) if is_video_list else [False] * _n
    _durations = list(durations) if durations else [None] * _n

    # ── 网格布局 ──────────────────────────────────────────────────
    slots: list[SlotInfo] = []
    visual_slot = 0
    grid_index = 0  # 用户视角的图片计数（1-based，只对图片格计数）

    def _slot_coords(slot: int) -> tuple[int, int, int, int]:
        row = slot // config.cols
        col = slot % config.cols
        x1 = config.grid_start_x + col * (config.cell_size + config.gap)
        y1 = config.grid_start_y + row * (config.cell_size + config.gap)
        return x1, y1, x1 + config.cell_size, y1 + config.cell_size

    # 拍照位
    if config.has_camera_slot:
        x1, y1, x2, y2 = _slot_coords(0)
        _draw_camera_slot(draw, x1, y1, x2, y2, config)
        visual_slot = 1

    # 图片/视频格
    for photo_idx, photo in enumerate(photos):
        row = visual_slot // config.cols
        col = visual_slot % config.cols
        x1, y1, x2, y2 = _slot_coords(visual_slot)

        # 跳过超出屏幕的格子
        if y2 > config.grid_end_y:
            break

        is_video = _is_video[photo_idx] if photo_idx < len(_is_video) else False
        duration = _durations[photo_idx] if photo_idx < len(_durations) else None

        # 粘贴缩略图
        try:
            thumb = Image.open(photo.source_path).convert("RGB")
            thumb = thumb.resize((config.cell_size, config.cell_size), Image.LANCZOS)
            img.paste(thumb, (x1, y1))
        except Exception:
            # 图片加载失败：用灰色占位
            draw.rectangle([x1, y1, x2, y2], fill=(180, 180, 180))

        # 视频时长叠加层（仅视频格）
        draw_overlay = ImageDraw.Draw(img, "RGBA")
        if is_video and duration:
            _draw_video_duration(draw_overlay, duration, x1, y1, x2, y2)

        # 选择圆圈
        if config.has_selection_circle:
            cx, cy, circle_box = _draw_selection_circle(draw_overlay, x2, y1, y2, config)
            click_target = (cx, cy)
            click_box = circle_box
            target_type = "selection_circle"
        else:
            click_target = ((x1 + x2) // 2, (y1 + y2) // 2)
            click_box = (x1, y1, x2, y2)
            target_type = "photo_center"

        # grid_index 只对图片格计数
        if not is_video:
            grid_index += 1

        slots.append(SlotInfo(
            grid_index=grid_index if not is_video else 0,
            visual_slot=visual_slot,
            row=row,
            col=col,
            bbox=(x1, y1, x2, y2),
            click_target=click_target,
            click_box=click_box,
            target_type=target_type,
            photo=photo,
            is_video=is_video,
            duration=duration,
        ))
        visual_slot += 1

    return img, slots
