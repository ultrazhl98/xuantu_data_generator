"""
instruction_generator.py — 训练指令生成

支持两大类指令：
1. 顺序类：基于 grid_index / row / col / timestamp，纯逻辑生成
2. 内容类：调用 Gemma 模型，根据图片标签生成自然语言指令

每条指令生成一个 TrainingSample。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Optional

from .renderer import SlotInfo
from .app_config import AppConfig


# ── 数据结构 ──────────────────────────────────────────────────────

@dataclass
class TrainingSample:
    image_path: str
    app: str
    instruction: str
    instruction_type: str          # "sequential" | "content"
    click_targets: list[tuple]     # [(cx, cy), ...]
    click_boxes: list[tuple]       # [(x1, y1, x2, y2), ...] 每个点击目标对应的 box
    selected_grid_indices: list[int]


# ── 中文数字 ─────────────────────────────────────────────────────

_CN_NUMS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
            "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]

def _cn(n: int) -> str:
    if 1 <= n <= len(_CN_NUMS):
        return _CN_NUMS[n - 1]
    return str(n)

def _num(n: int, rng: random.Random) -> str:
    """随机用中文数字或阿拉伯数字"""
    if n <= 10 and rng.random() < 0.5:
        return _cn(n)
    return str(n)


# ── 顺序类指令 ────────────────────────────────────────────────────

def _make_single_index(slot: SlotInfo, image_path: str, app: str,
                        rng: random.Random) -> TrainingSample:
    n = _num(slot.grid_index, rng)
    templates = [
        f"发送第{n}张图片",
        f"选择第{n}张照片",
        f"分享第{n}张图片",
        f"把第{n}张图片发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[slot.click_target],
        click_boxes=[slot.click_box],
        selected_grid_indices=[slot.grid_index],
    )


def _make_row_col(slot: SlotInfo, image_path: str, app: str,
                   rng: random.Random) -> TrainingSample:
    r = _num(slot.row + 1, rng)
    c = _num(slot.col + 1, rng)
    templates = [
        f"发送第{r}行第{c}列的图片",
        f"选择第{r}排第{c}个照片",
        f"第{r}行第{c}列那张图片发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[slot.click_target],
        click_boxes=[slot.click_box],
        selected_grid_indices=[slot.grid_index],
    )


def _make_multi_index(slots_subset: list[SlotInfo], image_path: str, app: str,
                       rng: random.Random) -> TrainingSample:
    indices = [s.grid_index for s in slots_subset]
    indices_str = "、".join(_num(i, rng) for i in indices)
    # 连续范围 or 离散
    if len(indices) >= 2 and indices[-1] - indices[0] == len(indices) - 1:
        n1, n2 = _num(indices[0], rng), _num(indices[-1], rng)
        templates = [
            f"发送第{n1}到第{n2}张图片",
            f"选择第{n1}至{n2}张照片",
        ]
    else:
        templates = [
            f"选择第{indices_str}张图片",
            f"发送第{indices_str}张照片",
            f"把第{indices_str}张图片发过来",
        ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[s.click_target for s in slots_subset],
        click_boxes=[s.click_box for s in slots_subset],
        selected_grid_indices=indices,
    )


def _make_newest_n(slots: list[SlotInfo], n: int, image_path: str, app: str,
                    rng: random.Random) -> Optional[TrainingSample]:
    """最新 N 张（grid_index 最小的 N 张，因左上角最新）"""
    sorted_slots = sorted(slots, key=lambda s: s.grid_index)
    chosen = sorted_slots[:n]
    if len(chosen) < n:
        return None
    num_str = _num(n, rng)
    templates = [
        f"发送最新的{num_str}张图片",
        f"选择最近{num_str}张照片",
        f"把最新的{num_str}张图发给我",
    ]
    if n == 1:
        templates += ["发送最新的图片", "选择最近的一张照片"]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[s.click_target for s in chosen],
        click_boxes=[s.click_box for s in chosen],
        selected_grid_indices=[s.grid_index for s in chosen],
    )


def _make_last_n(slots: list[SlotInfo], n: int, image_path: str, app: str,
                  rng: random.Random) -> Optional[TrainingSample]:
    """最后 N 张（grid_index 最大的 N 张）"""
    sorted_slots = sorted(slots, key=lambda s: s.grid_index, reverse=True)
    chosen = sorted_slots[:n]
    if len(chosen) < n:
        return None
    num_str = _num(n, rng)
    templates = [
        f"发送最后{num_str}张图片",
        f"选择最末{num_str}张照片",
        f"把最后{num_str}张图发给我",
    ]
    return TrainingSample(
        image_path=image_path,
        app=app,
        instruction=rng.choice(templates),
        instruction_type="sequential",
        click_targets=[s.click_target for s in chosen],
        click_boxes=[s.click_box for s in chosen],
        selected_grid_indices=[s.grid_index for s in chosen],
    )


# ── 内容类指令（模型驱动） ────────────────────────────────────────

def _build_content_prompt(slots: list[SlotInfo], n: int) -> str:
    """构建让 Gemma 生成内容指令的 prompt"""
    lines = ["你在一个手机相册界面中看到以下图片："]
    for slot in slots:
        labels_str = "、".join(slot.photo.labels) if slot.photo.labels else "未知"
        lines.append(f"第{slot.grid_index}张：标签 [{labels_str}]")

    lines.append(f"\n请生成 {n} 条自然语言指令，每条指令要求用户选择或发送特定的图片。")
    lines.append("指令要多样化，包括但不限于：")
    lines.append("- 按内容选择单张（如\"发送那张猫的照片\"）")
    lines.append("- 按类别选择多张（如\"把所有动物的图片发给我\"）")
    lines.append("- 按第N个某类内容选择（如\"发送第二张有狗的照片\"）")
    lines.append("- 按内容组合选择（如\"把有猫和有狗的照片都发过来\"）")
    lines.append("\n注意：")
    lines.append("- selected_indices 使用图片编号（上面列出的第几张）")
    lines.append("- 每条指令的 selected_indices 不能为空")
    lines.append("- 指令要自然口语化，像真实用户的说法")
    lines.append("\n只返回 JSON 数组，不要其他文字：")
    lines.append('[{"instruction": "...", "selected_indices": [1, 4]}, ...]')
    return "\n".join(lines)

def _build_content_prompt(slots: list[SlotInfo], n: int) -> str:
    """构建增强型、具备泛化能力的指令生成 prompt"""
    
    # 1. 场景化上下文描述
    lines = [
        "### 角色设定",
        "你是一个正在使用智能相册的真实用户。你正对着手机使用语音控制功能，让 AI 助手帮你挑选照片发送给朋友或整理文件夹。",
        "你说话风格自然、随意，会根据屏幕上的内容差异灵活调整说法。",
        "\n### 当前屏幕照片元数据（Metadata）",
    ]

    # 2. 注入图片信息，并提示模型关注标签重复情况
    for slot in slots:
        labels_str = "、".join(slot.photo.labels) if slot.photo.labels else "未知"
        lines.append(f"图片 {slot.grid_index}：核心标签 [{labels_str}]")

    # 3. 核心生成逻辑与多样性约束
    lines.extend([
        f"\n### 任务要求：生成 {n} 条不重复的、地道的口语指令",
        "1. **消除歧义优先**：如果屏幕上有两张及以上的图片标签相似（例如都有'狗'），你的指令必须包含区分性描述，如：",
        "   - 方位词：'左边那张狗'、'最后一行那个小猫'",
        "   - 序数词：'选第二张有天安门的'、'第三张风景照'",
        "   - 特征词：'那张金毛的图'、'正在跑步的那只狗'",
        
        "2. **拒绝机械化句式**：禁止反复使用'发送第X张'或'选择标签为X的图片'。尝试以下真实语气：",
        "   - 动作多样化：'帮我点一下'、'把...勾选上'、'把...都发过去'、'找找看那张...'、'打包这几张'",
        "   - 省略与代词：'就要这张'、'还有这个'、'除了猫的那张，其他的都要'",
        
        "3. **覆盖多种逻辑**：",
        "   - 单选：'发一下那张柯基的图'",
        "   - 类别多选：'把这次去北京拍的照片都选上'（对应标签包含北京的图片），对应的图片不要超过3张，如果不符合可以不生成",
        "   - 逻辑组合：'把小猫和小狗的图片发到朋友圈'，对应的图片不要超过3张，如果不符合可以不生成",
        "   - 对应数量限制：一条指令对应的需要选择的图片数量不超过3张",


        "\n### 负面约束（Strict Negative Constraints）",
        "- 严禁在指令中直接出现 'selected_indices' 或 '标签' 等开发术语。",
        "- 严禁每条指令都以相同的动词开头。",
        "- 严禁生成无法从给定图片列表中找到对应目标的指令。",

        "\n### 输出格式",
        "必须严格返回 JSON 数组格式，禁止任何解释性文字：",
        '[{"instruction": "指令文本", "selected_indices": [编号, 编号]}]'
    ])
    
    return "\n".join(lines)



def _parse_content_response(text: str) -> list[dict]:
    """解析模型返回的 JSON 数组"""
    text = text.strip()
    # 去除 ```json ... ``` 包裹
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                result = json.loads(part)
                if isinstance(result, list):
                    return result
            except (json.JSONDecodeError, ValueError):
                continue
    # 直接解析：找第一个 [ 到最后一个 ]
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    return json.loads(text)


def generate_content_samples_via_model(
    slots: list[SlotInfo],
    image_path: str,
    app: str,
    n: int,
    model: str = "gemma4:e4b",
) -> list[TrainingSample]:
    """调用 Gemma 模型生成内容类指令"""
    import ollama

    prompt = _build_content_prompt(slots, n)
    print(f"\n{'='*60}")
    print(f"[Content Prompt] model={model}")
    print(f"{'='*60}")
    print(prompt)
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.7},
    )
    text = response["message"]["content"]
    print(f"\n{'-'*60}")
    print(f"[Model Response]")
    print(f"{'-'*60}")
    print(text)
    print(f"{'='*60}\n")
    raw_items = _parse_content_response(text)

    # 构建 grid_index → slot 映射
    slot_map = {s.grid_index: s for s in slots}

    samples = []
    for item in raw_items:
        instruction = item.get("instruction", "").strip()
        indices = item.get("selected_indices", [])
        if not instruction or not indices:
            continue

        # 过滤无效索引
        valid_indices = [i for i in indices if i in slot_map]
        if not valid_indices:
            continue

        matched_slots = [slot_map[i] for i in valid_indices]
        samples.append(TrainingSample(
            image_path=image_path,
            app=app,
            instruction=instruction,
            instruction_type="content",
            click_targets=[s.click_target for s in matched_slots],
            click_boxes=[s.click_box for s in matched_slots],
            selected_grid_indices=valid_indices,
        ))

    return samples[:n]


# ── 主生成函数 ────────────────────────────────────────────────────

def generate_samples(
    image_path: str,
    slots: list[SlotInfo],
    config: AppConfig,
    n_sequential: int = 3,
    n_content: int = 3,
    model: str = "gemma4:e4b",
    rng: Optional[random.Random] = None,
) -> list[TrainingSample]:
    """
    从一张合成图的 slots 信息中生成训练样本列表。

    n_sequential: 生成的顺序类指令数（每张图随机抽取）
    n_content:    生成的内容类指令数
    model:        用于生成内容类指令的 Ollama 模型名称
    """
    rng = rng or random.Random()
    samples: list[TrainingSample] = []
    n = len(slots)
    if n == 0:
        return samples

    # ── 顺序类 ───────────────────────────────────────────────────
    sequential_candidates: list[TrainingSample] = []

    # 单张定位
    for slot in slots:
        sequential_candidates.append(_make_single_index(slot, image_path, config.name, rng))
        if slot.row > 0 or slot.col > 0:   # 行列坐标（1,1 以外才有意义说出来）
            sequential_candidates.append(_make_row_col(slot, image_path, config.name, rng))

    # 多选：随机选 2~3 张
    if n >= 2:
        for _ in range(min(3, n)):
            k = rng.randint(2, min(3, n))
            chosen = sorted(rng.sample(slots, k), key=lambda s: s.grid_index)
            sequential_candidates.append(_make_multi_index(chosen, image_path, config.name, rng))

    # 最新/最后 N 张
    for cnt in [1, 2, 3]:
        s = _make_newest_n(slots, cnt, image_path, config.name, rng)
        if s:
            sequential_candidates.append(s)
        s = _make_last_n(slots, cnt, image_path, config.name, rng)
        if s:
            sequential_candidates.append(s)

    rng.shuffle(sequential_candidates)
    samples.extend(sequential_candidates[:n_sequential])

    # ── 内容类（模型驱动） ───────────────────────────────────────
    if n_content > 0:
        try:
            content_samples = generate_content_samples_via_model(
                slots=slots,
                image_path=image_path,
                app=config.name,
                n=n_content,
                model=model,
            )
            samples.extend(content_samples)
        except Exception as e:
            import sys
            print(f"警告：内容指令生成失败：{e}", file=sys.stderr)

    return samples
