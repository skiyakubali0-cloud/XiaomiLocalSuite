"""Local signing dialog for the existing unified-plugin builder; no device access."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, ttk
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BUILD_FAILED = '插件构建失败，请检查本机 SDK、锁定依赖及签名输入。'
PREPARE_FAILED = '依赖准备失败，请检查网络及锁定依赖；未下载 SDK 或接受许可。'


def _run(command, source_root, env, failure):
    try:
        subprocess.run(command, cwd=source_root, env=env, capture_output=True, check=True)
    except (OSError, subprocess.SubprocessError):
        # Tools may echo passwords or private paths. Never relay their output.
        raise ValueError(failure) from None


def run_build(source_root, keystore, alias, storepassword, keypassword, sdk, depsdir):
    """Return the new APK Path only after checking its paired build evidence."""
    try:
        source_root = Path(source_root).expanduser().resolve()
        unified = (source_root / 'suite/unified-api102').resolve()
        build = unified / 'build'
        if not unified.is_relative_to(source_root) or build.is_symlink():
            raise ValueError(BUILD_FAILED)
        keystore = Path(keystore).expanduser().resolve()
        if not keystore.is_file() or not all((alias.strip(), storepassword, keypassword, sdk, depsdir)):
            raise ValueError(BUILD_FAILED)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output = build / ('unified-' + stamp + '-' + uuid4().hex + '.apk')
        evidence = output.with_suffix('.build-evidence.json')
        if any(path.exists() or path.is_symlink() for path in (output, evidence)):
            raise ValueError(BUILD_FAILED)
        env = os.environ.copy()
        env['SUITE_STORE_PASSWORD'] = storepassword
        env['SUITE_KEY_PASSWORD'] = keypassword
        _run([sys.executable, '-B', str(unified / 'build_apk.py'), '--wallet-selectable',
              '--sdk', str(Path(sdk).expanduser().resolve()),
              '--deps-dir', str(Path(depsdir).expanduser().resolve()),
              '--keystore', str(keystore), '--key-alias', alias, '--output', str(output)],
             source_root, env, BUILD_FAILED)
        if any(path.is_symlink() or not path.is_file() for path in (output, evidence)):
            raise ValueError(BUILD_FAILED)
        report = json.loads(evidence.read_text(encoding='utf-8'))
        if (not isinstance(report, dict) or report.get('apk') != str(output.relative_to(unified))
                or report.get('apk_sha256') != hashlib.sha256(output.read_bytes()).hexdigest()):
            raise ValueError(BUILD_FAILED)
        return output
    except (OSError, ValueError):
        raise ValueError(BUILD_FAILED) from None


def prepare_dependencies(source_root=ROOT):
    """Explicit network action: use both existing pinned-dependency downloaders."""
    source_root = Path(source_root).expanduser().resolve()
    env = os.environ.copy()
    env.pop('SUITE_STORE_PASSWORD', None)
    env.pop('SUITE_KEY_PASSWORD', None)
    for script in ('suite/unified-api102/fetch_dependencies.py', 'tools/recipe_tools.py'):
        _run([sys.executable, '-B', str(source_root / script), '--download'],
             source_root, env, PREPARE_FAILED)
    return '依赖准备完成：3 个 libxposed AAR 与 4 个预警 DEX JAR 已校验。请重新打开构建窗口；SDK 需自行准备。'


def open_dialog(app, on_built):
    """Open a dialog; on_built receives the verified APK Path on the GUI thread."""
    window = tk.Toplevel(app.root)
    window.title('本地构建统一插件')
    window.transient(app.root)
    window.grab_set()
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill='both', expand=True)
    frame.columnconfigure(1, weight=1)
    fields = [
        ('现有签名密钥库', '', 'file'),
        ('密钥别名', '', None),
        ('密钥库密码', '', 'password'),
        ('密钥密码', '', 'password'),
        ('Android SDK', os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME', ''), 'directory'),
        ('离线 AAR 目录', str(ROOT / 'suite/unified-api102/build/deps'), 'directory'),
    ]
    variables = []

    def choose(variable, kind):
        picker = filedialog.askopenfilename if kind == 'file' else filedialog.askdirectory
        selected = picker(parent=window, title='选择现有文件' if kind == 'file' else '选择目录')
        if selected:
            variable.set(selected)

    for row, (label, default, kind) in enumerate(fields):
        variable = tk.StringVar(master=window, value=default)
        variables.append(variable)
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky='w', pady=5)
        ttk.Entry(frame, textvariable=variable, show='*' if kind == 'password' else '',
                  width=52).grid(row=row, column=1, sticky='ew', padx=8)
        if kind in ('file', 'directory'):
            ttk.Button(frame, text='选择…', command=lambda v=variable, k=kind: choose(v, k)).grid(row=row, column=2)

    ttk.Label(frame, wraplength=600, text=(
        '使用自备 JDK 17+、Android 36 / build-tools 36.0.0 SDK 和现有密钥，不生成密钥。\n'
        '构建只读取本机依赖；联网准备仅下载并校验锁定的 3 个 AAR 与 4 个预警 DEX JAR，'
        '不下载 SDK 或接受许可。离线预警依赖使用 tools/recipe_tools.py --local-dir 目录。\n'
        '开始后关闭此窗口并清空输入；如需再次操作，请重新打开。'
    )).grid(row=6, column=0, columnspan=3, sticky='w', pady=12)

    def close():
        for variable in variables:
            variable.set('')
        window.destroy()

    def build():
        values = tuple(variable.get() for variable in variables)
        close()
        app._start('正在本机构建统一插件…', lambda: run_build(ROOT, *values), on_built)

    def prepare():
        close()
        app._start('正在联网准备锁定依赖…', lambda: prepare_dependencies(ROOT), app._show)

    actions = ttk.Frame(frame)
    actions.grid(row=7, column=0, columnspan=3, sticky='e')
    ttk.Button(actions, text='联网准备依赖', command=prepare).pack(side='left', padx=6)
    ttk.Button(actions, text='本地构建', command=build).pack(side='left', padx=6)
    ttk.Button(actions, text='取消', command=close).pack(side='left')
    window.protocol('WM_DELETE_WINDOW', close)
    return window
