# 玄图数据生成器 (Xuantu Data Generator)

为移动端图库/相册UI交互模型生成合成训练数据的系统。自动生成逼真的中文社交应用截图（相册、微信、微博、小红书），配合自然语言指令和点击坐标，用于训练VLMs/Agent模型。

## 核心输出

**JSONL 训练样本** (`output/training_samples.jsonl`)：
```json
{
  "image": "output/images/00000.jpg",
  "app": "相册",
  "instruction": "发送第2行第3列的图片",
  "instruction_type": "sequential",
  "click_targets": [[918, 459]],
  "click_boxes": [[897, 438, 939, 480]],
  "selected_grid_indices": [1],
  "selected_cells": [{"row": 0, "col": 2, "type": "image", "grid_index": 1}]
}
```

**合成截图** (`output/images/*.jpg`)：1276×2848px 移动端截图

**网格 sidecar** (`output/grids/*.jsonl` + `*.meta.json`)：每张图一个 sidecar，逐行记录每个格子的行列/bbox/点击点/图片或视频/photo 元信息，既是人类可读的"标注"，也是指令阶段的输入来源。

---

## 快速开始

### 1. 环境安装

```bash
pip install -r requirements.txt
playwright install chromium  # 若使用Playwright渲染器
```

### 2. 准备测试数据

使用占位图片快速测试（无需真实照片）：

```bash
python create_test_photos.py          # 生成~60张占位图片
python create_test_photos.py --n 10   # 每个类别10张
```

### 3. 生成训练数据

推荐两阶段流程（渲染与指令解耦，渲染一次可多次重跑指令）：

```bash
# 阶段 1：渲染图片 + 写网格 sidecar
python render.py --count 100 --apps all --seed 42

# 阶段 2：读 sidecar 生成指令（不依赖图像素）
python generate_instructions.py --n-sequential 3 --n-content 3 --seed 42
```

也可用旧的一体化入口（内部会依次跑上面两步）：

```bash
python generate.py --count 100 --apps all
```

---

## 两阶段流水线

### 阶段 1：渲染 (`render.py`)

只做采样 + 渲染，不生成指令，不依赖 Ollama。

```bash
python render.py --count 100 --apps all \
  --seed 42 --video-ratio 0.3 --camera-ratio 0.3
```

产物：
- `output/images/{i:05d}.jpg` 截图
- `output/grids/{i:05d}.jsonl` 网格 sidecar（每行一个 photo/video 格子）
- `output/grids/{i:05d}.meta.json` `{app, image_path}`

| 参数 | 说明 | 默认 |
|------|------|------|
| `--count / -n` | 生成图片数 | 100 |
| `--apps` | 应用列表或 `all` | all |
| `--output` | 输出目录 | output |
| `--seed` | 随机种子 | 无 |
| `--video-ratio` | 视频格比例（0~1） | 0.3 |
| `--camera-ratio` | 拍照格出现概率 | 0.3 |
| `--partial-ratio` | 部分填充网格比例 | 0.1 |
| `--ensure-labels` | 确保指定标签出现 | 无 |
| `--photos-per-screen` | 每屏图片数 | 按 app 预设 |

### 阶段 2：生成指令 (`generate_instructions.py`)

扫描 `output/grids/` 下所有 sidecar，生成指令并写 `output/training_samples.jsonl`。
内容类指令需要 Ollama；把 `--n-content 0 --n-video-content 0` 可以完全跳过 LLM。

```bash
# 不依赖 Ollama，只生成顺序类
python generate_instructions.py --n-sequential 3 --n-content 0 \
  --n-video-sequential 2 --n-video-content 0 --seed 42

# 完整（需 ollama serve + 模型已 pull）
python generate_instructions.py --n-sequential 3 --n-content 3 \
  --n-video-sequential 2 --n-video-content 2 \
  --model gemma4:e4b --content-workers 4 --seed 42
```

