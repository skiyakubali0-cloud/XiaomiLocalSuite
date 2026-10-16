"""Offline suite 1.4 packager. All writes stay below this file's directory.

No import/execution of the original build.py, no Android/device commands.
Run tests before explicitly packaging the main-owned APK and migration helper.
"""
from pathlib import Path, PurePosixPath
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
# suite is a symlink onto an external volume. Never infer BASE from HERE.parent.
BASE = Path(__file__).resolve().parents[2]
SUITE = BASE / 'suite'
RELEASE = BASE / 'releases'
SOURCE_MODULE = SUITE / 'module'
APK = SUITE / 'unified-api102/build/XuanyuanUnifiedCompat-1.2-api102.apk'
MIGRATION = SUITE / 'unified-api102/migrate-legacy.sh'
PKG = 'local.xuanyuan.mipushcompat'
PREVIOUS_SHA = '221d9cf4691e12382d2a5eab8fabc4470ff5f8a635a75650fca9a6129397c59c'
INITIAL_12_SHA = 'fe2cc510d76aeca054582d20f092833a336e13b39686fb1d49f5a20a3a5688d7'
REVISION_12_SHA = 'e49470e7cf7a08f3d9bc1ae2ebd5ba170ed3fcf0549fe9d927da2b9bf166d973'
CHILDREN = {
    'phone': ('2026101208', '2026101502', '1.8.1', {'payload/XuanyuanSmsCompat.apk'}),
    'xiaoai': ('2026101302', '2026101504', '1.7.3', {'compat/XuanyuanAiPrivacy.apk', 'compat/XuanyuanSuggestionCompat.apk'}),
    'disaster': ('2026101401', '2026101501', '1.2', {'compat/XuanyuanDisasterCompat.apk'}),
}
LEGACY_LEAVES = {'XuanyuanSmsCompat.apk', 'XuanyuanAiPrivacy.apk', 'XuanyuanSuggestionCompat.apk',
                 'XuanyuanDisasterCompat.apk', 'XuanyuanClockCompat-1.0.apk'}
MARKER = 'system/product/etc/xuanyuan-suite-phone.enabled'
GLOBAL_CALENDAR_SHA = 'e2f2e6f2cc5d5ab32480447c23b91c90b2c5db863a38907c6dff61fec80566e7'


def digest(path):
    with Path(path).open('rb') as stream:
        return stream_digest(stream)


def stream_digest(stream):
    h = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def replace_once(text, old, new):
    require(text.count(old) == 1, 'Source contract drift: ' + old[:100])
    return text.replace(old, new, 1)


def properties(text):
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def safe_name(name):
    parts = PurePosixPath(name).parts
    return (bool(parts) and not name.startswith('/') and '\\' not in name
            and all(p not in ('..', '.') and not p.startswith('.') for p in parts)
            and not any(p.lower() in ('private', 'private-backup', '__macosx', 'tests', 'testkeys') for p in parts)
            and not name.lower().endswith(('.jks', '.keystore', '.pem', '.key', '.p12', '.pfx')))


def archive_members(z):
    names = z.namelist()
    require(len(names) == len(set(names)), 'Duplicate ZIP entries')
    for info in z.infolist():
        require(safe_name(info.filename), 'Forbidden ZIP entry: ' + info.filename)
        require((info.external_attr >> 16) & 0o170000 != 0o120000, 'ZIP symlinks forbidden')
    return {i.filename for i in z.infolist() if not i.is_dir()}


