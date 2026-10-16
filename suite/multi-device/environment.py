"""Read-only desktop prerequisites; never downloads tools or accesses a phone."""
from __future__ import annotations

import re
import shutil
import sys

import intake


def inspect():
    checks = []

    def add(name, ready, detail, required=True):
        checks.append(dict(name=name, ready=bool(ready), detail=detail, required=required))

    add('Python', sys.version_info >= (3, 11), '.'.join(map(str, sys.version_info[:3])))
    try:
        import tkinter
        add('Tk', tkinter.TkVersion >= 8.6, str(tkinter.TkVersion))
    except ImportError:
        add('Tk', False, '需要带 Tk 8.6+ 的 Python')
    add('运行平台', sys.platform in ('darwin', 'linux'),
        'macOS / Linux；Windows 请使用带图形支持的 WSL2' if sys.platform == 'win32' else sys.platform)
    java = shutil.which('java')
    try:
        text = intake._run([java, '-version'], timeout=10) if java else ''
        match = re.search(r'version\s+"(?:1\.)?(\d+)', text)
        add('Java', match and int(match[1]) >= 17, text.splitlines()[0] if text else '缺少 JDK 17+')
    except (OSError, ValueError):
        add('Java', False, '无法运行 java；需要 JDK 17+')
    for name in ('aapt2', 'apksigner'):
        tool = intake._tool(name)
        try:
            result = intake._run([tool, 'version'], timeout=10) if tool else ''
            add(name, bool(result.strip()), tool or '缺少 Android SDK build-tools')
        except (OSError, ValueError):
            add(name, False, '工具无法运行；检查 SDK 与 Java 版本是否匹配')
    for name in ('payload-dumper-go', 'fsck.erofs'):
        tool = intake._tool(name) or shutil.which('/opt/homebrew/bin/' + name)
        add(name, tool is not None, tool or '完整 OTA 解包才需要；已解包目录 / 单 APK 导入不需要', False)
    return dict(ready=all(c['ready'] for c in checks if c['required']), checks=checks)


def format_report(result):
    lines = ['环境检查通过' if result['ready'] else '环境尚未就绪，请补齐以下必需项']
    for item in result['checks']:
        state = '可用' if item['ready'] else '缺少或不兼容' if item['required'] else '未安装（可选）'
        lines.append('{}：{} · {}'.format(item['name'], state, item['detail']))
    lines.extend(['', '工具不会自动下载依赖或接受许可。安装方式见“使用教程”。',
                  '环境通过只证明工具可运行；材料仍须单独分析并检查兼容性。'])
    return '\n'.join(lines)
