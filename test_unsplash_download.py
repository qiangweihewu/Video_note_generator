#!/usr/bin/env python3
"""
测试Unsplash图片下载功能
"""

import os
import sys
from article_note_generator import ArticleNoteGenerator

def test_unsplash_download():
    """测试Unsplash图片下载到本地功能"""
    print("🧪 测试Unsplash图片下载功能...")
    
    # 创建生成器实例
    generator = ArticleNoteGenerator()
    
    # 检查Unsplash客户端是否可用
    if not generator.unsplash_client:
        print("⚠️ Unsplash客户端未初始化，请检查.env文件中的UNSPLASH_ACCESS_KEY配置")
        return False
    
    # 测试查询
    test_query = "technology"
    print(f"🔍 测试查询: {test_query}")
    
    try:
        # 获取图片（应该会自动下载到本地）
        images = generator._get_unsplash_images(test_query, count=2)
        
        if images:
            print(f"✅ 成功获取{len(images)}张图片")
            for i, img_url in enumerate(images, 1):
                print(f"  {i}. {img_url}")
            
            # 检查本地unsplash文件夹是否存在
            unsplash_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unsplash')
            if os.path.exists(unsplash_dir):
                local_files = os.listdir(unsplash_dir)
                if local_files:
                    print(f"📁 本地unsplash文件夹中有{len(local_files)}个文件:")
                    for file in local_files:
                        file_path = os.path.join(unsplash_dir, file)
                        file_size = os.path.getsize(file_path)
                        print(f"  - {file} ({file_size} bytes)")
                else:
                    print("📁 本地unsplash文件夹为空")
            else:
                print("⚠️ 本地unsplash文件夹不存在")
            
            return True
        else:
            print("❌ 未获取到任何图片")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = test_unsplash_download()
    if success:
        print("\n🎉 测试成功！Unsplash图片下载功能正常工作")
    else:
        print("\n💥 测试失败！请检查配置和网络连接")
        sys.exit(1)