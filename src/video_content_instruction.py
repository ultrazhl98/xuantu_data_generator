"""
video_content_instruction.py — 基于内容的视频指令生成（调用 LLM 模型）

通过 Ollama 模型根据视频标签和时长生成自然语言指令。
"""

from __future__ import annotations

from .renderer import SlotInfo
from .instruction_types import TrainingSample
from .content_instruction import _parse_content_response


def _build_video_content_prompt(slots: list[SlotInfo], n: int) -> str:
    """构建视频指令生成 prompt"""

    lines = [
        "### 角色设定",
        "你是一个正在使用智能相册的真实用户。你正对着手机使用语音控制功能，让 AI 助手帮你挑选视频发送给朋友或整理文件夹。",
        "你说话风格自然、随意，会根据屏幕上的内容差异灵活调整说法。",
        "\n### 当前屏幕视频元数据（Metadata）",
    ]

    for slot in slots:
        labels_str = "、".join(slot.photo.labels) if slot.photo.labels else "未知"
        desc = slot.photo.description or ""
        dur = slot.duration or "未知"
        lines.append(f"视频 {slot.video_index}：核心标签 [{labels_str}]，描述：{desc}，时长：{dur}")

    lines.extend([
        f"\n### 任务要求：生成 {n} 条不重复的、地道的口语指令",
        "1. **消除歧义优先**：如果屏幕上有两个及以上的视频标签相似（例如都有'狗'），你的指令必须包含区分性描述，如：",
        "   - 方位词：'左边那个狗的视频'、'最后一行那个猫的视频'",
        "   - 序数词：'选第二个有天安门的视频'、'第三个风景视频'",
        "   - 特征词：'那个金毛的视频'、'正在跑步的那个视频'",
        "   - 时长特征：'那个比较长的视频'、'短的那个视频'",

        "2. **拒绝机械化句式**：禁止反复使用'发送第X个'或'选择标签为X的视频'。尝试以下真实语气：",
        "   - 动作多样化：'帮我播放一下'、'把...发过去'、'找找看那个...'、'打开这个视频'",
        "3. **覆盖多种逻辑**：",
        "   - 单选：'播放一下那个柯基的视频'",
        "   - 类别多选：'把这次去北京拍的视频都选上'（对应标签包含北京的视频），对应的视频不要超过3个，如果不符合可以不生成",
        "   - 逻辑组合：'把小猫和小狗的视频都发过去'，对应的视频不要超过3个，如果不符合可以不生成",
        "   - 对应数量限制：一条指令对应的需要选择的视频数量不超过3个",

        "\n### 负面约束（Strict Negative Constraints）",
        "- 严禁在指令中直接出现 'selected_indices' 或 '标签' 等开发术语。",
        "- 严禁每条指令都以相同的动词开头。",
        "- 严禁生成无法从给定视频列表中找到对应目标的指令。",
        "- 严禁在指令中使用'图片'、'照片'等词，必须使用'视频'。",

        "\n### 输出格式",
        "1. 必须返回 JSON 数组，每条数据包含 'instruction' 和 'selected_indices'。",
        "2. **selected_indices**：数组长度取决于你的指令内容。单选时只填一个编号 [1]；多选时按顺序填入所有匹配的编号 [1, 3]。",
        "3. 确保指令描述的内容与 selected_indices 对应的视频标签完全吻合，不要产生幻觉。",

        '[{"instruction": "指令文本", "selected_indices": 对应的标号列表}]'
    ])

    return "\n".join(lines)


def generate_video_content_samples_via_model(
    slots: list[SlotInfo],
    image_path: str,
    app: str,
    n: int,
    model: str = "gemma4:e4b",
) -> list[TrainingSample]:
    """调用 Gemma 模型生成视频内容类指令"""
    import ollama

    prompt = _build_video_content_prompt(slots, n)
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.7},
    )
    text = response["message"]["content"]
    raw_items = _parse_content_response(text)

    # 构建 video_index → slot 映射
    slot_map = {s.video_index: s for s in slots}

    samples = []
    for item in raw_items:
        instruction = item.get("instruction", "").strip()
        indices = item.get("selected_indices", [])
        if not instruction or not indices:
            continue

        valid_indices = [i for i in indices if i in slot_map]
        if not valid_indices:
            continue

        matched_slots = [slot_map[i] for i in valid_indices]
        samples.append(TrainingSample(
            image_path=image_path,
            app=app,
            instruction=instruction,
            instruction_type="video_content",
            click_targets=[s.click_target for s in matched_slots],
            click_boxes=[s.click_box for s in matched_slots],
            selected_grid_indices=valid_indices,
        ))

    return samples[:n]