def child_edits(key, z, apk_sha):
    """Exact script edits only. Binary entries are copied as streams unchanged."""
    previous, code, version, removed = CHILDREN[key]
    names = archive_members(z)
    require(removed <= names, 'Expected legacy APK missing: ' + key)
    prop = z.read('module.prop').decode()
    props = properties(prop)
    require(props['id'] == 'xuanyuan-os4-' + key and props['versionCode'] == previous,
            'Unreviewed child version: ' + key)
    prop = replace_once(prop, 'version=' + props['version'] + '\n', 'version=' + version + ' (unified API102)\n')
    prop = replace_once(prop, 'versionCode=' + previous + '\n', 'versionCode=' + code + '\n')
    notes = {
        'phone': '电话需先启用商店并重启；保留默认电话/短信记录、黄页与录音监控精确恢复脚本。\n挂载标记：/product/etc/xuanyuan-suite-phone.enabled。恢复后重启并关闭统一设置中的电话兼容。',
        'xiaoai': '小爱依赖智能助理；保留原AI引擎与framework哈希守卫、一次性权限记录和原厂AI权限数据。\n在统一设置选择 AI识屏智控 / 小爱建议；恢复前先切换默认助理，恢复后重启并关闭这两项兼容。',
        'disaster': '保留精确手机管家源、ROM、MetaModule守卫与原有首次备份和恢复脚本。\n恢复时停用挂载并重启，然后关闭统一设置中的预警兼容；不覆盖原备份或数据库。',
    }
    readme = (f'统一 API102 内部组件：{key} {version}，versionCode {code}。\n'
              '仅 xuanyuan / EEA OS4.0.0.6.XOAEUXM / Android17 API37 / 用户0。\n'
              '原始小米签名 APK、DEX、assets 与 native 文件逐字节保留。\n'
              '外部前提：KernelSU、Zygisk、支持 API102 的 LSPosed/Vector、OverlayFS MetaModule。\n'
              '请通过父套件安装共享 local.xuanyuan.mipushcompat v13；本子包不携带或重装旧插件 APK。\n'
              '统一设置中的五项兼容默认关闭。先在父WebUI暂存现代Root子模块，再选择旧插件迁移，重启应用更新后配置唯一LSP入口/开关/作用域并再重启。\n'
              '安装不写 LSP 数据库，不改兼容偏好、不自动迁移、接受协议或开启录音/报警。\n'
              + notes[key] + '\n任何单项恢复均保留共享 APK、其他组件、原有应用数据和个人备份。\n'
              '主机转换测试不等于实机功能验证；真实通话、录音、灾害推送和报警行为仍须单独验证。\n'
              '完整说明见父套件 guides/统一套件1.4说明.txt。\n')
    edits = {'module.prop': prop.encode(), 'README.txt': readme.encode()}
    if key in ('phone', 'xiaoai'):
        # SystemConfig reads the mounted child XML at cold boot. Disabling the
        # child and rebooting removes this feature along with its overlay.
        name = f'system/product/etc/permissions/xuanyuan-os4-{key}.xml'
        edits[name] = replace_once(z.read(name).decode(), '</permissions>',
            f'<feature name="local.xuanyuan.compat.{key}" version="1"/></permissions>').encode()
    if key == 'phone':
        service = z.read('service.sh').decode()
        start = service.index('HOOK_PATH=')
        end = service.index('YELLOW_PATH=', start)
        require('payload/XuanyuanSmsCompat.apk' in service[start:end] and service[start:end].rstrip().endswith('fi'),
                'Phone hook installer drift')
        edits['service.sh'] = (service[:start] + "echo 'Compatibility is supplied by unified API102; choose phone in unified settings.'\n" + service[end:]).encode()
        edits['uninstall.sh'] = replace_once(z.read('uninstall.sh').decode(),
            'pm disable-user --user 0 local.xuanyuan.smscompat',
            "echo 'Phone mount disabled after reboot; turn off phone in unified settings. Shared APK retained.'").encode()
        require(MARKER not in names, 'Unexpected existing phone marker')
        edits[MARKER] = b'unified-api102\n'
    elif key == 'xiaoai':
        custom = z.read('customize.sh').decode()
        for line in (
            'pm install -r "$MODPATH/compat/XuanyuanAiPrivacy.apk" || abort \'AI权限兼容 APK 安装失败\'\n',
            'pm enable local.xuanyuan.aiprivacy >/dev/null\n',
            'pm install -r "$MODPATH/compat/XuanyuanSuggestionCompat.apk" || abort \'小爱建议兼容 APK 安装失败\'\n',
            'pm enable local.xuanyuan.suggestioncompat >/dev/null\n'):
            custom = replace_once(custom, line, '')
        custom = custom[:custom.index("ui_print 'LSPosed：")] + "ui_print '统一设置中手动启用 AI识屏智控、小爱建议并核对作用域；协议由用户确认。'\n"
        edits['customize.sh'] = custom.encode()
        edits['privacy.sh'] = replace_once(z.read('privacy.sh').decode(),
            'export CLASSPATH="$MODDIR/compat/XuanyuanAiPrivacy.apk"',
            'CLASSPATH=$(pm path --user 0 local.xuanyuan.mipushcompat | sed -n \'s/^package://p\')\n'
            '[ -f "$CLASSPATH" ] || { echo \'统一兼容包缺失或为分包安装\' >&2; exit 1; }\n'
            '[ "$(sha256sum "$CLASSPATH" | cut -d\' \' -f1)" = ' + apk_sha + ' ] || exit 1\nexport CLASSPATH').encode()
    else:
        custom = replace_once(z.read('customize.sh').decode(),
            'cat "$MODPATH/compat/XuanyuanDisasterCompat.apk" | pm install -r --user 0 -S "$(stat -c %s "$MODPATH/compat/XuanyuanDisasterCompat.apk")" || abort \'Compatibility APK installation failed\'\n', '')
        custom = replace_once(custom, "ui_print 'Enable 自然灾害预警兼容 in LSPosed; scope: 手机管家 ONLY, then reboot.'",
            "ui_print '统一设置中手动启用预警兼容；作用域仅手机管家，然后重启。'")
        edits['customize.sh'] = custom.encode()
        edits['action.sh'] = replace_once(z.read('action.sh').decode(),
            'local.xuanyuan.disastercompat/.EntryActivity',
            'local.xuanyuan.mipushcompat/local.xuanyuan.disastercompat.EntryActivity').encode()
    return edits


