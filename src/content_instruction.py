"""
content_instruction.py — 基于内容的指令生成（调用 LLM 模型）

通过 Ollama 模型根据图片标签生成自然语言指令。
"""

from __future__ import annotations

import json

from .renderer import SlotInfo
from .instruction_types import TrainingSample


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
        desc = slot.photo.description or ""
        lines.append(f"图片 {slot.grid_index}：核心标签 [{labels_str}]，描述：{desc}")

    # 3. 核心生成逻辑与多样性约束
    lines.extend([
        f"\n### 任务要求：生成 {n} 条不重复的、地道的口语指令",
        "1. **消除歧义优先**：如果屏幕上有两张及以上的图片标签相似（例如都有'狗'），你的指令必须包含区分性描述，如：",
        "   - 方位词：'左边那张狗'、'最后一行那个小猫'",
        "   - 序数词：'选第二张有天安门的'、'第三张风景照'",
        "   - 特征词：'那张金毛的图'、'正在跑步的那只狗'",

        "2. **拒绝机械化句式**：禁止反复使用'发送第X张'或'选择标签为X的图片'。尝试以下真实语气：",
        "   - 动作多样化：'帮我点一下'、'把...勾选上'、'把...都发过去'、'找找看那张...'、'打包这几张'",
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
        "1. 必须返回 JSON 数组，每条数据包含 'instruction' 和 'selected_indices'。",
        "2. **selected_indices**：数组长度取决于你的指令内容。单选时只填一个编号 [5]；多选时按顺序填入所有匹配的编号 [1, 3, 7]。",
        "3. 确保指令描述的内容与 selected_indices 对应的图片标签完全吻合，不要产生幻觉。",
       
        '[{"instruction": "指令文本", "selected_indices": 对应的标号列表}]'
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
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.7},
    )
    text = response["message"]["content"]
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
