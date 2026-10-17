#!/usr/bin/env python3
"""Native local interface for the existing offline builder; no device access."""
from __future__ import annotations
import copy
from datetime import datetime
import json
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import intake
import environment
import plugin_builder
import suite_builder as builder
from gui_session import Session

HERE = Path(__file__).resolve().parent
GUI_VERSION = '0.7.0'
REVIEWED = HERE / 'profiles/xuanyuan-eea-os4.0.0.6.json'
KNOWN_TITLE = '历史配方 · 小米15 Ultra（需自备完整1.4）'
NEW_TITLE = '其他机型 · 从目标固件识别'
FULL_TITLE = '小米15 Ultra · OS4.0.0.6 完整1.7适配'
SELECTED_TITLE = '历史配方 · 三组件精选（需自备完整1.4）'
KNOWN_COMPONENTS = [('market', '小米应用商店'), ('assistant', '智能助理负一屏'),
    ('xiaoai', '超级小爱'), ('phone', '电话、短信与录音'), ('gallery', '相册与AI编辑'),
    ('weather', '天气与街道定位'), ('disaster', '自然灾害预警与报警定位'),
    ('wallet', '钱包与NFC'), ('clock', '时钟法定节假日'), ('calendar', '国行日历'),
    ('mipush', 'MiPush与API102统一兼容')]


def friendly(error):
    text = str(error)
    labels = [('insufficient extraction space', '解包空间不足'),
              ('Insufficient output disk space', '打包空间不足'),
              ('No APK components', '没有可用APK，请先解包或补充材料'),
              ('Source firmware belongs to a different device', '来源固件与目标机型不同'),
              ('Target firmware', '目标固件信息不完整或与配置不符'),
              ('Select at least one', '请先勾选至少一个组件'),
              ('Material changed', '材料已变化，请重新分析并检查'),
              ('Reviewed suite artifact hash differs', '1.4安装包校验不符'),
              ('Permission denied', '目录没有写入权限')]
    for match, label in labels:
        if match in text:
            return label + '\n' + text
    return text