def transform_child(key, source, target, expected_sha, apk_sha):
    require(digest(source) == expected_sha, 'Source checksum mismatch: ' + key)
    with zipfile.ZipFile(source) as src:
        names = archive_members(src)
        edits = child_edits(key, src, apk_sha)
        removed = CHILDREN[key][3]
        hashes, preserved = {}, {}
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_STORED, allowZip64=True) as out:
            for name in sorted((names - removed - {'checksums.sha256'}) | edits.keys()):
                h = hashlib.sha256()
                if name in edits:
                    content = edits[name]
                    out.writestr(name, content)
                    h.update(content)
                else:
                    # Do not unpack/re-sign/patch Xiaomi APK, DEX, assets or native libraries.
                    with src.open(name) as inp, out.open(copy.copy(src.getinfo(name)), 'w', force_zip64=True) as dst:
                        for block in iter(lambda: inp.read(1024 * 1024), b''):
                            dst.write(block)
                            h.update(block)
                    preserved[name] = h.hexdigest()
                hashes[name] = h.hexdigest()
            out.writestr('checksums.sha256', ''.join(f'{sha}  {name}\n' for name, sha in sorted(hashes.items())))
    # Read back each unchanged entry: binary byte preservation is part of packaging acceptance.
    with zipfile.ZipFile(target) as out:
        require(not any(Path(n).name in LEGACY_LEAVES for n in out.namelist()), 'Legacy APK remained')
        for name, sha in hashes.items():
            with out.open(name) as stream:
                require(stream_digest(stream) == sha, 'Output entry mismatch: ' + name)
    return {'source': Path(source).name, 'source_sha256': expected_sha, 'sha256': digest(target), 'preserved_entries': preserved,
            'removed': sorted(removed), 'changed': sorted(edits), 'previousVersionCode': CHILDREN[key][0],
            'versionCode': CHILDREN[key][1]}


