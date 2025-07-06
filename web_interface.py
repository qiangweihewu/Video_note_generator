#!/usr/bin/env python3
"""
文章笔记生成器 - Web界面

这个脚本提供了一个基于Flask的Web界面，让用户可以通过浏览器使用文章笔记生成器的功能。
用户可以上传音频文件、输入视频URL，选择输出格式和微信公众号模板，然后在浏览器中查看生成的内容。
"""

import os
import sys
import time
import uuid
import json
import shutil
from pathlib import Path
from urllib.parse import quote

from flask import Flask, request, render_template, redirect, url_for, send_from_directory, jsonify
from werkzeug.utils import secure_filename

# 导入文章笔记生成器
from article_note_generator import ArticleNoteGenerator, extract_urls_from_text

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'temp_notes'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 限制上传文件大小为100MB
app.config['SECRET_KEY'] = os.urandom(24)

# 确保上传和输出目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# 初始化生成器
generator = ArticleNoteGenerator(output_dir=app.config['OUTPUT_FOLDER'])

# 允许的文件类型
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'ogg', 'aac'}
ALLOWED_TEXT_EXTENSIONS = {'txt', 'md'}

# 模板信息和预览文件映射
TEMPLATES = [
    {
        'id': 'default',
        'name': '基础模板',
        'description': '简洁大方的白底黑字风格，适合各类文章',
        'category': '通用',
        'preview_file': '20250705_215024_wechat.html'
    },
    {
        'id': 'modern',
        'name': '现代风格',
        'description': '时尚简约的蓝色主题，适合科技类文章',
        'category': '科技',
        'preview_file': '20250705_215118_wechat.html'
    },
    {
        'id': 'tech',
        'name': '技术专栏',
        'description': '类似GitHub风格的技术文档样式，适合深度技术文章',
        'category': '技术',
        'preview_file': '20250705_215206_wechat.html'
    },
    {
        'id': 'mianpro',
        'name': 'mianpro风格',
        'description': '温暖活泼的粉红色调，适合生活类、情感类文章',
        'category': '生活',
        'preview_file': '20250705_215309_wechat.html'
    },
    {
        'id': 'lapis',
        'name': '蓝宝石主题',
        'description': '优雅简洁的蓝色主题，适合商务、职场类文章',
        'category': '商务',
        'preview_file': '20250705_215418_wechat.html'
    },
    {
        'id': 'maize',
        'name': '玉米黄主题',
        'description': '温暖活泼的黄色主题，适合美食、旅行类文章',
        'category': '美食',
        'preview_file': '20250705_215502_wechat.html'
    },
    {
        'id': 'orangeheart',
        'name': '橙心主题',
        'description': '热情洋溢的橙色主题，适合励志、健康类文章',
        'category': '励志',
        'preview_file': '20250705_215553_wechat.html'
    },
    {
        'id': 'phycat',
        'name': '物理猫主题',
        'description': '清新自然的青色主题，适合科普、教育类文章',
        'category': '科普',
        'preview_file': '20250705_215638_wechat.html'
    },
    {
        'id': 'pie',
        'name': '派主题',
        'description': '简约现代的紫灰主题，适合艺术、设计类文章',
        'category': '艺术',
        'preview_file': '20250705_215726_wechat.html'
    },
    {
        'id': 'purple',
        'name': '紫色主题',
        'description': '高贵典雅的紫色主题，适合时尚、美妆类文章',
        'category': '时尚',
        'preview_file': '20250705_215815_wechat.html'
    },
    {
        'id': 'rainbow',
        'name': '彩虹主题',
        'description': '缤纷多彩的彩虹渐变主题，适合儿童、娱乐类文章',
        'category': '娱乐',
        'preview_file': '20250705_215906_wechat.html'
    }
]

