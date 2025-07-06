import os
import sys
import json
import time
import shutil
import re
import subprocess
from typing import Dict, List, Optional, Tuple
import datetime
from pathlib import Path
import random
from itertools import zip_longest

import yt_dlp
import httpx
from unsplash.api import Api as UnsplashApi
from unsplash.auth import Auth as UnsplashAuth
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import whisper
import openai
import argparse

# 导入markdown转换模块
try:
    import markdown
    from markdown.extensions import fenced_code, tables, toc
    MARKDOWN_CONVERSION_AVAILABLE = True
except ImportError:
    MARKDOWN_CONVERSION_AVAILABLE = False
    print("⚠️ Markdown转HTML模块未找到，HTML预览功能将不可用。请运行: pip install markdown")

# 加载环境变量
load_dotenv()

# AI 提供者配置
AI_PROVIDER = os.getenv('AI_PROVIDER', 'openrouter').lower()

# 检查必要的环境变量
base_required_env_vars = {
    'UNSPLASH_ACCESS_KEY': '用于图片搜索 (必须)',
    'UNSPLASH_SECRET_KEY': '用于Unsplash认证 (必须)',
    'UNSPLASH_REDIRECT_URI': '用于Unsplash回调 (必须)'
}

provider_specific_env_vars = {}
if AI_PROVIDER == 'openrouter':
    provider_specific_env_vars = {
        'OPENROUTER_API_KEY': '用于OpenRouter API',
    }
    os.environ.setdefault('OPENROUTER_API_URL', 'https://openrouter.ai/api/v1')
elif AI_PROVIDER == 'google':
    provider_specific_env_vars = {
        'GOOGLE_API_KEY': '用于 Google AI Gemini API'
    }
else:
    print(f"⚠️ AI_PROVIDER 设置为 '{AI_PROVIDER}'，这是一个无效的值。请在 .env 文件中将其设置为 'google' 或 'openrouter'。将默认使用 OpenRouter (如果已配置)。")
    AI_PROVIDER = 'openrouter'
    provider_specific_env_vars = {
        'OPENROUTER_API_KEY': '用于OpenRouter API',
    }
    os.environ.setdefault('OPENROUTER_API_URL', 'https://openrouter.ai/api/v1')

required_env_vars = {**base_required_env_vars, **provider_specific_env_vars}

missing_env_vars = []
for var, desc in required_env_vars.items():
    if not os.getenv(var):
        missing_env_vars.append(f"  - {var} ({desc})")

if missing_env_vars:
    print("错误：以下必要的环境变量未设置：")
    print("\n".join(missing_env_vars))
    print(f"\n请根据您选择的 AI 提供者 ({AI_PROVIDER}) 在 .env 文件中设置相应的 API 密钥。")
    if AI_PROVIDER == 'google' and 'GOOGLE_API_KEY' in [v.split(' ')[0] for v in missing_env_vars]:
        print("您选择了 AI_PROVIDER='google'，但 GOOGLE_API_KEY 未设置。")
    elif AI_PROVIDER == 'openrouter' and 'OPENROUTER_API_KEY' in [v.split(' ')[0] for v in missing_env_vars]:
         print("您选择了 AI_PROVIDER='openrouter' (或默认)，但 OPENROUTER_API_KEY 未设置。")
    print("程序将退出。")
    sys.exit(1)

print(f"✅ AI Provider 已选择: {AI_PROVIDER.upper()}")

# 配置代理
http_proxy = os.getenv('HTTP_PROXY')
https_proxy = os.getenv('HTTPS_PROXY')
proxies = {
    'http': http_proxy,
    'https': https_proxy
} if http_proxy and https_proxy else None

# 禁用 SSL 验证（仅用于开发环境）
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

# AI Client and Model Configuration
openrouter_client = None
google_gemini_client = None
AI_MODEL_NAME = None
ai_client_available = False

if AI_PROVIDER == 'openrouter':
    openrouter_api_key = os.getenv('OPENROUTER_API_KEY')
    openrouter_app_name = os.getenv('OPENROUTER_APP_NAME', 'article_note_generator')
    openrouter_http_referer = os.getenv('OPENROUTER_HTTP_REFERER', 'https://github.com')
    openrouter_api_url = os.getenv('OPENROUTER_API_URL')

    if openrouter_api_key:
        openrouter_client = openai.OpenAI(
            api_key=openrouter_api_key,
            base_url=openrouter_api_url,
            default_headers={
                "HTTP-Referer": openrouter_http_referer,
                "X-Title": openrouter_app_name,
            }
        )
        try:
            print(f"正在测试 OpenRouter API 连接 (模型列表)...")
            openrouter_client.models.list()
            print("✅ OpenRouter API 连接测试成功")
            ai_client_available = True
            AI_MODEL_NAME = os.getenv('OPENROUTER_MODEL', "openai/gpt-3.5-turbo-1106")
            print(f"✅ OpenRouter 模型已设置为: {AI_MODEL_NAME}")
        except Exception as e:
            print(f"⚠️ OpenRouter API 连接测试失败: {str(e)}")
            print("如果您希望使用OpenRouter，请检查您的API密钥和网络连接。")
    else:
        print("⚠️ OpenRouter API Key 未设置。如果选择OpenRouter作为AI Provider，相关功能将不可用。")

elif AI_PROVIDER == 'google':
    google_api_key = os.getenv('GOOGLE_API_KEY')
    if google_api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_api_key)
            google_gemini_client = genai
            print("✅ Google AI Gemini API 配置初步成功 (SDK已加载)")
            ai_client_available = True
            AI_MODEL_NAME = os.getenv('GOOGLE_GEMINI_MODEL', "gemini-pro")
            print(f"✅ Google Gemini 模型已设置为: {AI_MODEL_NAME}")
        except ImportError:
            print("⚠️ Google AI SDK (google-generativeai) 未安装。")
            print("请运行 'pip install google-generativeai' 来安装它。")
            print("Google AI Gemini 功能将不可用。")
        except Exception as e:
            print(f"⚠️ Google AI Gemini API 配置失败: {str(e)}")
            print("请检查您的 GOOGLE_API_KEY 和网络连接。")
    else:
        print("⚠️ Google API Key 未设置。如果选择Google作为AI Provider，相关功能将不可用。")

if not ai_client_available:
    print("⚠️ AI客户端未能成功初始化。AI相关功能（内容整理、小红书版本生成等）将不可用。")
    print("请检查您的 .env 文件中的 API 密钥配置和网络连接。")

# 检查Unsplash配置
unsplash_access_key = os.getenv('UNSPLASH_ACCESS_KEY')
unsplash_client = None

if unsplash_access_key:
    try:
        auth = UnsplashAuth(
            client_id=unsplash_access_key,
            client_secret=None,
            redirect_uri=None
        )
        unsplash_client = UnsplashApi(auth)
        print("✅ Unsplash API 配置成功")
    except Exception as e:
        print(f"❌ Failed to initialize Unsplash client: {str(e)}")

# 检查ffmpeg
ffmpeg_path = None
try:
    subprocess.run(["/opt/homebrew/bin/ffmpeg", "-version"], 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE)
    print("✅ ffmpeg is available at /opt/homebrew/bin/ffmpeg")
    ffmpeg_path = "/opt/homebrew/bin/ffmpeg"
