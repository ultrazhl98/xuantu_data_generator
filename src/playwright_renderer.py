"""
playwright_renderer.py — HTML/CSS + Playwright 渲染相册 UI

用真实 CSS 渲染 App 界面，优势：
- 系统字体 -apple-system / PingFang SC
- SVG 矢量图标（信号条、WiFi 弧线、电池）
- CSS 圆角、阴影、精确布局
- 坐标从 DOM getBoundingClientRect() 精确读取，无需手算
"""

from __future__ import annotations

import atexit
import io
import tempfile
from pathlib import Path

from PIL import Image

from .app_config import AppConfig
from .source_library import PhotoEntry

# 状态栏高度（所有 App 通用）
_STATUS_BAR_H = 55

# ── Browser 单例 ─────────────────────────────────────────────────────

_pw = None
_browser = None


def _get_browser():
    global _pw, _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch()
    return _browser


def close_browser():
    global _pw, _browser
    if _browser is not None:
        try:
            _browser.close()
            _pw.stop()
        except Exception:
            pass
        _browser = None
        _pw = None


atexit.register(close_browser)


# ── SVG 图标 ─────────────────────────────────────────────────────────

_SVG_SIGNAL = (
    '<svg width="20" height="16" viewBox="0 0 20 16" fill="currentColor" '
    'style="display:block">'
    '<rect x="0"  y="11" width="3.5" height="5"  rx="0.8"/>'
    '<rect x="5.5"  y="7.5" width="3.5" height="8.5" rx="0.8"/>'
    '<rect x="11" y="4"  width="3.5" height="12" rx="0.8"/>'
    '<rect x="16.5" y="0"  width="3.5" height="16" rx="0.8"/>'
    "</svg>"
)

_SVG_WIFI = (
    '<svg width="22" height="18" viewBox="0 0 22 18" fill="none" '
    'style="display:block">'
    '<circle cx="11" cy="15.5" r="2" fill="currentColor"/>'
    '<path d="M7.2 12.0 A5.2 5.2 0 0 1 14.8 12.0"'
    ' stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
    '<path d="M3.5 8.5 A9.5 9.5 0 0 1 18.5 8.5"'
    ' stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
    '<path d="M-0.2 5.0 A14.2 14.2 0 0 1 22.2 5.0"'
    ' stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>'
    "</svg>"
)

_SVG_BATTERY = (
    '<svg width="32" height="16" viewBox="0 0 32 16" '
    'style="display:block">'
    '<rect x="0.5" y="1.5" width="25" height="13" rx="3"'
    ' stroke="currentColor" stroke-width="1.5" fill="none"/>'
    '<rect x="26.5" y="5" width="4" height="6" rx="2" fill="currentColor"/>'
    '<rect x="2.5" y="3.5" width="20" height="9" rx="1.5" fill="currentColor"/>'
    "</svg>"
)

_SVG_CAMERA = (
    '<svg viewBox="0 0 90 78" fill="none" stroke="#999" '
    'stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"'
    ' width="72" height="62">'
    '<rect x="4" y="18" width="82" height="56" rx="9"/>'
    '<circle cx="45" cy="46" r="18"/>'
    '<circle cx="45" cy="46" r="10"/>'
    '<rect x="30" y="7" width="30" height="14" rx="5"/>'
    '<circle cx="72" cy="30" r="4" fill="#999" stroke="none"/>'
    "</svg>"
)

_SVG_SEARCH = (
    '<svg width="28" height="28" viewBox="0 0 28 28" fill="none" '
    'stroke="#8e8e93" stroke-width="2.2" stroke-linecap="round" '
    'style="display:block;flex-shrink:0">'
    '<circle cx="12" cy="12" r="8.5"/>'
    '<line x1="18.5" y1="18.5" x2="25" y2="25"/>'
    "</svg>"
)

_SVG_CHEVRON = (
    '<svg width="16" height="30" viewBox="0 0 16 30" fill="none" '
    'stroke="#007aff" stroke-width="3.5" stroke-linecap="round" '
    'stroke-linejoin="round" style="display:block">'
    '<polyline points="13,2 3,15 13,28"/>'
    "</svg>"
)


# ── CSS 构建 ──────────────────────────────────────────────────────────