def controller(text):
    text = replace_once(text, '. "$M/catalog.sh"', '. "$M/catalog.sh"\n. "$M/shared.sh"')
    text = replace_once(text, "ORDER='market assistant xiaoai phone gallery weather disaster wallet clock calendar'",
                        "ORDER='market assistant xiaoai phone gallery weather disaster wallet clock calendar mipush'")
    text = replace_once(text, '  if [ -f "$MODULES/$MID/module.prop" ]; then\n   module_version_ok',
                        '  if [ "$KIND" = module ] && [ -f "$MODULES/$MID/module.prop" ]; then\n   module_version_ok')
    text = replace_once(text, '   case "$ID" in phone|xiaoai|clock|disaster)',
                        '   case "$ID" in phone|xiaoai|clock|disaster|mipush)\n    shared_check || fail \'统一兼容包存在未知版本或分包安装\';; esac\n   case "$ID" in phone|xiaoai|clock|disaster|mipush)')
    text = replace_once(text, ' [ "$LIVE_CODE" = "$CODE" ] && return 0',
        ' [ "$LIVE_CODE" = "$CODE" ] && return 0\n case "$MID|$LIVE_CODE|$CODE|$OP" in\n' +
        ''.join(f'  xuanyuan-os4-{key}\\|{previous}\\|{new}\\|install) return 0;;\n'
                for key, (old, new, _, _) in CHILDREN.items()
                for previous in ((old, '2026101501', '2026101502', '2026101503') if key == 'xiaoai' else (old, '2026101501') if key == 'phone' else (old,))) + ' esac')
    # Stock EEA lacks the CN gallery plugin. Permit only truly absent packages
    # during install; present APK hashes and restore checks stay unchanged.
    text = replace_once(text, '    gallery) gallery_check;;\n   esac\n   echo "安装：',
                        '    gallery) gallery_check install;;\n   esac\n   echo "安装：')
    text = replace_once(text, '  H=$(pkg_sha "$P")\n  case "$P:$H" in',
                        '  if [ "${1:-}" = install ] && ! present "$P" && [ -z "$(path_of "$P")" ]; then continue; fi\n  H=$(pkg_sha "$P")\n  case "$P:$H" in')
    text = replace_once(text, 'remove_hook() { if present "$1"; then pm uninstall -k --user 0 "$1"; fi; }\n', '')
    text = replace_once(text, ' ID=$1; lookup "$ID"\n if [ "$KIND" = module ]; then',
        ' ID=$1; lookup "$ID"\n case "$ID" in phone|xiaoai|disaster|clock|mipush)\n  shared_install || fail \'统一兼容包安装或校验失败\';; esac\n if [ "$KIND" = module ]; then')
    text = replace_once(text, ' com.android.mms local.xuanyuan.smscompat;', ' com.android.mms;')
    text = replace_once(text, '   disaster) enable_pkg local.xuanyuan.disastercompat;;',
                        "   disaster) echo '在统一设置中启用预警兼容';;")
    text = replace_once(text, ' com.miui.voiceassistProxy local.xuanyuan.aiprivacy local.xuanyuan.suggestioncompat;', ' com.miui.voiceassistProxy;')
    text = replace_once(text, 'case "$ID" in clock) install_apk "$M/payload/$FILE"; enable_pkg "$PKG";; calendar) calendar_swap cn;; esac',
                        'case "$ID" in clock|mipush) :;; calendar) calendar_swap cn;; esac')
    text = replace_once(text, '  remove_hook local.xuanyuan.aiprivacy\n  remove_hook local.xuanyuan.suggestioncompat;;',
        "  echo '重启后小爱挂载标记失效；在统一设置中关闭 AI识屏智控和小爱建议，共享 APK 保留。';;")
    text = replace_once(text, '  remove_hook local.xuanyuan.smscompat',
        "  echo '重启后电话挂载标记失效；在统一设置中关闭电话兼容，共享 APK 保留。'")
    text = replace_once(text, 'disaster) "$K" module disable "$MID"; remove_hook local.xuanyuan.disastercompat;;',
        'disaster) "$K" module disable "$MID"; echo \'重启后预警挂载标记失效；在统一设置中关闭预警兼容，共享 APK 保留。\';;')
    text = replace_once(text, 'disaster) am start -n local.xuanyuan.disastercompat/.EntryActivity;;',
        'disaster) am start -n local.xuanyuan.mipushcompat/local.xuanyuan.disastercompat.EntryActivity;;')
    text = replace_once(text, ' calendar) am start -n com.android.calendar/.homepage.AllInOneActivity;;',
        ' calendar) am start -n com.android.calendar/.homepage.AllInOneActivity;;\n mipush) am start -n local.xuanyuan.mipushcompat/.Manager;;')
    text = replace_once(text, ' lsp) platform; "$K" module action zygisk_lsposed;;',
        ' settings) platform; am start -n local.xuanyuan.mipushcompat/local.xuanyuan.unified.SettingsActivity;;\n lsp) platform; "$K" module action zygisk_lsposed;;')
    text = text.replace('先把法定重复规则改回普通规则，再从 LSPosed 停用时钟补丁', '先把法定重复规则改回普通规则，再在统一设置中关闭时钟兼容；共享 APK 保留')
    text = replace_once(text, 'case "$1" in\n status)', 'case "$1" in\n library) [ "$#" = 1 ] || fail \'参数数量错误\';;\n preset) [ "$#" = 1 ] || fail \'参数数量错误\'; platform; integrity; am start -n local.xuanyuan.mipushcompat/local.xuanyuan.unified.PresetActivity;;\n status)')
    return text


