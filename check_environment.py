#!/usr/bin/env python3
import sys
import subprocess
import os
from pathlib import Path
import platform

# 使用现代的 importlib.metadata 替代已弃用的 pkg_resources
try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    # Python < 3.8 的后备方案
    from importlib_metadata import version, PackageNotFoundError

def check_python_version():
    print("\n检查 Python 版本...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 版本过低。需要 Python 3.8 或更高版本")
        print(f"当前版本: Python {version.major}.{version.minor}.{version.micro}")
        return False
    print(f"✅ Python 版本符合要求: {version.major}.{version.minor}.{version.micro}")
    return True

def check_ffmpeg():
    print("\n检查 FFmpeg...")
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE)
        if result.returncode == 0:
            print("✅ FFmpeg 已安装")
            return True
        else:
            print("❌ FFmpeg 未安装或无法访问")
            return False
    except FileNotFoundError:
        print("❌ FFmpeg 未安装或未添加到系统路径")
        if platform.system() == "Darwin":
            print("建议使用 Homebrew 安装: brew install ffmpeg")
        elif platform.system() == "Windows":
            print("请从 https://ffmpeg.org/download.html 下载并添加到系统环境变量")
        else:
            print("请使用包管理器安装，如: sudo apt install ffmpeg")
        return False

def check_dependencies():
    print("\n检查 Python 依赖...")
    required = {}
    try:
        with open('requirements.txt', 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    # 处理包名和版本要求
                    parts = line.strip().split('>=')
                    if len(parts) == 2:
                        required[parts[0]] = parts[1]
                    else:
                        required[line.strip()] = None
    except FileNotFoundError:
        print("❌ 未找到 requirements.txt 文件")
        return False

    all_satisfied = True
    for package, required_version in required.items():
        try:
            installed_version = version(package)
            if required_version:
                # 简单的版本比较（对于大多数情况足够）
                try:
                    from packaging.version import parse as parse_version
                    if parse_version(installed_version) < parse_version(required_version):
                        print(f"❌ {package} 版本过低 (当前: {installed_version}, 需要: >={required_version})")
                        all_satisfied = False
                    else:
                        print(f"✅ {package} 已安装 (版本: {installed_version})")
                except ImportError:
                    # 如果 packaging 不可用，跳过版本比较
                    print(f"✅ {package} 已安装 (版本: {installed_version}) - 跳过版本检查")
            else:
                print(f"✅ {package} 已安装 (版本: {installed_version})")
        except PackageNotFoundError:
            print(f"❌ 缺少依赖: {package}")
            all_satisfied = False

    return all_satisfied

def check_env_file():
    print("\n检查环境变量配置...")
    env_example = Path('.env.example')
    env_file = Path('.env')
    
    if not env_example.exists():
        print("❌ 未找到 .env.example 文件")
        return False
    
    if not env_file.exists():
        print("❌ 未找到 .env 文件，请复制 .env.example 并配置")
        return False
    
    required_vars = [
        'OPENROUTER_API_KEY',
        'UNSPLASH_ACCESS_KEY',
    ]
    
    missing_vars = []
    with open(env_file, 'r') as f:
        env_content = f.read()
        for var in required_vars:
            if var not in env_content or f"{var}=your-" in env_content:
                missing_vars.append(var)
    
    if missing_vars:
        print("❌ 以下环境变量未正确配置:")
        for var in missing_vars:
            print(f"  - {var}")
        return False
    
    print("✅ 环境变量文件存在并包含必要配置")
    return True

def main():
    print("=== 文章笔记生成器环境检查 ===")
    
    checks = [
        ("Python 版本", check_python_version),
        ("FFmpeg", check_ffmpeg),
        ("Python 依赖", check_dependencies),
        ("环境变量", check_env_file)
    ]
    
    all_passed = True
    for name, check in checks:
        if not check():
            all_passed = False
    
    print("\n=== 检查结果 ===")
    if all_passed:
        print("✅ 所有检查通过！可以开始使用文章笔记生成器了。")
        print("💡 支持生成小红书笔记和微信公众号文章两种格式")
    else:
        print("❌ 存在一些问题需要解决。请根据上述提示进行修复。")

if __name__ == '__main__':
    main()
