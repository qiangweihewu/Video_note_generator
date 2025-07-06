# 📸 图片生成功能使用指南

## 功能概述

文章笔记生成器现在支持将小红书风格的 markdown 文件转换为精美的图片。这个功能专门针对小红书内容进行了优化，生成的图片具有现代化的设计风格，非常适合社交媒体分享。

## 🚀 快速开始

### 1. 安装依赖

首先确保已安装所有必要的依赖：

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 基础使用

有三种方式可以生成图片：

#### 方式一：在处理视频/音频时自动生成图片
```bash
python article_note_generator.py "https://example.com/video" --generate-image
```

#### 方式二：单独转换现有的小红书 markdown 文件
```bash
python markdown_to_image.py temp_notes/20250702_234851_xiaohongshu.md
```

#### 方式三：指定输出文件名和尺寸
```bash
python markdown_to_image.py temp_notes/20250702_234851_xiaohongshu.md output.png --width 900 --height 1200
```

## 📋 命令行参数

### 主程序参数

- `--generate-image`: 为小红书版本的 markdown 文件生成图片
- `--image-width`: 设置图片宽度（默认：750px）
- `--image-height`: 设置图片高度（可选，自动计算）

### 独立转换工具参数

```bash
python markdown_to_image.py <markdown_file> [output_file] [--width WIDTH] [--height HEIGHT]
```

- `markdown_file`: 输入的 markdown 文件路径
- `output_file`: 输出图片文件路径（可选，默认自动生成）
- `--width`: 图片宽度（默认：750px）
- `--height`: 图片高度（可选，自动计算）

## 🎨 设计特色

生成的图片具有以下特色：

1. **小红书风格设计**: 专门为小红书内容优化的视觉风格
2. **渐变背景**: 美观的紫色渐变背景
3. **优雅的卡片设计**: 白色卡片容器，圆角设计
4. **完美的字体呈现**: 支持中文字体，清晰易读
5. **标签美化**: 彩色标签展示，视觉效果佳
6. **响应式布局**: 自动适应内容长度

## 🔧 技术实现

### 渲染引擎

1. **Playwright 渲染** (推荐): 
   - 使用真实浏览器引擎渲染
   - 完美支持 CSS 样式和字体
   - 生成高质量图片

2. **备用方案**: 
   - 当 Playwright 不可用时自动启用
   - 基于 PIL 的文本渲染
   - 确保基础功能可用

### 支持的格式

- **输入**: Markdown 格式文件
- **输出**: PNG 格式图片
- **尺寸**: 自定义宽度和高度

## 📝 使用示例

### 示例 1: 完整工作流程

```bash
# 1. 处理视频/音频并生成图片
python article_note_generator.py "https://www.youtube.com/watch?v=example" --generate-image

# 生成的文件:
# - temp_notes/20250702_234851_original.md
# - temp_notes/20250702_234851_organized.md  
# - temp_notes/20250702_234851_xiaohongshu.md
# - temp_notes/20250702_234851_xiaohongshu.png
```

### 示例 2: 批量转换

```bash
# 转换目录中的所有小红书 markdown 文件
for file in temp_notes/*xiaohongshu.md; do
    python markdown_to_image.py "$file"
done
```

### 示例 3: 自定义尺寸

```bash
# 生成适合移动端的图片
python markdown_to_image.py temp_notes/xiaohongshu.md mobile.png --width 375 --height 812

# 生成适合桌面的宽图
python markdown_to_image.py temp_notes/xiaohongshu.md desktop.png --width 1200 --height 800
```

## 🧪 测试功能

运行测试脚本验证功能是否正常：

```bash
python test_image_generation.py
```

测试包括：
- ✅ 依赖项检查
- ✅ 同步图片生成
- ✅ 异步图片生成
- ✅ 文件完整性验证

## 🔍 故障排除

### 常见问题

1. **Playwright 未安装**
   ```bash
   pip install playwright
   playwright install chromium
   ```

2. **字体渲染问题**
   - macOS: 自动使用 PingFang SC 字体
   - 其他系统: 降级为系统默认字体

3. **图片生成失败**
   - 检查输入文件是否存在
   - 确认磁盘空间充足
   - 查看错误日志

4. **依赖项缺失**
   ```bash
   pip install markdown jinja2 beautifulsoup4 pillow
   ```

### 调试模式

查看详细日志信息：

```python
# 在代码中启用调试模式
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 📊 性能说明

- **处理速度**: 通常 2-5 秒生成一张图片
- **图片质量**: 高清 PNG 格式
- **文件大小**: 通常 1-5MB，取决于内容复杂度
- **内存使用**: 浏览器进程约 100-200MB

## 🎯 使用技巧

1. **优化图片尺寸**: 
   - 小红书推荐：750x1334 (9:16)
   - 微博配图：750x1000
   - 通用分享：750x自动

2. **内容优化**: 
   - 确保 markdown 格式正确
   - 标题使用 emoji 增加视觉效果
   - 适当使用粗体和标签

3. **批量处理**: 
   - 编写脚本批量转换
   - 使用不同尺寸模板
   - 自动化社交媒体发布流程

## 🔗 相关文件

- `markdown_to_image.py`: 核心转换模块
- `test_image_generation.py`: 功能测试脚本
- `article_note_generator.py`: 主程序（集成图片生成）
- `requirements.txt`: 依赖项列表

## 📈 更新日志

### v1.0.0 (2025-07-02)
- ✨ 新增图片生成功能
- 🎨 小红书风格模板设计
- 🔧 Playwright 渲染引擎
- 📱 响应式设计支持
- 🧪 完整测试套件

---

**提示**: 如果您在使用过程中遇到任何问题，请检查依赖项安装情况，或查看生成的错误日志获取详细信息。
