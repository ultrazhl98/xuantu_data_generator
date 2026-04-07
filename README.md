# 玄图数据生成器 (Xuantu Data Generator)

为移动端图库/相册UI交互模型生成合成训练数据的系统。自动生成逼真的中文社交应用截图（相册、微信、微博、小红书），配合自然语言指令和点击坐标，用于训练VLMs/Agent模型。

## 核心输出

**JSONL训练样本**：
```json
{
  "image": "...",
  "instruction": "...",
  "click_targets": [[x, y], ...],
  "selected_grid_indices": [...]
}
```

**合成截图**：1276×2848px 的移动端设备截图

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

```bash
python generate.py --count 100 --apps all
```

---

## 使用方法

### 基础命令

```bash
# 生成100个样本，包含所有应用
python generate.py --count 100 --apps all

# 生成10个样本，指定应用，并可视化点击位置
python generate.py --count 10 --apps 相册,微信 --visualize

# 使用固定seed确保可重现性
python generate.py --count 50 --seed 42

# 调整视频比例（0表示无视频）
python generate.py --count 500 --apps 相册,微信 --video-ratio 0.3
```

### 高级选项

| 参数 | 说明 | 示例 |
|------|------|------|
| `--count` | 生成样本数（必需） | `--count 100` |
| `--apps` | 应用列表：相册、微信、微博、小红书，或"all" | `--apps 相册,微信` |
| `--seed` | 随机种子，用于重现 | `--seed 42` |
| `--visualize` | 生成带点击位置可视化标注的图片 | `--visualize` |
| `--video-ratio` | 视频单元格比例（0~1） | `--video-ratio 0.3` |
| `--ensure-labels` | 确保指定标签出现 | `--ensure-labels cat,dog` |
| `--n-sequential` | 每张图片的顺序类指令数 | `--n-sequential 3` |
| `--n-content` | 每张图片的内容类指令数 | `--n-content 3` |
| `--partial-ratio` | 部分填充网格比例（0~1，默认0.1） | `--partial-ratio 0.2` |

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
├── generate.py                    # 主入口 (Click CLI)
├── create_test_photos.py          # 生成测试占位图
├── label_photos.py                # 标注照片（Gemma 3）
├── requirements.txt               # 依赖列表
├── source_photos/
│   ├── images/                    # 源照片（gitignore）
│   └── metadata.json              # 照片元数据
├── output/                        # 输出目录（gitignore）
│   ├── images/                    # 生成的截图
│   ├── debug/                     # 调试文件
│   └── training_samples.jsonl     # 训练样本
└── src/
    ├── generator.py               # 批处理循环：采样 → 渲染 → 标注 → 写入
    ├── source_library.py          # 源照片管理
    ├── app_config.py              # 应用配置（4个预设）
    ├── renderer.py                # Pillow渲染器
    ├── playwright_renderer.py     # HTML/CSS + Playwright渲染器
    └── instruction_generator.py   # 指令生成逻辑
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

- **training_samples.jsonl**：JSONL格式的训练样本，每行一个JSON对象
- **images/\*.png**：生成的移动端截图（1276×2848px）
- **debug/\*_visualization.png**：带点击位置标注的调试图片（使用 `--visualize` 时生成）

---

## 工作流示例

### 场景1：快速原型测试

```bash
# 1. 生成测试数据
python create_test_photos.py --n 5

# 2. 生成10个样本并可视化
python generate.py --count 10 --visualize

# 3. 检查output/目录中的结果
```

### 场景2：完整流程（使用真实照片）

```bash
# 1. 放置照片到 source_photos/images/
# 2. 启动Ollama服务
ollama serve

# 3. 新开终端标注照片
python label_photos.py

# 4. 生成训练数据
python generate.py --count 1000 --apps all --seed 42

# 5. 结果保存到 output/training_samples.jsonl
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