| 参数 | 说明 | 默认 |
|------|------|------|
| `--output` | 输入/输出目录（读取其下 `grids/`） | output |
| `--n-sequential` | 每张图顺序类指令数 | 3 |
| `--n-content` | 每张图内容类指令数 | 3 |
| `--n-video-sequential` | 每张图视频顺序类指令数 | 2 |
| `--n-video-content` | 每张图视频内容类指令数 | 2 |
| `--model` | Ollama 模型名 | gemma4:e4b |
| `--content-workers` | 内容指令并发线程数 | 4 |
| `--seed` | 随机种子 | 无 |
| `--samples-filename` | 输出 jsonl 文件名 | training_samples.jsonl |

**优势**：同一份 `grids/` 下可反复重跑指令阶段（换模型、换 seed、换数量），无需重新渲染：

```bash
python generate_instructions.py --seed 1 --samples-filename run1.jsonl
python generate_instructions.py --seed 2 --samples-filename run2.jsonl
```

### 一体化入口 (`generate.py`)

等价于先跑 `render.py` 再跑 `generate_instructions.py`，并支持 `--visualize`。

```bash
python generate.py --count 100 --apps 相册,微信 --visualize
python generate.py --count 50 --seed 42
python generate.py --count 500 --video-ratio 0.3
```

| 参数 | 说明 | 示例 |
|------|------|------|
| `--count` | 生成样本数 | `--count 100` |
| `--apps` | 应用列表或 `all` | `--apps 相册,微信` |
| `--seed` | 随机种子 | `--seed 42` |
| `--visualize` | 生成带点击位置标注的可视化图 | `--visualize` |
| `--video-ratio` | 视频单元格比例 | `--video-ratio 0.3` |
| `--ensure-labels` | 确保指定标签出现 | `--ensure-labels cat,dog` |
| `--n-sequential` | 顺序类指令数 | `--n-sequential 3` |
| `--n-content` | 内容类指令数 | `--n-content 3` |
| `--partial-ratio` | 部分填充网格比例 | `--partial-ratio 0.2` |

### 标注真实照片

需要本地 Ollama 及 Gemma 3 模型：

```bash
# 安装Ollama并启动
brew install ollama && ollama serve

# 拉取模型
ollama pull gemma3:12b

# 标注照片
python label_photos.py

# 仅添加新照片（不重新标注已有的）
python label_photos.py --append

# 使用指定模型
python label_photos.py --model gemma3:12b
```

---

## 指令类型

### 1. 顺序类指令
基于网格索引的指令。示例：
- "发送第3张照片"
- "发送第2行第3列的照片"
- "发送第1、3、5张照片"
- "发送最新的3张照片"

### 2. 内容类指令
基于标签匹配的指令。示例：
- "发送所有猫咪照片"
- "发送第2张狗狗照片"
- "发送猫咪和狗狗照片"

---

## 项目结构

```
.
├── render.py                          # 阶段 1：渲染 CLI
├── generate_instructions.py           # 阶段 2：指令生成 CLI
├── generate.py                        # 一体化入口（内部串联两阶段）
├── create_test_photos.py              # 生成测试占位图
├── label_photos.py                    # 标注照片（Gemma 3）
├── requirements.txt
├── source_photos/
│   ├── images/                        # 源照片（gitignore）
│   └── metadata.json                  # 照片元数据
├── output/                            # 输出目录（gitignore）
│   ├── images/{i:05d}.jpg             # 生成的截图
│   ├── grids/{i:05d}.jsonl            # 网格 sidecar（每行一个格子）
│   ├── grids/{i:05d}.meta.json        # sidecar 元信息 {app, image_path}
│   ├── visualize/                     # 可视化标注图（--visualize）
│   └── training_samples.jsonl         # 训练样本
└── src/
    ├── render_stage.py                # 采样 + 渲染 + 写 sidecar
    ├── instruction_stage.py           # 读 sidecar + 生成指令 + 写 jsonl
    ├── grid_sidecar.py                # SlotInfo ↔ sidecar 序列化
    ├── generator.py                   # 兼容入口：render_stage + instruction_stage
    ├── instruction_types.py           # TrainingSample（含 selected_cells）
    ├── sequential_instruction.py      # 图片顺序类指令
    ├── content_instruction.py         # 图片内容类指令（LLM）
    ├── video_sequential_instruction.py
    ├── video_content_instruction.py
    ├── source_library.py              # 源照片管理
    ├── app_config.py                  # 应用配置（4 个预设）
    ├── renderer.py                    # Pillow 渲染器 + SlotInfo
    └── playwright_renderer.py         # HTML/CSS + Playwright 渲染器
```