def _build_css(config: AppConfig) -> str:
    W, H = config.image_size
    grid_left = (W - config.cols * config.cell_size - (config.cols - 1) * config.gap) // 2
    header_h = config.grid_start_y - _STATUS_BAR_H
    bottom_h = H - config.grid_end_y

    grid_bg_map = {
        "simple":      "#f2f2f2",
        "dark":        "#1c1c1e",
        "with_search": "#ffffff",
        "with_tabs":   "#ffffff",
    }
    grid_bg = grid_bg_map.get(config.header_style, "#f2f2f2")
    is_dark = config.theme == "dark"
    sb_bg = "#000000" if is_dark else "#ffffff"
    sb_fg = "#ffffff" if is_dark else "#000000"

    return f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{
    width: {W}px; height: {H}px;
    overflow: hidden;
    font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
    -webkit-font-smoothing: antialiased;
    background: {sb_bg};
}}

/* ════════ 状态栏 ({_STATUS_BAR_H}px) ════════ */
.status-bar {{
    height: {_STATUS_BAR_H}px;
    background: {sb_bg};
    color: {sb_fg};
    display: flex;
    align-items: center;
    padding: 0 50px;
}}
.sb-time {{
    font-size: 36px;
    font-weight: 600;
    letter-spacing: -0.5px;
}}
.sb-icons {{
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 10px;
    color: {sb_fg};
}}

/* ════════ 相册 NavBar ════════ */
.header-simple {{
    height: {header_h}px;
    background: #ffffff;
    display: flex;
    align-items: center;
    padding: 0 24px;
    border-bottom: 1px solid rgba(0,0,0,0.14);
}}
.nav-back {{
    display: flex;
    align-items: center;
    gap: 4px;
    color: #007aff;
}}
.nav-back-text {{
    font-size: 44px;
    font-weight: 500;
}}
.nav-actions {{
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 28px;
}}
.nav-action {{
    font-size: 40px;
    color: #007aff;
    font-weight: 400;
}}
.nav-more {{
    font-size: 38px;
    color: #007aff;
    font-weight: 700;
    letter-spacing: 3px;
}}

/* ════════ 微信 Header ════════ */
.header-dark {{
    height: {header_h}px;
    background: #1e1e1e;
    display: flex;
    align-items: center;
    padding: 0 30px;
}}
.wc-close {{
    font-size: 48px;
    color: #8e8e8e;
    line-height: 1;
    width: 52px;
}}
.wc-title-wrap {{
    flex: 1;
    display: flex;
    justify-content: center;
}}
.wc-title-pill {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 10px 24px;
    border-radius: 22px;
    background: rgba(255,255,255,0.12);
}}
.wc-title-text {{
    font-size: 44px;
    font-weight: 500;
    color: #ffffff;
}}
.wc-title-arrow {{
    font-size: 20px;
    color: rgba(255,255,255,0.6);
}}
.wc-spacer {{ width: 44px; }}

