#!/usr/bin/env python3
"""
Template Preview Script

This script opens the template preview HTML file in the default web browser.
It provides a convenient way to view all available WeChat article templates.
"""

import os
import sys
import webbrowser
from pathlib import Path

def main():
    """Open the template preview HTML file in the default web browser."""
    # Get the directory of the current script
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    
    # Path to the template preview HTML file
    preview_file = script_dir / "template_preview.html"
    
    # Check if the preview file exists
    if not preview_file.exists():
        print(f"Error: Template preview file not found at {preview_file}")
        print("Please run test_templates.py first to generate template examples.")
        sys.exit(1)
    
    # Convert the path to a file URL
    file_url = f"file://{preview_file.absolute()}"
    
    print(f"Opening template preview in your default browser...")
    
    # Open the preview file in the default web browser
    webbrowser.open(file_url)
    
    print("✅ Template preview opened successfully!")
    print("\nAvailable templates:")
    print("  1. default    - 基础模板：简洁大方的白底黑字风格")
    print("  2. modern     - 现代风格：时尚简约的蓝色主题")
    print("  3. tech       - 技术专栏：类似GitHub风格的技术文档样式")
    print("  4. mianpro    - mianpro风格：温暖活泼的粉红色调")
    print("  5. lapis      - 蓝宝石主题：优雅简洁的蓝色主题")
    print("  6. maize      - 玉米黄主题：温暖活泼的黄色主题")
    print("  7. orangeheart- 橙心主题：热情洋溢的橙色主题")
    print("  8. phycat     - 物理猫主题：清新自然的青色主题")
    print("  9. pie        - 派主题：简约现代的紫灰主题")
    print("  10. purple    - 紫色主题：高贵典雅的紫色主题")
    print("  11. rainbow   - 彩虹主题：缤纷多彩的彩虹渐变主题")
    print("\nUse with: python article_note_generator.py URL --format wechat --wechat-template TEMPLATE_NAME")
    print("\nFor more details, see TEMPLATE_GUIDE.md")

if __name__ == "__main__":
    main()