def shared(text, apk_sha):
    text = replace_once(text, '@APK_SHA@', apk_sha)
    known = ' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] || [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_PREVIOUS_SHA" ]'
    return replace_once(text, known, known + ' || [ "$UNIFIED_LIVE_SHA" = "' + INITIAL_12_SHA + '" ] || [ "$UNIFIED_LIVE_SHA" = "' + REVISION_12_SHA + '" ] || [ "$UNIFIED_LIVE_SHA" = "cf8e6513f013351ef4d88bdd00f1a490da0bcba67b8a55263bcd57f8350140ac" ] || [ "$UNIFIED_LIVE_SHA" = "346ba49559a7ef1986d479a2f7acff5359c66c8ed4df099c90fa4885ba27e6ca" ]')


def webui(text):
    text = replace_once(text, '<button id="lsp" disabled>打开 LSPosed</button>',
        '<button id="lsp" disabled>打开 LSPosed</button><button id="settings" disabled>统一兼容与推送设置</button><button class="primary" id="preset" disabled>一键配置当前方案</button>')
    text = replace_once(text, "['status','job','lsp','reboot']", "['status','job','lsp','reboot','settings','preset']")
    text = replace_once(text, "  $('lsp').disabled = !host || !statusOK || busy || preparing;",
                        "  $('lsp').disabled = !host || !statusOK || busy || preparing;\n  $('settings').disabled = !host || !statusOK || busy || preparing;\n  $('preset').disabled = !writable();")
    text = replace_once(text, "$('lsp').addEventListener('click',", "$('settings').addEventListener('click',async () => { if(!host || !statusOK || busy || preparing) return; try{error('');await exec('settings');}catch(err){error(err.message);} });\n$('lsp').addEventListener('click',")
    text = replace_once(text, "$('settings').addEventListener('click',", "$('preset').addEventListener('click',async () => { if(!writable()) return; try{error('');await exec('preset');}catch(err){error(err.message);} });\n$('settings').addEventListener('click',")
    return text


def check_apk(path):
    require(path.is_file(), 'Unified APK not ready: ' + str(path))
    with zipfile.ZipFile(path) as z:
        names = archive_members(z)
        require('assets/xposed_init' not in names, 'Legacy Xposed entry forbidden')
        require(z.read('META-INF/xposed/java_init.list').decode().strip() == 'local.xuanyuan.unified.UnifiedModule', 'Unexpected unified entry')
        props = properties(z.read('META-INF/xposed/module.prop').decode())
        require(props.get('minApiVersion') == '102' and props.get('targetApiVersion') == '102', 'API102 required')
        require(z.read('META-INF/xposed/scope.list').strip() == b'', 'Default scope must stay empty')
        dex = b''.join(z.read(n) for n in names if re.fullmatch(r'classes\d*\.dex', n))
        require(dex and b'de/robv/android/xposed/' not in dex and b'de.robv.android.xposed.' not in dex,
                'Legacy Xposed references forbidden')
    tools = Path(os.environ.get('ANDROID_SDK_ROOT', '/opt/homebrew/share/android-commandlinetools')) / 'build-tools/36.0.0'
    badging = subprocess.run([str(tools / 'aapt2'), 'dump', 'badging', str(path)], check=True, capture_output=True, text=True).stdout
    require(re.search(r"^package: name='local.xuanyuan.mipushcompat' versionCode='13'", badging, re.M), 'Expected same-package v13 APK')
    manifest = subprocess.run([str(tools / 'aapt2'), 'dump', 'xmltree', str(path), '--file', 'AndroidManifest.xml'], check=True, capture_output=True, text=True).stdout
    for component in ('.Manager', 'local.xuanyuan.unified.SettingsActivity', 'local.xuanyuan.unified.PresetActivity', 'local.xuanyuan.disastercompat.EntryActivity'):
        require('"' + component + '"' in manifest, 'Missing component: ' + component)
    subprocess.run([str(tools / 'apksigner'), 'verify', str(path)], check=True, capture_output=True)
    return digest(path)


