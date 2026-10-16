"""Select existing reviewed modules; never reinterpret an arbitrary ZIP as a recipe."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import suite_builder as b

IDS = ('market', 'assistant', 'xiaoai')
TITLES = ('小米应用商店', '智能助理负一屏', '超级小爱')
CHILD_SHA = dict(zip(IDS, (
    '1d53c4dd674930c1ed907e6b36aa71996b83860e48030fd9ba8be5ae9cb6ec1a',
    'd2535c0d026827b5aa0c0a801ce0badc30cae515d09eb52026a4a8a1b9893537',
    'e6bb2b36ba5e6ea4483b593c19c462d4e7ff9aba85802cbb1015bab9527f77f2')))
UNIFIED_SHA = '660cb1245fa9dac261d64570fba557ba44c166382960799b27bc130b59e14d25'
ORDER = 'market assistant xiaoai phone gallery weather disaster wallet clock calendar mipush'
SMALL = ('catalog.sh', 'control.sh', 'customize.sh', 'migrate-legacy.sh', 'module.prop',
         'runner.sh', 'service.sh', 'shared.sh', 'skip_mount', 'webroot/index.html')


def new_profile():
    p = b.load(b.HERE / 'profiles/xuanyuan-eea-os4.0.0.6.json')
    p['mode'] = 'selected-suite'
    p['install_policy'] = 'during-flash'
    p['components'] = [{'id': key, 'enabled': False} for key in IDS]
    return p


def selected(profile):
    rows = profile.get('components')
    b.require(isinstance(rows, list) and all(isinstance(c, dict) for c in rows)
              and [c.get('id') for c in rows] == list(IDS), 'Only the three reviewed components are selectable')
    b.require(all(type(c.get('enabled')) is bool for c in rows), 'Selection must be boolean')
    enabled = [c['id'] for c in rows if c['enabled']]
    b.require(enabled, 'Select at least one component')
    b.require('xiaoai' not in enabled or 'assistant' in enabled, '超级小爱依赖智能助理；请同时勾选智能助理')
    return enabled


def check(profile, base, materials=None):
    ids = selected(profile)
    b.require(profile.get('install_policy', 'during-flash') == 'during-flash', 'Unsupported installation policy')
    original = copy.deepcopy(profile)
    original['mode'] = 'reviewed-suite'
    result = b.check_profile(original, base, materials)
    b.require(profile.get('hooks', []) == [], 'Custom hooks are not part of this reviewed selection')
    with zipfile.ZipFile(result['artifact']) as z:
        catalog = {c['id']: c for c in json.loads(z.read('webroot/catalog.json'))}
        for key in ids:
            item = catalog[key]
            b.require(item['sha256'] == CHILD_SHA[key] and item['file'] == 'payload/' + key + '.zip', 'Reviewed child identity differs')
        b.require(hashlib.sha256(z.read('payload/unified.apk')).hexdigest() == UNIFIED_SHA, 'Shared API102 APK differs')
        size = sum(z.getinfo('payload/' + key + '.zip').file_size for key in ids) + z.getinfo('payload/unified.apk').file_size
    result.update(mode='selected-suite', state='reviewed-components', device_tested=False,
                  components=[{'id': key, 'title': TITLES[IDS.index(key)], 'state': 'reviewed-module',
                               'sha256': CHILD_SHA[key]} for key in ids], payload_bytes=size,
                  reused_payloads_from_device_tested_suite=True, install_policy='during-flash',
                  warnings=['Only exact existing module ZIPs and the API102 APK are reused.',
                            'The selected parent package has host checks only; it has not been installed.',
                            'No wallet payload, reset, global XMSF changes or automatic old-component removal.',
                            'Selected components install synchronously during flashing; LSPosed setup stays manual.',
                            'A failed child stops subsequent steps; completed staging is retained and reported.'])
    return result


def once(text, old, new):
    b.require(text.count(old) == 1, 'Selected recipe source contract changed: ' + old[:90])
    return text.replace(old, new, 1)


def files(z, ids):
    data = {n: z.read(n) for n in SMALL}
    catalog = [c for c in json.loads(z.read('webroot/catalog.json')) if c['id'] in ids]
    data['webroot/catalog.json'] = (json.dumps(catalog, ensure_ascii=False, indent=2) + '\n').encode()
    lookup = z.read('catalog.sh').decode().splitlines()
    data['catalog.sh'] = ('\n'.join(line for line in lookup if not any(line.startswith(key + ')')
        for key in ORDER.split() if key not in ids)) + '\n').encode()
    owned = z.read('owned-packages.txt').decode().splitlines()
    data['owned-packages.txt'] = ('\n'.join(line for line in owned if line.split('|')[0] in ids) + '\n').encode()
    controller = once(data['control.sh'].decode(), "ORDER='" + ORDER + "'", "ORDER='" + ' '.join(ids) + "'")
    controller = once(controller, 'for R in DIALER SMS ASSISTANT WALLET; do', 'for R in ASSISTANT; do')
    controller = once(controller,
        ' preset) [ "$#" = 1 ] || fail \'参数数量错误\'; platform; integrity; am start -n local.xuanyuan.mipushcompat/local.xuanyuan.unified.PresetActivity;;',
        " preset) fail '精选包已在刷入时安装所选组件；完整11项预设不可用';;")
    data['control.sh'] = controller.encode()
    # The original APK can still launch its full preset Activity. Its root helper
    # must fail before any component, feature, migration or reboot operation.
    data['preset.sh'] = b"#!/system/bin/sh\nprintf '%s\\n' 'Selected package: use its Root WebUI; full-suite preset is unavailable.' >&2\nexit 1\n"
    migrate = data['migrate-legacy.sh'].decode()
    old = "PACKAGES='local.xuanyuan.smscompat local.xuanyuan.aiprivacy local.xuanyuan.suggestioncompat local.xuanyuan.disastercompat local.xuanyuan.clockcompat'"
    new = "PACKAGES='local.xuanyuan.aiprivacy local.xuanyuan.suggestioncompat'" if 'xiaoai' in ids else "PACKAGES=''"
    migrate = once(migrate, old, new)
    migrate = once(migrate, "case \"$1\" in status|remove|restore) ;; *) fail '未知操作';; esac",
        "case \"$1\" in status) ;; remove|restore) fail '精选包不迁移旧插件；请用完整套件单独处理，不要在原统一设置点击迁移或恢复';; *) fail '未知操作';; esac")
    data['migrate-legacy.sh'] = migrate.encode()
    ui = data['webroot/index.html'].decode()
    ui = once(ui, '一键配置当前方案', '安装本包已选组件')
    ui = once(ui, "$('preset').addEventListener('click',async () => { if(!writable()) return; try{error('');await exec('preset');}catch(err){error(err.message);} });",
        "$('preset').addEventListener('click',() => { if(writable()) prepare('install',catalog.map(item => item.id)); });")
    ui = once(ui, "byId = new Map(catalog.map(item => [item.id,item]));", "byId = new Map(catalog.map(item => [item.id,item])); selected = new Set(catalog.map(item => item.id));")
    data['webroot/index.html'] = ui.encode()
    data['install-selected.sh'] = once((b.HERE / 'autoinstall.sh').read_text(),
                                       '@SELECTED_IDS@', ','.join(ids)).encode()
    custom = data['customize.sh'].decode()
    custom = once(custom, "shared_check || abort '统一兼容包存在未知版本或分包安装，保留原状并停止'\n", '')
    custom = once(custom, "shared_install || abort '统一兼容 APK 安装或校验失败，保留数据并停止'\n", '')
    custom = once(custom, '统一兼容与推送设置已安装；重启后打开1.4 WebUI的一键配置当前方案。',
                  '图形界面所选组件已同步安装，挂载将在手动重启后生效，无需再进WebUI安装。')
    custom = once(custom, '先启用唯一统一 LSP 插件；一键配置按勾选检查组件、兼容功能并请求作用域，按页面提示重启后继续。',
                  '超级小爱：在LSPosed启用统一API102插件，按说明开启AI识屏智控和小爱建议，核对作用域并重启。')
    custom = once(custom, "ui_print '图形界面所选组件已同步安装，挂载将在手动重启后生效，无需再进WebUI安装。'",
        'cd "$MODPATH" || abort \'无法进入父模块目录\'\n'
        'sh "$MODPATH/install-selected.sh" || abort \'所选组件安装失败，已停止后续步骤；可能已部分安装，查看/data/adb/xuanyuan-os4-suite-state/jobs中日志\'\n'
        '[ "$(cat "$MODPATH/install-selected.ok")" = "' + ','.join(ids) + '" ] || abort \'组件安装结果未确认\'\n'
        "ui_print '图形界面所选组件已同步安装，挂载将在手动重启后生效，无需再进WebUI安装。'")
    data['customize.sh'] = custom.encode()
    prop = data['module.prop'].decode()
    prop = once(prop, 'version=1.4\n', 'version=1.5-selected\n')
    prop = once(prop, 'versionCode=2026101504\n', 'versionCode=2026101505\n')
    prop = once(prop, 'description=EEA OS4.0.0.6 专用；11项组件，共享API102兼容APK；Root组件独立恢复，旧插件由用户迁移。',
                'description=EEA OS4.0.0.6 刷入同步安装：' + ','.join(ids) + '；共享API102；独立恢复；不含钱包。')
    data['module.prop'] = prop.encode()
    data['selection.json'] = (json.dumps({'schema': 1, 'components': ids, 'source_suite': '1.4',
        'source_sha256': b.load(b.HERE / 'profiles/reviewed-recipes.json')['xuanyuan-eea-os4.0.0.6']['artifact_sha256'],
        'wallet': 'excluded-no-reset', 'install_policy': 'during-flash', 'device_tested': False}, ensure_ascii=False, indent=2) + '\n').encode()
    data['README.txt'] = ('小米15 Ultra EEA OS4.0.0.6 / Android17 API37 精选整合包\n'
        '包含：' + '、'.join(TITLES[IDS.index(key)] for key in ids) + '。沿用完整1.4的原子模块ZIP及统一API102 APK原字节。\n'
        '只支持该精确机型/ROM及单机主用户0；需要KernelSU、OverlayFS，以及小爱所需的Zygisk和API102 LSPosed。\n'
        '刷入本ZIP时统一预检，然后同步按商店→智能助理→小爱顺序安装勾选组件；无需再进WebUI安装。挂载仍需安装完成后手动重启，不会自动重启。\n'
        '每个组件仍交给KernelSU原生安装器执行原ZIP；子模块ZIP不改写。运行库、桌面、AI引擎、元模块版本及任务锁在开始前检查。\n'
        '中途失败立即停止后续步骤并使父安装报错；先前完成的子模块或共享APK可能仍已安装/暂存，不作自动卸载、清数据或整体回滚。日志及started/completed保留在/data/adb/xuanyuan-os4-suite-state/jobs/flash-*。请核对日志后再处理，不盲目重复刷入。\n'
        '仅勾选商店/助理时不安装共享APK；包含小爱时沿用原共享APK安装与精确身份检查，保留其数据与现有选择。\n'
        '在LSPosed仅启用原统一插件local.xuanyuan.mipushcompat；超级小爱在统一设置按需开启AI识屏智控/小爱建议，作用域为系统框架、com.xiaomi.aicr、com.miui.personalassistant。\n'
        '共享设置仍是原版完整API102 APK，含其他功能入口；本包不安装其他组件，不要使用其完整11项一键预设，该Root路径已阻止。WebUI用于以后单独恢复或重新安装。\n'
        '若已有旧兼容插件，请先用完整1.4套件单独完成迁移和重启，再使用本包；精选包保留真实迁移状态检查，但拒绝旧插件迁移/恢复写入。不要点击原统一设置中的迁移/恢复，它在调用Root前会关闭全部五项兼容。\n'
        '各组件在Root WebUI单独恢复；先切换默认数字助理再停用小爱，恢复助理前先停用小爱。商店仍保护现有电话依赖。\n'
        '已有其他组件、兼容开关、推送配置和凭据不自动删除或重置；原统一APK保留全部功能，手动保存会发布全部五个当前复选值并合并现有推送作用域，请保留未选功能原值。共享APK所有手动入口并非仅三项隔离。\n'
        '钱包/TSM/eSE/NFC负载不在本包；无钱包重置、支付/卡片操作或全局XMSF修改。协议、账号登录、语音登记由用户处理。\n'
        '这是从现有已适配模块派生的可安装精选包；仅做主机命令替身与源码检查，未验证真实KernelSU嵌套刷入、重启或全新系统效果。\n'
        '与完整1.4使用同一父模块ID；以后安装会替换管理入口，但不自动卸载先前其他子模块。请保存完整1.4以便恢复完整管理目录。\n').encode()
    return data


def build(profile, base, output, materials=None):
    report = check(profile, base, materials)
    ids = [c['id'] for c in report['components']]
    output = Path(output)
    b.require(output.suffix == '.zip' and not output.exists(), 'Use a new .zip output path')
    b.require(not output.with_suffix('.build.json').exists(), 'Build evidence already exists')
    output.parent.mkdir(parents=True, exist_ok=True)
    b.require(shutil.disk_usage(output.parent).free > 2 * report['payload_bytes'] + 32 * 1024 * 1024, 'Insufficient output disk space')
    fd, name = tempfile.mkstemp(prefix=output.name + '.', suffix='.partial', dir=output.parent)
    os.close(fd)
    pending = Path(name)
    try:
        with zipfile.ZipFile(report['artifact']) as source, zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_STORED) as dest:
            data = files(source, ids)
            payloads = ['payload/' + key + '.zip' for key in ids] + ['payload/unified.apk']
            sums = {}
            for member in payloads:
                h = hashlib.sha256()
                with source.open(member) as src, dest.open(member, 'w') as dst:
                    for chunk in iter(lambda: src.read(1024 * 1024), b''):
                        h.update(chunk); dst.write(chunk)
                digest = h.hexdigest()
                b.require(digest == (UNIFIED_SHA if member.endswith('.apk') else CHILD_SHA[Path(member).stem]), 'Child changed while building')
                sums[member] = digest
            control = ''.join(hashlib.sha256(content).hexdigest() + '  ' + n + '\n'
                for n, content in sorted(data.items()) if n != 'customize.sh')
            data['control.sha256'] = control.encode()
            for n, content in sorted(data.items()):
                info = zipfile.ZipInfo(n); info.external_attr = (0o100755 if n.endswith('.sh') else 0o100644) << 16
                dest.writestr(info, content)
                sums[n] = hashlib.sha256(content).hexdigest()
            dest.writestr('checksums.sha256', ''.join(d + '  ' + n + '\n' for n, d in sorted(sums.items())))
        b.verify_archive(pending)
        b.require(b.sha(report['artifact']) == report['artifact_sha256'], 'Source changed during build')
        with output.open('xb') as dst, pending.open('rb') as src:
            try: shutil.copyfileobj(src, dst, 1024 * 1024)
            except BaseException:
                output.unlink(missing_ok=True); raise
        public = {k: v for k, v in report.items() if k != 'artifact'}
        public.update(output=output.name, sha256=b.sha(output), bytes=output.stat().st_size)
        b.require(public['sha256'] == b.sha(pending), 'Output changed during publish')
        b.write_new(output.with_suffix('.build.json'), public)
        return public
    finally:
        pending.unlink(missing_ok=True)
