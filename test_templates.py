#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试所有微信公众号模板的脚本
"""

import os
import datetime
from article_note_generator import ArticleNoteGenerator

def main():
    """测试所有微信公众号模板"""
    # 创建一个简单的测试内容
    test_content = """# 测试标题

这是一个测试段落，用于验证所有微信公众号模板是否正常工作。

## 二级标题

- 列表项1
- 列表项2
- 列表项3

### 三级标题

这是另一个段落，包含一些**加粗文本**和*斜体文本*。

> 这是一段引用文本，用于测试引用样式。

#### 四级标题

1. 有序列表项1
2. 有序列表项2
3. 有序列表项3

##### 五级标题

这是最后一个测试段落。
"""

    # 创建生成器实例
    generator = ArticleNoteGenerator(output_dir="template_tests")
    
    # 确保输出目录存在
    os.makedirs("template_tests", exist_ok=True)
    
    # 获取所有可用的模板
    templates = [
        "default", "modern", "tech", "mianpro",
        "lapis", "maize", "orangeheart", "phycat",
        "pie", "purple", "rainbow"
    ]
    
    # 创建测试内容信息
    content_info = {
        'title': '测试标题',
        'uploader': '测试用户',
        'description': '测试描述',
        'duration': 60,
        'platform': 'test'
    }
    
    # 为每个模板生成文章
    for template in templates:
        print(f"\n测试模板: {template}")
        template_desc = generator._get_template_description(template)
        print(f"模板描述: {template_desc}")
        
        # 直接使用_generate_notes方法生成笔记
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 生成笔记
        files = generator._generate_notes(test_content, content_info, None, "wechat", template)
        
        if files:
            print(f"✅ 已生成 {template} 模板的文章:")
            for file in files:
                print(f"  - {file}")
        else:
            print(f"❌ {template} 模板生成失败")
    
    print("\n所有模板测试完成！")
    print(f"测试文件保存在 {os.path.abspath('template_tests')} 目录")

if __name__ == "__main__":
    main()