def calendar_restore_source():
    # Reuse the already verified 1.1 payload link after external-storage relocation.
    return SOURCE_MODULE / 'payload/calendar-global.apk'


def baseline():
    catalog = json.loads((SOURCE_MODULE / 'webroot/catalog.json').read_text())
    require([x['id'] for x in catalog] == ['market', 'assistant', 'xiaoai', 'phone', 'gallery', 'weather', 'disaster', 'wallet', 'clock', 'calendar'], 'Catalog baseline changed')
    known = {x['name']: x['sha256'] for x in json.loads((RELEASE / '本地化复用清单.json').read_text())['files']}
    for item in catalog:
        # Clock is no longer a source payload; its old SHA is documented in the baseline guide/build.py.
        if item['id'] == 'clock':
            require(item['sha256'] == '7c85575c3b32decdc5398d905d7a1d4f3655b9f1f3ee8cdbad59721d1521a073', 'Clock baseline changed')
            continue
        require(item['sha256'] == known.get(item['source']), 'Canonical manifest disagrees: ' + item['source'])
        source = RELEASE / item['source']
        require(digest(source) == item['sha256'], 'Release checksum mismatch: ' + item['source'])
    require(known.get('MiPushCompat-0.8.2-wallet-heartbeat-candidate.apk') == PREVIOUS_SHA, 'Previous APK baseline changed')
    require(digest(calendar_restore_source()) == GLOBAL_CALENDAR_SHA, 'Calendar restore payload mismatch')
    return catalog


def checksum_files(module):
    files = sorted(p for p in module.rglob('*') if p.is_file() and safe_name(p.relative_to(module).as_posix())
                   and p.name not in ('checksums.sha256', 'control.sha256'))
    control = module / 'control.sha256'
    control.write_text(''.join(f'{digest(p)}  {p.relative_to(module).as_posix()}\n' for p in files
                               if p.relative_to(module).parts[0] != 'payload' and p.name != 'customize.sh'))
    files.append(control)
    sums = module / 'checksums.sha256'
    sums.write_text(''.join(f'{digest(p)}  {p.relative_to(module).as_posix()}\n' for p in files))
    return sorted(files + [sums])