/* ════════ 微博 Header ════════ */
.header-search {{ background: #ffffff; }}
.wb-title-row {{
    height: {max(header_h - 100, 55)}px;
    display: flex;
    align-items: center;
    padding: 0 24px;
    border-bottom: 1px solid rgba(0,0,0,0.08);
}}
.wb-cancel {{ font-size: 40px; color: #007aff; font-weight: 400; }}
.wb-title {{
    flex: 1;
    text-align: center;
    font-size: 44px;
    font-weight: 600;
    color: #000000;
}}
.wb-next-btn {{
    font-size: 36px;
    color: #ffffff;
    font-weight: 500;
    background: #007aff;
    padding: 12px 30px;
    border-radius: 22px;
}}
.wb-search-row {{
    height: {header_h - max(header_h - 100, 55)}px;
    display: flex;
    align-items: center;
    padding: 0 22px;
    background: #ffffff;
}}
.wb-search-bar {{
    flex: 1;
    height: 88px;
    background: #ebebf0;
    border-radius: 16px;
    display: flex;
    align-items: center;
    padding: 0 18px;
    gap: 12px;
}}
.wb-search-text {{
    font-size: 38px;
    color: #8e8e93;
}}

/* ════════ 小红书 Header ════════ */
.header-tabs {{ background: #ffffff; }}
.rb-nav-row {{
    height: {max(header_h - 56, 50)}px;
    display: flex;
    align-items: center;
    padding: 0 24px;
}}
.rb-close {{
    font-size: 48px;
    color: #000000;
    line-height: 1;
    font-weight: 300;
    width: 52px;
}}
.rb-title {{
    flex: 1;
    text-align: center;
    font-size: 44px;
    font-weight: 600;
    color: #000000;
}}
.rb-draft-btn {{
    font-size: 34px;
    color: #333;
    font-weight: 400;
    padding: 8px 18px;
    border-radius: 16px;
    border: 1px solid rgba(0,0,0,0.15);
    display: flex;
    align-items: center;
    gap: 6px;
}}
.rb-tabs-row {{
    height: 56px;
    display: flex;
    align-items: stretch;
    border-bottom: 1px solid rgba(0,0,0,0.1);
    padding: 0 30px;
}}
.rb-tab {{
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 38px;
    color: #8e8e93;
    position: relative;
    font-weight: 400;
}}
.rb-tab-active {{
    color: #000000;
    font-weight: 600;
}}
.rb-tab-active::after {{
    content: '';
    position: absolute;
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 42px;
    height: 3px;
    background: #000000;
    border-radius: 2px;
}}

/* ════════ 图片网格 ════════ */
.grid-area {{
    height: {config.grid_end_y - config.grid_start_y}px;
    background: {grid_bg};
    overflow: hidden;
}}
.grid {{
    display: grid;
    grid-template-columns: repeat({config.cols}, {config.cell_size}px);
    gap: {config.gap}px;
    padding: 0 0 0 {grid_left}px;
}}

/* ════════ 照片格 ════════ */
.photo-cell {{
    position: relative;
    width: {config.cell_size}px;
    height: {config.cell_size}px;
    overflow: hidden;
    background: #c8c8cc;
}}
.photo-cell img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}}

/* 选择圆圈 */
.selection-circle {{
    position: absolute;
    {"top" if config.selection_circle_position == "top-right" else "bottom"}: 10px;
    right: 10px;
    width: 42px;
    height: 42px;
    border-radius: 50%;
    border: 2.5px solid rgba(255,255,255,0.92);
    box-shadow: 0 1px 3px rgba(0,0,0,0.25);
}}

/* 视频时长标签 — 纯白色文字 + 文字阴影，无背景框 */
.video-duration {{
    position: absolute;
    bottom: 6px;
    left: 6px;
    padding: 0;
    background: none;
    color: #ffffff;
    font-size: 20px;
    line-height: 1.45;
    letter-spacing: 0.3px;
    white-space: nowrap;
    text-shadow: 1px 1px 2px rgba(0,0,0,0.7);
}}

/* 拍照位 */
.camera-slot {{
    width: {config.cell_size}px;
    height: {config.cell_size}px;
    background: #f0f0f5;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
}}
.camera-label {{
    font-size: 22px;
    color: #999;
    font-weight: 400;
}}

/* ════════ 底部栏 ════════ */
.bottom-bar {{
    height: {bottom_h}px;
    display: flex;
    align-items: center;
    border-top: 1px solid {"rgba(255,255,255,0.08)" if is_dark else "rgba(0,0,0,0.1)"};
    background: {"#1e1e1e" if is_dark else "#ffffff"};
    position: relative;
}}
/* 相册/小红书：仅 home indicator */
.bottom-bar-minimal {{
    justify-content: center;
    padding-top: 2px;
}}
.home-indicator {{
    width: 180px;
    height: 5px;
    border-radius: 3px;
    background: {"rgba(255,255,255,0.25)" if is_dark else "rgba(0,0,0,0.18)"};
}}

/* 微信底部：预览 + 完成 */
.bottom-bar-wechat {{
    padding: 0 28px;
    justify-content: space-between;
}}
.wc-preview {{
    font-size: 36px;
    color: #ffffff;
    font-weight: 400;
}}
.wc-done-btn {{
    font-size: 34px;
    color: #ffffff;
    background: #07c160;
    padding: 14px 36px;
    border-radius: 8px;
    font-weight: 500;
}}

/* 微博底部：提示文字 */
.bottom-bar-weibo {{
    justify-content: center;
    flex-direction: column;
    align-items: center;
    gap: 6px;
}}
.wb-hint {{
    font-size: 32px;
    color: #007aff;
    font-weight: 400;
}}
"""


# ── HTML 组件构建 ─────────────────────────────────────────────────────

def _status_bar_html() -> str:
    return (
        '<div class="status-bar">'
        '<span class="sb-time">9:41</span>'
        '<span class="sb-icons">'
        + _SVG_SIGNAL
        + _SVG_WIFI
        + _SVG_BATTERY
        + "</span></div>"
    )


def _header_html(config: AppConfig) -> str:
    style = config.header_style

    if style == "simple":
        return (
            '<div class="header-simple">'
            '<span class="nav-back">'
            + _SVG_CHEVRON
            + '<span class="nav-back-text">图片</span>'
            '</span>'
            '<span class="nav-actions">'
            '<span class="nav-action">多选</span>'
            '<span class="nav-more">···</span>'
            '</span>'
            "</div>"
        )

    if style == "dark":
        return (
            '<div class="header-dark">'
            '<span class="wc-close">✕</span>'
            '<span class="wc-title-wrap">'
            '<span class="wc-title-pill">'
            '<span class="wc-title-text">图片和视频</span>'
            '<span class="wc-title-arrow">▾</span>'
            '</span></span>'
            '<span class="wc-spacer"></span>'
            "</div>"
        )

    if style == "with_search":
        return (
            '<div class="header-search">'
            '<div class="wb-title-row">'
            '<span class="wb-cancel">取消</span>'
            '<span class="wb-title">微博相册 ▾</span>'
            '<span class="wb-next-btn">下一步</span>'
            "</div>"
            '<div class="wb-search-row">'
            '<div class="wb-search-bar">'
            + _SVG_SEARCH
            + '<span class="wb-search-text">照片、人物、地点...</span>'
            "</div></div></div>"
        )

    if style == "with_tabs":
        return (
            '<div class="header-tabs">'
            '<div class="rb-nav-row">'
            '<span class="rb-close">✕</span>'
            '<span class="rb-title">相册 ▾</span>'
            '<span class="rb-draft-btn">⊙ 草稿箱</span>'
            "</div>"
            '<div class="rb-tabs-row">'
            '<div class="rb-tab rb-tab-active">全部</div>'
            '<div class="rb-tab">视频</div>'
            '<div class="rb-tab">照片</div>'
            '<div class="rb-tab">实况图</div>'
            "</div></div>"
        )

    return ""


def _bottom_bar_html(config: AppConfig) -> str:
    style = config.header_style

    if style == "dark":
        # 微信：预览 + 完成
        return (
            '<div class="bottom-bar bottom-bar-wechat">'
            '<span class="wc-preview">预览</span>'
            '<span class="wc-done-btn">完成</span>'
            "</div>"
        )

    if style == "with_search":
        # 微博：提示 + home indicator
        return (
            '<div class="bottom-bar bottom-bar-weibo">'
            '<span class="wb-hint">● 可同时选择图片和视频</span>'
            '<div class="home-indicator"></div>'
            "</div>"
        )

    # 相册 / 小红书：仅 home indicator
    return (
        '<div class="bottom-bar bottom-bar-minimal">'
        '<div class="home-indicator"></div>'
        "</div>"
    )


def _grid_html(
    config: AppConfig,
    photos: list[PhotoEntry],
    is_video_list: list[bool],
    durations: list,
) -> str:
    items: list[str] = []
    visual_slot = 0

    # 拍照位（微博）
    if config.has_camera_slot:
        items.append(
            f'<div class="camera-slot">{_SVG_CAMERA}'
            f'<span class="camera-label">拍照</span></div>'
        )
        visual_slot = 1

    # 照片/视频格
    grid_index = 0
    for photo_idx, photo in enumerate(photos):
        row = visual_slot // config.cols
        y2_abs = config.grid_start_y + (row + 1) * (config.cell_size + config.gap)
        if y2_abs > config.grid_end_y:
            break

        is_video = is_video_list[photo_idx] if photo_idx < len(is_video_list) else False
        duration = durations[photo_idx] if photo_idx < len(durations) else None

        # grid_index 只对图片格计数
        if not is_video:
            grid_index += 1

        src = Path(photo.source_path).resolve().as_uri()

        # 视频格：左下角时长叠加；图片格：无叠加
        overlay_html = ""
        if is_video and duration:
            overlay_html = f'<div class="video-duration">{duration}</div>'

        circle_html = (
            '<div class="selection-circle"></div>' if config.has_selection_circle else ""
        )

        # 图片格附带 data-grid-index；视频格只有 data-visual-slot
        grid_index_attr = f' data-grid-index="{grid_index}"' if not is_video else ""
        is_video_attr = ' data-is-video="true"' if is_video else ""
        duration_attr = f' data-duration="{duration}"' if is_video and duration else ""

        items.append(
            f'<div class="photo-cell"'
            f'{grid_index_attr}'
            f' data-visual-slot="{visual_slot}"'
            f'{is_video_attr}'
            f'{duration_attr}>'
            f'<img src="{src}" loading="eager" decoding="sync"/>'
            f"{overlay_html}"
            f"{circle_html}"
            f"</div>"
        )
        visual_slot += 1

    return (
        '<div class="grid-area"><div class="grid">'
        + "".join(items)
        + "</div></div>"
    )


def _build_html(
    config: AppConfig,
    photos: list[PhotoEntry],
    is_video_list: list[bool],
    durations: list,
) -> str:
    css = _build_css(config)
    return (
        "<!DOCTYPE html><html><head>"
        '<meta charset="UTF-8">'
        f"<style>{css}</style>"
        "</head><body>"
        + _status_bar_html()
        + _header_html(config)
        + _grid_html(config, photos, is_video_list, durations)
        + _bottom_bar_html(config)
        + "</body></html>"
    )


# ── 主渲染函数 ─────────────────────────────────────────────────────────

def _make_slot_info(**kwargs):
    from .renderer import SlotInfo
    return SlotInfo(**kwargs)


def render_album(
    config: AppConfig,
    photos: list[PhotoEntry],
    root_dir: str = ".",
    is_video_list: list = None,
    durations: list = None,
) -> tuple[Image.Image, list]:
    """
    用 HTML/CSS + Playwright 渲染相册截图。

    返回：
        img   - PIL Image (RGB)
        slots - list[SlotInfo]（含图片格和视频格，视频格 grid_index=0）
    """
    _n = len(photos)
    _is_video = list(is_video_list) if is_video_list else [False] * _n
    _durations = list(durations) if durations else [None] * _n

    html = _build_html(config, photos, _is_video, _durations)

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    )
    tmp.write(html)
    tmp.close()
    tmp_path = Path(tmp.name)

    browser = _get_browser()
    W, H = config.image_size
    page = browser.new_page(
        viewport={"width": W, "height": H},
        device_scale_factor=1,
    )

    try:
        page.goto(tmp_path.as_uri(), wait_until="load")

        page.evaluate(
            """() => Promise.all(
                Array.from(document.images).map(img =>
                    img.complete
                        ? Promise.resolve()
                        : new Promise(r => { img.onload = img.onerror = r; })
                )
            )"""
        )

        png_bytes = page.screenshot(
            clip={"x": 0, "y": 0, "width": W, "height": H}
        )
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

        slots_data: list[dict] = page.evaluate(
            """() => Array.from(document.querySelectorAll('[data-visual-slot]')).map(cell => {
                const circle = cell.querySelector('.selection-circle');
                const cR = cell.getBoundingClientRect();
                const sR = circle ? circle.getBoundingClientRect() : null;
                const isVideo = cell.dataset.isVideo === 'true';
                return {
                    grid_index:  cell.dataset.gridIndex ? +cell.dataset.gridIndex : 0,
                    visual_slot: +cell.dataset.visualSlot,
                    is_video:    isVideo,
                    duration:    cell.dataset.duration || null,
                    bbox: [
                        Math.round(cR.left), Math.round(cR.top),
                        Math.round(cR.right), Math.round(cR.bottom)
                    ],
                    click_target: sR
                        ? [
                            Math.round(sR.left + sR.width  / 2),
                            Math.round(sR.top  + sR.height / 2)
                          ]
                        : [
                            Math.round(cR.left + cR.width  / 2),
                            Math.round(cR.top  + cR.height / 2)
                          ],
                    click_box: sR
                        ? [
                            Math.round(sR.left), Math.round(sR.top),
                            Math.round(sR.right), Math.round(sR.bottom)
                          ]
                        : [
                            Math.round(cR.left), Math.round(cR.top),
                            Math.round(cR.right), Math.round(cR.bottom)
                          ],
                    target_type: sR ? 'selection_circle' : 'photo_center',
                };
            })"""
        )

    finally:
        page.close()
        tmp_path.unlink(missing_ok=True)

    slots = []
    photo_iter = iter(photos)
    for d in slots_data:
        photo = next(photo_iter)
        vs = d["visual_slot"]
        slots.append(_make_slot_info(
            grid_index=d["grid_index"],
            visual_slot=vs,
            row=vs // config.cols,
            col=vs % config.cols,
            bbox=tuple(d["bbox"]),
            click_target=tuple(d["click_target"]),
            click_box=tuple(d["click_box"]),
            target_type=d["target_type"],
            photo=photo,
            is_video=d["is_video"],
            duration=d["duration"],
        ))

    return img, slots