except Exception:
    try:
        subprocess.run(["ffmpeg", "-version"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
        print("✅ ffmpeg is available (from PATH)")
        ffmpeg_path = "ffmpeg"
    except Exception as e:
        print(f"⚠️ ffmpeg not found: {str(e)}")

class DownloadError(Exception):
    """自定义下载错误类"""
    def __init__(self, message: str, platform: str, error_type: str, details: str = None):
        self.message = message
        self.platform = platform
        self.error_type = error_type
        self.details = details
        super().__init__(self.message)

class ArticleNoteGenerator:
    def __init__(self, output_dir: str = "temp_notes"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        self.ai_client_available = ai_client_available
        self.unsplash_client = unsplash_client
        self.ffmpeg_path = ffmpeg_path
        
        # 初始化whisper模型
        print("正在加载Whisper模型...")
        self.whisper_model = None
        try:
            self.whisper_model = whisper.load_model("medium")
            print("✅ Whisper模型加载成功")
        except Exception as e:
            print(f"⚠️ Whisper模型加载失败: {str(e)}")
            print("将在需要时重试加载")
        
        # 日志目录
        self.log_dir = os.path.join(self.output_dir, 'logs')
        os.makedirs(self.log_dir, exist_ok=True)
        
        # cookie目录
        self.cookie_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies')
        os.makedirs(self.cookie_dir, exist_ok=True)
        
        # 平台cookie文件
        self.platform_cookies = {
            'douyin': os.path.join(self.cookie_dir, 'douyin_cookies.txt'),
            'bilibili': os.path.join(self.cookie_dir, 'bilibili_cookies.txt'),
            'youtube': os.path.join(self.cookie_dir, 'youtube_cookies.txt')
        }

    def _call_gemini_api(self, system_prompt: str, user_prompt: str, max_retries: int = 3) -> Optional[str]:
        """Helper function to call Google Gemini API with retry mechanism."""
        if not google_gemini_client or not AI_MODEL_NAME:
            print("⚠️ Google Gemini client or model name not configured.")
            return None
        
        for attempt in range(max_retries):
            try:
                print(f"🤖 Calling Google Gemini API (model: {AI_MODEL_NAME}, attempt {attempt + 1}/{max_retries})...")
                model = google_gemini_client.GenerativeModel(AI_MODEL_NAME)
                full_prompt = f"{system_prompt}\n\n{user_prompt}"
                
                # 添加生成配置以提高稳定性
                generation_config = {
                    'temperature': 0.7,
                    'top_p': 0.8,
                    'top_k': 40,
                    'max_output_tokens': 4000,
                }
                
                response = model.generate_content(
                    full_prompt,
                    generation_config=generation_config
                )

                if response and response.text:
                    print("✅ Google Gemini API call successful")
                    return response.text.strip()
                elif response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    print("✅ Google Gemini API call successful")
                    return response.candidates[0].content.parts[0].text.strip()
                else:
                    print(f"⚠️ Google Gemini API returned an empty response or unexpected format.")
                    if response:
                        print(f"Full response object: {response}")
                    if attempt < max_retries - 1:
                        print(f"Retrying in 5 seconds...")
                        time.sleep(5)
                        continue
                    return None
                    
            except Exception as e:
                error_msg = str(e)
                print(f"⚠️ Google Gemini API call failed (attempt {attempt + 1}/{max_retries}): {error_msg}")
                
                # 检查错误类型
                if "500" in error_msg or "Internal" in error_msg:
                    print("🔄 Server error detected, this is likely a temporary issue with Google's servers")
                elif "quota" in error_msg.lower() or "limit" in error_msg.lower():
                    print("📊 API quota or rate limit reached")
                elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                    print("🌐 Network connection issue detected")
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5  # 递增等待时间
                    print(f"⏳ Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    print("❌ All retry attempts failed")
                    import traceback
                    print(traceback.format_exc())
                    
        return None
    
    def _ensure_whisper_model(self) -> None:
        """确保Whisper模型已加载"""
        if self.whisper_model is None:
            try:
                print("正在加载Whisper模型...")
                self.whisper_model = whisper.load_model("medium")
                print("✅ Whisper模型加载成功")
            except Exception as e:
                print(f"⚠️ Whisper模型加载失败: {str(e)}")

    def _determine_platform(self, url: str) -> Optional[str]:
        """确定视频平台"""
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'douyin.com' in url:
            return 'douyin'
        elif 'bilibili.com' in url:
            return 'bilibili'
        return None

    def _handle_download_error(self, error: Exception, platform: str, url: str) -> str:
        """处理下载错误并返回用户友好的错误消息"""
        error_msg = str(error)
        
        if "SSL" in error_msg:
            return "⚠️ SSL证书验证失败，请检查网络连接"
        elif "cookies" in error_msg.lower():
            return f"⚠️ {platform}访问被拒绝，可能需要更新cookie或更换IP地址"
        elif "404" in error_msg:
            return "⚠️ 视频不存在或已被删除"
        elif "403" in error_msg:
            return "⚠️ 访问被拒绝，可能需要登录或更换IP地址"
        elif "unavailable" in error_msg.lower():
            return "⚠️ 视频当前不可用，可能是地区限制或版权问题"
        else:
            return f"⚠️ 下载失败: {error_msg}"

    def _get_platform_options(self, platform: str) -> Dict:
        """获取平台特定的下载选项"""
        options = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': '%(title)s.%(ext)s'
        }
        
        if platform in self.platform_cookies and os.path.exists(self.platform_cookies[platform]):
            options['cookiefile'] = self.platform_cookies[platform]
            
        return options

    def _download_video(self, url: str, temp_dir: str) -> Tuple[Optional[str], Optional[Dict[str, str]], bool]:
        """下载视频并返回音频或字幕文件路径、信息以及一个布尔值，该布尔值指示返回的是否是字幕文件。"""
        try:
            platform = self._determine_platform(url)
            if not platform:
                raise DownloadError("不支持的视频平台", "unknown", "platform_error")

            # 检查字幕
            subtitle_path, info = self._download_subtitles(url, temp_dir)
            if subtitle_path:
                video_info = {
                    'title': info.get('title', '未知标题'),
                    'uploader': info.get('uploader', '未知作者'),
                    'description': info.get('description', ''),
                    'duration': info.get('duration', 0),
                    'platform': platform
                }
                return subtitle_path, video_info, True

            # 如果没有字幕，则下载音频
            audio_path, info = self._download_audio(url, temp_dir)
            if audio_path:
                video_info = {
                    'title': info.get('title', '未知标题'),
                    'uploader': info.get('uploader', '未知作者'),
                    'description': info.get('description', ''),
                    'duration': info.get('duration', 0),
                    'platform': platform
                }
                return audio_path, video_info, False

            return None, None, False

        except Exception as e:
            error_msg = self._handle_download_error(e, platform, url)
            print(f"⚠️ {error_msg}")
            return None, None, False

    def _download_audio(self, url: str, temp_dir: str) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
        """下载音频并返回文件路径和信息"""
        platform = self._determine_platform(url)
        options = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }],
            'quiet': True,
            'no_warnings': True,
        }

        for attempt in range(3):
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    print(f"正在尝试下载音频（第{attempt + 1}次）...")
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        raise DownloadError("无法获取视频信息", platform, "info_error")

                    downloaded_files = [f for f in os.listdir(temp_dir) if f.endswith('.mp3')]
                    if not downloaded_files:
                        raise DownloadError("未找到下载的音频文件", platform, "file_error")

                    audio_path = os.path.join(temp_dir, downloaded_files[0])
                    if not os.path.exists(audio_path):
                        raise DownloadError("音频文件不存在", platform, "file_error")

                    print(f"✅ {platform}音频下载成功")
                    return audio_path, info

            except Exception as e:
                print(f"⚠️ 音频下载失败（第{attempt + 1}次）: {str(e)}")
                if attempt < 2:
                    print("等待5秒后重试...")
                    time.sleep(5)
                else:
                    raise

    def _download_subtitles(self, url: str, temp_dir: str) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
        """下载字幕并返回文件路径和信息"""
        platform = self._determine_platform(url)
        options = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['zh-Hans', 'zh-Hant', 'zh', 'en'],
            'subtitlesformat': 'vtt/srt/best',
            'skip_download': True,
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                print("正在检查和下载字幕...")
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None, None

                subtitle_files = [f for f in os.listdir(temp_dir) if f.endswith(('.vtt', '.srt'))]
                if not subtitle_files:
                    return None, None

                subtitle_path = os.path.join(temp_dir, subtitle_files[0])
                print(f"✅ {platform}字幕下载成功")
                return subtitle_path, info

        except Exception as e:
            print(f"⚠️ 字幕下载失败: {str(e)}")
            return None, None

    def _read_subtitle_file(self, file_path: str) -> str:
        """读取字幕文件内容"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            content_lines = []
            for line in lines:
                if not re.match(r'^(\d{2}:)?\d{2}:\d{2}\.\d{3}\s+-->\s+(\d{2}:)?\d{2}:\d{2}\.\d{3}', line) and \
                   not line.strip().isdigit() and \
                   'WEBVTT' not in line and \
                   'Kind:' not in line and \
                   'Language:' not in line:
                    content_lines.append(line.strip())
            
            return ' '.join(content_lines)
        except Exception as e:
            print(f"⚠️ 读取字幕文件失败: {str(e)}")
            return ""

    def _transcribe_audio(self, audio_path: str) -> str:
        """使用Whisper转录音频"""
        try:
            self._ensure_whisper_model()
            if not self.whisper_model:
                raise Exception("Whisper模型未加载")
                
            print("正在转录音频（这可能需要几分钟）...")
            result = self.whisper_model.transcribe(
                audio_path,
                language='zh',
                task='transcribe',
                best_of=5,
                initial_prompt="以下是一段视频的转录内容。请用流畅的中文输出。"
            )
            return result["text"].strip()
            
        except Exception as e:
            print(f"⚠️ 音频转录失败: {str(e)}")
            return ""

    def process_local_audio(self, audio_path: str, output_format: str = "both", wechat_template: str = "default") -> List[str]:
        """处理本地音频文件，生成笔记
        
        Args:
            audio_path (str): 本地音频文件路径
            output_format (str): 输出格式 ("xiaohongshu", "wechat", "both")
            wechat_template (str): 微信公众号模板风格 ("default", "modern", "tech", "mianpro", "lapis", "maize", "orangeheart", "phycat", "pie", "purple", "rainbow")
        
        Returns:
            List[str]: 生成的笔记文件路径列表
        """
        print(f"\n🎵 正在处理本地音频文件: {audio_path}")
        
        if not os.path.exists(audio_path):
            print(f"⚠️ 音频文件不存在: {audio_path}")
            return []
        
        # 检查文件格式
        supported_formats = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac']
        file_ext = os.path.splitext(audio_path)[1].lower()
        if file_ext not in supported_formats:
            print(f"⚠️ 不支持的音频格式: {file_ext}")
            print(f"支持的格式: {', '.join(supported_formats)}")
            return []
        
        try:
            # 转录音频
            print("\n🎙️ 正在转录音频...")
            transcript = self._transcribe_audio(audio_path)
            if not transcript:
                print("⚠️ 音频转录失败")
                return []

            # 创建音频信息
            audio_info = {
                'title': os.path.splitext(os.path.basename(audio_path))[0],
                'uploader': '本地文件',
                'description': '',
                'duration': 0,
                'platform': 'local'
            }

            return self._generate_notes(transcript, audio_info, None, output_format, wechat_template)
            
        except Exception as e:
            print(f"⚠️ 处理本地音频时出错: {str(e)}")
            return []

    def _organize_content(self, content: str) -> str:
        """使用AI整理内容，支持自动切换AI提供者"""
        if not ai_client_available:
            print("⚠️ AI client not available. Returning original content.")
            return content

        system_prompt = """你是一位著名的科普作家和博客作者，著作等身，屡获殊荣，尤其在内容创作领域有深厚的造诣。

请使用 4C 模型（建立联系 Connection、展示冲突 Conflict、强调改变 Change、即时收获 Catch）为转录的文字内容创建结构。

写作要求：
- 从用户的问题出发，引导读者理解核心概念及其背景
- 使用第二人称与读者对话，语气亲切平实
- 确保所有观点和内容基于用户提供的转录文本
- 如无具体实例，则不编造
- 涉及复杂逻辑时，使用直观类比
- 避免内容重复冗余
- 逻辑递进清晰，从问题开始，逐步深入

Markdown格式要求：
- 大标题突出主题，吸引眼球，最好使用疑问句
- 小标题简洁有力，结构清晰，尽量使用单词或短语
- 直入主题，在第一部分清晰阐述问题和需求
- 正文使用自然段，避免使用列表形式
- 内容翔实，避免过度简略，特别注意保留原文中的数据和示例信息
- 如有来源URL，使用文内链接形式
- 保留原文中的Markdown格式图片链接"""

        user_prompt = f"""请根据以下转录文字内容，创作一篇结构清晰、易于理解的博客文章。

转录文字内容：