def allowed_file(filename, allowed_extensions):
    """检查文件是否是允许的类型"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def get_session_folder(session_id):
    """获取会话的输出文件夹"""
    session_folder = os.path.join(app.config['OUTPUT_FOLDER'], session_id)
    os.makedirs(session_folder, exist_ok=True)
    return session_folder

def process_video_url(url, output_format, wechat_template, session_id):
    """处理视频URL"""
    try:
        # 设置输出目录为会话目录
        generator.output_dir = get_session_folder(session_id)
        
        # 处理视频
        file_paths = generator.process_video(url, output_format, wechat_template)
        
        if not file_paths:
            return {"success": False, "message": "处理视频失败，未生成任何文件"}
        
        # 获取生成的文件信息
        files_info = []
        for file_path in file_paths:
            if os.path.exists(file_path):
                file_name = os.path.basename(file_path)
                file_type = file_name.split('_')[-1].split('.')[0]
                file_ext = os.path.splitext(file_name)[1]
                
                files_info.append({
                    "path": file_path,
                    "name": file_name,
                    "type": file_type,
                    "extension": file_ext,
                    "url": f"/output/{session_id}/{quote(file_name)}"
                })
        
        return {
            "success": True,
            "message": f"成功处理视频URL: {url}",
            "files": files_info
        }
    except Exception as e:
        return {"success": False, "message": f"处理视频时出错: {str(e)}"}

def process_audio_file(file_path, output_format, wechat_template, session_id):
    """处理音频文件"""
    try:
        # 设置输出目录为会话目录
        generator.output_dir = get_session_folder(session_id)
        
        # 处理音频
        file_paths = generator.process_local_audio(file_path, output_format, wechat_template)
        
        if not file_paths:
            return {"success": False, "message": "处理音频失败，未生成任何文件"}
        
        # 获取生成的文件信息
        files_info = []
        for file_path in file_paths:
            if os.path.exists(file_path):
                file_name = os.path.basename(file_path)
                file_type = file_name.split('_')[-1].split('.')[0]
                file_ext = os.path.splitext(file_name)[1]
                
                files_info.append({
                    "path": file_path,
                    "name": file_name,
                    "type": file_type,
                    "extension": file_ext,
                    "url": f"/output/{session_id}/{quote(file_name)}"
                })
        
        return {
            "success": True,
            "message": f"成功处理音频文件",
            "files": files_info
        }
    except Exception as e:
        return {"success": False, "message": f"处理音频时出错: {str(e)}"}

def process_batch_urls(urls, output_format, wechat_template, session_id):
    """批量处理多个视频URL"""
    batch_results = []
    
    for url in urls:
        url = url.strip()
        if not url:
            continue
            
        result = process_video_url(url, output_format, wechat_template, session_id)
        result['url'] = url  # 添加URL到结果中，用于在模板中显示
        batch_results.append(result)
    
    # 计算成功和失败的数量及比率
    success_count = sum(1 for r in batch_results if r['success'])
    failure_count = len(batch_results) - success_count
    
    total_count = len(batch_results)
    success_rate = (success_count / total_count * 100) if total_count > 0 else 0
    failure_rate = (failure_count / total_count * 100) if total_count > 0 else 0
    
    return {
        'batch_results': batch_results,
        'success_count': success_count,
        'failure_count': failure_count,
        'success_rate': success_rate,
        'failure_rate': failure_rate
    }

@app.route('/')
def index():
    """首页"""
    return render_template('index.html', templates=TEMPLATES)

@app.route('/process', methods=['POST'])
def process():
    """处理表单提交"""
    # 生成会话ID
    session_id = str(uuid.uuid4())
    
    # 获取表单数据
    output_format = request.form.get('output_format', 'both')
    wechat_template = request.form.get('wechat_template', 'default')
    
    # 检查是否为批量处理
    enable_batch = request.form.get('enable_batch') == 'on'
    
    # 批量处理多个URL
    if enable_batch:
        batch_urls = request.form.get('batch_urls', '').strip()
        if batch_urls:
            # 提取所有URL
            all_urls = []
            for line in batch_urls.split('\n'):
                urls = extract_urls_from_text(line)
                all_urls.extend(urls)
            
            if all_urls:
                # 限制最多处理10个URL
                all_urls = all_urls[:10]
                batch_result = process_batch_urls(all_urls, output_format, wechat_template, session_id)
                return render_template('batch_result.html', **batch_result, session_id=session_id)
            else:
                result = {"success": False, "message": "未提供有效的视频URL"}
                return render_template('result.html', result=result, session_id=session_id)
    
    # 单个URL处理
    result = {"success": False, "message": "未提供有效的输入"}
    
    # 处理视频URL
    video_url = request.form.get('video_url', '').strip()
    if video_url:
        # 提取URL
        urls = extract_urls_from_text(video_url)
        if urls:
            result = process_video_url(urls[0], output_format, wechat_template, session_id)
        else:
            result = {"success": False, "message": "未提供有效的视频URL"}
    
    # 处理音频文件
    elif 'audio_file' in request.files:
        audio_file = request.files['audio_file']
        if audio_file and audio_file.filename and allowed_file(audio_file.filename, ALLOWED_AUDIO_EXTENSIONS):
            filename = secure_filename(audio_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{session_id}_{filename}")
            audio_file.save(file_path)
            
            result = process_audio_file(file_path, output_format, wechat_template, session_id)
            
            # 处理完成后删除上传的文件
            if os.path.exists(file_path):
                os.remove(file_path)
        else:
            result = {"success": False, "message": "未提供有效的音频文件或文件类型不支持"}
    
    # 返回结果
    return render_template('result.html', result=result, session_id=session_id)

@app.route('/output/<session_id>/<filename>')
def output_file(session_id, filename):
    """提供输出文件下载"""
    return send_from_directory(os.path.join(app.config['OUTPUT_FOLDER'], session_id), filename)

@app.route('/template_tests/<filename>')
def template_test_file(filename):
    """提供模板测试文件"""
    template_tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template_tests')
    return send_from_directory(template_tests_dir, filename)

@app.route('/preview/<template_id>')
def preview_template(template_id):
    """预览模板"""
    # 查找模板信息
    template_info = next((t for t in TEMPLATES if t['id'] == template_id), None)
    if not template_info:
        return "模板不存在", 404
    
    # 使用映射的预览文件
    preview_file = None
    if 'preview_file' in template_info:
        template_tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template_tests')
        preview_file_path = os.path.join(template_tests_dir, template_info['preview_file'])
        if os.path.exists(preview_file_path):
            preview_file = os.path.join('template_tests', template_info['preview_file'])
    
    # 如果映射的文件不存在，查找任何可用的预览文件
    if not preview_file:
        template_tests_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template_tests')
        if os.path.exists(template_tests_dir):
            for file in os.listdir(template_tests_dir):
                if file.endswith('_wechat.html'):
                    preview_file = os.path.join('template_tests', file)
                    break
    
    return render_template('preview.html', template=template_info, preview_file=preview_file)

@app.route('/templates')
def templates():
    """模板列表页面"""
    return render_template('templates.html', templates=TEMPLATES)

@app.route('/about')
def about():
    """关于页面"""
    return render_template('about.html')

def create_template_files():
    """创建模板文件"""
    # 创建模板目录
    templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    os.makedirs(templates_dir, exist_ok=True)
    
    # 创建静态文件目录
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    templates_static_dir = os.path.join(static_dir, 'templates')
    os.makedirs(templates_static_dir, exist_ok=True)

if __name__ == '__main__':
    # 创建必要的目录和文件
    create_template_files()
    
    # 运行Flask应用
    app.run(debug=True, host='0.0.0.0', port=5001)