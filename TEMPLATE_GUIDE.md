# 微信公众号模板指南

本文档提供了文章笔记生成器支持的所有微信公众号模板的详细说明和使用指南。

## 可用模板

文章笔记生成器目前支持以下11种微信公众号模板风格：

1. **default** - 基础模板：简洁大方的白底黑字风格，适合各类文章
2. **modern** - 现代风格：时尚简约的蓝色主题，适合科技类文章
3. **tech** - 技术专栏：类似GitHub风格的技术文档样式，适合深度技术文章
4. **mianpro** - mianpro风格：温暖活泼的粉红色调，适合生活类、情感类文章
5. **lapis** - 蓝宝石主题：优雅简洁的蓝色主题，适合商务、职场类文章
6. **maize** - 玉米黄主题：温暖活泼的黄色主题，适合美食、旅行类文章
7. **orangeheart** - 橙心主题：热情洋溢的橙色主题，适合励志、健康类文章
8. **phycat** - 物理猫主题：清新自然的青色主题，适合科普、教育类文章
9. **pie** - 派主题：简约现代的紫灰主题，适合艺术、设计类文章
10. **purple** - 紫色主题：高贵典雅的紫色主题，适合时尚、美妆类文章
11. **rainbow** - 彩虹主题：缤纷多彩的彩虹渐变主题，适合儿童、娱乐类文章

## 使用方法

在命令行中使用`--wechat-template`参数指定要使用的模板：

```bash
# 使用基础模板
python article_note_generator.py your_video_url --wechat-template default

# 使用现代风格模板
python article_note_generator.py your_video_url --wechat-template modern

# 使用技术专栏模板
python article_note_generator.py your_video_url --wechat-template tech

# 使用mianpro风格模板
python article_note_generator.py your_video_url --wechat-template mianpro

# 使用蓝宝石主题
python article_note_generator.py your_video_url --wechat-template lapis

# 使用玉米黄主题
python article_note_generator.py your_video_url --wechat-template maize

# 使用橙心主题
python article_note_generator.py your_video_url --wechat-template orangeheart

# 使用物理猫主题
python article_note_generator.py your_video_url --wechat-template phycat

# 使用派主题
python article_note_generator.py your_video_url --wechat-template pie

# 使用紫色主题
python article_note_generator.py your_video_url --wechat-template purple

# 使用彩虹主题
python article_note_generator.py your_video_url --wechat-template rainbow
```

## 模板特点

### default（基础模板）
- 简洁大方的白底黑字风格
- 清晰的标题层级
- 适合各类文章

### modern（现代风格）
- 时尚简约的蓝色主题
- 封面图设计
- 适合科技类文章

### tech（技术专栏）
- 类似GitHub风格的技术文档样式
- 代码块优化
- 适合深度技术文章

### mianpro（mianpro风格）
- 温暖活泼的粉红色调
- 图片悬停效果
- 适合生活类、情感类文章

### lapis（蓝宝石主题）
- 优雅简洁的蓝色主题
- 专业的排版风格
- 适合商务、职场类文章

### maize（玉米黄主题）
- 温暖活泼的黄色主题
- 明亮的色调
- 适合美食、旅行类文章

### orangeheart（橙心主题）
- 热情洋溢的橙色主题
- 充满活力的设计
- 适合励志、健康类文章

### phycat（物理猫主题）
- 清新自然的青色主题
- 舒适的阅读体验
- 适合科普、教育类文章

### pie（派主题）
- 简约现代的紫灰主题
- 低调优雅的设计
- 适合艺术、设计类文章

### purple（紫色主题）
- 高贵典雅的紫色主题
- 精致的排版
- 适合时尚、美妆类文章

### rainbow（彩虹主题）
- 缤纷多彩的彩虹渐变主题
- 动态的标题效果
- 适合儿童、娱乐类文章

## 测试模板

你可以使用`test_templates.py`脚本来测试所有模板：

```bash
python test_templates.py
```

这将生成使用每种模板的示例文章，并在浏览器中打开HTML预览。生成的文件保存在`template_tests`目录中。

## 选择合适的模板

选择模板时，考虑以下因素：
1. **内容类型**：不同的内容类型适合不同的模板风格
2. **目标受众**：考虑你的读者群体偏好
3. **品牌一致性**：选择与你的个人或品牌风格一致的模板
4. **阅读体验**：确保模板提供良好的阅读体验，特别是在移动设备上

## 自定义模板

如果你想自定义模板，可以修改`article_note_generator.py`文件中的`_get_template_css`方法，添加你自己的CSS样式。