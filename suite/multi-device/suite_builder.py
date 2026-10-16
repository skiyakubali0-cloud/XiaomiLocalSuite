#!/usr/bin/env python3
"""Offline, exact-profile suite builder. Never connects to or modifies a phone."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tempfile
import zipfile

import intake

HERE = Path(__file__).resolve().parent
VERSION = '0.5.0'
TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z')
PACKAGE = re.compile(r'[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
# These require device/framework/credential-specific recipes, never a plain APK overlay.
SENSITIVE = {'android', 'com.android.phone', 'com.android.server.telecom',
             'com.android.nfc', 'com.android.settings', 'com.android.systemui',
             'com.android.providers.telephony', 'com.android.providers.contacts',
             'com.android.providers.calendar', 'com.miui.securitycenter',
             'com.miui.home', 'com.xiaomi.xmsf', 'com.android.permissioncontroller',
             'com.google.android.permissioncontroller', 'com.miui.packageinstaller'}
WALLET_WORDS = ('mipay', 'tsm', 'wallet', 'secureelement', 'ese', 'nfc')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def path_of(value, base):
    require(isinstance(value, str) and value and '\x00' not in value, 'Missing material path')
    p = Path(value).expanduser()
    return (p if p.is_absolute() else base / p).resolve(strict=True)


def system_path(value):
    require(isinstance(value, str), 'Missing target system path')
    p = PurePosixPath(value)
    require(not p.is_absolute() and value == p.as_posix() and '..' not in p.parts,
            'Unsafe target path: ' + value)
    require(len(p.parts) >= 4 and p.parts[0] in ('system', 'product', 'system_ext')
            and p.parts[1] in ('app', 'priv-app') and value.endswith('.apk')
            and all(TOKEN.fullmatch(x) for x in p.parts), 'Only existing system APK paths allowed: ' + value)
    return value


def wallet(package):
    return any(part in package.lower() for part in WALLET_WORDS)


def identity(profile):
    require(profile.get('schema') == 1, 'Unsupported profile schema')
    require(TOKEN.fullmatch(profile.get('id', '')) is not None, 'Invalid profile id')
    t = profile.get('target', {})
    for k in ('device', 'incremental'):
        require(isinstance(t.get(k), str) and TOKEN.fullmatch(t[k]), 'Exact target ' + k + ' required')
    require(type(t.get('sdk')) is int and 21 <= t['sdk'] <= 99, 'Exact integer target sdk required')
    require(isinstance(t.get('abis'), list) and bool(t['abis']) and all(
        x in ('arm64-v8a', 'armeabi-v7a', 'x86', 'x86_64', 'riscv64') for x in t['abis']), 'Target ABI list required')
    require(profile.get('wallet_policy') == 'separate-validation-no-reset', 'Wallet must remain separate, no reset')
    return t


def scan_apk(path):
    result = intake.scan(Path(path))
    apks = result.get('apks', [])
    require(len(apks) == 1, 'Expected exactly one APK: ' + str(path))
    return apks[0]


def assess_component(component, target, base):
    errors = []
    try:
        require(isinstance(component.get('enabled'), bool), 'enabled must be boolean')
        require(TOKEN.fullmatch(component.get('id', '')) is not None, 'Invalid component id')
        package = component.get('package', '')
        require(PACKAGE.fullmatch(package), 'Invalid package name')
        require(not wallet(package), 'Wallet/NFC/TSM/eSE APK requires separate validation; automatic build forbidden')
        require(package not in SENSITIVE, 'Critical framework/telephony/security package requires a reviewed recipe')
        dst = system_path(component.get('target_path'))
        source = path_of(component.get('source_apk'), base)
        original = path_of(component.get('target_apk'), base)
        for key, file in [('source_sha256', source), ('target_sha256', original)]:
            require(isinstance(component.get(key), str) and SHA.fullmatch(component[key]), 'Missing material hash: ' + key)
            require(sha(file) == component[key], 'Material changed: ' + key)
        src, stock = scan_apk(source), scan_apk(original)
        for data in (src, stock):
            require(data.get('package') == package, 'APK package mismatch')
            require(data.get('metadata_complete') is True, 'APK manifest metadata incomplete')
            require(data.get('signature_verified') is True, 'APK signature verification incomplete')
            require(not data.get('split') and data.get('requires_splits') is False, 'Split APK/base dependencies need a separate reviewed recipe')
            require(data.get('signers_sha256') and all(SHA.fullmatch(x) for x in data['signers_sha256']), 'Verified APK signer missing')
            require(type(data.get('version_code')) is int and type(data.get('min_sdk')) is int, 'APK version/minSDK unknown')
            require(not data.get('errors'), 'APK metadata errors: ' + str(data.get('errors')))
        require(set(src['signers_sha256']) == set(stock['signers_sha256']), 'Signing certificate differs from target; no signature bypass')
        require(src.get('shared_user_id') == stock.get('shared_user_id'), 'sharedUserId mismatch')
        require(src['version_code'] >= stock['version_code'], 'Downgrade blocked to preserve existing data')
        require(src['min_sdk'] <= target['sdk'], 'APK minSDK exceeds target OS')
        require(not src.get('abis') or bool(set(src['abis']) & set(target['abis'])), 'Native ABI incompatible')
        for key in ('uses_libraries', 'requested_permissions'):
            require(key in src and key in stock, 'APK metadata missing ' + key)
            additions = set(src[key]) - set(stock[key])
            require(not additions, 'New ' + key + ' requires recipe review: ' + ', '.join(sorted(additions)))
        require(not src.get('uses_static_libraries') and not src.get('uses_sdk_libraries'), 'Static/SDK shared-library resolution requires review')
        return {'id': component['id'], 'package': package, 'state': 'static-pass',
                'source_sha256': component['source_sha256'], 'target_sha256': component['target_sha256'],
                'target_path': dst, 'source_version': src['version_code'], 'target_version': stock['version_code'],
                'source_apk': str(source), 'target_apk': str(original),
                'qualification': 'candidate-not-device-tested'}
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        errors.append(str(error))
    return {'id': component.get('id'), 'package': component.get('package'), 'state': 'blocked', 'errors': errors}


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate archive entries')
        for name in names:
            p = PurePosixPath(name)
            require(not p.is_absolute() and '..' not in p.parts and '\\' not in name,
                    'Unsafe archive entry')
        checks = archive.read('checksums.sha256').decode().splitlines()
        expected = {}
        for line in checks:
            digest, name = line.split('  ', 1)
            require(SHA.fullmatch(digest) and name not in expected, 'Invalid checksum manifest')
            expected[name] = digest
        require(set(expected) | {'checksums.sha256'} == set(names), 'Archive membership differs from checksums')
        for name, digest in expected.items():
            h = hashlib.sha256()
            with archive.open(name) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(chunk)
            require(h.hexdigest() == digest, 'Archive checksum failed: ' + name)


def check_profile(profile, base, materials=None):
    target = identity(profile)
    mode = profile.get('mode')
    if mode == 'selected-suite':
        import selected_suite
        return selected_suite.check(profile, base, materials)
    require(mode in ('reviewed-suite', 'apk-overlay'), 'Unknown profile mode')
    result = {'tool_version': VERSION, 'profile': profile['id'], 'mode': mode, 'target': target,
              'wallet': 'separate-validation-no-reset', 'device_tested': False,
              'warnings': ['Static checks do not prove runtime features or fresh-install behavior.'], 'components': []}
    if mode == 'reviewed-suite':
        # Registry is code shipped with the builder, not an arbitrary user-supplied qualification flag.
        registry = load(HERE / 'profiles/reviewed-recipes.json')
        known = registry.get(profile['id'])
        require(known is not None and known['target'] == target, 'No reviewed recipe for this exact target')
        require(profile.get('artifact_sha256') == known['artifact_sha256']
                and profile.get('artifact') == known['artifact'], 'Reviewed recipe differs from registry')
        path = path_of(profile['artifact'], Path(materials) if materials else base)
        require(sha(path) == known['artifact_sha256'], 'Reviewed suite artifact hash differs')
        verify_archive(path)
        result.update(state='reviewed-recipe', artifact=str(path), artifact_sha256=known['artifact_sha256'],
                      device_tested=known['device_tested'], fresh_install_tested=False,
                      warnings=result['warnings'] + ['Only exact reviewed suite bytes are reused; wallet first migration stays manual.'])
        return result
    require(profile.get('hooks', []) == [], 'LSP hook migration requires an exact reviewed suite recipe; API102 alone does not establish compatibility')
    require(isinstance(profile.get('components'), list) and profile['components'], 'No APK components; extract target/source firmware first')
    require(all(isinstance(c, dict) for c in profile['components']), 'Invalid component record')
    enabled = [c for c in profile['components'] if c.get('enabled') is not False]
    require(enabled, 'Select at least one component')
    require(len(enabled) <= 64, 'Too many components')
    require(len({c.get('id') for c in enabled}) == len(enabled), 'Duplicate component ids')
    require(len({c.get('package') for c in enabled}) == len(enabled), 'Duplicate package selection')
    require(len({c.get('target_path') for c in enabled}) == len(enabled), 'Duplicate mount destination')
    origin = profile.get('target_input')
    require(isinstance(origin, str), 'Target firmware provenance required')
    stock = intake.scan(path_of(origin, base))
    for key in ('device', 'sdk', 'incremental'):
        require(stock.get(key) == target[key], 'Target firmware ' + key + ' unknown or different from profile')
    require(stock.get('kind') in ('firmware-directory',), 'Extract the target firmware to a directory before overlay checks')
    require(set(stock.get('abis') or []) == set(target['abis']), 'Target ABI list unknown or differs from firmware')
    known_target = {str(Path(a['path']).resolve()): a for a in stock.get('apks', [])}
    for c in enabled:
        # A target_apk must really belong to the inspected target firmware, never an arbitrary source APK.
        try:
            original = path_of(c.get('target_apk'), base)
            entry = known_target.get(str(original))
            require(entry is not None and entry.get('partition_path') == c.get('target_path'), 'Target APK is not at this path in target firmware')
            item = assess_component(c, target, base)
        except (ValueError, OSError, TypeError) as error:
            item = {'id': c.get('id'), 'state': 'blocked', 'errors': [str(error)]}
        result['components'].append(item)
    result['state'] = 'blocked' if any(c['state'] == 'blocked' for c in result['components']) else 'candidate-static-pass'
    result['warnings'] += ['No new privileged permissions, SELinux rules or LSP hooks are inferred.',
                           'Disable candidate modules and reboot BEFORE OTA; post-fs-data checks are best-effort and cannot enforce the mount path deadline.',
                           'Wallet/TSM/eSE/NFC and global XMSF are never included in APK overlay recipes.']
    return result


def draft(profile_id, target_path, source_path):
    require(TOKEN.fullmatch(profile_id), 'Invalid profile id')
    target, source = intake.scan(Path(target_path)), intake.scan(Path(source_path))
    model = {key: target.get(key) for key in ('device', 'sdk', 'incremental', 'abis')}
    if source.get('device') and source['device'] != model['device']:
        raise ValueError('Source firmware belongs to a different device; not auto-ported')
    originals = {}
    for a in target.get('apks', []):
        originals.setdefault(a.get('package'), []).append(a)
    rows = []
    for i, a in enumerate(source.get('apks', [])):
        matches = originals.get(a.get('package'), [])
        original = matches[0] if len(matches) == 1 else {}
        package = a.get('package') or 'unknown'
        rows.append({'id': 'app' + str(i + 1), 'enabled': False, 'package': package,
                     'source_apk': a['path'], 'source_sha256': a['sha256'],
                     'target_apk': original.get('path'), 'target_sha256': original.get('sha256'),
                     'target_path': original.get('partition_path'),
                     'note': 'Wallet: separate validation only' if wallet(package) else
                             'Select explicitly; check before build. Missing/duplicate target means reviewed recipe required.'})
    return {'schema': 1, 'id': profile_id, 'mode': 'apk-overlay', 'target': model,
            'target_input': str(Path(target_path).resolve()), 'source_input': str(Path(source_path).resolve()),
            'wallet_policy': 'separate-validation-no-reset', 'hooks': [], 'components': rows,
            'note': 'All proposed components start disabled. Unknown values are not compatibility approval.'}


def q(value):
    return shlex.quote(str(value))


def overlay_files(profile, report):
    target = profile['target']
    checks = [f'[ "$(getprop {key})" = {q(target[field])} ] || abort \'Target ROM/device mismatch\''
              for key, field in [('ro.product.device', 'device'), ('ro.build.version.sdk', 'sdk'),
                                 ('ro.build.version.incremental', 'incremental')]]
    module_id = 'xiaomi-profile-' + profile['id']
    paths, extra = {}, []
    for c in report['components']:
        dst = c['target_path']
        paths[(dst if dst.startswith('system/') else 'system/' + dst)] = Path(c['source_apk'])
        mount = dst if dst.startswith('system/') else 'system/' + dst
        extra += ['for OTHER in /data/adb/modules/* /data/adb/modules_update/* /data/adb/metamodule/mnt/*; do',
                  '[ "$OTHER" = "$MODPATH" ] && continue',
                  f"[ ! -e \"$OTHER/{mount}\" ] || abort 'Another root module owns the target APK; restore it first'",
                  'done', f'P=$(pm path --user 0 {q(c["package"])} | sed -n \'s/^package://p\')',
                  f'[ "$P" = {q("/" + dst)} ] || abort \'Active APK moved, updated or split; not changing it\'',
                  f'[ "$(sha256sum "$P" | cut -d\' \' -f1)" = {q(c["target_sha256"])} ] || abort \'Live target APK differs from firmware\'']
    custom = '\n'.join(['#!/system/bin/sh', '[ "$KSU" = true ] || abort \'KernelSU required\'', *checks,
        '[ "$(am get-current-user)" = 0 ] && [ "$(pm list users | grep -c \'UserInfo{\')" = 1 ] || abort \'Single owner0 required\'',
        '[ -x /data/adb/metamodule/meta-overlayfs ] && [ -f /data/adb/modules/meta-overlayfs/module.prop ] && [ ! -e /data/adb/modules/meta-overlayfs/disable ] && [ ! -e /data/adb/modules/meta-overlayfs/remove ] || abort \'Active OverlayFS MetaModule required\'',
        '[ "$(sed -n \'s/^versionCode=//p\' /data/adb/modules/meta-overlayfs/module.prop)" = 13100 ] || abort \'Only reviewed OverlayFS 1.3.1 supported\'',
        '[ ! -e /data/adb/metamodule/modules.img ] || mountpoint -q /data/adb/metamodule/mnt || abort \'Overlay image must be mounted; reboot before installing\'',
        f'[ ! -e /data/adb/metamodule/mnt/{module_id} ] && [ ! -e /data/adb/modules/{module_id} ] || abort \'This profile already has module/image content; uninstall and reboot before changing selection\'',
        '(cd "$MODPATH" && sha256sum -c checksums.sha256) || abort \'Package checksum failure\'',
        *extra, 'set_perm_recursive "$MODPATH" 0 0 0755 0644',
        'set_perm "$MODPATH/post-fs-data.sh" 0 0 0755',
        "ui_print 'Candidate APK overlay only. Reboot to activate; disable this module and reboot to restore mounts.'",
        "ui_print 'No app-data, wallet, XMSF, permission, role or LSPosed settings changed.'", ''])
    prop = ('id=xiaomi-profile-' + profile['id'] + '\nname=Xiaomi APK candidate ' + profile['id'] +
            '\nversion=0.5.0-candidate\nversionCode=5\nauthor=local\ndescription=Exact-ROM APK overlay; static checks only; no wallet migration or data reset.\n')
    public = {'schema': 1, 'profile': profile['id'], 'target': target, 'qualification': report['state'],
              'wallet': report['wallet'], 'device_tested': False,
              'components': [{k: v for k, v in c.items() if not k.endswith('_apk')} for c in report['components']]}
    readme = ('APK静态检查候选包，未经过此机型实机验证。不是完整国行功能迁移。\n'
              '仅限profile.json中的精确机型与ROM、用户0、KernelSU及OverlayFS。\n'
              '安装器检查当前APK路径及SHA；已被应用商店更新、分包或未知版本时停止。\n'
              '安装后重启生效；恢复：在KernelSU禁用本模块并重启。不会卸载App或清理数据。\n'
              'OTA前必须先禁用候选模块并重启；post-fs-data检测依赖KSU调度时限，不能保证挂载路径强制拦截。\n'
              '改变本配置选择前须卸载原候选模块并重启，避免镜像残留。\n'
              '同一候选包内的APK一起恢复。需独立恢复时，每次只选一个组件分别生成ZIP。\n'
              '不处理钱包/TSM/eSE/NFC，不修改全局XMSF，不添加权限、SELinux规则或LSP钩子。\n'
              'AI、联网、帐号、服务端能力须另行验证。APK原始签名与字节不改写。\n')
    bootguard = '\n'.join(['#!/system/bin/sh', 'M=${0%/*}',
        'if ! (', *[line.split(' || abort ')[0] + ' &&' for line in checks[:-1]],
        checks[-1].split(' || abort ')[0], '); then',
        '  touch "$M/disable"',
        '  echo \'Pinned ROM/device differs; disable requested (post-fs-data scheduling dependent)\' > "$M/compatibility-blocked.txt"',
        'fi', ''])
    paths.update({'customize.sh': custom.encode(), 'post-fs-data.sh': bootguard.encode(), 'module.prop': prop.encode(),
                  'profile.json': (json.dumps(public, ensure_ascii=False, indent=2) + '\n').encode(),
                  'README.txt': readme.encode()})
    return paths


def build(profile, base, output, *, materials=None, candidate=False):
    if profile.get('mode') == 'selected-suite':
        import selected_suite
        return selected_suite.build(profile, base, output, materials)
    # Always recompute from real files. A saved report never authorizes a later build.
    report = check_profile(profile, base, materials)
    require(report['state'] != 'blocked', 'Compatibility checks failed; see check report')
    require(report['mode'] == 'reviewed-suite' or candidate, 'Unverified model: explicit --candidate required; no claim of runtime compatibility')
    output = Path(output)
    require(output.suffix == '.zip' and not output.exists(), 'Use a new .zip output path; stable artifacts are never overwritten')
    output.parent.mkdir(parents=True, exist_ok=True)
    require(not output.with_suffix('.build.json').exists(), 'Build evidence already exists')
    need = (Path(report['artifact']).stat().st_size if report['mode'] == 'reviewed-suite' else
            sum(Path(c['source_apk']).stat().st_size for c in report['components'])) * 2 + 32 * 1024 * 1024
    require(shutil.disk_usage(output.parent).free > need, 'Insufficient output disk space')
    fd, temporary = tempfile.mkstemp(prefix=output.name + '.', suffix='.partial', dir=output.parent)
    os.close(fd)
    pending = Path(temporary)
    try:
        if report['mode'] == 'reviewed-suite':
            shutil.copyfile(report['artifact'], pending)
            require(sha(pending) == report['artifact_sha256'], 'Source changed while exporting')
        else:
            files = overlay_files(profile, report)
            checksums = []
            with zipfile.ZipFile(pending, 'w', zipfile.ZIP_STORED) as archive:
                for name, content in sorted(files.items()):
                    if isinstance(content, Path):
                        expected = next(c['source_sha256'] for c in report['components'] if str(content) == c['source_apk'])
                        require(sha(content) == expected, 'Source APK changed during build')
                        archive.write(content, name)
                        digest = expected
                    else:
                        archive.writestr(name, content)
                        digest = hashlib.sha256(content).hexdigest()
                    checksums.append(digest + '  ' + name + '\n')
                archive.writestr('checksums.sha256', ''.join(checksums))
        verify_archive(pending)
        # link is an atomic no-overwrite publish on supported local/external filesystems.
        # open('xb') is used instead, because exFAT does not implement hard links.
        with output.open('xb') as stream, pending.open('rb') as source:
            try:
                shutil.copyfileobj(source, stream, 1024 * 1024)
            except BaseException:
                output.unlink(missing_ok=True)
                raise
        output_sha = sha(output)
        require(output_sha == sha(pending), 'Output changed during publish')
        public_report = {k: v for k, v in report.items() if k != 'artifact'}
        for c in public_report.get('components', []):
            c.pop('source_apk', None)
            c.pop('target_apk', None)
        public_report.update(output=output.name, sha256=output_sha, bytes=output.stat().st_size,
                             profile_sha256=hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest())
        write_new(output.with_suffix('.build.json'), public_report)
        return public_report
    finally:
        pending.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='小米套件多机型离线构建器；不连接手机、不自动重置钱包')
    sub = parser.add_subparsers(dest='action', required=True)
    inspect = sub.add_parser('inspect', help='检查APK/固件元数据，不等于功能兼容验证')
    inspect.add_argument('input', type=Path)
    inspect.add_argument('--out', type=Path)
    extract = sub.add_parser('extract', help='显式解包payload OTA的指定EROFS分区到新目录')
    extract.add_argument('input', type=Path)
    extract.add_argument('--out', type=Path, required=True)
    extract.add_argument('--partitions', default='product,system_ext,system')
    select = sub.add_parser('select', help='按包名选择组件并另存配置；不修改原配置')
    select.add_argument('--profile', type=Path, required=True)
    select.add_argument('--packages', required=True, help='逗号分隔包名，使用 - 表示全部取消')
    select.add_argument('--out', type=Path, required=True)
    init = sub.add_parser('init', help='为新机型生成默认不勾选的独立配置')
    init.add_argument('--id', required=True)
    init.add_argument('--target', type=Path, required=True)
    init.add_argument('--source', type=Path, required=True)
    init.add_argument('--out', type=Path, required=True)
    for name in ('check', 'build'):
        p = sub.add_parser(name)
        p.add_argument('--profile', type=Path, required=True)
        p.add_argument('--materials', type=Path, help='已审阅整合包所在目录')
        p.add_argument('--out', type=Path, required=True)
        if name == 'build':
            p.add_argument('--candidate', action='store_true', help='明确生成仅静态检查的新机型APK候选包')
    args = parser.parse_args()
    try:
        if args.action == 'inspect':
            result = intake.scan(args.input)
            if args.out:
                write_new(args.out, result)
        elif args.action == 'extract':
            result = intake.extract_apks(args.input, args.out, partitions=tuple(args.partitions.split(',')))
        elif args.action == 'select':
            result = load(args.profile)
            require(result.get('mode') == 'apk-overlay', 'Reviewed suites keep their existing phone selection UI')
            selected = [] if args.packages == '-' else args.packages.split(',')
            require(len(set(selected)) == len(selected) and all(PACKAGE.fullmatch(x) for x in selected), 'Invalid package selection')
            require(set(selected) <= {c['package'] for c in result['components']}, 'Unknown package selection')
            for c in result['components']:
                c['enabled'] = c['package'] in selected
                # Resolve before saving elsewhere so relative material paths do not change meaning.
                for key in ('source_apk', 'target_apk'):
                    if c.get(key): c[key] = str(path_of(c[key], args.profile.resolve().parent))
            for key in ('target_input', 'source_input'):
                if result.get(key): result[key] = str(path_of(result[key], args.profile.resolve().parent))
            write_new(args.out, result)
        elif args.action == 'init':
            result = draft(args.id, args.target, args.source)
            write_new(args.out, result)
        else:
            profile = load(args.profile)
            if args.action == 'check':
                result = check_profile(profile, args.profile.resolve().parent, args.materials)
                write_new(args.out, result)
            else:
                result = build(profile, args.profile.resolve().parent, args.out,
                               materials=args.materials, candidate=args.candidate)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get('state') == 'blocked' else 0
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(json.dumps({'state': 'blocked', 'error': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