def stage(apk_sha, catalog):
    module = HERE / 'module'
    require(not module.exists(), 'Staging module already exists; inspect/remove only unified-bundle/module before retry')
    module.mkdir()
    (module / 'payload').mkdir()
    (module / 'webroot').mkdir()
    (module / 'guides').mkdir()
    for name in ('service.sh', 'runner.sh'):
        shutil.copyfile(SOURCE_MODULE / name, module / name)
    shutil.copyfile(HERE / 'customize.sh', module / 'customize.sh')
    shutil.copyfile(HERE / 'ROOT-README.txt', module / 'README.txt')
    shutil.copyfile(MIGRATION, module / 'migrate-legacy.sh')
    shutil.copyfile(HERE / 'preset.sh', module / 'preset.sh')
    (module / 'shared.sh').write_text(shared((HERE / 'shared.sh.in').read_text(), apk_sha))
    (module / 'control.sh').write_text(controller((SOURCE_MODULE / 'control.sh').read_text()))
    (module / 'webroot/index.html').write_text(webui((SOURCE_MODULE / 'webroot/index.html').read_text()))
    (module / 'module.prop').write_text('id=xuanyuan-os4-suite\nname=小米本地化套件 · 统一兼容与推送\nversion=1.4\nversionCode=2026101504\nauthor=XiaomiLocalSuite contributors\ndescription=EEA OS4.0.0.6 专用；11项组件，共享API102兼容APK；Root组件独立恢复，旧插件由用户迁移。\n')
    (module / 'skip_mount').touch()
    # Only these current guides enter the bundle. No directory-wide copying.
    for name in ('国行天气模块说明.txt', '国行相册模块说明.txt', '国行日历安装复用说明.txt'):
        override = ('【统一套件1.4 API102说明】\n一个LSP入口：local.xuanyuan.unified.UnifiedModule。\n'
                    '可用一键配置当前方案，或在统一设置中手动选择兼容开关并核对作用域；初始五项关闭。\n'
                    '旧文的独立兼容APK安装或多个LSP入口步骤按父模块README和统一套件1.4说明执行。\n'
                    '已有旧插件先暂存现代Root子模块，再由用户选择迁移；重启应用更新后配置唯一入口/开关/作用域并再重启。单项恢复保留共享APK。\n'
                    '下文的原厂应用、数据恢复与业务限制继续适用；历史实测不代表统一API102版本实机通过。\n\n')
        (module / 'guides' / name).write_text(override + (RELEASE / name).read_text())
    shutil.copyfile(HERE / 'GUIDE.txt', module / 'guides/统一套件1.4说明.txt')
    (module / 'payload/unified.apk').symlink_to(APK.resolve())
    (module / 'payload/calendar-global.apk').symlink_to((calendar_restore_source()).resolve())
    report, shell, owned = {}, ['# Generated from canonical release checksums.\nlookup() {\ncase "$1" in\n'], []
    # Preserve reviewed ownership hashes for Xiaomi packages; remove only the legacy hook packages.
    legacy_packages = {'local.xuanyuan.smscompat', 'local.xuanyuan.aiprivacy', 'local.xuanyuan.suggestioncompat', 'local.xuanyuan.disastercompat'}
    for line in (SOURCE_MODULE / 'owned-packages.txt').read_text().splitlines():
        if line.split('|')[1] not in legacy_packages:
            owned.append(line + '\n')
    entries = copy.deepcopy(catalog)
    entries.append(dict(id='mipush', title='MiPush 推送配置', version='1.2 API102', description='按应用选择推送兼容与诊断，配置保持用户选择', dependencies=[], scopes=['在统一 APK 的 MiPush 页面按应用申请作用域'], restoreLabel='在推送设置中停用', restoreNote='在 MiPush 页面取消所选适配；保留凭据和共享 APK，不提供自动重置。', restoreSupported=False, kind='apk'))
    for item in entries:
        key = item['id']
        mid, package, code = '', '', ''
        if key in ('clock', 'mipush'):
            filename = 'unified.apk'
            package = PKG
            item.update(sha256=apk_sha, bytes=APK.stat().st_size, source=APK.name, version='1.2 API102')
            if key == 'clock':
                item['restoreNote'] = '先将法定日期闹钟和作息改为普通重复，再在统一设置关闭时钟兼容；保留闹钟数据和共享 APK。'
                item['restoreLabel'] = '在统一设置停用'
        else:
            source = RELEASE / item['source']
            filename = key + ('.zip' if item['kind'] == 'module' else '.apk')
            target = module / 'payload' / filename
            if key in CHILDREN:
                report[key] = transform_child(key, source, target, item['sha256'], apk_sha)
                item.update(sourceArchive=item['source'], sourceSha256=item['sha256'], sha256=report[key]['sha256'], bytes=target.stat().st_size,
                            source=target.name, version=CHILDREN[key][2] + ' unified API102')
            else:
                target.symlink_to(source.resolve())
                report[key] = {'source_sha256': item['sha256'], 'sha256': item['sha256'], 'exact_bytes': True}
            if item['kind'] == 'module':
                with zipfile.ZipFile(target) as z:
                    props = properties(z.read('module.prop').decode())
                mid, code = props['id'], props['versionCode']
            else:
                package = 'com.android.calendar'
        if key in ('phone', 'xiaoai', 'disaster', 'clock'):
            item['scopes'] = ['统一兼容与推送设置中选择功能；作用域：' + s.split('：')[-1] for s in item['scopes']]
        item['file'] = 'payload/' + filename
        item['versionCode'] = code
        # Catalog strings are trusted reviewed titles, but quote them explicitly.
        def quote(value):
            return "'" + value.replace("'", "'\\''") + "'"
        values = dict(MID=mid, PKG=package, CODE=code, FILE=filename, SHA=item['sha256'], TITLE=item['title'], KIND=item['kind'])
        shell.append(key + ') ' + '; '.join(k + '=' + quote(v) for k, v in values.items()) + ';;\n')
    shell.append('*) return 1;;\nesac\n}\n')
    (module / 'catalog.sh').write_text(''.join(shell))
    (module / 'owned-packages.txt').write_text(''.join(owned))
    (module / 'webroot/catalog.json').write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n')
    files = checksum_files(module)
    return module, files, report


