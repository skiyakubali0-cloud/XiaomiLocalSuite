"""Resolve the exact 1.7 recipe from local stock files/APK members, never a suite ZIP."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

import build_suite as archive_tools

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'suite/multi-device'))
import intake


def recipe(source=ROOT):
    return json.loads((Path(source) / 'recipes/xuanyuan-1.7.json').read_text(encoding='utf-8'))


def selection(ids, source=ROOT):
    spec = recipe(source)
    allowed = [c['id'] for c in spec['components']]
    archive_tools.require(isinstance(ids, (list, tuple)) and ids and len(ids) == len(set(ids))
                          and all(i in allowed for i in ids), '请选择至少一个有效组件；不接受未知或重复 ID')
    selected = set(ids)
    for c in spec['components']:
        if c['id'] in selected:
            selected.update(c.get('requires', []))
    return [i for i in allowed if i in selected]


def firmware_identity(path):
    root = Path(path).expanduser().resolve(strict=True)
    archive_tools.require(root.is_dir(), '目标 OTA 请先显式解包到目录；不能用单 APK 代替目标固件')
    props, warnings, total = [], [], 0
    for file, relative in intake._tree(root, warnings):
        if file.name not in ('build.prop', 'default.prop'):
            continue
        archive_tools.require(len(props) < intake.MAX_PROP_FILES, '固件属性文件过多')
        with file.open('rb') as stream:
            raw = stream.read(intake.MAX_METADATA + 1)
        total += len(raw)
        archive_tools.require(len(raw) <= intake.MAX_METADATA and total <= intake.MAX_TOTAL_PROPERTIES,
                              '固件属性文件超过大小限制')
        props.append((relative, intake._properties(raw.decode('utf-8'), warnings, file.name)))
    return intake._firmware_properties(props, root, warnings), warnings


def validate_target(target, source=ROOT):
    identity, warnings = firmware_identity(target)
    expected = recipe(source)['target']
    archive_tools.require(all(identity.get(key) == value for key, value in expected.items()),
                          '完整 1.7 配方仅支持 xuanyuan EEA OS4.0.0.6.XOAEUXM / Android 17 / arm64-v8a')
    return identity, warnings


def required_materials(ids, source=ROOT):
    selected = selection(ids, source)
    lock, _ = archive_tools.load_lock(Path(source))
    return [item for item in lock['artifacts'] if item['component'] in selected
            or item['component'] == 'parent' and 'calendar' in selected and item['path'] != 'payload/unified.apk']


def material_label(item, source=ROOT):
    identities = json.loads((Path(source) / 'recipes/apk-materials.json').read_text(encoding='utf-8'))
    apk = identities.get(item['sha256'])
    if apk and apk['bytes'] == item['bytes']:
        return apk['package'] + ' · versionCode ' + str(apk['version_code'])
    return item['path']


def validate_plugin(path, source=ROOT, apk_checker=None):
    path, source = Path(path), Path(source)
    archive_tools.validate_apk_metadata(path)
    if apk_checker is None:
        signer, aapt = intake._tool('apksigner'), intake._tool('aapt2')
        archive_tools.require(signer and aapt, '统一插件校验需要 Android SDK apksigner 和 aapt2')
        archive_tools.check_apk(path, signer, aapt)
    else:
        apk_checker(path)
    evidence = json.loads(path.with_suffix('.build-evidence.json').read_text(encoding='utf-8'))
    archive_tools.require(evidence['apk_sha256'] == archive_tools.digest(path), '统一插件 APK 与构建记录不匹配')
    project = source / 'suite/unified-api102'
    inputs = [project / name for name in ('AndroidManifest.xml', 'build_apk.py', 'fetch_dependencies.py', 'deps.lock.json')]
    inputs += sorted(p for p in (project / 'src').rglob('*.java') if not p.name.startswith('._'))
    inputs += sorted(p for p in (project / 'META-INF/xposed').iterdir() if not p.name.startswith('._'))
    expected = {p.relative_to(project).as_posix(): archive_tools.digest(p) for p in inputs}
    archive_tools.require(evidence['sources'] == expected, '统一插件不是当前源码构建；请重新构建并选择配套记录')
    dependencies = json.loads((project / 'deps.lock.json').read_text())
    archive_tools.require(evidence['dependencies'] == {d['file']: d['sha256'] for d in dependencies},
                          '统一插件依赖记录不匹配')
    return archive_tools.digest(path)


class MaterialIndex:
    def __init__(self, expected):
        self.sizes = defaultdict(set)
        for sha, size in expected.items():
            self.sizes[size].add(sha)
        self.found = {}

    def add(self, path):
        path = Path(path)
        size = path.stat().st_size
        if size in self.sizes:
            sha = archive_tools.digest(path)
            if sha in self.sizes[size]:
                self.found.setdefault(sha, (path, None, size))
        if path.suffix.lower() != '.apk':
            return
        # APKs are containers only. Nothing imported is executed or installed.
        with intake._zip(path) as archive:
            # Android APK resource names are case-sensitive. Members are streamed
            # into hash-locked recipe destinations, never extracted by their names.
            for info in archive.infolist():
                name = info.filename
                if info.is_dir() or info.file_size not in self.sizes or not name.endswith(('.so', '.dex', '.jar')):
                    continue
                with archive.open(info) as stream:
                    sha = hashlib.file_digest(stream, 'sha256').hexdigest()
                if sha in self.sizes[info.file_size]:
                    self.found.setdefault(sha, (path, name, info.file_size))

    def scan(self, paths):
        for value in dict.fromkeys(map(str, paths)):
            root = Path(value).expanduser().resolve(strict=True)
            if root.is_file():
                archive_tools.require(root.suffix.lower() == '.apk', '材料文件仅接受 APK；OTA 请先解包，不接受旧模块 ZIP')
                self.add(root)
            else:
                for path, _ in intake._tree(root, []):
                    if path.suffix.lower() in ('.apk', '.so', '.jar', '.dex'):
                        self.add(path)

    def lookup(self, sha):
        found = self.found.get(sha)
        if found is None:
            return None
        path, member, size = found
        if member is None:
            with path.open('rb') as stream:
                raw = stream.read(size + 1)
        else:
            with intake._zip(path) as archive, archive.open(member) as stream:
                raw = stream.read(size + 1)
        archive_tools.require(len(raw) == size and hashlib.sha256(raw).hexdigest() == sha,
                              '材料在检查后发生变化；请重新导入并检查')
        return raw

    def copy(self, sha, output):
        path, member, size = self.found[sha]
        h, copied = hashlib.sha256(), 0
        with (intake._zip(path) if member else path.open('rb')) as source:
            stream = source.open(member) if member else source
            try:
                with output.open('xb') as target:
                    while raw := stream.read(1024 * 1024):
                        copied += len(raw)
                        archive_tools.require(copied <= size, '材料大小发生变化')
                        h.update(raw)
                        target.write(raw)
            finally:
                if member:
                    stream.close()
        archive_tools.require(copied == size and h.hexdigest() == sha, '材料在生成时发生变化；输出已停止')


def resolve(target, sources, ids, source=ROOT, generator=None):
    source = Path(source)
    identity, warnings = validate_target(target, source)
    archive_tools.require(sources, '请选择同机型国行固件解包目录或 APK 材料')
    for value in sources:
        if Path(value).is_dir():
            model, _ = firmware_identity(value)
            if model['device'] is not None:
                archive_tools.require(model['device'] == identity['device']
                                      and model['incremental'] in recipe(source)['source_roms'], '来源固件机型或版本不匹配')
    if generator is None:
        import recipe_generated as generator
    items = required_materials(ids, source)
    expected = {item['sha256']: item['bytes'] for item in items}
    expected.update(generator.INPUTS)
    index = MaterialIndex(expected)
    tool_cache = source / 'build/recipe-tools'
    index.scan([target, *sources, *([tool_cache] if tool_cache.is_dir() else [])])
    found, missing = {}, []
    for item in items:
        if item['sha256'] in index.found:
            found[(item['component'], item['path'])] = None
            continue
        reason = '缺少精确材料或其原始生成输入'
        try:
            raw = generator.generate(item, index.lookup)
        except ValueError as error:
            raw, reason = None, str(error)
        if raw is None:
            missing.append({**item, 'label': material_label(item, source), 'reason': reason})
        else:
            archive_tools.require(len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'],
                                  '生成材料与已审阅 1.7 哈希不匹配：' + item['path'])
            found[(item['component'], item['path'])] = raw
    return dict(target={k: identity[k] for k in recipe(source)['target']}, selected=selection(ids, source),
                items=items, found=found, missing=missing, warnings=warnings, index=index)


def check(target, sources, ids, unified_apk, source=ROOT, *, generator=None, apk_checker=None):
    resolved = resolve(target, sources, ids, source, generator)
    plugin_sha, errors = None, []
    try:
        plugin_sha = validate_plugin(unified_apk, source, apk_checker)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        errors.append('统一插件：' + str(error))
    rows = []
    for item in recipe(source)['components']:
        if item['id'] not in resolved['selected']:
            continue
        missing = [m for m in resolved['missing'] if m['component'] == item['id']
                   or item['id'] == 'calendar' and m['component'] == 'parent']
        rows.append(dict(id=item['id'], state='blocked' if missing else 'reviewed-materials',
                         errors=[m['reason'] + '：' + m['label'] + ' · ' + m['path']
                                 + ' · SHA256 ' + m['sha256'] for m in missing]))
    return dict(state='blocked' if resolved['missing'] or errors else 'reviewed-raw-materials', mode='xuanyuan-1.7',
                target=resolved['target'], selected=resolved['selected'], components=rows,
                missing=resolved['missing'], unified_sha256=plugin_sha, wallet_reset=False,
                auto_install_components=True, install_policy=recipe(source)['install_policy'],
                private_reference_required=False, device_tested=False, warnings=resolved['warnings'], errors=errors)


def build(target, sources, ids, unified_apk, output, source=ROOT, *, generator=None, apk_checker=None):
    # Re-read inputs and use verified snapshots; a saved report never supplies bytes.
    import recipe_assemble
    source, output = Path(source), Path(output)
    archive_tools.require(not output.exists() and not output.is_symlink(), '输出已经存在，不覆盖')
    validate_plugin(unified_apk, source, apk_checker)
    resolved = resolve(target, sources, ids, source, generator)
    archive_tools.require(not resolved['missing'], '所选组件材料缺失，请先检查完整缺项清单')
    output.parent.mkdir(parents=True, exist_ok=True)
    need = sum(item['bytes'] for item in resolved['items']) * 3 + 64 * 1024**2
    archive_tools.require(shutil.disk_usage(output.parent).free > need, '输出磁盘空间不足')
    with tempfile.TemporaryDirectory(prefix='.xls-recipe-', dir=output.parent) as temporary:
        root = Path(temporary)
        for item in resolved['items']:
            key = item['component'], item['path']
            path = root / key[0] / key[1]
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = resolved['found'][key]
            if raw is None:
                resolved['index'].copy(item['sha256'], path)
            else:
                path.write_bytes(raw)
        staged_apk = root / 'unified.apk'
        shutil.copyfile(unified_apk, staged_apk)
        shutil.copyfile(Path(unified_apk).with_suffix('.build-evidence.json'), staged_apk.with_suffix('.build-evidence.json'))
        validate_plugin(staged_apk, source, apk_checker)
        result = recipe_assemble.assemble(source, root, staged_apk, resolved['selected'], output,
                                         apk_checker=(apk_checker or (lambda p: validate_plugin(p, source))))
    result.update(state='reviewed-raw-materials', mode='xuanyuan-1.7', target=resolved['target'],
                  selected=resolved['selected'], private_reference_required=False, wallet_reset=False, device_tested=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'build'))
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--source', type=Path, action='append', required=True)
    parser.add_argument('--components', required=True, help='Comma-separated component IDs')
    parser.add_argument('--unified-apk', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        ids = args.components.split(',')
        if args.action == 'build':
            archive_tools.require(args.output is not None, 'build 需要 --output')
            result = build(args.target, args.source, ids, args.unified_apk, args.output)
        else:
            result = check(args.target, args.source, ids, args.unified_apk)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result['state'] == 'blocked' else 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print('配方检查失败：' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
