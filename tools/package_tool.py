#!/usr/bin/env python3
"""Package audited Git blobs as a deterministic, source-only desktop tool ZIP."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import zipfile

from check_public_tree import check

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.7.1'
TAG = 'tool-v' + VERSION
TITLE = 'XiaomiLocalSuite-Tool-' + VERSION
MANIFEST = 'SHA256SUMS'
METADATA = 'SOURCE.json'
ROOT_FILES = {'README.md', 'LICENSE', 'NOTICE', 'CONTRIBUTING.md', 'SECURITY.md',
              'THIRD_PARTY_NOTICES.md', 'materials.lock.json', 'launch.py'}
SOURCE_DIRS = {'clock', 'components', 'docs', 'launchers', 'native', 'phone', 'recipes', 'suite', 'tools',
               'xiaoai-privacy', 'xiaoai-suggestions'}
TEXT_SUFFIXES = {'.py', '.sh', '.command', '.cmd', '.md', '.txt', '.json', '.xml',
                 '.java', '.cpp', '.S', '.prop', '.in', '.html', '.js', '.css', '.list'}
TEXT_NAMES = {'skip_mount', 'use_china'}
EXCLUDED_PARTS = {'private', '.local-private', '__pycache__', 'deps', 'build', 'materials',
                  'releases', 'verification', 'dist', 'node_modules', '.venv', 'venv',
                  'artifacts', 'output', 'outputs', 'tmp', 'temp', 'gui-workspace'}
GENERATED_PREFIXES = ('host-', 'src-fixture-', 'test-work-')
WINDOWS_RESERVED = re.compile(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)', re.I)
POSIX_LAUNCHERS = {'launchers/macOS.command', 'launchers/linux.sh'}
REQUIRED_FILES = POSIX_LAUNCHERS | {
    'launch.py', 'launchers/windows.cmd', 'README.md', 'LICENSE', 'NOTICE',
    'docs/USER_GUIDE.md', 'docs/FULL_RECIPE.md', 'tools/package_tool.py', 'tools/check_public_tree.py',
    'docs/AUTOINSTALL_VALIDATION.md', 'docs/STOCK_APPS.md',
    'materials.lock.json', 'recipes/xuanyuan-1.7.json', 'recipes/generated.json', 'recipes/apk-materials.json',
    'tools/build_suite.py', 'tools/recipe_materials.py', 'tools/recipe_assemble.py',
    'tools/recipe_generated.py', 'tools/recipe_tools.py',
    'native/assistant/assistant-route.S', 'native/assistant/build-runtime-route.py',
    'suite/multi-device/gui.py', 'suite/multi-device/gui_session.py',
    'suite/multi-device/suite_builder.py', 'suite/multi-device/intake.py',
    'suite/multi-device/environment.py', 'suite/multi-device/selected_suite.py',
    'suite/multi-device/plugin_builder.py',
    'suite/multi-device/autoinstall.sh',
    'suite/unified-api102/build_apk.py', 'suite/unified-api102/fetch_dependencies.py',
    'suite/unified-api102/deps.lock.json', 'suite/unified-api102/AndroidManifest.xml',
    'suite/unified-api102/META-INF/xposed/java_init.list',
    'suite/unified-api102/META-INF/xposed/module.prop',
    'suite/unified-api102/META-INF/xposed/scope.list',
    'suite/module/control.sh', 'suite/module/preset.sh', 'suite/module/webroot/catalog.json',
    'suite/module/install-selected.sh',
    'suite/module/stock-apps.sh', 'components/phone/restore-stock.sh', 'components/phone/uninstall.sh',
    'suite/unified-api102/src/local/xuanyuan/unified/StockAppsActivity.java',
    'suite/multi-device/profiles/reviewed-recipes.json',
    'suite/multi-device/profiles/xuanyuan-eea-os4.0.0.6.json',
    'xiaoai-privacy/src/local/xuanyuan/aiprivacy/Manager.java',
    'xiaoai-privacy/src/local/xuanyuan/aiprivacy/PrivacyHook.java',
    'xiaoai-suggestions/hook/src/local/xuanyuan/suggestioncompat/SuggestionHook.java',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(repo, *args, input=None):
    return subprocess.run(['git', '-C', str(repo), *args], input=input,
                          check=True, capture_output=True).stdout


def safe_name(name):
    path = PurePosixPath(name)
    return (bool(name) and not path.is_absolute() and str(path) == name
            and all(part not in {'.', '..'} and not part.startswith('.')
                    and not part.endswith((' ', '.')) and not WINDOWS_RESERVED.match(part)
                    for part in path.parts)
            and not any(ord(c) < 32 or c in '\\:<>"|?*' for c in name))


def allowed(name):
    path = PurePosixPath(name)
    if any(part.lower() in EXCLUDED_PARTS or part.startswith(GENERATED_PREFIXES) for part in path.parts):
        return False
    return (name in ROOT_FILES or len(path.parts) > 1 and path.parts[0] in SOURCE_DIRS
            and (path.suffix in TEXT_SUFFIXES or path.name in TEXT_NAMES))


def audit(name, raw):
    require(safe_name(name), 'Unsafe or nonportable source path: ' + name)
    findings = check(name, raw)
    require(not findings, 'Public-tree audit failed: ' + str(findings))


def complete(files):
    missing = REQUIRED_FILES - files.keys()
    require(not missing, 'Incomplete tool source; missing: ' + ', '.join(sorted(missing)))
    for name in POSIX_LAUNCHERS:
        require(files[name][1] == 0o100755, 'POSIX launcher must be executable (Git mode 100755): ' + name)


def snapshot(repo, ref):
    commit = git(repo, 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}').decode().strip()
    entries = []
    for record in git(repo, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not record:
            continue
        header, raw_name = record.split(b'\t', 1)
        mode, kind, oid = header.decode('ascii').split()
        name = raw_name.decode('utf-8')
        require(mode in {'100644', '100755'} and kind == 'blob', 'Non-regular Git entry: ' + name)
        if allowed(name):
            entries.append((name, oid, int(mode, 8)))
    require(entries, 'No allowlisted source files in selected commit')
    payload = io.BytesIO(git(repo, 'cat-file', '--batch',
                           input=''.join(oid + '\n' for _, oid, _ in entries).encode('ascii')))
    files = {}
    for name, oid, mode in entries:
        actual_oid, kind, size = payload.readline().split()
        require(actual_oid.decode() == oid and kind == b'blob', 'Unexpected Git blob response')
        raw = payload.read(int(size))
        require(payload.read(1) == b'\n', 'Truncated Git blob response')
        audit(name, raw)
        files[name] = (raw, mode)
    require(len({name.casefold() for name in files}) == len(files), 'Case-insensitive source path collision')
    complete(files)
    files[METADATA] = ((json.dumps({'softwarecommit': commit, 'buildversion': VERSION},
                                  sort_keys=True, indent=2) + '\n').encode(), 0o100644)
    return files


def manifest(files):
    return ''.join(hashlib.sha256(raw).hexdigest() + '  ' + name + '\n'
                   for name, (raw, _) in sorted(files.items())).encode('utf-8')


def output_path(repo, output, source_names):
    output = Path(output).expanduser().absolute()
    require(not output.exists() and not output.is_symlink(), 'Output already exists')
    output = output.resolve()
    require(output.suffix.lower() == '.zip', 'Output must have a .zip extension')
    if output.is_relative_to(repo):
        relative = output.relative_to(repo).as_posix()
        tracked = {n.decode('utf-8') for n in git(repo, 'ls-files', '-z').split(b'\0') if n}
        for name in tracked | set(source_names):
            require(relative != name and not relative.startswith(name + '/')
                    and not name.startswith(relative + '/'), 'Output overlaps a tracked path')
        require(relative.startswith('releases/'), 'In-repository output must be under ignored releases/')
        ignored = subprocess.run(['git', '-C', str(repo), 'check-ignore', '--no-index', '-q', '--', relative])
        require(ignored.returncode == 0, 'In-repository output must be Git-ignored')
    return output


def package(repo, ref, output):
    repo = Path(repo).resolve()
    files = snapshot(repo, ref)
    output = output_path(repo, output, files)
    files[MANIFEST] = (manifest(files), 0o100644)
    require(len(files) <= zipfile.ZIP_FILECOUNT_LIMIT, 'Too many members for classic ZIP')
    for name, (raw, _) in files.items():
        audit(name, raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation avoids races and preserves existing files, even on failure.
    with output.open('xb') as stream:
        try:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
                for name, (raw, mode) in sorted(files.items()):
                    info = zipfile.ZipInfo(TITLE + '/' + name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = mode << 16
                    archive.writestr(info, raw)
        except BaseException:
            stream.close()
            output.unlink()
            raise
    return output


def verify(path):
    with zipfile.ZipFile(path, 'r', allowZip64=False) as archive:
        files = {}
        for info in archive.infolist():
            require(info.filename.startswith(TITLE + '/'), 'Unexpected ZIP root')
            name = info.filename[len(TITLE) + 1:]
            require(safe_name(name) and name not in files, 'Unsafe or duplicate ZIP member')
            require(info.external_attr >> 16 in {0o100644, 0o100755}, 'Non-regular or unsupported ZIP member mode')
            require(info.extract_version < 45 and not info.extra, 'Only classic ZIP members are supported')
            require(name in {METADATA, MANIFEST} or allowed(name), 'Member outside source allowlist')
            # The public-tree audit caps each source member at 1 MiB.
            require(info.file_size <= 1024 * 1024, 'Oversized ZIP member')
            raw = archive.read(info)
            audit(name, raw)
            files[name] = (raw, info.external_attr >> 16)
    require(len({name.casefold() for name in files}) == len(files), 'Case-insensitive ZIP path collision')
    require(MANIFEST in files and METADATA in files, 'Missing manifest or build metadata')
    sums = files.pop(MANIFEST)[0]
    require(sums == manifest(files), 'Manifest membership or SHA256 mismatch')
    complete(files)
    metadata = json.loads(files[METADATA][0])
    require(set(metadata) == {'softwarecommit', 'buildversion'} and metadata['buildversion'] == VERSION
            and isinstance(metadata['softwarecommit'], str)
            and re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', metadata['softwarecommit']), 'Invalid build metadata')
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=TAG)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path, help='new ZIP outside repository, or in ignored releases/')
    mode.add_argument('--verify', type=Path, metavar='ZIP', help='verify source allowlist, manifest and SHA256 offline')
    parser.add_argument('--ref', default='HEAD', help='committed source ref (default: HEAD), or ' + TAG)
    args = parser.parse_args(argv)
    if args.verify and args.ref != 'HEAD':
        parser.error('--ref is only used with --output')
    try:
        if args.verify:
            metadata = verify(args.verify)
            print('Verified {} source snapshot {}'.format(TAG, metadata['softwarecommit']))
        else:
            print('Created ' + str(package(ROOT, args.ref, args.output)))
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile,
            zipfile.LargeZipFile, UnicodeError) as error:
        # Do not echo subprocess output, which can contain private Git configuration.
        print('Packaging stopped: ' + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