def build(expected_apk_sha):
    # Fail before creating staging or copying large payloads when main inputs are absent.
    require(bool(re.fullmatch(r'[0-9a-f]{64}', expected_apk_sha or '')), 'Main-confirmed --apk-sha is required')
    require(APK.is_file(), 'Unified APK not ready: ' + str(APK))
    require(digest(APK) == expected_apk_sha, 'APK differs from main-confirmed final hash')
    apk_sha = check_apk(APK)
    require(MIGRATION.is_file(), 'Main-owned migrate-legacy.sh not ready')
    subprocess.run(['/bin/sh', '-n', str(MIGRATION)], check=True)
    catalog = baseline()
    module, files, report = stage(apk_sha, catalog)
    for script in module.glob('*.sh'):
        if script.name.startswith('.'):
            continue
        subprocess.run(['/bin/sh', '-n', str(script)], check=True)
    output = HERE / 'xuanyuan-os4-suite-1.4.zip'
    require(not output.exists(), 'Refusing to overwrite existing suite artifact')
    pending = HERE / 'xuanyuan-os4-suite-1.4.zip.partial'
    require(not pending.exists(), 'Partial artifact already exists; inspect before retry')
    with zipfile.ZipFile(pending, 'w', zipfile.ZIP_STORED, allowZip64=True) as z:
        for path in files:
            z.write(path, path.relative_to(module).as_posix())
    # Verify what entered the ZIP, including symlink-backed sources that might change during packaging.
    expected = {}
    for line in (module / 'checksums.sha256').read_text().splitlines():
        sha, name = line.split('  ', 1)
        expected[name] = sha
    expected['checksums.sha256'] = digest(module / 'checksums.sha256')
    with zipfile.ZipFile(pending) as z:
        require(archive_members(z) == set(expected), 'Final ZIP membership mismatch')
        for name, sha in expected.items():
            with z.open(name) as stream:
                require(stream_digest(stream) == sha, 'Final ZIP checksum mismatch: ' + name)
    pending.replace(output)
    report = dict(artifact=str(output), bytes=output.stat().st_size, sha256=digest(output),
                  unified_apk_sha256=apk_sha, migration_sha256=digest(MIGRATION), sources=report,
                  baseline_files={name: digest(SOURCE_MODULE / name) for name in ('control.sh', 'catalog.sh', 'owned-packages.txt', 'customize.sh')},
                  device_verified=False)
    (HERE / 'build-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    (HERE / 'SHA256SUMS.txt').write_text(report['sha256'] + '  ' + output.name + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'sources'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true', help='explicitly stage and package large suite after main inputs are ready')
    parser.add_argument('--apk-sha', help='final SHA256 explicitly confirmed by main after Privacy hardening')
    args = parser.parse_args()
    if args.build:
        build(args.apk_sha)
    else:
        parser.print_help()
