"""Pair the reviewed 1.4 UI APK with the exact, validated three-component 1.5."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import shutil
import tempfile
import zipfile

PARENT_SHA = '21e9ff3d81ac34c119f5ba81f4986c2e9fd43655eaf4ac19f66478e0014e1d8b'
OLD_APK = '660cb1245fa9dac261d64570fba557ba44c166382960799b27bc130b59e14d25'
NEW_APK = '9846373803f3e440372f014cb7bfa499636d99968bed278911ee75116c4d537b'
OLD_CHILD = 'e6bb2b36ba5e6ea4483b593c19c462d4e7ff9aba85802cbb1015bab9527f77f2'
CHILD_NAME = 'xuanyuan-os4-xiaoai-1.7.4-ui-api102.zip'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Pinned source contract changed: ' + old[:80])
    return text.replace(old, new, 1)


def verify(archive):
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive entries')
        sums = dict(line.split('  ', 1)[::-1] for line in z.read('checksums.sha256').decode().splitlines())
        if set(sums) != set(names) - {'checksums.sha256'}:
            raise ValueError('Manifest does not cover every entry')
        for name, expected in sums.items():
            with z.open(name) as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                    raise ValueError('Archive digest differs: ' + name)


def child_changes(z):
    privacy = z.read('privacy.sh').decode()
    privacy = once(privacy,
        '[ "$(sha256sum "$CLASSPATH" | cut -d\' \' -f1)" = ' + OLD_APK + ' ] || exit 1',
        'case "$(sha256sum "$CLASSPATH" | cut -d\' \' -f1)" in\n ' + OLD_APK + '|' + NEW_APK + ') ;;\n *) exit 1;;\nesac')
    prop = once(z.read('module.prop').decode(), 'version=1.7.3 (unified API102)', 'version=1.7.4 (unified UI API102)')
    prop = once(prop, 'versionCode=2026101504', 'versionCode=2026101601')
    return {'privacy.sh': privacy.encode(), 'module.prop': prop.encode()}


def write_child(source, target):
    changed = child_changes(source)
    sums = {}
    with zipfile.ZipFile(target, 'w') as out:
        for info in source.infolist():
            if info.filename == 'checksums.sha256':
                continue
            h = hashlib.sha256()
            with out.open(copy.copy(info), 'w') as dst:
                if info.filename in changed:
                    raw = changed[info.filename]
                    dst.write(raw); h.update(raw)
                else:
                    with source.open(info) as src:
                        for raw in iter(lambda: src.read(1024 * 1024), b''):
                            dst.write(raw); h.update(raw)
            sums[info.filename] = h.hexdigest()
        out.writestr(copy.copy(source.getinfo('checksums.sha256')),
                     ''.join(h + '  ' + n + '\n' for n, h in sorted(sums.items())))
    verify(target)


def parent_changes(data, child_sha, child_bytes):
    result = dict(data)
    shared = once(result['shared.sh'].decode(), 'UNIFIED_SHA=' + OLD_APK, 'UNIFIED_SHA=' + NEW_APK)
    shared = once(shared, ' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] ||',
                  ' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] || [ "$UNIFIED_LIVE_SHA" = "' + OLD_APK + '" ] ||')
    result['shared.sh'] = shared.encode()
    result['migrate-legacy.sh'] = once(result['migrate-legacy.sh'].decode(), 'SELF_SHA=' + OLD_APK, 'SELF_SHA=' + NEW_APK).encode()
    catalog = once(result['catalog.sh'].decode(), OLD_CHILD, child_sha)
    catalog = once(catalog, "CODE='2026101504'", "CODE='2026101601'")
    result['catalog.sh'] = catalog.encode()
    rows = json.loads(result['webroot/catalog.json'])
    row = next(r for r in rows if r['id'] == 'xiaoai')
    row.update(sha256=child_sha, bytes=child_bytes, version='1.7.4 unified UI API102',
               versionCode='2026101601', source=CHILD_NAME, previousPayloadSha256=OLD_CHILD)
    result['webroot/catalog.json'] = (json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode()
    control = result['control.sh'].decode()
    pattern = r'(xuanyuan-os4-xiaoai\\\|[0-9]+\\\|)2026101504(\\\|install)'
    control, count = re.subn(pattern, r'\g<1>2026101601\2', control)
    if count != 4:
        raise ValueError('Unexpected child upgrade allowlist')
    line = '  xuanyuan-os4-xiaoai\\|2026101503\\|2026101601\\|install) return 0;;'
    control = once(control, line, line + '\n  xuanyuan-os4-xiaoai\\|2026101504\\|2026101601\\|install) return 0;;')
    result['control.sh'] = control.encode()
    prop = once(result['module.prop'].decode(), 'version=1.5-selected', 'version=1.5.1-ui-selected')
    result['module.prop'] = once(prop, 'versionCode=2026101505', 'versionCode=2026101601').encode()
    selection = json.loads(result['selection.json'])
    selection.update(parent_source_sha256=PARENT_SHA, ui_apk_sha256=NEW_APK,
                     xiaoai_payload_sha256=child_sha, device_tested=False)
    result['selection.json'] = (json.dumps(selection, ensure_ascii=False, indent=2) + '\n').encode()
    readme = result['README.txt'].decode()
    readme = readme.replace('沿用完整1.4的原子模块ZIP及统一API102 APK原字节。',
                            '商店/助理子ZIP原字节保留；小爱子包仅修订权限CLI校验与版本元数据，共享APK为1.4界面修订。')
    readme = readme.replace('原版完整API102 APK', '保留完整功能的新版界面API102 APK')
    readme += '\n1.5.1界面配套：共享APK1.4；小爱1.7.4只更新权限CLI的精确APK校验和版本元数据。其APK与库均不改动。原1.2与本1.4界面APK可通过小爱CLI，未知APK仍拒绝。钱包不包含、不自动重置。此新父包尚未实机安装，原1.5实机结论不自动转移。\n'
    result['README.txt'] = readme.encode()
    return result


def build(source, apk, output):
    source, apk, output = map(Path, (source, apk, output))
    child_output = output.with_name(CHILD_NAME)
    report_output = output.with_suffix('.build.json')
    if sha(source) != PARENT_SHA or sha(apk) != NEW_APK:
        raise ValueError('Only the reviewed exact parent and UI APK are accepted')
    if any(p.exists() for p in (output, child_output, report_output)):
        raise ValueError('Use new output paths; existing artifacts are never overwritten')
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < 1500 * 1024 * 1024:
        raise ValueError('Need 1.5GB free for staged verification and exclusive publication')
    verify(source)
    with tempfile.TemporaryDirectory(prefix='.ui-suite-', dir=output.parent) as temp:
        child = Path(temp) / CHILD_NAME
        pending = Path(temp) / output.name
        with zipfile.ZipFile(source) as z:
            if json.loads(z.read('selection.json'))['components'] != ['market', 'assistant', 'xiaoai']:
                raise ValueError('Unexpected selected components')
            with z.open('payload/xiaoai.zip') as stream, zipfile.ZipFile(stream) as child_source:
                write_child(child_source, child)
            child_sha = sha(child)
            data = {n: z.read(n) for n in z.namelist() if not n.startswith('payload/') and n not in ('checksums.sha256', 'control.sha256')}
            data = parent_changes(data, child_sha, child.stat().st_size)
            data['control.sha256'] = ''.join(digest(raw) + '  ' + n + '\n' for n, raw in sorted(data.items()) if n != 'customize.sh').encode()
            replacements = {'payload/unified.apk': apk, 'payload/xiaoai.zip': child}
            sums = {}
            with zipfile.ZipFile(pending, 'w') as out:
                for info in z.infolist():
                    name = info.filename
                    if name == 'checksums.sha256':
                        continue
                    h = hashlib.sha256()
                    with out.open(copy.copy(info), 'w') as dst:
                        if name in data:
                            dst.write(data[name]); h.update(data[name])
                        else:
                            with replacements[name].open('rb') if name in replacements else z.open(info) as src:
                                for raw in iter(lambda: src.read(1024 * 1024), b''):
                                    dst.write(raw); h.update(raw)
                    sums[name] = h.hexdigest()
                out.writestr(copy.copy(z.getinfo('checksums.sha256')), ''.join(h + '  ' + n + '\n' for n, h in sorted(sums.items())))
        verify(pending)
        if sha(source) != PARENT_SHA or sha(apk) != NEW_APK:
            raise ValueError('Source changed during build')
        report = {'source_sha256': PARENT_SHA, 'apk_sha256': NEW_APK, 'xiaoai_sha256': child_sha,
                  'sha256': sha(pending), 'bytes': pending.stat().st_size, 'components': ['market', 'assistant', 'xiaoai'],
                  'wallet_included': False, 'device_tested': False, 'version': '1.5.1-ui-selected'}
        for src, dest in ((pending, output), (child, child_output)):
            with dest.open('xb') as dst, src.open('rb') as inp:
                shutil.copyfileobj(inp, dst, 1024 * 1024)
        with report_output.open('x') as f:
            f.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source'); parser.add_argument('apk'); parser.add_argument('output')
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.apk, args.output), indent=2))