{content}"""

        # 尝试使用主要AI提供者
        organized_text = self._try_ai_call(system_prompt, user_prompt, AI_PROVIDER)
        if organized_text:
            return organized_text
        
        # 如果主要提供者失败，尝试备用提供者
        backup_provider = 'openrouter' if AI_PROVIDER == 'google' else 'google'
        if backup_provider == 'openrouter' and openrouter_client:
            print(f"🔄 主要AI提供者失败，尝试使用备用提供者: {backup_provider}")
            organized_text = self._try_ai_call(system_prompt, user_prompt, backup_provider)
            if organized_text:
                return organized_text
        elif backup_provider == 'google' and google_gemini_client:
            print(f"🔄 主要AI提供者失败，尝试使用备用提供者: {backup_provider}")
            organized_text = self._try_ai_call(system_prompt, user_prompt, backup_provider)
            if organized_text:
                return organized_text
        
        print("⚠️ 所有AI提供者都失败了，返回原始内容")
        return content

    def _try_ai_call(self, system_prompt: str, user_prompt: str, provider: str) -> Optional[str]:
        """尝试调用指定的AI提供者"""
        try:
            if provider == 'google':
                if not google_gemini_client:
                    print("⚠️ Google AI Provider not available.")
                    return None
                return self._call_gemini_api(system_prompt, user_prompt)
            
            elif provider == 'openrouter':
                if not openrouter_client:
                    print("⚠️ OpenRouter AI Provider not available.")
                    return None

                print(f"🤖 Calling OpenRouter API (model: {AI_MODEL_NAME})...")
                response = openrouter_client.chat.completions.create(
                    model=AI_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=4000
                )
                if response.choices and response.choices[0].message and response.choices[0].message.content:
                    print("✅ OpenRouter API call successful")
                    return response.choices[0].message.content.strip()
                else:
                    print(f"⚠️ OpenRouter API returned an empty or unexpected response: {response}")
                    return None
            else:
                print(f"⚠️ Unknown AI_PROVIDER '{provider}'.")
                return None

        except Exception as e:
            print(f"⚠️ {provider} API call failed: {str(e)}")
            return None

    def split_content(self, text: str, max_chars: int = 2000) -> List[str]:
        """按段落分割文本，保持上下文的连贯性"""
        if not text:
            return []

        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_length = 0
        last_paragraph = None
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            para_length = len(para)
            
            if not current_chunk and last_paragraph:
                current_chunk.append(f"上文概要：\n{last_paragraph}\n")
                current_length += len(last_paragraph) + 20
            
            if para_length > max_chars:
                if current_chunk:
                    last_paragraph = current_chunk[-1]
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_length = 0
                    if last_paragraph:
                        current_chunk.append(f"上文概要：\n{last_paragraph}\n")
                        current_length += len(last_paragraph) + 20
                
                sentences = re.split(r'([。！？])', para)
                current_sentence = []
                current_sentence_length = 0
                
                for i in range(0, len(sentences), 2):
                    sentence = sentences[i]
                    if i + 1 < len(sentences):
                        sentence += sentences[i + 1]
                    
                    if current_sentence_length + len(sentence) > max_chars and current_sentence:
                        chunks.append(''.join(current_sentence))
                        current_sentence = [sentence]
                        current_sentence_length = len(sentence)
                    else:
                        current_sentence.append(sentence)
                        current_sentence_length += len(sentence)
                
                if current_sentence:
                    chunks.append(''.join(current_sentence))
            else:
                if current_length + para_length > max_chars and current_chunk:
                    last_paragraph = current_chunk[-1]
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = []
                    current_length = 0
                    if last_paragraph:
                        current_chunk.append(f"上文概要：\n{last_paragraph}\n")
                        current_length += len(last_paragraph) + 20
                current_chunk.append(para)
                current_length += para_length
        
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        return chunks

    def _organize_long_content(self, content: str, duration: int = 0) -> str:
        """使用AI整理长文内容"""
        if not content.strip():
            return ""
        
        if not ai_client_available:
            print("⚠️ AI client not available for long content organization. Returning original content.")
            return content
        
        content_chunks = self.split_content(content)
        organized_chunks = []
        
        print(f"内容将分为 {len(content_chunks)} 个部分进行处理...")
        
        for i, chunk in enumerate(content_chunks, 1):
            print(f"正在处理第 {i}/{len(content_chunks)} 部分...")
            organized_chunk = self._organize_content(chunk)
            organized_chunks.append(organized_chunk)
    
        return "\n\n".join(organized_chunks)

    def _convert_md_to_html(self, md_content: str, title: str = '') -> str:
        """将Markdown内容转换为HTML"""
        try:
            import markdown
            from markdown.extensions import fenced_code, tables, toc
            
            # 预处理markdown内容，处理标签
            lines = md_content.split('\n')
            processed_lines = []
            for line in lines:
                if all(word.strip().startswith('#') for word in line.split() if word.strip()):
                    tags = line.strip().split()
                    processed_line = '<div class="tags">' + ' '.join([f'<span class="tag">{tag}</span>' for tag in tags]) + '</div>'
                    processed_lines.append(processed_line)
                else:
                    processed_lines.append(line)
            processed_content = '\n'.join(processed_lines)
            
            # HTML模板
            html_template = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>{title}</title>
                <style>
                    body {{
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 20px;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                    }}
                    img {{
                        max-width: 100%;
                        height: auto;
                        border-radius: 8px;
                        margin: 20px 0;
                    }}
                    h1, h2, h3 {{
                        color: #2c3e50;
                    }}
                    code {{
                        background: #f8f9fa;
                        padding: 2px 5px;
                        border-radius: 3px;
                    }}
                    pre {{
                        background: #f8f9fa;
                        padding: 15px;
                        border-radius: 5px;
                        overflow-x: auto;
                    }}
                    blockquote {{
                        border-left: 4px solid #dfe2e5;
                        margin: 0;
                        padding-left: 20px;
                        color: #666;
                    }}
                    .tags {{
                        margin: 20px 0;
                        line-height: 2;
                    }}
                    .tag {{
                        display: inline-block;
                        padding: 4px 12px;
                        margin: 0 8px 8px 0;
                        background-color: #f3f4f6;
                        color: #2563eb;
                        border-radius: 16px;
                        font-size: 0.9em;
                        transition: all 0.2s;
                    }}
                    .tag:hover {{
                        background-color: #2563eb;
                        color: white;
                    }}
                </style>
            </head>
            <body>
                {markdown.markdown(processed_content, extensions=['fenced_code', 'tables', 'toc'])}
            </body>
            </html>
            """
            
            return html_template
        except ImportError:
            print("⚠️ 请安装markdown库: pip install markdown")
            return ""
        except Exception as e:
            print(f"⚠️ 转换HTML失败: {str(e)}")
            return ""

    def convert_to_xiaohongshu(self, content: str) -> Tuple[str, List[str], List[str], List[str]]:
        """将博客文章转换为小红书风格的笔记，并生成标题和标签"""
        if not ai_client_available:
            print("⚠️ AI client not available for Xiaohongshu conversion. Returning original content.")
            return content, [], [], []

        system_prompt = """你是一位专业的小红书爆款文案写作大师，擅长将普通内容转换为刷屏级爆款笔记。
请将输入的内容转换为小红书风格的笔记，需要满足以下要求：

1. 标题创作（重要‼️）：
- 二极管标题法：
  * 追求快乐：产品/方法 + 只需N秒 + 逆天效果
  * 逃避痛苦：不采取行动 + 巨大损失 + 紧迫感
- 爆款关键词（必选1-2个）：
  * 高转化词：好用到哭、宝藏、神器、压箱底、隐藏干货、高级感
  * 情感词：绝绝子、破防了、治愈、万万没想到、爆款、永远可以相信
  * 身份词：小白必看、手残党必备、打工人、普通女生
  * 程度词：疯狂点赞、超有料、无敌、一百分、良心推荐
- 标题规则：
  * 字数：20字以内
  * emoji：2-4个相关表情
  * 标点：感叹号、省略号增强表达
  * 风格：口语化、制造悬念

2. 正文创作：
- 开篇设置（抓住痛点）：
  * 共情开场：描述读者痛点
  * 悬念引导：埋下解决方案的伏笔
  * 场景还原：具体描述场景
- 内容结构：
  * 每段开头用emoji引导
  * 重点内容加粗突出
  * 适当空行增加可读性
  * 步骤说明要清晰
- 写作风格：
  * 热情亲切的语气
  * 大量使用口语化表达
  * 插入互动性问句
  * 加入个人经验分享
- 高级技巧：
  * 使用平台热梗
  * 加入流行口头禅
  * 设置悬念和爆点
  * 情感共鸣描写

3. 标签优化：
- 提取4类标签（每类1-2个）：
  * 核心关键词：主题相关
  * 关联关键词：长尾词
  * 高转化词：购买意向强
  * 热搜词：行业热点

4. 整体要求：
- 内容体量：根据内容自动调整
- 结构清晰：善用分点和空行
- 情感真实：避免过度营销
- 互动引导：设置互动机会
- AI友好：避免机器味

注意：创作时要始终记住，标题决定打开率，内容决定完播率，互动决定涨粉率！"""

        user_prompt = f"""请将以下内容转换为爆款小红书笔记。

内容如下：
{content}

请按照以下格式返回：
1. 第一行：爆款标题（遵循二极管标题法，必须有emoji）
2. 空一行
3. 正文内容（注意结构、风格、技巧的运用，控制在600-800字之间）
4. 空一行
5. 标签列表（每类标签都要有，用#号开头）

创作要求：
1. 标题要让人忍不住点进来看
2. 内容要有干货，但表达要轻松
3. 每段都要用emoji装饰
4. 标签要覆盖核心词、关联词、转化词、热搜词
5. 设置2-3处互动引导
6. 通篇要有感情和温度
7. 正文控制在600-800字之间

"""

        try:
            xiaohongshu_text_from_api = None
            if AI_PROVIDER == 'google':
                if not google_gemini_client:
                    print("⚠️ Google AI Provider selected, but client not initialized for Xiaohongshu conversion.")
                    return content, [], [], []
                xiaohongshu_text_from_api = self._call_gemini_api(system_prompt, user_prompt)
            
            elif AI_PROVIDER == 'openrouter':
                if not openrouter_client:
                    print("⚠️ OpenRouter AI Provider selected, but client not initialized for Xiaohongshu conversion.")
                    return content, [], [], []

                print(f"🤖 Calling OpenRouter API for Xiaohongshu (model: {AI_MODEL_NAME})...")
                response = openrouter_client.chat.completions.create(
                    model=AI_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=2000
                )
                if response.choices and response.choices[0].message and response.choices[0].message.content:
                    xiaohongshu_text_from_api = response.choices[0].message.content.strip()
                else:
                    print(f"⚠️ OpenRouter API returned an empty or unexpected response for Xiaohongshu: {response}")
                    return content, [], [], []
            else:
                print(f"⚠️ Unknown AI_PROVIDER '{AI_PROVIDER}' for Xiaohongshu conversion.")
                return content, [], [], []

            if not xiaohongshu_text_from_api:
                print("⚠️ AI API call returned no content for Xiaohongshu conversion.")
                return content, [], [], []

            print(f"\n📝 API返回内容 (Xiaohongshu)：\n{xiaohongshu_text_from_api}\n")

            # 提取标题（第一行）
            titles = []
            for line in xiaohongshu_text_from_api.split('\n'):
                line = line.strip()
                if line and not line.startswith('#') and '：' not in line and '。' not in line:
                    titles = [line]
                    break
            
            if not titles:
                print("⚠️ 未找到标题，尝试其他方式提取...")
                title_match = re.search(r'^[^#\n]+', xiaohongshu_text_from_api)
                if title_match:
                    titles = [title_match.group(0).strip()]
            
            if titles:
                print(f"✅ 提取到标题: {titles[0]}")
            else:
                print("⚠️ 未能提取到标题")
            
            # 提取标签（查找所有#开头的标签）
            tags = []
            tag_matches = re.findall(r'#([^\s#]+)', xiaohongshu_text_from_api)
            if tag_matches:
                tags = tag_matches
                print(f"✅ 提取到{len(tags)}个标签")
            else:
                print("⚠️ 未找到标签")
            
            # 获取相关图片
            images = []
            if self.unsplash_client:
                search_terms = titles + tags[:2] if tags else titles
                search_query = ' '.join(search_terms)
                try:
                    images = self._get_unsplash_images(search_query, count=4)
                    if images:
                        print(f"✅ 成功获取{len(images)}张配图")
                    else:
                        print("⚠️ 未找到相关配图")
                except Exception as e:
                    print(f"⚠️ 获取配图失败: {str(e)}")
            
            return xiaohongshu_text_from_api, titles, tags, images

        except Exception as e:
            print(f"⚠️ 转换小红书笔记失败: {str(e)}")
            return content, [], [], []

    def _try_xiaohongshu_conversion(self, system_prompt: str, user_prompt: str, provider: str) -> Optional[str]:
        """尝试使用指定提供者进行小红书转换"""
        try:
            if provider == 'google':
                if not google_gemini_client:
                    print("⚠️ Google AI Provider not available for Xiaohongshu conversion.")
                    return None
                return self._call_gemini_api(system_prompt, user_prompt)
            
            elif provider == 'openrouter':
                if not openrouter_client:
                    print("⚠️ OpenRouter AI Provider not available for Xiaohongshu conversion.")
                    return None

                print(f"🤖 Calling OpenRouter API for Xiaohongshu (model: {AI_MODEL_NAME})...")
                response = openrouter_client.chat.completions.create(
                    model=AI_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=2000
                )
                if response.choices and response.choices[0].message and response.choices[0].message.content:
                    print("✅ OpenRouter API call successful for Xiaohongshu")
                    return response.choices[0].message.content.strip()
                else:
                    print(f"⚠️ OpenRouter API returned an empty or unexpected response for Xiaohongshu: {response}")
                    return None
            else:
                print(f"⚠️ Unknown AI_PROVIDER '{provider}' for Xiaohongshu conversion.")
                return None

        except Exception as e:
            print(f"⚠️ {provider} API call failed for Xiaohongshu conversion: {str(e)}")
            return None

    def _try_wechat_conversion(self, system_prompt: str, user_prompt: str, provider: str) -> Optional[str]:
        """尝试使用指定提供者进行微信转换"""
        try:
            if provider == 'google':
                if not google_gemini_client:
                    print("⚠️ Google AI Provider not available for WeChat conversion.")
                    return None
                return self._call_gemini_api(system_prompt, user_prompt)
            
            elif provider == 'openrouter':
                if not openrouter_client:
                    print("⚠️ OpenRouter AI Provider not available for WeChat conversion.")
                    return None

                print(f"🤖 Calling OpenRouter API for WeChat (model: {AI_MODEL_NAME})...")
                response = openrouter_client.chat.completions.create(
                    model=AI_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=3000
                )
                if response.choices and response.choices[0].message and response.choices[0].message.content:
                    print("✅ OpenRouter API call successful for WeChat")
                    return response.choices[0].message.content.strip()
                else:
                    print(f"⚠️ OpenRouter API returned an empty or unexpected response for WeChat: {response}")
                    return None
            else:
                print(f"⚠️ Unknown AI_PROVIDER '{provider}' for WeChat conversion.")
                return None

        except Exception as e:
            print(f"⚠️ {provider} API call failed for WeChat conversion: {str(e)}")
            return None

    def convert_to_wechat(self, content: str, template_style: str = "default") -> Tuple[str, List[str], List[str], str]:
        """将博客文章转换为微信公众号风格的文章，并生成标题和配图
        
        Args:
            content: 原始内容
            template_style: 模板风格，可选值: default, modern, tech, mianpro
            
        Returns:
            Tuple[str, List[str], List[str], str]: (处理后的内容, 标题列表, 图片URL列表, 使用的模板风格)
        """
        if not ai_client_available:
            print("⚠️ AI client not available for WeChat conversion. Returning original content.")
            return content, [], [], template_style

        # 基于提供的微信公众号写作文档构建系统提示词
        system_prompt = """你是微信公众号内容编辑助手，擅长撰写适合移动端阅读、引人入胜、互动性强的文章。

请根据微信公众号文章的九大特点来优化内容：

1. **内容结构**：精炼清晰，800-2000字，3-5小标题，逻辑分明
2. **语气风格**：口语化、贴近读者，灵活运用"轻松幽默 / 情感共鸣 / 专业严谨"等风格
3. **移动友好**：段落简短（2-5行），适合碎片化阅读
4. **强互动性**：文末常用提问、评论引导、点赞转发CTA
5. **视觉吸引**：排版简洁美观，关键词可加粗
6. **价值导向**：提供干货、情绪价值、共鸣感或实用技巧
7. **时效敏感**：紧贴热点话题、节气、新闻事件
8. **隐性营销**：柔性植入品牌/产品，避免硬广
9. **流量平台属性**：微信生态强、私域流量浓，标题+封面图对点击率影响极大

写作结构要求：
- 吸引眼球的标题（15字内）
- 精彩导语（引入问题/讲故事/给数据）
- 正文按3-5小标题展开，每段不超150字
- 结尾：总结+引导读者评论、转发或关注

排版建议：
- 每段控制在2-5行
- 加粗关键词
- 每小节配emoji（如📌✅🚀）
- 每500字建议一张插图

请将内容转换为符合微信公众号特点的文章格式。"""

        user_prompt = f"""请将以下内容转换为微信公众号文章。

内容如下：
{content}

请按照以下格式返回：
1. 第一行：吸引眼球的标题（15字内）
2. 空一行
3. 精彩导语（引入问题/讲故事/给数据）
4. 正文内容（3-5个小标题，每段2-5行，关键词加粗，适当使用emoji）
5. 结尾（总结+互动引导）

要求：
1. 字数控制在800-2000字
2. 语气亲切自然，口语化表达
3. 段落简短，适合手机阅读
4. 加粗重点内容
5. 设置互动引导
6. 提供实用价值"""

        try:
            # 尝试使用主要AI提供者
            wechat_text_from_api = self._try_wechat_conversion(system_prompt, user_prompt, AI_PROVIDER)
            
            # 如果主要提供者失败，尝试备用提供者
            if not wechat_text_from_api:
                backup_provider = 'openrouter' if AI_PROVIDER == 'google' else 'google'
                if backup_provider == 'openrouter' and openrouter_client:
                    print(f"🔄 主要AI提供者失败，尝试使用备用提供者进行微信转换: {backup_provider}")
                    wechat_text_from_api = self._try_wechat_conversion(system_prompt, user_prompt, backup_provider)
                elif backup_provider == 'google' and google_gemini_client:
                    print(f"🔄 主要AI提供者失败，尝试使用备用提供者进行微信转换: {backup_provider}")
                    wechat_text_from_api = self._try_wechat_conversion(system_prompt, user_prompt, backup_provider)

            if not wechat_text_from_api:
                print("⚠️ 所有AI提供者都失败了，无法进行微信转换")
                return content, [], [], template_style

            print(f"\n📝 API返回内容 (WeChat)：\n{wechat_text_from_api}\n")

            # 提取标题（第一行）
            titles = []
            for line in wechat_text_from_api.split('\n'):
                line = line.strip()
                if line and not line.startswith('#') and len(line) <= 20:
                    titles = [line]
                    break
            
            if not titles:
                print("⚠️ 未找到标题，尝试其他方式提取...")
                title_match = re.search(r'^[^#\n]+', wechat_text_from_api)
                if title_match:
                    titles = [title_match.group(0).strip()]
            
            if titles:
                print(f"✅ 提取到标题: {titles[0]}")
            else:
                print("⚠️ 未能提取到标题")
            
            # 获取相关图片
            images = []
            if self.unsplash_client:
                # 从标题和内容中提取关键词作为搜索词
                search_query = titles[0] if titles else "article"
                try:
                    images = self._get_unsplash_images(search_query, count=6)
                    if images:
                        print(f"✅ 成功获取{len(images)}张配图")
                    else:
                        print("⚠️ 未找到相关配图")
                except Exception as e:
                    print(f"⚠️ 获取配图失败: {str(e)}")
            
            return wechat_text_from_api, titles, images, template_style

        except Exception as e:
            print(f"⚠️ 转换微信公众号文章失败: {str(e)}")
            return content, [], [], template_style

    def _get_unsplash_images(self, query: str, count: int = 3) -> List[str]:
        """从Unsplash获取相关图片并保存到本地"""
        if not self.unsplash_client:
            print("⚠️ Unsplash客户端未初始化")
            return []
            
        try:
            # 创建unsplash文件夹
            unsplash_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'unsplash')
            os.makedirs(unsplash_dir, exist_ok=True)
            
            # 将查询词翻译成英文以获得更好的结果
            translated_query = self._translate_text_for_image_search(query)
            
            # 使用httpx直接调用Unsplash API
            headers = {
                'Authorization': f'Client-ID {os.getenv("UNSPLASH_ACCESS_KEY")}'
            }
            
            # 对每个关键词分别搜索
            all_photos = []
            all_photo_data = []  # 保存完整的图片数据用于下载
            
            for keyword in translated_query.split(','):
                response = httpx.get(
                    'https://api.unsplash.com/search/photos',
                    params={
                        'query': keyword.strip(),
                        'per_page': count,
                        'orientation': 'landscape',  # 微信公众号偏好横版图片
                        'content_filter': 'high'    # 只返回高质量图片
                    },
                    headers=headers,
                    verify=False  # 禁用SSL验证
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data['results']:
                        # 获取图片URL，优先使用regular尺寸
                        for photo in data['results']:
                            photo_url = photo['urls'].get('regular', photo['urls']['small'])
                            all_photos.append(photo_url)
                            all_photo_data.append(photo)
            
            # 如果收集到的图片不够，用最后一个关键词继续搜索
            while len(all_photos) < count and translated_query:
                response = httpx.get(
                    'https://api.unsplash.com/search/photos',
                    params={
                        'query': translated_query.split(',')[-1].strip(),
                        'per_page': count - len(all_photos),
                        'orientation': 'landscape',
                        'content_filter': 'high',
                        'page': 2  # 获取下一页的结果
                    },
                    headers=headers,
                    verify=False
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data['results']:
                        for photo in data['results']:
                            photo_url = photo['urls'].get('regular', photo['urls']['small'])
                            all_photos.append(photo_url)
                            all_photo_data.append(photo)
                    else:
                        break
                else:
                    break
            
            # 限制到指定数量
            selected_photos = all_photos[:count]
            selected_photo_data = all_photo_data[:count]
            
            # 下载图片到本地
            local_image_paths = []
            for i, (photo_url, photo_data) in enumerate(zip(selected_photos, selected_photo_data)):
                try:
                    # 生成本地文件名
                    photo_id = photo_data.get('id', f'unsplash_{i}')
                    file_extension = '.jpg'  # Unsplash图片通常是jpg格式
                    local_filename = f"{photo_id}_{query.replace(' ', '_')[:20]}{file_extension}"
                    local_path = os.path.join(unsplash_dir, local_filename)
                    
                    # 如果文件已存在，跳过下载
                    if os.path.exists(local_path):
                        print(f"📁 图片已存在，跳过下载: {local_filename}")
                        local_image_paths.append(photo_url)  # 仍然返回在线URL
                        continue
                    
                    # 下载图片
                    print(f"⬇️ 正在下载图片 {i+1}/{len(selected_photos)}: {local_filename}")
                    img_response = httpx.get(photo_url, verify=False, timeout=30)
                    
                    if img_response.status_code == 200:
                        with open(local_path, 'wb') as f:
                            f.write(img_response.content)
                        print(f"✅ 图片已保存到: {local_path}")
                        local_image_paths.append(photo_url)  # 返回在线URL用于HTML显示
                    else:
                        print(f"⚠️ 下载图片失败，状态码: {img_response.status_code}")
                        local_image_paths.append(photo_url)  # 即使下载失败也返回在线URL
                        
                except Exception as download_error:
                    print(f"⚠️ 下载图片时出错: {str(download_error)}")
                    local_image_paths.append(photo_url)  # 出错时仍返回在线URL
            
            if local_image_paths:
                print(f"✅ 成功获取{len(local_image_paths)}张图片，已保存到 {unsplash_dir} 文件夹")
            
            return local_image_paths
            
        except Exception as e:
            print(f"⚠️ 获取图片失败: {str(e)}")
            return []

    def _try_translation(self, system_prompt: str, user_prompt: str, provider: str) -> Optional[str]:
        """尝试使用指定提供者进行翻译"""
        try:
            if provider == 'google':
                if not google_gemini_client:
                    print("⚠️ Google AI Provider not available for translation.")
                    return None
                return self._call_gemini_api(system_prompt, user_prompt)
            
            elif provider == 'openrouter':
                if not openrouter_client:
                    print("⚠️ OpenRouter AI Provider not available for translation.")
                    return None

                print(f"🤖 Calling OpenRouter API for translation (model: {AI_MODEL_NAME})...")
                response = openrouter_client.chat.completions.create(
                    model=AI_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=50
                )
                if response.choices and response.choices[0].message and response.choices[0].message.content:
                    print("✅ OpenRouter API call successful for translation")
                    return response.choices[0].message.content.strip()
                else:
                    print(f"⚠️ OpenRouter API returned an empty or unexpected response for translation: {response}")
                    return None
            else:
                print(f"⚠️ Unknown AI_PROVIDER '{provider}' for translation.")
                return None

        except Exception as e:
            print(f"⚠️ {provider} API call failed for translation: {str(e)}")
            return None

    def _translate_text_for_image_search(self, query: str) -> str:
        """Helper function to translate text using the configured AI provider for image search with backup support."""
        if not ai_client_available or not query:
            print("⚠️ AI client not available for translation or empty query.")
            return query

        system_prompt = "你是一个翻译助手。请将输入的中文关键词翻译成最相关的1-3个英文关键词，用逗号分隔。直接返回翻译结果，不要加任何解释。例如：\n输入：'保险理财知识'\n输出：insurance,finance,investment"
        user_prompt = query

        # 尝试使用主要AI提供者
        translated_query = self._try_translation(system_prompt, user_prompt, AI_PROVIDER)
        if translated_query:
            print(f"📝 Translated image search query from '{query}' to '{translated_query}'")
            return translated_query
        
        # 如果主要提供者失败，尝试备用提供者
        backup_provider = 'openrouter' if AI_PROVIDER == 'google' else 'google'
        if backup_provider == 'openrouter' and openrouter_client:
            print(f"🔄 主要AI提供者失败，尝试使用备用提供者进行翻译: {backup_provider}")
            translated_query = self._try_translation(system_prompt, user_prompt, backup_provider)
            if translated_query:
                print(f"📝 Translated image search query from '{query}' to '{translated_query}' using backup provider")
                return translated_query
        elif backup_provider == 'google' and google_gemini_client:
            print(f"🔄 主要AI提供者失败，尝试使用备用提供者进行翻译: {backup_provider}")
            translated_query = self._try_translation(system_prompt, user_prompt, backup_provider)
            if translated_query:
                print(f"📝 Translated image search query from '{query}' to '{translated_query}' using backup provider")
                return translated_query
        
        print(f"⚠️ 所有AI提供者都失败了，使用原始查询词: '{query}'")
        return query

    def _generate_wechat_html(self, content: str, title: str, images: List[str], template_style: str = "default") -> str:
        """生成微信公众号风格的HTML文件
        
        Args:
            content: 文章内容
            title: 文章标题
            images: 图片URL列表
            template_style: 模板风格，可选值: default, modern, tech, mianpro
        """
        try:
            # 将内容按段落分割
            paragraphs = content.split('\n\n')
            
            # 在适当位置插入图片
            html_content = []
            image_index = 0
            
            # 根据不同模板调整图片插入策略
            if template_style == "modern" or template_style == "tech":
                # 现代/技术风格: 第一张图片放在文章开头作为封面
                if images and len(images) > 0:
                    html_content.append(f'<div class="cover-image"><img src="{images[0]}" alt="封面图" /></div>')
                    image_index = 1
            
            for i, paragraph in enumerate(paragraphs):
                if not paragraph.strip():
                    continue
                    
                # 处理标题
                if paragraph.startswith('#'):
                    level = len(paragraph) - len(paragraph.lstrip('#'))
                    text = paragraph.lstrip('# ').strip()
                    html_content.append(f'<h{level}>{text}</h{level}>')
                else:
                    # 处理加粗文本
                    paragraph = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', paragraph)
                    html_content.append(f'<p>{paragraph}</p>')
                
                # 根据不同模板调整图片插入频率
                insert_image_interval = 3  # 默认每3段插入一张图片
                if template_style == "modern":
                    insert_image_interval = 4  # 现代风格每4段插入一张图片
                elif template_style == "tech":
                    insert_image_interval = 5  # 技术风格每5段插入一张图片
                elif template_style == "mianpro":
                    insert_image_interval = 2  # mianpro风格每2段插入一张图片
                
                # 插入图片
                if image_index < len(images) and (i + 1) % insert_image_interval == 0:
                    html_content.append(f'<img src="{images[image_index]}" alt="配图" />')
                    image_index += 1
            
            # 如果还有剩余图片，在末尾添加
            while image_index < len(images):
                html_content.append(f'<img src="{images[image_index]}" alt="配图" />')
                image_index += 1
            
            # 选择模板样式
            css_styles = self._get_template_css(template_style)
            
            # 生成完整的HTML
            html_template = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        {css_styles}
    </style>
</head>
<body>
    <div class="article">
        <h1>{title}</h1>
        {''.join(html_content)}
        
        <div class="cta">
            💡 觉得有用请点赞转发，让更多人看到！
        </div>
        
        <div class="footer">
            本文由文章笔记生成器自动生成
        </div>
    </div>
</body>
</html>
            """
            
            return html_template
        except Exception as e:
            print(f"⚠️ 生成微信公众号HTML失败: {str(e)}")
            return ""
            
    def _get_template_css(self, template_style: str) -> str:
        """根据模板风格返回对应的CSS样式
        
        Args:
            template_style: 模板风格，可选值:
                - default: 基础模板，简洁大方
                - modern: 现代风格模板，适合科技类文章
                - tech: 技术专栏模板，适合深度技术文章
                - mianpro: 由kilimro贡献的模板
                - lapis: 蓝宝石主题，优雅简洁
                - maize: 玉米黄主题，温暖活泼
                - orangeheart: 橙心主题，热情洋溢
                - phycat: 物理猫主题，清新自然
                - pie: 派主题，简约现代
                - purple: 紫色主题，高贵典雅
                - rainbow: 彩虹主题，缤纷多彩
            
        Returns:
            str: CSS样式代码
        """
        # 默认样式 (简洁大方)
        if template_style == "default":
            return """
        body {
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            color: #333;
            background-color: #f8f9fa;
        }
        
        .article {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        h1 {
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
            text-align: center;
            margin-bottom: 30px;
            line-height: 1.4;
        }
        
        h2 {
            font-size: 20px;
            font-weight: bold;
            color: #34495e;
            margin: 30px 0 15px 0;
            padding-left: 10px;
            border-left: 4px solid #3498db;
        }
        
        h3 {
            font-size: 18px;
            font-weight: bold;
            color: #34495e;
            margin: 25px 0 12px 0;
        }
        
        p {
            margin: 15px 0;
            text-align: justify;
            font-size: 16px;
        }
        
        strong {
            color: #e74c3c;
            font-weight: bold;
        }
        
        img {
            width: 100%;
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            margin: 25px 0;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
        
        .cta {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 25px;
            text-align: center;
            margin: 30px 0;
            font-weight: bold;
        }
        
        @media (max-width: 480px) {
            body {
                padding: 10px;
            }
            
            .article {
                padding: 20px;
            }
            
            h1 {
                font-size: 20px;
            }
            
            h2 {
                font-size: 18px;
            }
            
            p {
                font-size: 15px;
            }
        }
        """
        
        # 现代风格 (适合科技类文章)
        elif template_style == "modern":
            return """
        body {
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            color: #2d3436;
            background-color: #f7f9fc;
        }
        
        .article {
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.08);
        }
        
        h1 {
            font-size: 28px;
            font-weight: 700;
            color: #0984e3;
            text-align: center;
            margin-bottom: 35px;
            line-height: 1.4;
            letter-spacing: -0.5px;
        }
        
        h2 {
            font-size: 22px;
            font-weight: 600;
            color: #2d3436;
            margin: 35px 0 20px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #dfe6e9;
        }
        
        h3 {
            font-size: 20px;
            font-weight: 600;
            color: #2d3436;
            margin: 30px 0 15px 0;
        }
        
        p {
            margin: 18px 0;
            text-align: justify;
            font-size: 16px;
            line-height: 1.9;
        }
        
        strong {
            color: #0984e3;
            font-weight: 600;
            background-color: rgba(9, 132, 227, 0.08);
            padding: 2px 5px;
            border-radius: 3px;
        }
        
        img {
            width: 100%;
            max-width: 100%;
            height: auto;
            border-radius: 10px;
            margin: 30px 0;
            box-shadow: 0 8px 25px rgba(0,0,0,0.1);
        }
        
        .cover-image {
            margin: -40px -40px 40px -40px;
        }
        
        .cover-image img {
            border-radius: 12px 12px 0 0;
            margin: 0;
            box-shadow: none;
        }
        
        .footer {
            margin-top: 50px;
            padding-top: 25px;
            border-top: 1px solid #dfe6e9;
            text-align: center;
            color: #636e72;
            font-size: 14px;
        }
        
        .cta {
            background: linear-gradient(135deg, #0984e3 0%, #6c5ce7 100%);
            color: white;
            padding: 18px 30px;
            border-radius: 30px;
            text-align: center;
            margin: 40px 0;
            font-weight: 600;
            box-shadow: 0 8px 15px rgba(9, 132, 227, 0.2);
        }
        
        @media (max-width: 480px) {
            body {
                padding: 10px;
            }
            
            .article {
                padding: 25px;
            }
            
            .cover-image {
                margin: -25px -25px 25px -25px;
            }
            
            h1 {
                font-size: 22px;
            }
            
            h2 {
                font-size: 20px;
            }
            
            p {
                font-size: 15px;
            }
        }
        """
        
        # 技术专栏风格 (适合深度技术文章)
        elif template_style == "tech":
            return """
        body {
            max-width: 750px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            color: #24292e;
            background-color: #f6f8fa;
        }
        
        .article {
            background: white;
            padding: 40px;
            border-radius: 5px;
            box-shadow: 0 1px 5px rgba(27,31,35,0.15);
        }
        
        h1 {
            font-size: 26px;
            font-weight: 600;
            color: #24292e;
            text-align: left;
            margin-bottom: 25px;
            line-height: 1.4;
            padding-bottom: 12px;
            border-bottom: 1px solid #eaecef;
        }
        
        h2 {
            font-size: 20px;
            font-weight: 600;
            color: #24292e;
            margin: 35px 0 16px 0;
            padding-bottom: 8px;
            border-bottom: 1px solid #eaecef;
        }
        
        h3 {
            font-size: 18px;
            font-weight: 600;
            color: #24292e;
            margin: 25px 0 12px 0;
        }
        
        p {
            margin: 16px 0;
            text-align: left;
            font-size: 16px;
            line-height: 1.7;
        }
        
        strong {
            color: #24292e;
            font-weight: 600;
            background-color: #f1f8ff;
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        img {
            width: 100%;
            max-width: 100%;
            height: auto;
            border: 1px solid #eaecef;
            border-radius: 3px;
            margin: 20px 0;
        }
        
        .cover-image {
            margin: -40px -40px 30px -40px;
        }
        
        .cover-image img {
            border-radius: 5px 5px 0 0;
            border: none;
            border-bottom: 1px solid #eaecef;
            margin: 0;
        }
        
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eaecef;
            text-align: center;
            color: #6a737d;
            font-size: 14px;
        }
        
        .cta {
            background-color: #0366d6;
            color: white;
            padding: 16px 24px;
            border-radius: 6px;
            text-align: center;
            margin: 30px 0;
            font-weight: 500;
        }
        
        code {
            font-family: SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace;
            background-color: #f6f8fa;
            padding: 3px 6px;
            border-radius: 3px;
            font-size: 85%;
        }
        
        @media (max-width: 480px) {
            body {
                padding: 10px;
            }
            
            .article {
                padding: 20px;
            }
            
            .cover-image {
                margin: -20px -20px 20px -20px;
            }
            
            h1 {
                font-size: 22px;
            }
            
            h2 {
                font-size: 18px;
            }
            
            p {
                font-size: 15px;
            }
        }
        """
        
        # mianpro风格 (由kilimro贡献的模板)
        elif template_style == "mianpro":
            return """
        body {
            max-width: 650px;
            margin: 0 auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.8;
            color: #333;
            background-color: #fafafa;
        }
        
        .article {
            background: white;
            padding: 35px;
            border-radius: 16px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.05);
        }
        
        h1 {
            font-size: 26px;
            font-weight: bold;
            color: #333;
            text-align: center;
            margin-bottom: 30px;
            line-height: 1.5;
            position: relative;
            padding-bottom: 15px;
        }
        
        h1:after {
            content: "";
            position: absolute;
            bottom: 0;
            left: 50%;
            transform: translateX(-50%);
            width: 60px;
            height: 3px;
            background: linear-gradient(90deg, #ff6b6b, #ff8e8e);
            border-radius: 3px;
        }
        
        h2 {
            font-size: 22px;
            font-weight: bold;
            color: #333;
            margin: 35px 0 18px 0;
            padding-left: 12px;
            border-left: 4px solid #ff6b6b;
        }
        
        h3 {
            font-size: 20px;
            font-weight: bold;
            color: #333;
            margin: 28px 0 15px 0;
        }
        
        p {
            margin: 16px 0;
            text-align: justify;
            font-size: 16px;
            line-height: 2;
            letter-spacing: 0.5px;
        }
        
        strong {
            color: #ff6b6b;
            font-weight: bold;
        }
        
        img {
            width: 100%;
            max-width: 100%;
            height: auto;
            border-radius: 12px;
            margin: 25px 0;
            box-shadow: 0 8px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        
        img:hover {
            transform: scale(1.02);
        }
        
        .footer {
            margin-top: 45px;
            padding-top: 22px;
            border-top: 1px dashed #ddd;
            text-align: center;
            color: #888;
            font-size: 14px;
        }
        
        .cta {
            background: linear-gradient(135deg, #ff6b6b 0%, #ffa0a0 100%);
            color: white;
            padding: 18px 28px;
            border-radius: 50px;
            text-align: center;
            margin: 35px 0;
            font-weight: bold;
            box-shadow: 0 8px 15px rgba(255, 107, 107, 0.2);
        }
        
        @media (max-width: 480px) {
            body {
                padding: 12px;
            }
            
            .article {
                padding: 25px;
            }
            
            h1 {
                font-size: 22px;
            }
            
            h2 {
                font-size: 20px;
            }
            
            p {
                font-size: 15px;
            }
        }
        """
        
        # 彩虹主题 (rainbow)
        elif template_style == "rainbow":
            return """
        :root {
            --text-color: #40464f;
            --primary-color: #5677fc;
            --bg-color: #ffffff;
            --marker-color: #a2b6d4;
            --source-color: #a8a8a9;
            --header-span-color: var(--primary-color);
            --block-bg-color: #f6f8fa;
        }
        body {
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.75;
            font-size: 16px;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: var(--bg-color);
        }
        .article {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        p, pre {
            margin: 1em 0.8em;
        }
        strong {
            color: var(--primary-color);
        }
        a {
            word-wrap: break-word;
            color: var(--primary-color);
            text-decoration: none;
        }
        h4, h5, h6 {
            font-weight: normal;
        }
        h1, h2, h3, h4, h5, h6 {
            padding: 0px;
            margin: 1.2em 0 1em;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
            color: #e74c3c;
        }
        h2 {
            padding: 1px 12.5px;
            border-radius: 4px;
            display: inline-block;
            font-size: 1.3em;
            background: linear-gradient(90deg, #e74c3c, #f39c12, #f1c40f, #2ecc71, #3498db, #9b59b6);
            color: var(--bg-color);
            background-size: 600% 600%;
            animation: rainbow 6s ease infinite;
        }
        @keyframes rainbow {
            0%{background-position:0% 50%}
            50%{background-position:100% 50%}
            100%{background-position:0% 50%}
        }
        h3 {
            font-size: 1.3em;
            color: #3498db;
        }
        h4 {
            font-size: 1.2em;
            color: #2ecc71;
        }
        h5 {
            font-size: 1.2em;
            color: #f39c12;
        }
        h6 {
            font-size: 1.2em;
            color: #9b59b6;
        }
        ul {
            list-style-type: disc;
        }
        em {
            padding: 0 3px 0 0;
        }
        ul ul {
            list-style-type: square;
        }
        ol {
            list-style-type: decimal;
        }
        blockquote {
            display: block;
            font-size: 0.9em;
            border-left: 3px solid #3498db;
            padding: 0.5em 1em;
            margin: 0;
            background: var(--block-bg-color);
        }
        p code {
            color: #e74c3c;
            font-size: 0.9em;
            font-weight: normal;
            word-wrap: break-word;
            padding: 2px 4px 2px;
            border-radius: 3px;
            margin: 2px;
            background-color: var(--block-bg-color);
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            word-break: break-all;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 0 auto;
            display: block;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        table {
            display: table;
            text-align: justify;
            overflow-x: auto;
            border-collapse: collapse;
            margin: 1.4em auto;
            max-width: 100%;
            table-layout: fixed;
            text-align: left;
            overflow: auto;
            word-wrap: break-word;
            word-break: break-all;
        }
        table th, table td {
            border: 1px solid #d9dfe4;
            padding: 9px 12px;
            font-size: 0.75em;
            line-height: 22px;
            vertical-align: top;
        }
        table th {
            text-align: center;
            font-weight: bold;
            color: #3498db;
            background: #f7f7f7;
        }
        hr {
            margin-top: 20px;
            margin-bottom: 20px;
            border: 0;
            border-top: 2px solid #eef2f5;
            border-radius: 2px;
        }
        .cta {
            background: linear-gradient(90deg, #e74c3c, #f39c12, #f1c40f, #2ecc71, #3498db, #9b59b6);
            background-size: 600% 600%;
            animation: rainbow 6s ease infinite;
            color: white;
            padding: 15px 25px;
            border-radius: 25px;
            text-align: center;
            margin: 30px 0;
            font-weight: bold;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
        """
        
        # 紫色主题 (purple)
        elif template_style == "purple":
            return """
        :root {
            --text-color: #40464f;
            --primary-color: #9966cc;
            --bg-color: #ffffff;
            --marker-color: #c8a9e5;
            --source-color: #a8a8a9;
            --header-span-color: var(--primary-color);
            --block-bg-color: #f9f4ff;
        }
        body {
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.75;
            font-size: 16px;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: var(--bg-color);
        }
        .article {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        p, pre {
            margin: 1em 0.8em;
        }
        strong {
            color: var(--primary-color);
        }
        a {
            word-wrap: break-word;
            color: var(--primary-color);
            text-decoration: none;
        }
        h4, h5, h6 {
            font-weight: normal;
        }
        h1, h2, h3, h4, h5, h6 {
            padding: 0px;
            color: var(--primary-color);
            margin: 1.2em 0 1em;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
        }
        h2 {
            padding: 1px 12.5px;
            border-radius: 4px;
            display: inline-block;
            font-size: 1.3em;
            background-color: var(--header-span-color);
            color: var(--bg-color);
        }
        h3 {
            font-size: 1.3em;
        }
        h4 {
            font-size: 1.2em;
        }
        h5 {
            font-size: 1.2em;
        }
        h6 {
            font-size: 1.2em;
        }
        ul {
            list-style-type: disc;
        }
        em {
            padding: 0 3px 0 0;
        }
        ul ul {
            list-style-type: square;
        }
        ol {
            list-style-type: decimal;
        }
        blockquote {
            display: block;
            font-size: 0.9em;
            border-left: 3px solid var(--primary-color);
            padding: 0.5em 1em;
            margin: 0;
            background: var(--block-bg-color);
        }
        p code {
            color: var(--primary-color);
            font-size: 0.9em;
            font-weight: normal;
            word-wrap: break-word;
            padding: 2px 4px 2px;
            border-radius: 3px;
            margin: 2px;
            background-color: var(--block-bg-color);
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            word-break: break-all;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 0 auto;
            display: block;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        table {
            display: table;
            text-align: justify;
            overflow-x: auto;
            border-collapse: collapse;
            margin: 1.4em auto;
            max-width: 100%;
            table-layout: fixed;
            text-align: left;
            overflow: auto;
            word-wrap: break-word;
            word-break: break-all;
        }
        table th, table td {
            border: 1px solid #d9dfe4;
            padding: 9px 12px;
            font-size: 0.75em;
            line-height: 22px;
            vertical-align: top;
        }
        table th {
            text-align: center;
            font-weight: bold;
            color: var(--primary-color);
            background: #f7f7f7;
        }
        hr {
            margin-top: 20px;
            margin-bottom: 20px;
            border: 0;
            border-top: 2px solid #eef2f5;
            border-radius: 2px;
        }
        .cta {
            background: linear-gradient(135deg, #9966cc 0%, #c8a9e5 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 25px;
            text-align: center;
            margin: 30px 0;
            font-weight: bold;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
        """
        
        # 派主题 (pie)
        elif template_style == "pie":
            return """
        :root {
            --text-color: #40464f;
            --primary-color: #8076a3;
            --bg-color: #ffffff;
            --marker-color: #c0b8d6;
            --source-color: #a8a8a9;
            --header-span-color: var(--primary-color);
            --block-bg-color: #f7f5fa;
        }
        body {
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.75;
            font-size: 16px;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: var(--bg-color);
        }
        .article {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        p, pre {
            margin: 1em 0.8em;
        }
        strong {
            color: var(--primary-color);
        }
        a {
            word-wrap: break-word;
            color: var(--primary-color);
            text-decoration: none;
        }
        h4, h5, h6 {
            font-weight: normal;
        }
        h1, h2, h3, h4, h5, h6 {
            padding: 0px;
            color: var(--primary-color);
            margin: 1.2em 0 1em;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
        }
        h2 {
            padding: 1px 12.5px;
            border-radius: 4px;
            display: inline-block;
            font-size: 1.3em;
            background-color: var(--header-span-color);
            color: var(--bg-color);
        }
        h3 {
            font-size: 1.3em;
        }
        h4 {
            font-size: 1.2em;
        }
        h5 {
            font-size: 1.2em;
        }
        h6 {
            font-size: 1.2em;
        }
        ul {
            list-style-type: disc;
        }
        em {
            padding: 0 3px 0 0;
        }
        ul ul {
            list-style-type: square;
        }
        ol {
            list-style-type: decimal;
        }
        blockquote {
            display: block;
            font-size: 0.9em;
            border-left: 3px solid var(--primary-color);
            padding: 0.5em 1em;
            margin: 0;
            background: var(--block-bg-color);
        }
        p code {
            color: var(--primary-color);
            font-size: 0.9em;
            font-weight: normal;
            word-wrap: break-word;
            padding: 2px 4px 2px;
            border-radius: 3px;
            margin: 2px;
            background-color: var(--block-bg-color);
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            word-break: break-all;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 0 auto;
            display: block;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        table {
            display: table;
            text-align: justify;
            overflow-x: auto;
            border-collapse: collapse;
            margin: 1.4em auto;
            max-width: 100%;
            table-layout: fixed;
            text-align: left;
            overflow: auto;
            word-wrap: break-word;
            word-break: break-all;
        }
        table th, table td {
            border: 1px solid #d9dfe4;
            padding: 9px 12px;
            font-size: 0.75em;
            line-height: 22px;
            vertical-align: top;
        }
        table th {
            text-align: center;
            font-weight: bold;
            color: var(--primary-color);
            background: #f7f7f7;
        }
        hr {
            margin-top: 20px;
            margin-bottom: 20px;
            border: 0;
            border-top: 2px solid #eef2f5;
            border-radius: 2px;
        }
        .cta {
            background: linear-gradient(135deg, #8076a3 0%, #c0b8d6 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 25px;
            text-align: center;
            margin: 30px 0;
            font-weight: bold;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
        """
        
        # 物理猫主题 (phycat)
        elif template_style == "phycat":
            return """
        :root {
            --text-color: #40464f;
            --primary-color: #00a6ac;
            --bg-color: #ffffff;
            --marker-color: #7fd4d8;
            --source-color: #a8a8a9;
            --header-span-color: var(--primary-color);
            --block-bg-color: #f0fafb;
        }
        body {
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.75;
            font-size: 16px;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: var(--bg-color);
        }
        .article {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        p, pre {
            margin: 1em 0.8em;
        }
        strong {
            color: var(--primary-color);
        }
        a {
            word-wrap: break-word;
            color: var(--primary-color);
            text-decoration: none;
        }
        h4, h5, h6 {
            font-weight: normal;
        }
        h1, h2, h3, h4, h5, h6 {
            padding: 0px;
            color: var(--primary-color);
            margin: 1.2em 0 1em;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
        }
        h2 {
            padding: 1px 12.5px;
            border-radius: 4px;
            display: inline-block;
            font-size: 1.3em;
            background-color: var(--header-span-color);
            color: var(--bg-color);
        }
        h3 {
            font-size: 1.3em;
        }
        h4 {
            font-size: 1.2em;
        }
        h5 {
            font-size: 1.2em;
        }
        h6 {
            font-size: 1.2em;
        }
        ul {
            list-style-type: disc;
        }
        em {
            padding: 0 3px 0 0;
        }
        ul ul {
            list-style-type: square;
        }
        ol {
            list-style-type: decimal;
        }
        blockquote {
            display: block;
            font-size: 0.9em;
            border-left: 3px solid var(--primary-color);
            padding: 0.5em 1em;
            margin: 0;
            background: var(--block-bg-color);
        }
        p code {
            color: var(--primary-color);
            font-size: 0.9em;
            font-weight: normal;
            word-wrap: break-word;
            padding: 2px 4px 2px;
            border-radius: 3px;
            margin: 2px;
            background-color: var(--block-bg-color);
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            word-break: break-all;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 0 auto;
            display: block;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        table {
            display: table;
            text-align: justify;
            overflow-x: auto;
            border-collapse: collapse;
            margin: 1.4em auto;
            max-width: 100%;
            table-layout: fixed;
            text-align: left;
            overflow: auto;
            word-wrap: break-word;
            word-break: break-all;
        }
        table th, table td {
            border: 1px solid #d9dfe4;
            padding: 9px 12px;
            font-size: 0.75em;
            line-height: 22px;
            vertical-align: top;
        }
        table th {
            text-align: center;
            font-weight: bold;
            color: var(--primary-color);
            background: #f7f7f7;
        }
        hr {
            margin-top: 20px;
            margin-bottom: 20px;
            border: 0;
            border-top: 2px solid #eef2f5;
            border-radius: 2px;
        }
        .cta {
            background: linear-gradient(135deg, #00a6ac 0%, #7fd4d8 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 25px;
            text-align: center;
            margin: 30px 0;
            font-weight: bold;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
        """
        
        # 橙心主题 (orangeheart)
        elif template_style == "orangeheart":
            return """
        :root {
            --text-color: #40464f;
            --primary-color: #ff6b35;
            --bg-color: #ffffff;
            --marker-color: #ffaa8a;
            --source-color: #a8a8a9;
            --header-span-color: var(--primary-color);
            --block-bg-color: #fff5f0;
        }
        body {
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.75;
            font-size: 16px;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: var(--bg-color);
        }
        .article {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        p, pre {
            margin: 1em 0.8em;
        }
        strong {
            color: var(--primary-color);
        }
        a {
            word-wrap: break-word;
            color: var(--primary-color);
            text-decoration: none;
        }
        h4, h5, h6 {
            font-weight: normal;
        }
        h1, h2, h3, h4, h5, h6 {
            padding: 0px;
            color: var(--primary-color);
            margin: 1.2em 0 1em;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
        }
        h2 {
            padding: 1px 12.5px;
            border-radius: 4px;
            display: inline-block;
            font-size: 1.3em;
            background-color: var(--header-span-color);
            color: var(--bg-color);
        }
        h3 {
            font-size: 1.3em;
        }
        h4 {
            font-size: 1.2em;
        }
        h5 {
            font-size: 1.2em;
        }
        h6 {
            font-size: 1.2em;
        }
        ul {
            list-style-type: disc;
        }
        em {
            padding: 0 3px 0 0;
        }
        ul ul {
            list-style-type: square;
        }
        ol {
            list-style-type: decimal;
        }
        blockquote {
            display: block;
            font-size: 0.9em;
            border-left: 3px solid var(--primary-color);
            padding: 0.5em 1em;
            margin: 0;
            background: var(--block-bg-color);
        }
        p code {
            color: var(--primary-color);
            font-size: 0.9em;
            font-weight: normal;
            word-wrap: break-word;
            padding: 2px 4px 2px;
            border-radius: 3px;
            margin: 2px;
            background-color: var(--block-bg-color);
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            word-break: break-all;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 0 auto;
            display: block;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        table {
            display: table;
            text-align: justify;
            overflow-x: auto;
            border-collapse: collapse;
            margin: 1.4em auto;
            max-width: 100%;
            table-layout: fixed;
            text-align: left;
            overflow: auto;
            word-wrap: break-word;
            word-break: break-all;
        }
        table th, table td {
            border: 1px solid #d9dfe4;
            padding: 9px 12px;
            font-size: 0.75em;
            line-height: 22px;
            vertical-align: top;
        }
        table th {
            text-align: center;
            font-weight: bold;
            color: var(--primary-color);
            background: #f7f7f7;
        }
        hr {
            margin-top: 20px;
            margin-bottom: 20px;
            border: 0;
            border-top: 2px solid #eef2f5;
            border-radius: 2px;
        }
        .cta {
            background: linear-gradient(135deg, #ff6b35 0%, #ffaa8a 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 25px;
            text-align: center;
            margin: 30px 0;
            font-weight: bold;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
        """
        
        # 玉米黄主题 (maize)
        elif template_style == "maize":
            return """
        :root {
            --text-color: #40464f;
            --primary-color: #e6b422;
            --bg-color: #ffffff;
            --marker-color: #f5d77e;
            --source-color: #a8a8a9;
            --header-span-color: var(--primary-color);
            --block-bg-color: #fdf9e8;
        }
        body {
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.75;
            font-size: 16px;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: var(--bg-color);
        }
        .article {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        p, pre {
            margin: 1em 0.8em;
        }
        strong {
            color: var(--primary-color);
        }
        a {
            word-wrap: break-word;
            color: var(--primary-color);
            text-decoration: none;
        }
        h4, h5, h6 {
            font-weight: normal;
        }
        h1, h2, h3, h4, h5, h6 {
            padding: 0px;
            color: var(--primary-color);
            margin: 1.2em 0 1em;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
        }
        h2 {
            padding: 1px 12.5px;
            border-radius: 4px;
            display: inline-block;
            font-size: 1.3em;
            background-color: var(--header-span-color);
            color: var(--bg-color);
        }
        h3 {
            font-size: 1.3em;
        }
        h4 {
            font-size: 1.2em;
        }
        h5 {
            font-size: 1.2em;
        }
        h6 {
            font-size: 1.2em;
        }
        ul {
            list-style-type: disc;
        }
        em {
            padding: 0 3px 0 0;
        }
        ul ul {
            list-style-type: square;
        }
        ol {
            list-style-type: decimal;
        }
        blockquote {
            display: block;
            font-size: 0.9em;
            border-left: 3px solid var(--primary-color);
            padding: 0.5em 1em;
            margin: 0;
            background: var(--block-bg-color);
        }
        p code {
            color: var(--primary-color);
            font-size: 0.9em;
            font-weight: normal;
            word-wrap: break-word;
            padding: 2px 4px 2px;
            border-radius: 3px;
            margin: 2px;
            background-color: var(--block-bg-color);
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            word-break: break-all;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 0 auto;
            display: block;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        table {
            display: table;
            text-align: justify;
            overflow-x: auto;
            border-collapse: collapse;
            margin: 1.4em auto;
            max-width: 100%;
            table-layout: fixed;
            text-align: left;
            overflow: auto;
            word-wrap: break-word;
            word-break: break-all;
        }
        table th, table td {
            border: 1px solid #d9dfe4;
            padding: 9px 12px;
            font-size: 0.75em;
            line-height: 22px;
            vertical-align: top;
        }
        table th {
            text-align: center;
            font-weight: bold;
            color: var(--primary-color);
            background: #f7f7f7;
        }
        hr {
            margin-top: 20px;
            margin-bottom: 20px;
            border: 0;
            border-top: 2px solid #eef2f5;
            border-radius: 2px;
        }
        .cta {
            background: linear-gradient(135deg, #e6b422 0%, #f5d77e 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 25px;
            text-align: center;
            margin: 30px 0;
            font-weight: bold;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
        """
        
        # 蓝宝石主题 (lapis)
        elif template_style == "lapis":
            return """
        :root {
            --text-color: #40464f;
            --primary-color: #4870ac;
            --bg-color: #ffffff;
            --marker-color: #a2b6d4;
            --source-color: #a8a8a9;
            --header-span-color: var(--primary-color);
            --block-bg-color: #f6f8fa;
        }
        body {
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            line-height: 1.75;
            font-size: 16px;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: var(--bg-color);
        }
        .article {
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        p, pre {
            margin: 1em 0.8em;
        }
        strong {
            color: var(--primary-color);
        }
        a {
            word-wrap: break-word;
            color: var(--primary-color);
            text-decoration: none;
        }
        h4, h5, h6 {
            font-weight: normal;
        }
        h1, h2, h3, h4, h5, h6 {
            padding: 0px;
            color: var(--primary-color);
            margin: 1.2em 0 1em;
        }
        h1 {
            text-align: center;
            font-size: 1.5em;
        }
        h2 {
            padding: 1px 12.5px;
            border-radius: 4px;
            display: inline-block;
            font-size: 1.3em;
            background-color: var(--header-span-color);
            color: var(--bg-color);
        }
        h3 {
            font-size: 1.3em;
        }
        h4 {
            font-size: 1.2em;
        }
        h5 {
            font-size: 1.2em;
        }
        h6 {
            font-size: 1.2em;
        }
        ul {
            list-style-type: disc;
        }
        em {
            padding: 0 3px 0 0;
        }
        ul ul {
            list-style-type: square;
        }
        ol {
            list-style-type: decimal;
        }
        blockquote {
            display: block;
            font-size: 0.9em;
            border-left: 3px solid var(--primary-color);
            padding: 0.5em 1em;
            margin: 0;
            background: var(--block-bg-color);
        }
        p code {
            color: var(--primary-color);
            font-size: 0.9em;
            font-weight: normal;
            word-wrap: break-word;
            padding: 2px 4px 2px;
            border-radius: 3px;
            margin: 2px;
            background-color: var(--block-bg-color);
            font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
            word-break: break-all;
        }
        img {
            max-width: 100%;
            height: auto;
            margin: 0 auto;
            display: block;
            border-radius: 8px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        table {
            display: table;
            text-align: justify;
            overflow-x: auto;
            border-collapse: collapse;
            margin: 1.4em auto;
            max-width: 100%;
            table-layout: fixed;
            text-align: left;
            overflow: auto;
            word-wrap: break-word;
            word-break: break-all;
        }
        table th, table td {
            border: 1px solid #d9dfe4;
            padding: 9px 12px;
            font-size: 0.75em;
            line-height: 22px;
            vertical-align: top;
        }
        table th {
            text-align: center;
            font-weight: bold;
            color: var(--primary-color);
            background: #f7f7f7;
        }
        hr {
            margin-top: 20px;
            margin-bottom: 20px;
            border: 0;
            border-top: 2px solid #eef2f5;
            border-radius: 2px;
        }
        .cta {
            background: linear-gradient(135deg, #4870ac 0%, #7a9bd4 100%);
            color: white;
            padding: 15px 25px;
            border-radius: 25px;
            text-align: center;
            margin: 30px 0;
            font-weight: bold;
        }
        .footer {
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #eee;
            text-align: center;
            color: #7f8c8d;
            font-size: 14px;
        }
        """
            
        # 默认返回基础样式
        else:
            print(f"⚠️ 未知的模板风格: {template_style}，使用默认样式")
            return self._get_template_css("default")

    def _generate_notes(self, transcript: str, content_info: Dict[str, str], url: Optional[str], output_format: str = "both", wechat_template: str = "default") -> List[str]:
        """生成笔记文件的通用方法
        
        Args:
            transcript: 转录文本
            content_info: 内容信息
            url: 视频URL
            output_format: 输出格式 ("xiaohongshu", "wechat", "both")
            wechat_template: 微信公众号模板风格 ("default", "modern", "tech", "mianpro")
        """
        try:
            # 保存原始转录内容
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            original_file = os.path.join(self.output_dir, f"{timestamp}_original.md")
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write(f"# {content_info['title']}\n\n")
                f.write(f"## 内容信息\n")
                f.write(f"- 作者：{content_info['uploader']}\n")
                f.write(f"- 时长：{content_info['duration']}秒\n")
                f.write(f"- 平台：{content_info['platform']}\n")
                if url:
                    f.write(f"- 链接：{url}\n")
                f.write(f"\n## 原始转录内容\n\n")
                f.write(transcript)

            # 整理长文版本
            print("\n📝 正在整理长文版本...")
            organized_content = self._organize_long_content(transcript, content_info['duration'])
            organized_file = os.path.join(self.output_dir, f"{timestamp}_organized.md")
            with open(organized_file, 'w', encoding='utf-8') as f:
                f.write(f"# {content_info['title']} - 整理版\n\n")
                f.write(f"## 内容信息\n")
                f.write(f"- 作者：{content_info['uploader']}\n")
                f.write(f"- 时长：{content_info['duration']}秒\n")
                f.write(f"- 平台：{content_info['platform']}\n")
                if url:
                    f.write(f"- 链接：{url}\n")
                f.write(f"\n## 内容整理\n\n")
                f.write(organized_content)

            generated_files = [original_file, organized_file]

            # 根据输出格式生成相应的笔记
            if output_format in ["xiaohongshu", "both"]:
                print("\n📱 正在生成小红书版本...")
                xiaohongshu_content, titles, tags, images = self.convert_to_xiaohongshu(organized_content)
                
                # 保存小红书版本
                xiaohongshu_file = os.path.join(self.output_dir, f"{timestamp}_xiaohongshu.md")
                
                with open(xiaohongshu_file, "w", encoding="utf-8") as f:
                    if titles:
                        f.write(f"# {titles[0]}\n\n")
                    else:
                        f.write(f"# 未能生成标题\n\n")
                    
                    if images:
                        f.write(f"![封面图]({images[0]})\n\n")
                    
                    content_parts = xiaohongshu_content.split('\n\n')
                    mid_point = len(content_parts) // 2
                    
                    f.write('\n\n'.join(content_parts[:mid_point]))
                    f.write('\n\n')
                    
                    if len(images) > 1:
                        f.write(f"![配图]({images[1]})\n\n")
                    
                    f.write('\n\n'.join(content_parts[mid_point:]))
                    
                    if len(images) > 2:
                        f.write(f"\n\n![配图]({images[2]})")
                    
                    if tags:
                        f.write("\n\n---\n")
                        f.write("\n".join([f"#{tag}" for tag in tags]))

                print(f"\n✅ 小红书版本已保存至: {xiaohongshu_file}")
                generated_files.append(xiaohongshu_file)

                # 转换为HTML并打开
                if MARKDOWN_CONVERSION_AVAILABLE:
                    with open(xiaohongshu_file, 'r', encoding='utf-8') as f:
                        md_content = f.read()
                    
                    html_content = self._convert_md_to_html(md_content, titles[0] if titles else "小红书笔记")
                    
                    html_file = xiaohongshu_file.replace('.md', '.html')
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    
                    import webbrowser
                    webbrowser.open('file://' + os.path.abspath(html_file))
                    print(f"✅ HTML预览已在浏览器中打开: {html_file}")

            if output_format in ["wechat", "both"]:
                print("\n📰 正在生成微信公众号版本...")
                wechat_content, titles, images, template_style = self.convert_to_wechat(organized_content, wechat_template)
                
                # 保存微信公众号版本
                wechat_file = os.path.join(self.output_dir, f"{timestamp}_wechat.md")
                
                with open(wechat_file, "w", encoding="utf-8") as f:
                    if titles:
                        f.write(f"# {titles[0]}\n\n")
                    else:
                        f.write(f"# 未能生成标题\n\n")
                    
                    f.write(wechat_content)

                print(f"\n✅ 微信公众号版本已保存至: {wechat_file}")
                generated_files.append(wechat_file)

                # 生成微信公众号HTML版本
                if images:
                    wechat_html_content = self._generate_wechat_html(wechat_content, titles[0] if titles else "微信公众号文章", images)
                    
                    if wechat_html_content:
                        wechat_html_file = os.path.join(self.output_dir, f"{timestamp}_wechat.html")
                        with open(wechat_html_file, 'w', encoding='utf-8') as f:
                            f.write(wechat_html_content)
                        
                        import webbrowser
                        webbrowser.open('file://' + os.path.abspath(wechat_html_file))
                        print(f"✅ 微信公众号HTML预览已在浏览器中打开: {wechat_html_file}")
                        generated_files.append(wechat_html_file)

            return generated_files

        except Exception as e:
            print(f"⚠️ 生成笔记时出错: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return []

    def _get_template_description(self, template_style: str) -> str:
        """获取模板风格的描述
        
        Args:
            template_style: 模板风格
            
        Returns:
            str: 模板描述
        """
        descriptions = {
            "default": "基础模板 - 简洁大方的白底黑字风格，适合各类文章",
            "modern": "现代风格 - 时尚简约的蓝色主题，适合科技类文章",
            "tech": "技术专栏 - 类似GitHub风格的技术文档样式，适合深度技术文章",
            "mianpro": "mianpro风格 - 温暖活泼的粉红色调，适合生活类、情感类文章",
            "lapis": "蓝宝石主题 - 优雅简洁的蓝色主题，适合商务、职场类文章",
            "maize": "玉米黄主题 - 温暖活泼的黄色主题，适合美食、旅行类文章",
            "orangeheart": "橙心主题 - 热情洋溢的橙色主题，适合励志、健康类文章",
            "phycat": "物理猫主题 - 清新自然的青色主题，适合科普、教育类文章",
            "pie": "派主题 - 简约现代的紫灰主题，适合艺术、设计类文章",
            "purple": "紫色主题 - 高贵典雅的紫色主题，适合时尚、美妆类文章",
            "rainbow": "彩虹主题 - 缤纷多彩的彩虹渐变主题，适合儿童、娱乐类文章"
        }
        return descriptions.get(template_style, "未知模板风格")
    
    def process_video(self, url: str, output_format: str = "both", wechat_template: str = "default") -> List[str]:
        """处理视频链接，生成笔记
        
        Args:
            url (str): 视频链接
            output_format (str): 输出格式 ("xiaohongshu", "wechat", "both")
            wechat_template (str): 微信公众号模板风格 ("default", "modern", "tech", "mianpro", "lapis", "maize", "orangeheart", "phycat", "pie", "purple", "rainbow")
        
        Returns:
            List[str]: 生成的笔记文件路径列表
        """
        print("\n📹 正在处理视频...")
        
        # 创建临时目录
        temp_dir = os.path.join(self.output_dir, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            print("⬇️ 正在下载视频或字幕...")
            file_path, video_info, is_subtitle = self._download_video(url, temp_dir)
            if not file_path or not video_info:
                return []

            if is_subtitle:
                print("✅ 字幕下载成功，正在读取内容...")
                transcript = self._read_subtitle_file(file_path)
            else:
                print(f"✅ 音频下载成功: {video_info['title']}")
                print("\n🎙️ 正在转录音频...")
                print("正在转录音频（这可能需要几分钟）...")
                transcript = self._transcribe_audio(file_path)
            
            if not transcript:
                return []

            return self._generate_notes(transcript, video_info, url, output_format, wechat_template)
            
        except Exception as e:
            print(f"⚠️ 处理视频时出错: {str(e)}")
            return []
        
        finally:
            # 清理临时文件
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def process_markdown_file(self, input_file: str, output_format: str = "both", wechat_template: str = "default") -> None:
        """处理markdown文件，生成优化后的笔记
        
        Args:
            input_file (str): 输入的markdown文件路径
            output_format (str): 输出格式 ("xiaohongshu", "wechat", "both")
            wechat_template (str): 微信公众号模板风格 ("default", "modern", "tech", "mianpro", "lapis", "maize", "orangeheart", "phycat", "pie", "purple", "rainbow")
        """
        try:
            # 读取markdown文件
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取视频链接
            video_links = re.findall(r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|bilibili\.com/video/|douyin\.com/video/)[^\s\)]+', content)
            
            if not video_links:
                print("未在markdown文件中找到视频链接")
                return
                
            print(f"找到 {len(video_links)} 个视频链接，开始处理...\n")
            
            # 处理每个视频链接
            for i, url in enumerate(video_links, 1):
                print(f"处理第 {i}/{len(video_links)} 个视频: {url}\n")
                self.process_video(url, output_format, wechat_template)
                
        except Exception as e:
            print(f"处理markdown文件时出错: {str(e)}")
            raise

def extract_urls_from_text(text: str) -> list:
    """从文本中提取所有有效的URL"""
    url_patterns = [
        r'https?://[^\s<>\[\]"\']+[^\s<>\[\]"\'.,]',
        r'https?://[a-zA-Z0-9]+\.[a-zA-Z]{2,3}/[^\s<>\[\]"\']+',
        r'BV[a-zA-Z0-9]{10}',
        r'v\.douyin\.com/[a-zA-Z0-9]+',
    ]
    
    urls = []
    for pattern in url_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            url = match.group()
            if url.startswith('BV'):
                url = f'https://www.bilibili.com/video/{url}'
            urls.append(url)
    
    # 去重并保持顺序
    seen = set()
    return [url for url in urls if not (url in seen or seen.add(url))]

if __name__ == '__main__':
    import sys, os, re
    import argparse
    
    parser = argparse.ArgumentParser(description='文章笔记生成器')
    parser.add_argument('input', nargs='?', help='输入源：视频URL、音频文件、包含URL的文件或markdown文件')
    parser.add_argument('--format', choices=['xiaohongshu', 'wechat', 'both'], default='both',
                       help='输出格式：xiaohongshu(小红书), wechat(微信公众号), both(两种都生成)')
    parser.add_argument('--wechat-template', choices=['default', 'modern', 'tech', 'mianpro', 'lapis', 'maize', 'orangeheart', 'phycat', 'pie', 'purple', 'rainbow'], default='default',
                        help='微信公众号模板风格：default(基础模板), modern(现代风格), tech(技术专栏), mianpro(mianpro风格), lapis(蓝宝石), maize(玉米黄), orangeheart(橙心), phycat(物理猫), pie(派), purple(紫色), rainbow(彩虹)')
    parser.add_argument('--preview', action='store_true', help='仅预览markdown文件（转换为HTML并在浏览器中打开）')
    parser.add_argument('--show-templates', action='store_true', help='显示所有微信公众号模板预览')
    args = parser.parse_args()
    
    generator = ArticleNoteGenerator()
    
    # 显示模板预览
    if args.show_templates:
        try:
            preview_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'preview_templates.py')
            if os.path.exists(preview_script):
                import webbrowser
                preview_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template_preview.html')
                
                if os.path.exists(preview_file):
                    print("📝 正在打开模板预览页面...")
                    webbrowser.open('file://' + os.path.abspath(preview_file))
                    print("✅ 模板预览已在浏览器中打开")
                else:
                    print("⚠️ 模板预览文件不存在，正在生成...")
                    print("请先运行 python test_templates.py 生成模板示例")
                sys.exit(0)
            else:
                print("⚠️ 模板预览脚本不存在")
                sys.exit(1)
        except Exception as e:
            print(f"⚠️ 显示模板预览时出错: {str(e)}")
            sys.exit(1)
    
    # 检查是否提供了输入参数
    if not args.input:
        print("⚠️ 错误：请输入有效的URL、音频文件、包含URL的文件或markdown文件路径")
        print("\n使用示例：")
        print("1. 处理单个视频：")
        print("   python article_note_generator.py https://example.com/video")
        print("\n2. 处理本地音频文件：")
        print("   python article_note_generator.py /path/to/audio.mp3")
        print("\n3. 处理包含URL的文件：")
        print("   python article_note_generator.py urls.txt")
        print("\n4. 处理Markdown文件：")
        print("   python article_note_generator.py notes.md")
        print("\n5. 指定输出格式：")
        print("   python article_note_generator.py video.url --format xiaohongshu")
        print("   python article_note_generator.py video.url --format wechat")
        print("   python article_note_generator.py video.url --format both")
        print("\n6. 指定微信公众号模板风格：")
        print("   python article_note_generator.py video.url --wechat-template modern")
        print("   python article_note_generator.py video.url --wechat-template tech")
        print("   python article_note_generator.py video.url --wechat-template mianpro")
        print("\n7. 查看所有模板预览：")
        print("   python article_note_generator.py --show-templates")
        sys.exit(1)
    
    if os.path.exists(args.input):
        # 读取文件内容
        try:
            with open(args.input, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                # 尝试使用gbk编码
                with open(args.input, 'r', encoding='gbk') as f:
                    content = f.read()
            except Exception as e:
                print(f"⚠️ 无法读取文件: {str(e)}")
                sys.exit(1)
        
        # 如果是仅预览模式
        if args.preview:
            if args.input.endswith('.md'):
                if not MARKDOWN_CONVERSION_AVAILABLE:
                    print("⚠️ HTML预览功能不可用，请安装markdown库: pip install markdown")
                    sys.exit(1)
                print(f"📝 预览Markdown文件: {args.input}")
                # 提取标题（如果有的话）
                title = ''
                content_lines = content.split('\n')
                if content_lines and content_lines[0].startswith('# '):
                    title = content_lines[0][2:].strip()
                # 转换为HTML
                html_content = generator._convert_md_to_html(content, title or os.path.basename(args.input))
                # 保存HTML文件
                html_file = args.input.replace('.md', '.html')
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                # 在默认浏览器中打开
                import webbrowser
                webbrowser.open('file://' + os.path.abspath(html_file))
                print(f"✅ HTML预览已在浏览器中打开: {html_file}")
                sys.exit(0)
            else:
                print("⚠️ 预览功能仅支持Markdown文件")
                sys.exit(1)
        
        # 检查是否是音频文件
        audio_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac']
        if any(args.input.lower().endswith(ext) for ext in audio_extensions):
            print(f"🎵 处理音频文件: {args.input}")
            
            # 显示所选模板的描述
            if args.format in ["wechat", "both"]:
                template_desc = generator._get_template_description(args.wechat_template)
                print(f"📝 已选择微信公众号模板: {args.wechat_template} - {template_desc}")
                
            generator.process_local_audio(args.input, args.format, args.wechat_template)
        # 如果是markdown文件，直接处理
        elif args.input.endswith('.md'):
            print(f"📝 处理Markdown文件: {args.input}")
            
            # 显示所选模板的描述
            if args.format in ["wechat", "both"]:
                template_desc = generator._get_template_description(args.wechat_template)
                print(f"📝 已选择微信公众号模板: {args.wechat_template} - {template_desc}")
                
            generator.process_markdown_file(args.input, args.format, args.wechat_template)
        else:
            # 从文件内容中提取URL
            urls = extract_urls_from_text(content)
            
            if not urls:
                print("⚠️ 未在文件中找到有效的URL")
                sys.exit(1)
            
            print(f"📋 从文件中找到 {len(urls)} 个URL:")
            for i, url in enumerate(urls, 1):
                print(f"  {i}. {url}")
            
            print("\n开始处理URL...")
            for i, url in enumerate(urls, 1):
                print(f"\n处理第 {i}/{len(urls)} 个URL: {url}")
                try:
                    generator.process_video(url, args.format, args.wechat_template)
                except Exception as e:
                    print(f"⚠️ 处理URL时出错：{str(e)}")
                    continue
    else:
        # 检查是否是有效的URL
        if not args.input.startswith(('http://', 'https://')):
            print("⚠️ 错误：请输入有效的URL、音频文件、包含URL的文件或markdown文件路径")
            print("\n使用示例：")
            print("1. 处理单个视频：")
            print("   python article_note_generator.py https://example.com/video")
            print("\n2. 处理本地音频文件：")
            print("   python article_note_generator.py /path/to/audio.mp3")
            print("\n3. 处理包含URL的文件：")
            print("   python article_note_generator.py urls.txt")
            print("\n4. 处理Markdown文件：")
            print("   python article_note_generator.py notes.md")
            print("\n5. 指定输出格式：")
            print("   python article_note_generator.py video.url --format xiaohongshu")
            print("   python article_note_generator.py video.url --format wechat")
            print("   python article_note_generator.py video.url --format both")
            print("\n6. 指定微信公众号模板风格：")
            print("   python article_note_generator.py video.url --wechat-template modern")
            print("   python article_note_generator.py video.url --wechat-template tech")
            print("   python article_note_generator.py video.url --wechat-template mianpro")
            print("   python article_note_generator.py video.url --wechat-template lapis")
            print("   python article_note_generator.py video.url --wechat-template rainbow")
            print("   # 更多模板: maize, orangeheart, phycat, pie, purple")
            print("\n7. 查看所有模板预览：")
            print("   python article_note_generator.py --show-templates")
            sys.exit(1)
        
        # 处理单个URL
        try:
            print(f"🎥 处理视频URL: {args.input}")
            
            # 显示所选模板的描述
            if args.format in ["wechat", "both"]:
                template_desc = generator._get_template_description(args.wechat_template)
                print(f"📝 已选择微信公众号模板: {args.wechat_template} - {template_desc}")
                
            file_paths = generator.process_video(args.input, args.format, args.wechat_template)
        except Exception as e:
            print(f"⚠️ 处理URL时出错：{str(e)}")
            sys.exit(1)