---

## 应用配置

系统预设4个应用，每个应用都有独特的UI样式：

| 应用 | 特点 |
|------|------|
| **相册** | 简洁风格，亮色主题 |
| **微信** | 深色主题，对话式布局 |
| **微博** | 搜索栏头部，信息流样式 |
| **小红书** | 标签页导航，多彩配色 |

---

## 输出文件

- **`output/training_samples.jsonl`**：训练样本，每行一条 JSON（字段含 `image / instruction / click_targets / click_boxes / selected_grid_indices / selected_cells`）
- **`output/images/{i:05d}.jpg`**：移动端截图（1276×2848px）
- **`output/grids/{i:05d}.jsonl`**：网格 sidecar，每行一个格子 `{visual_slot, row, col, type, grid_index, video_index, bbox, click_target, click_box, target_type, duration, photo}`
- **`output/grids/{i:05d}.meta.json`**：`{"app": "...", "image_path": "..."}`
- **`output/visualize/*.jpg`**：带点击位置标注的可视化图（使用 `--visualize` 时生成）

---

## 工作流示例

### 场景 1：快速原型测试（两阶段）

```bash
# 1. 生成测试数据
python create_test_photos.py --n 5

# 2. 渲染图片 + sidecar
python render.py --count 10 --seed 42

# 3. 生成指令（无需 Ollama）
python generate_instructions.py --n-sequential 3 --n-content 0 \
  --n-video-sequential 2 --n-video-content 0

# 4. 检查 output/ 下的结果
```

### 场景 2：渲染一次，多次尝试指令策略

```bash
python render.py --count 100 --seed 42                            # 只渲染一次

# 尝试不同 seed/数量组合，图片不变
python generate_instructions.py --seed 1 --samples-filename run1.jsonl
python generate_instructions.py --seed 2 --samples-filename run2.jsonl
python generate_instructions.py --n-sequential 5 --samples-filename run3.jsonl
```

### 场景 3：完整流程（真实照片 + LLM 指令）

```bash
# 1. 放置照片到 source_photos/images/
# 2. 启动 Ollama
ollama serve
ollama pull gemma4:e4b

# 3. 标注照片
python label_photos.py

# 4a. 一体化跑通
python generate.py --count 1000 --apps all --seed 42

# 4b. 或分两步（更灵活）
python render.py --count 1000 --apps all --seed 42
python generate_instructions.py --n-sequential 3 --n-content 3 \
  --n-video-sequential 2 --n-video-content 2 --seed 42
```

---

## 常见问题

**Q: 如何重现之前生成的数据？**
A: 使用 `--seed` 参数固定随机数种子
```bash
python generate.py --count 100 --seed 42
```

**Q: 没有Ollama时如何标注照片？**
A: 使用测试占位图进行开发，不依赖标注
```bash
python create_test_photos.py
python generate.py --count 100
```

**Q: 如何只生成某类应用的样本？**
A: 指定 `--apps` 参数
```bash
python generate.py --count 100 --apps 微信,微博
```

**Q: 点击坐标的精度如何？**
A: 坐标精确到像素级别，直接可用于UI自动化测试

**Q: 想换指令策略但不想重新渲染？**
A: 渲染产物（图片 + sidecar）与指令完全解耦。保留 `output/images/` 和 `output/grids/`，反复跑 `generate_instructions.py` 即可，可用 `--samples-filename` 避免覆盖。

**Q: sidecar (`output/grids/*.jsonl`) 能独立使用吗？**
A: 可以。sidecar 完整描述了每张图的网格行列内容，可直接作为标注数据消费；指令阶段也只依赖它，不读图像素。

---

## 依赖

- Python 3.8+
- Pillow：图像处理
- Playwright：浏览器自动化渲染
- Click：CLI框架
- Ollama + Gemma 3：照片标注（可选）

详见 `requirements.txt`

---

## 许可证

内部项目

## 修改日志

参见 Git 提交历史