class App:
    def __init__(self, root):
        self.root = root
        root.title('小米套件构建工具 · ' + GUI_VERSION)
        root.geometry('1100x870')
        root.minsize(950, 850)
        self.session = Session()
        self.sources = []
        self.busy = False
        self.updating = True
        self.events = queue.Queue()
        self.widgets = []
        self.row_map = {}
        self.mode = tk.StringVar(value=NEW_TITLE)
        self.target = tk.StringVar()
        self.source_summary = tk.StringVar()
        self.profile_id = tk.StringVar(value='my-device-os4')
        self.workspace = tk.StringVar(value=str(Path.home() / 'XiaomiLocalSuite-work'))
        self.artifact = tk.StringVar()
        self.unified = tk.StringVar()
        self.identity_text = tk.StringVar(value='选择机型配置或导入目标固件')
        self.last_output = None
        self.status = tk.StringVar(value='就绪 · 所有操作在本机完成')
        self.selection_note = tk.StringVar()
        self._layout()
        self.target.trace_add('write', lambda *_: self._inputs_changed())
        self.profile_id.trace_add('write', lambda *_: self._inputs_changed())
        self.artifact.trace_add('write', lambda *_: self._artifact_changed())
        self.unified.trace_add('write', lambda *_: self._plugin_changed())
        self.updating = False
        self._mode_changed()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(80, self._poll)

    def _button(self, parent, text, command, **options):
        widget = ttk.Button(parent, text=text, command=command, **options)
        self.widgets.append(widget)
        return widget

    def _entry(self, parent, variable, **options):
        widget = ttk.Entry(parent, textvariable=variable, **options)
        self.widgets.append(widget)
        return widget

    def _layout(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Title.TLabel', font=('Helvetica', 23, 'bold'))
        style.configure('Hint.TLabel', foreground='#566579')
        style.configure('Safety.TLabel', foreground='#7b561d')
        outer = ttk.Frame(self.root, padding=(22, 16))
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='小米套件构建工具', style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer, text='选择材料  →  勾选组件  →  检查兼容性  →  生成安装包', style='Hint.TLabel').pack(anchor='w', pady=(5, 12))
        helpbar = ttk.Frame(outer)
        helpbar.pack(fill='x', pady=(0, 8))
        ttk.Label(helpbar, text='工具不含小米 APK / 固件。普通导入流程不需要旧版套件。', style='Hint.TLabel').pack(side='left')
        self.help_button = self._button(helpbar, '使用教程', self.show_help)
        self.help_button.pack(side='right')
        self.environment_button = self._button(helpbar, '环境检查', self.check_environment)
        self.environment_button.pack(side='right', padx=6)
        top = ttk.Frame(outer)
        top.pack(fill='x')
        ttk.Label(top, text='机型配置').pack(side='left', padx=(0, 10))
        self.mode_box = ttk.Combobox(top, textvariable=self.mode, values=[FULL_TITLE, NEW_TITLE, KNOWN_TITLE, SELECTED_TITLE], state='readonly', width=43)
        self.mode_box.pack(side='left', fill='x', expand=True)
        self.mode_box.bind('<<ComboboxSelected>>', lambda _: self._mode_changed())
        self.widgets.append(self.mode_box)
        self._button(top, '打开配置…', self.open_profile).pack(side='left', padx=(10, 5))
        self.save_button = self._button(top, '保存配置…', self.save_profile)
        self.save_button.pack(side='left')

        inputs = ttk.LabelFrame(outer, text='1 · 选择材料', padding=12)
        inputs.pack(fill='x', pady=(12, 8))
        inputs.columnconfigure(1, weight=1)
        self.known_frame = ttk.Frame(inputs)
        self.known_frame.grid(row=0, column=0, columnspan=3, sticky='ew')
        self.known_frame.columnconfigure(1, weight=1)
        ttk.Label(self.known_frame, text='原1.4安装包', width=13).grid(row=0, column=0, sticky='w')
        self._entry(self.known_frame, self.artifact).grid(row=0, column=1, sticky='ew', padx=8)
        self._button(self.known_frame, '选择ZIP…', self.choose_artifact).grid(row=0, column=2)
        self.new_frame = ttk.Frame(inputs)
        self.new_frame.grid(row=1, column=0, columnspan=3, sticky='ew')
        self.new_frame.columnconfigure(1, weight=1)
        ttk.Label(self.new_frame, text='目标系统', width=13).grid(row=0, column=0, sticky='w')
        self._entry(self.new_frame, self.target).grid(row=0, column=1, sticky='ew', padx=8)
        target_buttons = ttk.Frame(self.new_frame)
        target_buttons.grid(row=0, column=2)
        self._button(target_buttons, '固件ZIP…', lambda: self.choose_target(False)).pack(side='left')
        self._button(target_buttons, '目录…', lambda: self.choose_target(True)).pack(side='left', padx=4)
        self._button(target_buttons, '解包OTA', lambda: self.extract('target')).pack(side='left')
        ttk.Label(self.new_frame, text='来源材料').grid(row=1, column=0, sticky='w', pady=7)
        self._entry(self.new_frame, self.source_summary, state='readonly').grid(row=1, column=1, sticky='ew', padx=8)
        source_buttons = ttk.Frame(self.new_frame)
        source_buttons.grid(row=1, column=2)
        self._button(source_buttons, '添加APK…', self.add_apks).pack(side='left')
        self._button(source_buttons, '目录…', lambda: self.choose_source(True)).pack(side='left', padx=4)
        self._button(source_buttons, '国行ZIP…', lambda: self.choose_source(False)).pack(side='left')
        self._button(source_buttons, '解包OTA', lambda: self.extract('source')).pack(side='left', padx=4)
        self._button(source_buttons, '清空', self.clear_sources).pack(side='left')
        ttk.Label(self.new_frame, text='配置标识').grid(row=2, column=0, sticky='w')
        self.profile_entry = self._entry(self.new_frame, self.profile_id)
        self.profile_entry.grid(row=2, column=1, sticky='ew', padx=8)
        ttk.Label(self.new_frame, text='英文字母、数字、点、横线', style='Hint.TLabel').grid(row=2, column=2, sticky='w')
        self.plugin_frame = ttk.Frame(self.new_frame)
        self.plugin_frame.grid(row=3, column=0, columnspan=3, sticky='ew', pady=(6, 0))
        self.plugin_frame.columnconfigure(1, weight=1)
        ttk.Label(self.plugin_frame, text='统一插件APK', width=13).grid(row=0, column=0, sticky='w')
        self._entry(self.plugin_frame, self.unified).grid(row=0, column=1, sticky='ew', padx=8)
        buttons = ttk.Frame(self.plugin_frame)
        buttons.grid(row=0, column=2)
        self._button(buttons, '选择APK…', self.choose_unified).pack(side='left')
        self._button(buttons, '本地构建统一插件…', self.build_unified).pack(side='left', padx=4)
        ttk.Label(inputs, text='工作目录', width=13).grid(row=2, column=0, sticky='w', pady=(8, 0))
        self._entry(inputs, self.workspace).grid(row=2, column=1, sticky='ew', padx=8, pady=(8, 0))
        self._button(inputs, '选择目录…', self.choose_workspace).grid(row=2, column=2, pady=(8, 0))
        ttk.Label(inputs, text='完整OTA解包需要较多空间，建议选择外接磁盘；空间不足时会停止。', style='Hint.TLabel').grid(row=3, column=0, columnspan=3, sticky='w', pady=(7, 0))
        info = ttk.Frame(outer)
        info.pack(fill='x', pady=(0, 6))
        ttk.Label(info, textvariable=self.identity_text, style='Hint.TLabel', wraplength=1020).pack(side='left', fill='x', expand=True)
        self.analyse_button = self._button(info, '分析材料', self.analyse)
        self.analyse_button.pack(side='right', padx=(10, 0))

        selection = ttk.LabelFrame(outer, text='2 · 选择组件', padding=(10, 7))
        selection.pack(fill='both', expand=True)
        bar = ttk.Frame(selection)
        bar.pack(fill='x')
        ttk.Label(bar, textvariable=self.selection_note, style='Hint.TLabel').pack(side='left')
        self.none_button = self._button(bar, '全部取消', lambda: self.select_all(False))
        self.none_button.pack(side='right')
        self.all_button = self._button(bar, '选择可用项', lambda: self.select_all(True))
        self.all_button.pack(side='right', padx=6)
        table = ttk.Frame(selection)
        table.pack(fill='both', expand=True, pady=(7, 0))
        columns = ('selected', 'name', 'package', 'state')
        self.table = ttk.Treeview(table, columns=columns, show='headings', height=4, selectmode='browse')
        for name, title, width in [('selected', '选择', 54), ('name', '组件 / APK', 200), ('package', '包名 / 目标', 460), ('state', '状态', 190)]:
            self.table.heading(name, text=title)
            self.table.column(name, width=width, minwidth=45, stretch=name in ('package', 'name'))
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.table.tag_configure('blocked', foreground='#b42318')
        self.table.tag_configure('passed', foreground='#146c43')
        self.table.tag_configure('locked', foreground='#8b6619')
        self.table.bind('<Button-1>', self._table_click)
        self.table.bind('<space>', self._table_space)

        reports = ttk.LabelFrame(outer, text='3 · 兼容报告与生成结果', padding=(10, 7))
        reports.pack(fill='both', expand=True, pady=(9, 8))
        self.report_text = scrolledtext.ScrolledText(reports, height=4, wrap='word', font=('Menlo', 11), state='disabled')
        self.report_text.pack(fill='both', expand=True)
        foot = ttk.Frame(outer)
        foot.pack(fill='x')
        ttk.Label(foot, text='钱包 / TSM / eSE / NFC：单独验证，不自动重置或清数据。', style='Safety.TLabel').pack(side='left')
        self.check_button = self._button(foot, '检查兼容性', self.check)
        self.check_button.pack(side='right', padx=(7, 0))
        self.build_button = self._button(foot, '生成安装包…', self.build)
        self.build_button.pack(side='right')
        self.report_button = self._button(foot, '保存报告…', self.save_report)
        self.report_button.pack(side='right', padx=7)
        bottom = ttk.Frame(outer)
        bottom.pack(fill='x', pady=(9, 0))
        ttk.Label(bottom, textvariable=self.status, style='Hint.TLabel').pack(side='left', fill='x', expand=True)
        self.progress = ttk.Progressbar(bottom, mode='indeterminate', length=140)
        self.progress.pack(side='right')

    @property
    def reviewed(self):
        return bool(self.session.profile and self.session.profile.get('mode') == 'reviewed-suite')

    @property
    def selected_suite(self):
        return bool(self.session.profile and self.session.profile.get('mode') == 'selected-suite')

    @property
    def full_recipe(self):
        return self.mode.get() == FULL_TITLE

    def _mode_changed(self):
        if self.busy:
            return
        self.updating = True
        self.session = Session()
        self.plugin_frame.grid() if self.full_recipe else self.plugin_frame.grid_remove()
        if self.full_recipe:
            self.profile_id.set('xuanyuan-eea-os4.0.0.6-full17')
        if self.mode.get() in (KNOWN_TITLE, SELECTED_TITLE):
            self.new_frame.grid_remove()
            self.known_frame.grid()
            if not self.artifact.get():
                for directory in (HERE, HERE.parent, HERE.parent / 'unified-bundle'):
                    candidate = directory / 'xuanyuan-os4-suite-1.4.zip'
                    if candidate.is_file():
                        self.artifact.set(str(candidate))
                        break
            self.session.use_reviewed(REVIEWED, self._materials())
            if self.mode.get() == SELECTED_TITLE:
                import selected_suite
                self.session.profile = selected_suite.new_profile()
            self._identify()
            self._show('勾选已有适配模块；超级小爱会补选智能助理。检查后生成含原子模块、权限及恢复脚本的精选整合包。\n钱包及其他组件不会进入输出包。' if self.selected_suite else '已选择完整1.4配方。校验后按原字节导出；组件和兼容功能在手机套件中勾选。\n钱包首次迁移仍须单独验证。')
        else:
            self.known_frame.grid_remove()
            self.new_frame.grid()
            self.identity_text.set('新机型：选择目标系统与来源材料后，点击“分析材料”。')
            self._show('精确1.7配方：目标为小米15 Ultra EEA OS4.0.0.6。来源为同机型国行材料与所需额外APK；无需私有参考ZIP。\n请选择当前源码自行构建的统一插件APK及配套记录。分析后勾选组件，检查将列出缺少的精确材料。钱包不自动重置。'
                       if self.full_recipe else '目标请选择将要安装的系统固件或已解包目录。来源可添加多个APK，也可选择同机型国行固件。\nOTA需先显式解包；不会自动占用磁盘或生成已验证结论。')
        self.updating = False
        self._render_rows()
        self._refresh()

    def check_environment(self):
        self._start('正在检查本机依赖，不下载或安装任何工具…', environment.inspect,
                    lambda result: self._show(environment.format_report(result)))

    def choose_unified(self):
        path = filedialog.askopenfilename(title='选择当前源码自签名统一APK（保留同名构建记录）', parent=self.root)
        if path:
            self.unified.set(path)

    def build_unified(self):
        plugin_builder.open_dialog(self, lambda path: self.unified.set(str(path)))

    def _plugin_changed(self):
        if self.updating or self.busy or not self.full_recipe:
            return
        if self.session.profile:
            self.session.profile['unified_apk'] = self.unified.get()
            self.session._invalidate()
            self._show('统一插件已更改，保留组件选择；请重新检查源码记录与材料。')
            self._refresh()

    def show_help(self):
        path = HERE.parents[1] / 'docs/USER_GUIDE.md'
        try:
            text = path.read_text(encoding='utf-8')
        except OSError:
            self._show('未找到离线教程，请检查是否完整解压工具包。仓库中的 docs/USER_GUIDE.md 提供完整步骤。')
            return
        window = tk.Toplevel(self.root)
        window.title('XiaomiLocalSuite · 离线使用教程')
        window.geometry('900x700')
        content = scrolledtext.ScrolledText(window, wrap='word', font=('Menlo', 12), padx=15, pady=15)
        content.pack(fill='both', expand=True)
        content.insert('1.0', text)
        content.configure(state='disabled')

    def _materials(self):
        return str(Path(self.artifact.get()).expanduser().parent) if self.artifact.get().strip() else None

    def _inputs_changed(self):
        if self.updating or self.busy or self.mode.get() in (KNOWN_TITLE, SELECTED_TITLE):
            return
        self.session = Session()
        self.identity_text.set('材料或配置标识已变化，请重新分析。')
        self._show('尚未检查当前材料。')
        self._render_rows()
        self._refresh()

    def _artifact_changed(self):
        if self.updating or self.busy or not (self.reviewed or self.selected_suite):
            return
        self.session.configure_materials(self._materials())
        self._show('安装包路径已变化，请重新检查兼容性。')
        self._refresh()

    def _identify(self):
        p = self.session.profile or {}
        t = p.get('target', {})
        abis = t.get('abis') or []
        abis = abis if isinstance(abis, list) and all(isinstance(a, str) for a in abis) else []
        self.identity_text.set('机型：{}    系统：{}    SDK：{}    ABI：{}'.format(
            t.get('device') or '待确认', t.get('incremental') or '待确认',
            t.get('sdk') or '待确认', ', '.join(abis) or '待确认'))

    def _refresh(self):
        for widget in self.widgets:
            widget.state(['disabled'] if self.busy else ['!disabled'])
        if self.busy:
            return
        self.profile_entry.state(['disabled'] if self.full_recipe else ['!disabled'])
        profile = self.session.profile
        self.analyse_button.configure(text='适配模块已载入' if self.selected_suite else '完整配方已载入' if self.reviewed else '分析材料')
        self.analyse_button.state(['disabled'] if self.reviewed or self.selected_suite else ['!disabled'])
        for widget in (self.all_button, self.none_button):
            widget.state(['disabled'] if self.reviewed or not profile else ['!disabled'])
        self.save_button.state(['!disabled'] if profile else ['disabled'])
        self.check_button.state(['!disabled'] if profile else ['disabled'])
        report = getattr(self.session, 'report', None)
        ready = report and report.get('state') in ('reviewed-recipe', 'reviewed-components', 'candidate-static-pass', 'reviewed-raw-materials')
        self.build_button.state(['!disabled'] if ready else ['disabled'])
        self.build_button.configure(text='生成1.7自动安装包…' if self.full_recipe else '生成自动安装整合包…' if self.selected_suite else '导出1.4完整包…' if self.reviewed else '生成候选ZIP…')
        self.report_button.state(['!disabled'] if report else ['disabled'])

    def _show(self, text):
        self.report_text.configure(state='normal')
        self.report_text.delete('1.0', 'end')
        self.report_text.insert('1.0', text)
        self.report_text.configure(state='disabled')

    def _render_rows(self):
        self.table.delete(*self.table.get_children())
        self.row_map = {}
        if self.reviewed:
            self.selection_note.set('完整包按原字节导出；安装后在手机中按需勾选')
            for index, (key, name) in enumerate(KNOWN_COMPONENTS):
                wallet = key == 'wallet'
                self.table.insert('', 'end', iid=str(index), values=('—' if wallet else '✓', name,
                    '完整配方内材料；不会在电脑端改写', '单独验证' if wallet else '手机端选择'), tags=('locked',) if wallet else ())
            self.table.yview_moveto(0)
            return
        self.selection_note.set('精确1.7适配；依赖自动补选；钱包须手动勾选，不自动重置' if self.full_recipe else '选择现有适配模块；小爱会补选智能助理；不含钱包' if self.selected_suite else '点击方框勾选；修改选择后需重新检查。钱包项锁定。')
        report = getattr(self.session, 'report', None) or {}
        checked = {r.get('id'): r for r in report.get('components', [])}
        components = {c.get('id'): c for c in (self.session.profile or {}).get('components', []) if isinstance(c.get('id'), str)}
        for index, row in enumerate(self.session.rows()):
            self.row_map[str(index)] = row
            result = checked.get(row['id'], {})
            state = '未选择'
            tag = ''
            if not row.get('selectable', True):
                state, tag = ('钱包相关：单独验证' if builder.wallet(str(row.get('package'))) else '配置无效，需检查'), 'locked'
            elif result.get('state') == 'blocked':
                state, tag = '检查未通过', 'blocked'
            elif result.get('state') in ('static-pass', 'reviewed-module', 'reviewed-materials'):
                state, tag = ('1.7材料已核对' if self.full_recipe else '原适配模块已核对' if self.selected_suite else '静态检查通过'), 'passed'
            elif row.get('enabled'):
                state = '待检查'
            source = components.get(row['id'], {}).get('source_apk')
            title = Path(source).name if isinstance(source, str) and source else row.get('title') or row.get('package') or row['id']
            self.table.insert('', 'end', iid=str(index), values=(
                ('☑' if row.get('enabled') else '☐') if row.get('selectable', True) else '—',
                title, row.get('package') or ('适配模块＋共享API102' if self.full_recipe or self.selected_suite else '未知'), state), tags=(tag,) if tag else ())
        self.table.yview_moveto(0)

    def _table_click(self, event):
        if self.table.identify_column(event.x) == '#1':
            self._toggle(self.table.identify_row(event.y))
            return 'break'

    def _table_space(self, _event):
        self._toggle(self.table.focus())
        return 'break'

    def _toggle(self, iid):
        if self.busy or self.reviewed:
            return
        row = self.row_map.get(iid)
        if not row or not row.get('selectable', True):
            return
        selected = {r['id'] for r in self.row_map.values() if r.get('enabled')}
        selected.symmetric_difference_update({row['id']})
        self.session.set_selected(sorted(selected))
        self._show('组件选择已修改，请点击“检查兼容性”。')
        self._render_rows()
        self._refresh()

    def select_all(self, enabled):
        if self.busy or self.reviewed or not self.session.profile:
            return
        self.session.set_selected([r['id'] for r in self.session.rows() if enabled and r.get('selectable', True)
                                   and (r.get('bulk_selectable', True) or r.get('enabled'))])
        self._show('组件选择已修改，请重新检查。钱包须单独手动勾选；不自动重置。')
        self._render_rows()
        self._refresh()

    def choose_artifact(self):
        path = filedialog.askopenfilename(title='选择原始1.4完整包（ZIP）', parent=self.root)
        if path:
            self.artifact.set(path)

    def choose_target(self, directory):
        path = filedialog.askdirectory(title='选择已解包目标系统目录', parent=self.root) if directory else filedialog.askopenfilename(
            title='选择目标系统OTA ZIP', parent=self.root)
        if path:
            self.target.set(path)

    def _sources_changed(self):
        self.source_summary.set(self.sources[0] if len(self.sources) == 1 else '{}项材料：{}'.format(
            len(self.sources), '、'.join(Path(p).name for p in self.sources)) if self.sources else '')
        self._inputs_changed()

    def add_apks(self):
        paths = filedialog.askopenfilenames(title='选择一个或多个来源APK', parent=self.root)
        for path in paths:
            if path not in self.sources:
                self.sources.append(path)
        self._sources_changed()

    def choose_source(self, directory):
        path = filedialog.askdirectory(title='选择来源APK或固件目录', parent=self.root) if directory else filedialog.askopenfilename(
            title='选择同机型国行OTA ZIP', parent=self.root)
        if path:
            self.sources = [path]
            self._sources_changed()

    def clear_sources(self):
        self.sources = []
        self._sources_changed()

    def choose_workspace(self):
        path = filedialog.askdirectory(title='选择工作目录，建议外接磁盘', parent=self.root)
        if path:
            self.workspace.set(path)

    def analyse(self):
        if not self.target.get().strip() or not self.sources:
            self._show('请先选择目标系统与来源APK / 固件。')
            return
        target, sources, profile_id = self.target.get(), list(self.sources), self.profile_id.get()
        if self.full_recipe:
            plugin = self.unified.get()
            self._start('正在核对目标固件并载入完整1.7配方…',
                        lambda: self.session.analyse_recipe(Path(target), sources, plugin), self._analysed)
        else:
            self._start('正在分析固件与APK，较大的文件需要等待…',
                lambda: self.session.analyse(Path(target), [Path(p) for p in sources], profile_id), self._analysed)

    def _analysed(self, _result):
        self._identify()
        self._render_rows()
        count = len(self.session.rows())
        if self.full_recipe:
            self._show('已载入11项精确1.7适配，默认不选。请勾选需要的组件，再检查材料。\n小爱补选智能助理，电话补选商店；钱包仅手动选择，首次迁移须在手机单独确认。\n统一插件需由当前源码构建并保留配套.build-evidence.json；导入材料缺项会逐项列出。')
        elif count:
            self._show('已发现{}项来源组件，默认均不勾选。请选择需要的组件，再检查兼容性。\n'
                       '钱包与NFC相关项保持锁定；静态检查不等于实机验证。'.format(count))
        else:
            self._show('尚未发现可配置APK。若选择的是OTA，请先点击对应的“解包OTA”，完成后再分析。\n'
                       '不会根据OTA文件名推断APK兼容性；缺失的机型、SDK、ROM或ABI信息会在检查时阻止生成。')

    def extract(self, kind):
        if self.busy:
            return
        if kind == 'target':
            source = self.target.get()
        else:
            candidates = [p for p in self.sources if Path(p).suffix.lower() == '.zip']
            if len(candidates) != 1:
                self._show('来源解包需要恰好选择一个国行OTA ZIP。')
                return
            source = candidates[0]
        if not source or Path(source).suffix.lower() != '.zip':
            self._show('请选择含payload.bin的OTA ZIP；已解包目录无需再次解包。')
            return
        work = Path(self.workspace.get()).expanduser()
        if not self.workspace.get().strip():
            self._show('请先选择用于解包的工作目录。')
            return
        output = work / (kind + '-extracted-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
        def run():
            work.mkdir(parents=True, exist_ok=True)
            return intake.extract_apks(Path(source), output)
        def completed(result):
            path = result['path']
            if kind == 'target':
                self.target.set(path)
            else:
                self.sources = [path if p == source else p for p in self.sources]
                self._sources_changed()
            self._show('解包完成：' + path + '\n请点击“分析材料”读取目标系统与来源APK。')
        self._start('正在解包OTA；先检查输出磁盘空间，再进行提取…', run, completed)

    def check(self):
        if self.reviewed or self.selected_suite:
            path = Path(self.artifact.get()).expanduser()
            if path.name != self.session.profile.get('artifact') or not path.is_file():
                self._show('请选择原始xuanyuan-os4-suite-1.4.zip文件；不能用改名文件或其他版本代替。')
                return
            self.session.configure_materials(str(path.parent))
        self._start('正在重新读取材料并检查兼容性…', self.session.check, self._checked)

    def _checked(self, result):
        state = result.get('state')
        if state == 'reviewed-recipe':
            lines = ['检查通过：已验证配方，可按原字节导出完整1.4。', 'SHA256：' + result.get('artifact_sha256', ''),
                     '组件和兼容功能在手机中勾选；钱包仍须单独验证。']
        elif state == 'reviewed-components':
            lines = ['原适配模块检查通过：' + '、'.join(c['title'] for c in result['components']),
                     '原子模块ZIP和API102 APK保留原字节；刷入时同步安装所选组件，WebUI保留单独恢复。',
                     '钱包与其他未选组件不打包。仅做主机测试；生成过程不连接或安装手机。']
        elif state == 'candidate-static-pass':
            lines = ['静态检查通过：可以生成候选ZIP，尚未在该机型实测。',
                     '候选模块在OTA前必须先停用并重启；不会自动跨ROM适配。']
        elif state == 'reviewed-raw-materials':
            lines = ['1.7所选组件的精确材料与统一插件构建记录检查通过。',
                     '生成包刷入时自动部署所选组件；电话若等待商店生效，会在手动重启后自动续装。电脑不连接手机。',
                     '未打包项不会由本包预设安装；已安装组件及其他页面的既有兼容开关保留，停用需单独关闭或恢复。',
                     '钱包只在勾选时打包，首次迁移仍需手机上单独确认。']
        else:
            lines = ['兼容检查未通过，已阻止生成。']
        for error in result.get('errors', []):
            lines.append('原因：' + friendly(error))
        if result.get('error'):
            lines.append('原因：' + friendly(result['error']))
        for component in result.get('components', []):
            for error in component.get('errors', []):
                lines.append('{}：{}'.format(component.get('package') or component.get('id'), friendly(error)))
        lines.append('钱包 / TSM / eSE / NFC：单独验证；不自动重置、清数据或迁移凭据。')
        self._show('\n'.join(lines))
        self._render_rows()

    def build(self):
        if not self.session.profile:
            return
        name = self.session.profile['id'] + ('-selected.zip' if self.full_recipe else '-autoinstall.zip' if self.selected_suite else '-1.4.zip' if self.reviewed else '-candidate.zip')
        output = filedialog.asksaveasfilename(title='选择新安装包保存位置', defaultextension='.zip', initialfile=name,
            filetypes=[('ZIP安装包', '*.zip')], parent=self.root)
        if not output:
            return
        self.last_output = str(Path(output).expanduser().resolve())
        candidate = not (self.reviewed or self.selected_suite or self.full_recipe)
        self._start('正在重新校验并生成ZIP，已有文件不会被覆盖…',
            lambda: self.session.build(Path(output), candidate=candidate), self._built)

    def _built(self, result):
        self._show('生成完成：{}\n大小：{:,}字节\nSHA256：{}\n\n{}\n钱包保持单独验证，不自动重置。'.format(
            self.last_output or result.get('output'), result.get('bytes', 0), result.get('sha256'),
            '刷入时自动部署电脑所选组件；电话依赖商店时，手动重启后自动续装。保留数据与逐项恢复；LSPosed及兼容开关仍需配置。首次钱包TSM迁移须单独确认。本轮未安装手机。' if self.full_recipe else '刷入时同步安装所选组件；不含钱包；本轮未安装手机，保留原API102插件与独立恢复。' if self.selected_suite else '完整1.4仍使用原API102统一插件。' if self.reviewed else '这是待实机验证的候选包，不会自动安装到手机。'))
        self.status.set('安装包已生成，保存位置以刚才选择的路径为准')

    def open_profile(self):
        # Tk9's native extension filter can leave valid JSON files disabled.
        # The loader validates JSON/schema; do not rely on the picker filter.
        path = filedialog.askopenfilename(title='打开机型配置（JSON）', parent=self.root)
        if not path:
            return
        def loaded(_result):
            self.updating = True
            p = self.session.profile
            self.mode.set(FULL_TITLE if p.get('mode') == 'xuanyuan-1.7' else SELECTED_TITLE if self.selected_suite else KNOWN_TITLE if self.reviewed else NEW_TITLE)
            self.plugin_frame.grid() if self.full_recipe else self.plugin_frame.grid_remove()
            if self.reviewed or self.selected_suite:
                self.new_frame.grid_remove()
                self.known_frame.grid()
                self.artifact.set(str(Path(self.session.materials or Path(path).parent) / p['artifact']))
            else:
                self.known_frame.grid_remove()
                self.new_frame.grid()
                def display_path(value):
                    path = Path(value).expanduser()
                    return str((path if path.is_absolute() else self.session.base / path).resolve())
                self.target.set(display_path(p['target_input']) if p.get('target_input') else '')
                self.profile_id.set(p['id'])
                source = p.get('source_inputs') or p.get('source_input') or []
                source = [source] if isinstance(source, str) else source
                self.sources = [display_path(value) for value in source]
                self.source_summary.set('、'.join(self.sources))
                if self.full_recipe:
                    self.unified.set(display_path(p['unified_apk']) if p.get('unified_apk') else '')
            self.updating = False
            self._identify()
            self._render_rows()
            self._show('已载入配置；导入配置不会直接生成或安装，请重新检查当前材料。')
        self._start('正在读取机型配置…', lambda: self.session.load_profile(Path(path)), loaded)

    def save_profile(self):
        if not self.session.profile:
            return
        path = filedialog.asksaveasfilename(title='另存机型配置', defaultextension='.json',
            initialfile=self.session.profile['id'] + '.json', parent=self.root)
        if path:
            self._start('正在保存配置…', lambda: self.session.save_profile(Path(path)),
                        lambda _: self._show('配置已另存：' + path + '\n个人钱包凭据不进入配置。'))

    def save_report(self):
        report = getattr(self.session, 'report', None)
        if not report:
            return
        path = filedialog.asksaveasfilename(title='保存兼容报告', defaultextension='.json', initialfile='compatibility-report.json', parent=self.root)
        if path:
            snapshot = copy.deepcopy(report)
            self._start('正在保存报告…', lambda: builder.write_new(Path(path), snapshot),
                        lambda _: self.status.set('报告已保存：' + path))

    def _start(self, label, function, success):
        if self.busy:
            return
        self.busy = True
        self.status.set(label)
        self.progress.start(12)
        self._refresh()
        def worker():
            try:
                result = function()
                self.events.put((True, result, success))
            except Exception as error:
                self.events.put((False, friendly(error), success))
        threading.Thread(target=worker, name='suite-builder-worker', daemon=False).start()

    def _poll(self):
        try:
            ok, result, success = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.progress.stop()
            try:
                if ok:
                    self.status.set('操作完成')
                    success(result)
                else:
                    self.status.set('操作未完成，请查看原因')
                    self._show('操作已停止：\n' + result + '\n\n不会覆盖已有文件或重置钱包。')
            except Exception as error:
                self.updating = False
                self._mode_changed()
                self.status.set('界面更新未完成，已恢复输入')
                self._show('未能载入结果，请重新打开配置并检查：\n' + friendly(error))
            finally:
                self.updating = False
                self._refresh()
        self.root.after(80, self._poll)

    def close(self):
        if self.busy:
            self.status.set('任务仍在处理中，请完成后再关闭，以免留下不完整输出。')
            return
        self.root.destroy()


def main():
    if sys.platform == 'darwin' and tk.TkVersion < 8.6:
        raise SystemExit('Tk版本过旧。请使用 launchers/macOS.command，或带Tk8.6+的Python3.11+运行launch.py。')
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
