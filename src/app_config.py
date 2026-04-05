from dataclasses import dataclass, field


@dataclass
class AppConfig:
    name: str
    image_size: tuple = (1276, 2848)
    cols: int = 4
    cell_size: int = 310
    gap: int = 3
    grid_start_y: int = 110
    bottom_nav_height: int = 34

    # 关键 flags
    has_camera_slot: bool = False   # 第一格是否为拍照按钮（不计入 grid_index）
    has_selection_circle: bool = True
    selection_circle_radius: int = 21   # px
    selection_circle_margin: int = 10   # 距 cell 角落的偏移
    selection_circle_position: str = "top-right"  # "top-right" | "bottom-right"

    # 外观（全绘制模式使用）
    theme: str = "light"            # "light" | "dark"
    header_style: str = "simple"    # "simple" | "dark" | "with_search" | "with_tabs"
    video_ratio: float = 0.0        # 0.0 = 纯图模式；0~1 = 随机混合视频的概率

    @property
    def grid_start_x(self) -> int:
        """网格左边距（使网格水平居中）"""
        total_cells_width = self.cols * self.cell_size + (self.cols - 1) * self.gap
        return (self.image_size[0] - total_cells_width) // 2

    @property
    def grid_end_y(self) -> int:
        return self.image_size[1] - self.bottom_nav_height

    @property
    def max_visible_rows(self) -> int:
        available_height = self.grid_end_y - self.grid_start_y
        return available_height // (self.cell_size + self.gap)

    @property
    def max_photos(self) -> int:
        """当前屏幕最多可显示的图片数（不含拍照位）"""
        total_slots = self.max_visible_rows * self.cols
        return total_slots - (1 if self.has_camera_slot else 0)

    # 颜色主题
    @property
    def grid_bg_color(self) -> tuple:
        """网格区域背景色（由 header_style 决定）"""
        if self.header_style == "dark":
            return (28, 28, 30)
        elif self.header_style in ("with_search", "with_tabs"):
            return (255, 255, 255)
        else:
            return (242, 242, 242)

    @property
    def bg_color(self):
        return (28, 28, 30) if self.theme == "dark" else (242, 242, 242)

    @property
    def header_bg_color(self):
        return (0, 0, 0) if self.theme == "dark" else (255, 255, 255)

    @property
    def header_text_color(self):
        return (255, 255, 255) if self.theme == "dark" else (0, 0, 0)

    @property
    def grid_gap_color(self):
        return (28, 28, 30) if self.theme == "dark" else (229, 229, 229)

    @property
    def status_bar_color(self):
        return (0, 0, 0) if self.theme == "dark" else (255, 255, 255)


# ── 4 种预设 App ──────────────────────────────────────────────────

ALBUM = AppConfig(
    name="相册",
    grid_start_y=180,
    has_camera_slot=False,
    header_style="simple",
)

WECHAT = AppConfig(
    name="微信",
    grid_start_y=220,
    has_camera_slot=False,
    theme="dark",
    header_style="dark",
    bottom_nav_height=100,
)

WEIBO = AppConfig(
    name="微博",
    grid_start_y=310,
    has_camera_slot=True,
    header_style="with_search",
    bottom_nav_height=95,
)

REDBOOK = AppConfig(
    name="小红书",
    grid_start_y=270,
    has_camera_slot=False,
    header_style="with_tabs",
)

APP_PRESETS: dict[str, AppConfig] = {
    "相册": ALBUM,
    "微信": WECHAT,
    "微博": WEIBO,
    "小红书": REDBOOK,
}
