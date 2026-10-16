"""Build the exact-ROM 1.6 selectable suite. Offline; never installs on a device."""
from pathlib import Path
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('paired_ui', HERE.parent / 'ui-release/build.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
SOURCE_SHA = 'a9e08dd1a312b1824e28903828a71c82f31a63e045a0ed01e25251cc0752d2e7'
CODE = '2026101602'
PARENT_CODE = '2026101603'
MARKET_4127_SHA = '1ac3be37cf56b29f417278903bca831e1623662e663b86b901316fae6fcebd10'
OLD_CODE = '2026101504'
IDS = ['market', 'assistant', 'xiaoai', 'phone', 'gallery', 'weather', 'disaster', 'clock', 'calendar', 'mipush']
CHILD_NAME = 'xuanyuan-os4-xiaoai-1.7.5-compatiblezip-api102.zip'
CERT = '625ac7776f26b9a616a458385d62643ea7660ad82c657ad958edf56937771953'


def controller(text):
    old = 'market\\|com.xiaomi.market\\|14dd58663e83d83dc6ab0f95af88be3d2b96ca28c651e3e8f7b0144807e4c05a'
    text = ui.once(text, old, old + '|market\\|com.xiaomi.market\\|' + MARKET_4127_SHA)
    text = ui.once(text, "ORDER='market assistant xiaoai phone gallery weather disaster wallet clock calendar mipush'", "ORDER='" + ' '.join(IDS) + "'")
    text, n = re.subn(r'(xuanyuan-os4-xiaoai\\\|[0-9]+\\\|)2026101504(\\\|install)', r'\g<1>' + CODE + r'\2', text)
    if n != 4:
        raise ValueError('Unexpected XiaoAI upgrade guards')
    line = '  xuanyuan-os4-xiaoai\\|2026101503\\|' + CODE + '\\|install) return 0;;'
    return ui.once(text, line, line + ''.join('\n  xuanyuan-os4-xiaoai\\|' + old + '\\|' + CODE + '\\|install) return 0;;' for old in [OLD_CODE, '2026101601']))


def preset(text):
    text = ui.once(text, "P_ORDER='market assistant xiaoai phone gallery weather disaster wallet clock calendar mipush'", "P_ORDER='" + ' '.join(IDS) + "'")
    text = text.replace('versionCode)" = ' + OLD_CODE, 'versionCode)" = ' + PARENT_CODE)
    text = ui.once(text, 'Requires suite 1.4 / ' + OLD_CODE, 'Requires suite 1.6.1 / ' + PARENT_CODE)
    return ui.once(text, 'xiaoai:' + OLD_CODE, 'xiaoai:' + CODE)


def bridge(old_hash, previous_hash, current_hash):
    return r'''
# Updating the shared APK must not strand an already enabled XiaoAI CLI.
X=/data/adb/modules/xuanyuan-os4-xiaoai
PAIR_XIAOAI=false
[ ! -d /data/adb/xuanyuan-os4-suite-state/lock ] && [ ! -d /data/adb/xuanyuan-unified-state/lock ] || abort '已有套件或迁移任务，请先完成'
if [ -f "$X/module.prop" ] && [ ! -e "$X/disable" ]; then
 [ ! -e "$X/remove" ] && [ ! -e "$X/update" ] && [ ! -d /data/adb/modules_update/xuanyuan-os4-xiaoai ] || abort '小爱有待处理更改，请先重启'
 [ "$(sed -n 's/^id=//p' "$X/module.prop")" = xuanyuan-os4-xiaoai ] || abort '小爱身份不匹配'
 XC=$(sed -n 's/^versionCode=//p' "$X/module.prop")
 XH=$(sha256sum "$X/privacy.sh" | cut -d' ' -f1)
 case "$XC:$XH" in
  2026101504:OLD_HASH|2026101601:PREVIOUS_HASH) PAIR_XIAOAI=true;;
  2026101602:CURRENT_HASH) ;;
  *) abort '当前小爱权限脚本未核对，保留原插件并停止；请先核对版本';;
 esac
fi
for XD in /data/adb/modules_update/* /data/adb/modules/*/update /data/adb/modules/*/remove; do
 [ -e "$XD" ] || continue
 [ "$XD" = "$MODPATH" ] || abort '其他模块有待处理更改，请先重启'
done
if [ "$PAIR_XIAOAI" = true ]; then
 ui_print '同步已启用小爱的权限CLI校验；不新增其他未选组件。'
 /data/adb/ksud module install "$MODPATH/payload/xiaoai.zip" || abort '小爱配套更新失败，未更新统一APK，请保留日志'
fi
'''.replace('OLD_HASH', old_hash).replace('PREVIOUS_HASH', previous_hash).replace('CURRENT_HASH', current_hash)


def changes(data, apk_sha, apk_bytes, child_sha, child_bytes, bridge_script=''):
    out = dict(data)
    shared = ui.once(out['shared.sh'].decode(), 'UNIFIED_SHA=' + ui.OLD_APK, 'UNIFIED_SHA=' + apk_sha)
    shared = ui.once(shared, ' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] ||',
        ' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] || [ "$UNIFIED_LIVE_SHA" = "' + ui.OLD_APK + '" ] || [ "$UNIFIED_LIVE_SHA" = "' + ui.NEW_APK + '" ] ||')
    out['shared.sh'] = shared.encode()
    migration = ui.once(out['migrate-legacy.sh'].decode(), 'SELF_SHA=' + ui.OLD_APK, 'SELF_SHA=' + apk_sha)
    out['migrate-legacy.sh'] = ui.once(migration, 'xiaoai) REQUIRED=' + OLD_CODE, 'xiaoai) REQUIRED=' + CODE).encode()
    out['control.sh'] = controller(out['control.sh'].decode()).encode()
    out['preset.sh'] = preset(out['preset.sh'].decode()).encode()
    catalog = ''.join(line + '\n' for line in out['catalog.sh'].decode().splitlines() if not line.startswith('wallet)'))
    catalog = ui.once(catalog, ui.OLD_CHILD, child_sha).replace(ui.OLD_APK, apk_sha)
    out['catalog.sh'] = ui.once(catalog, "CODE='" + OLD_CODE + "'", "CODE='" + CODE + "'").encode()
    out['owned-packages.txt'] = ''.join(line + '\n' for line in out['owned-packages.txt'].decode().splitlines() if not line.startswith('wallet|')).encode()
    rows = [r for r in json.loads(out['webroot/catalog.json']) if r['id'] != 'wallet']
    if [r['id'] for r in rows] != IDS:
        raise ValueError('Unexpected component catalog')
    for row in rows:
        if row['id'] == 'xiaoai':
            row.update(sha256=child_sha, bytes=child_bytes, version='1.7.5 full API102', versionCode=CODE, source=CHILD_NAME)
        elif row['id'] in ('clock', 'mipush'):
            row.update(sha256=apk_sha, bytes=apk_bytes, version='1.5 full API102', source='XuanyuanUnifiedCompat-1.5-full-nonwallet-api102.apk')
    out['webroot/catalog.json'] = (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode()
    prop = ui.once(out['module.prop'].decode(), 'version=1.4\n', 'version=1.6.1-selectable\n')
    prop = ui.once(prop, 'versionCode=' + OLD_CODE, 'versionCode=' + PARENT_CODE)
    out['module.prop'] = prop.replace('11项组件', '10项可选组件，钱包排除').encode()
    custom = out['customize.sh'].decode().replace('重启后打开1.4 WebUI的一键配置当前方案。', '重启后打开新版统一插件的组件配置，按需勾选并应用。')
    if bridge_script:
        custom = ui.once(custom, "shared_install || abort", bridge_script + "\nshared_install || abort")
    out['customize.sh'] = custom.encode()
    out['README.txt'] = ('小米本地化套件1.6.1：10项组件按需选择，统一API102入口。\n'
        '只支持xuanyuan / EEA OS4.0.0.6.XOAEUXM / Android17 API37 / 单用户0。\n'
        '刷入仅安装管理器和统一APK；重启后启用LSPosed统一插件，在组件配置勾选并应用，按计划分批安装及重启。\n'
        '电话依赖商店先安装并完成重启；小爱依赖智能助理。取消组件只跳过安装，不自动卸载；单项恢复使用WebUI。\n'
        '钱包负载、目录和所有安装/恢复入口排除；钱包UI不可选，继续单独验证，不自动重置任何凭据。\n'
        '已核对应用商店4.127.11与国行原包签名一致；只增加其精确SHA，不降级商店或放宽未知更新。\n'
        '保留既有数据；不自动接受协议、开启录音或报警、修改全局XMSF或LSP数据库。旧插件迁移仍需明确点击。\n'
        '新版统一APK1.5/code16；小爱1.7.5只调整精确统一APK校验，原厂负载保持。\n'
        '未在手机部署本新包；主机测试和旧子组件实测不代表全新系统已验证。详见发布目录的1.6说明及复用记录。\n').encode()
    out['guides/统一套件1.4说明.txt'] = out['README.txt']
    return out


def child_changes(z, apk_sha):
    text = ui.once(z.read('privacy.sh').decode(),
        '[ "$(sha256sum "$CLASSPATH" | cut -d\' \' -f1)" = ' + ui.OLD_APK + ' ] || exit 1',
        'case "$(sha256sum "$CLASSPATH" | cut -d\' \' -f1)" in\n ' + '|'.join([ui.OLD_APK, ui.NEW_APK, apk_sha]) + ') ;;\n *) exit 1;;\nesac')
    prop = ui.once(z.read('module.prop').decode(), 'version=1.7.3 (unified API102)', 'version=1.7.5 (full API102)')
    return {'privacy.sh':text.encode(), 'module.prop':ui.once(prop, 'versionCode=' + OLD_CODE, 'versionCode=' + CODE).encode()}


def write_archive(source, dest, replacements, excluded=()):
    sums = {}
    with zipfile.ZipFile(dest, 'w', allowZip64=True) as out:
        for info in source.infolist():
            name = info.filename
            if name in excluded or name == 'checksums.sha256':
                continue
            h = hashlib.sha256()
            # Android's native module extractor rejects forced ZIP64 on small entries.
            entry = copy.copy(info)
            entry.extract_version = entry.create_version = 20
            if entry.file_size >= 2**31:
                raise ValueError('This reviewed Android package requires classic ZIP entries below2GiB')
            with out.open(entry, 'w') as dst:
                raw = replacements.get(name)
                if isinstance(raw, bytes):
                    dst.write(raw); h.update(raw)
                else:
                    with raw.open('rb') if isinstance(raw, Path) else source.open(info) as src:
                        for block in iter(lambda: src.read(1024*1024), b''):
                            dst.write(block); h.update(block)
            sums[name] = h.hexdigest()
        out.writestr('checksums.sha256', ''.join(h+'  '+n+'\n' for n,h in sorted(sums.items())))
    ui.verify(dest)


def check_apk(apk, expected):
    if not re.fullmatch('[a-f0-9]{64}', expected) or ui.sha(apk) != expected:
        raise ValueError('Exact reviewed APK SHA required')
    tools = Path(os.environ.get('ANDROID_SDK_ROOT','/opt/homebrew/share/android-commandlinetools'))/'build-tools/36.0.0'
    cert = subprocess.check_output([str(tools/'apksigner'),'verify','--print-certs',str(apk)],text=True)
    badging = subprocess.check_output([str(tools/'aapt2'),'dump','badging',str(apk)],text=True)
    if CERT not in cert or not re.search(r"^package: name='local.xuanyuan.mipushcompat' versionCode='16'",badging,re.M):
        raise ValueError('Reviewed signing identity and version16 required')
    with zipfile.ZipFile(apk) as z:
        if z.read('META-INF/xposed/java_init.list').strip()!=b'local.xuanyuan.unified.UnifiedModule' or z.read('META-INF/xposed/scope.list').strip() or 'assets/xposed_init' in z.namelist():
            raise ValueError('One modern entry and empty default scope required')
        p=z.read('META-INF/xposed/module.prop').decode()
        if 'minApiVersion=102' not in p or 'targetApiVersion=102' not in p:
            raise ValueError('API102 required')


def build(source, apk, output, apk_sha):
    source,apk,output=map(Path,(source,apk,output))
    if ui.sha(source)!=SOURCE_SHA:
        raise ValueError('Only exact full1.4 source accepted')
    check_apk(apk,apk_sha)
    report_path=output.with_suffix('.build.json');child_path=output.with_name(CHILD_NAME)
    if any(p.exists() for p in [output,report_path,child_path]):
        raise ValueError('Existing artifacts never overwritten')
    output.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(output.parent).free < 3*1024**3:
        raise ValueError('Need 3GiB free for verified staging')
    ui.verify(source)
    with tempfile.TemporaryDirectory(prefix='.full16-',dir=output.parent) as temp, zipfile.ZipFile(source) as z:
        temp=Path(temp);child=temp/CHILD_NAME;pending=temp/output.name
        with z.open('payload/xiaoai.zip') as f,zipfile.ZipFile(f) as cz:
            child_edits=child_changes(cz,apk_sha)
            bridge_script=bridge(ui.digest(cz.read('privacy.sh')), ui.digest(ui.child_changes(cz)['privacy.sh']), ui.digest(child_edits['privacy.sh']))
            write_archive(cz,child,child_edits)
        child_sha=ui.sha(child)
        data={n:z.read(n) for n in z.namelist() if not n.startswith('payload/') and n not in ['control.sha256','checksums.sha256']}
        data=changes(data,apk_sha,apk.stat().st_size,child_sha,child.stat().st_size,bridge_script)
        data['control.sha256']=''.join(ui.digest(raw)+'  '+n+'\n' for n,raw in sorted(data.items()) if n!='customize.sh').encode()
        write_archive(z,pending,{**data,'payload/unified.apk':apk,'payload/xiaoai.zip':child},['payload/wallet.zip'])
        if ui.sha(source)!=SOURCE_SHA or ui.sha(apk)!=apk_sha:
            raise ValueError('Inputs changed during packaging')
        report={'version':'1.6.1-selectable','sha256':ui.sha(pending),'bytes':pending.stat().st_size,'source_sha256':SOURCE_SHA,'unified_apk_sha256':apk_sha,'xiaoai_sha256':child_sha,'components':IDS,'install_policy':'explicit-phone-selection-after-flash','wallet_included':False,'wallet_reset':False,'device_tested':False,'archive_format':'classic ZIP without forced ZIP64','rejected_previous_sha256':'4d14cb8a4e080e779f68f762debd21912a740eb00fa67691d3977e01a92e9c44'}
        # Same-filesystem rename publishes verified bytes without a second large copy.
        os.rename(child,child_path);os.rename(pending,output)
        with report_path.open('x') as f:f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('apk');p.add_argument('output');p.add_argument('--apk-sha',required=True)
    a=p.parse_args();print(json.dumps(build(a.source,a.apk,a.output,a.apk_sha),ensure_ascii=False,indent=2))
