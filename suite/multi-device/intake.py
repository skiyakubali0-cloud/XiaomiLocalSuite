"""Read local APK/firmware evidence; no device access or input-provided code.

Unknown scalar fields are None; unknown/empty collections are []. Warnings must
be considered by callers: this inventory is not a compatibility approval.
Source authenticity is always unknown, independently of APK signature checks.
Root symlinks are resolved, contained file links are allowed, directory links
are skipped. Concurrent modification of an input tree is unsupported.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import stat
import struct
import subprocess
import tempfile
import time
import zipfile


MAX_METADATA = 1024 * 1024
MAX_PROP_FILES = 128
MAX_TOTAL_PROPERTIES = 4 * MAX_METADATA
MAX_ENTRIES = 100000
MAX_APKS = 4096
MAX_OUTPUT = 2 * 1024 * 1024
EXCLUDED = {'private', 'data', 'user', 'testkeys', 'test-keys'}
PARTITIONS = ('product', 'system_ext', 'system', 'vendor', 'odm', 'oem')
OTA_METADATA = 'META-INF/com/android/metadata'


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _run(args, timeout=45):
    """Bound both subprocess runtime and combined output, without a shell."""
    with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT) as proc:
        try:
            deadline, output = time.monotonic() + timeout, bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise ValueError('tool timed out')
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_OUTPUT:
                        raise ValueError('tool output exceeds limit')
            code = proc.wait(timeout=max(0.01, deadline - time.monotonic()))
            text = output.decode('utf-8', errors='replace')
            if code:
                raise ValueError(f'tool exited {code}: {text[:500]}')
            return text
        except BaseException:
            proc.kill()
            proc.wait()
            raise


def _tool(name, explicit=None):
    if explicit is not None:
        return shutil.which(str(explicit))
    roots = [Path(os.environ[key]).expanduser() for key in
             ('ANDROID_SDK_ROOT', 'ANDROID_HOME') if os.environ.get(key)]
    # Use the lexical path too: this suite may live behind an external symlink.
    for base in dict.fromkeys((*Path(__file__).absolute().parents,
                              *Path(__file__).resolve().parents)):
        if base.name == 'rooting':
            roots.extend(sorted(base.glob('android-sdk*'))[:32])
    roots.extend((Path.home() / 'Library/Android/sdk',
                  Path('/opt/homebrew/share/android-commandlinetools')))
    for root in roots:
        for candidate in sorted((root / 'build-tools').glob(f'*/{name}'),
                                reverse=True):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate.resolve())
    return shutil.which(name)


def _zip(path):
    """Bound central-directory allocation before ZipFile parses untrusted input."""
    with path.open('rb') as source:
        source.seek(0, 2)
        size = source.tell()
        source.seek(max(0, size - 65557))
        tail = source.read(65557)
        end = tail.rfind(b'PK\x05\x06')
        if end < 0 or len(tail) - end < 22:
            raise ValueError('ZIP end record missing')
        fields = struct.unpack_from('<4s4H2LH', tail, end)
        _, disk, cd_disk, count_disk, count, cd_size, cd_offset, comment = fields
        if end + 22 + comment != len(tail) or disk or cd_disk or count_disk != count:
            raise ValueError('invalid or multi-disk ZIP')
        if count == 65535 or cd_size == 0xffffffff or cd_offset == 0xffffffff:
            source.seek(size - len(tail) + end - 20)
            locator = source.read(20)
            if len(locator) != 20:
                raise ValueError('ZIP64 locator missing')
            magic, disk, offset, disks = struct.unpack('<4sLQL', locator)
            if magic != b'PK\x06\x07' or disk or disks != 1:
                raise ValueError('invalid ZIP64 locator')
            source.seek(offset)
            raw = source.read(56)
            if len(raw) != 56:
                raise ValueError('ZIP64 end record missing')
            magic, length, _, _, disk, cd_disk, count_disk, count, cd_size, cd_offset = struct.unpack('<4sQ2H2L4Q', raw)
            if magic != b'PK\x06\x06' or length < 44 or disk or cd_disk or count_disk != count:
                raise ValueError('invalid ZIP64 end record')
        if count > MAX_ENTRIES or cd_size > 16 * MAX_METADATA or cd_offset + cd_size > size:
            raise ValueError('ZIP directory exceeds limit or file bounds')
    archive = zipfile.ZipFile(path)
    try:
        if len(archive.infolist()) > MAX_ENTRIES:
            raise ValueError('ZIP entry count exceeds limit')
        seen = set()
        for info in archive.infolist():
            name = info.filename
            parts = name.rstrip('/').split('/')
            if (not name or '\\' in name or '\x00' in info.orig_filename
                    or any(p in ('', '.', '..') or ':' in p for p in parts)
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError(f'unsafe ZIP entry: {name!r}')
            canonical = '/'.join(parts)
            if canonical in seen:
                raise ValueError(f'duplicate ZIP entry: {name!r}')
            seen.add(canonical)
        return archive
    except BaseException:
        archive.close()
        raise


def _properties(text, warnings, source):
    props = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            warnings.append(f'{source}: ignored malformed property')
            continue
        key, value = (part.strip() for part in line.split('=', 1))
        if key in props:
            warnings.append(f'{source}: duplicate property {key}')
        props.setdefault(key, set()).add(value)
    return props


def _one(values, name, warnings):
    values = set(values)
    if '' in values:
        warnings.append(f'{name}: empty evidence')
        return None
    if len(values) == 1:
        return next(iter(values))
    warnings.append(f'{name}: conflicting evidence' if values else f'{name}: unknown')
    return None


def _sdk(value, warnings):
    if value is not None and (len(value) > 4 or not value.isdecimal() or not 0 < int(value) < 10000):
        warnings.append('sdk: invalid numeric value')
        return None
    return int(value) if value is not None else None


def _fingerprint_devices(values, warnings):
    devices = set()
    for value in values:
        match = re.fullmatch(r'[^/\s]+/[^/\s]+/([^/:\s]+):[^/\s]+/[^/\s]+/[^:\s]+:[^/\s]+/[^\s]+', value)
        if match:
            devices.add(match[1])
        else:
            warnings.append('fingerprint: malformed')
    return devices


def _firmware_properties(files, root, warnings):
    """Resolve known init load paths; keep ambiguous files/duplicates fail-closed.

    Android init loads system, system_ext, vendor, odm, then product into a map
    before publishing properties. A partition fingerprint is not the whole
    device fingerprint. See platform/system/core/init/property_service.cpp.
    """
    load_paths = ('system/build.prop', 'system_ext/etc/build.prop',
                  'vendor/default.prop', 'vendor/build.prop',
                  'odm/etc/build.prop', 'product/etc/build.prop')
    ranked, unresolved, conflicts = {}, {}, {}
    for relative, properties in files:
        parts = relative.parts
        if root.name in PARTITIONS:
            parts = (root.name, *parts)
        if len(parts) > 2 and parts[0] == 'system' and parts[1] in PARTITIONS:
            parts = parts[1:]
        name = PurePosixPath(*parts).as_posix()
        for key, values in properties.items():
            if len(values) > 1:
                conflicts.setdefault(key, set()).update(values)
            if name not in load_paths:
                unresolved.setdefault(key, set()).update(values)
            else:
                rank = load_paths.index(name)
                previous = ranked.get(key)
                if previous is None or rank > previous[0]:
                    ranked[key] = (rank, values)
                elif rank == previous[0]:
                    ranked[key] = (rank, previous[1] | values)
    props = {key: set(values) for key, (_, values) in ranked.items()}
    for additional in (unresolved, conflicts):
        for key, values in additional.items():
            props.setdefault(key, set()).update(values)

    def canonical(key, field, fallback=()):
        values = props.get(key)
        if values is None:
            values = set().union(*(props.get(k, set()) for k in fallback))
        return _one(values, field, warnings)

    device = None
    if 'ro.product.device' in props:
        device = canonical('ro.product.device', 'device')
    else:
        order = canonical('ro.product.property_source_order', 'property_source_order') if 'ro.product.property_source_order' in props else 'odm,vendor,product,system_ext,system'
        if order and all(p in ('odm', 'vendor', 'product', 'system_ext', 'system') for p in order.split(',')):
            for partition in order.split(','):
                key = f'ro.product.{partition}.device'
                if key in props:
                    device = canonical(key, 'device')
                    break
        else:
            warnings.append('device: property source order unknown or invalid')
    sdk = canonical('ro.build.version.sdk', 'sdk',
                    (f'ro.{p}.build.version.sdk' for p in PARTITIONS))
    incremental = canonical('ro.build.version.incremental', 'incremental',
                            (f'ro.{p}.build.version.incremental' for p in PARTITIONS))
    fingerprint = canonical('ro.build.fingerprint', 'fingerprint')
    if 'ro.build.fingerprint' in props:
        devices = _fingerprint_devices(props['ro.build.fingerprint'], warnings)
        # Only the canonical fingerprint can corroborate the resolved device.
        if device:
            device = _one(devices | {device}, 'device', warnings) if devices else None
    abi = canonical('ro.product.cpu.abilist', 'abis') if 'ro.product.cpu.abilist' in props else None
    if 'ro.product.cpu.abilist' not in props:
        for partition in ('product', 'odm', 'vendor', 'system'):
            key = f'ro.{partition}.product.cpu.abilist'
            if key in props:
                abi = canonical(key, 'abis')
                break
    if not device:
        warnings.append('device: unknown or conflicting')
    if not abi:
        warnings.append('abis: unknown or conflicting')
    return dict(device=device, sdk=_sdk(sdk, warnings), incremental=incremental,
                fingerprint=fingerprint, abis=sorted(set(abi.split(','))) if abi else [])


def _manifest_libraries(manifest, result, warnings):
    """Read library names/required flags from aapt2's compiled XML tree."""
    current, attributes = None, {}

    def finish():
        if current == 'uses-split':
            result['requires_splits'] = True
            if not attributes.get('name'):
                warnings.append('uses-split: dependency name unknown')
        if current not in ('uses-library', 'uses-static-library', 'uses-sdk-library'):
            return
        name = attributes.get('name')
        if not name:
            warnings.append(f'{current}: library name unknown')
            return
        if current == 'uses-library':
            required = attributes.get('required', 'true')
            if required not in ('true', 'false', '0', '1', '(type 0x12)0x0', '(type 0x12)0xffffffff'):
                warnings.append(f'{current}: required flag unknown')
            key = 'optional_uses_libraries' if required in ('false', '0', '(type 0x12)0x0') else 'uses_libraries'
        else:
            key = 'uses_static_libraries' if current == 'uses-static-library' else 'uses_sdk_libraries'
        result[key] = sorted(set(result[key]) | {name})

    for line in manifest.splitlines():
        element = re.match(r'\s*E: ([\w-]+)', line)
        if element:
            finish()
            current, attributes = element[1], {}
        attribute = re.match(r'\s*A: (?:android:|http://schemas.android.com/apk/res/android:)([\w]+)(?:\([^)]*\))?=(.*)', line)
        if attribute:
            value = attribute[2].strip()
            quoted = re.match(r'"([^"]*)"', value)
            attributes[attribute[1]] = quoted[1] if quoted else value
    finish()


def _requires_splits(manifest, warnings):
    required, flags, types = False, set(), set()
    for attribute, raw in re.findall(
            r'(?:android:|http://schemas.android.com/apk/res/android:)'
            r'(isSplitRequired|requiredSplitTypes)(?:\([^)]*\))?=([^\n]*)', manifest):
        quoted = re.match(r'"([^"]*)"', raw.strip())
        value = quoted[1] if quoted else raw.strip()
        if attribute == 'isSplitRequired':
            if value in ('true', '1', '(type 0x12)0xffffffff'):
                flags.add(True)
                required = True
            elif value in ('false', '0', '(type 0x12)0x0'):
                flags.add(False)
            else:
                warnings.append('isSplitRequired: unresolved boolean')
                required = True
        else:
            if not quoted or value.startswith(('@', '?')):
                warnings.append('requiredSplitTypes: unresolved value')
                required = True
            types.add(value)
            required |= bool(value)
    if len(flags) > 1 or len(types) > 1:
        warnings.append('conflicting split requirement declarations')
    return required


def _apk(path, aapt2, apksigner, partition_path=None):
    warnings = []
    result = dict(path=str(path), sha256=_sha256(path), package=None,
                  version_code=None, min_sdk=None, target_sdk=None,
                  signers_sha256=[], abis=[], uses_libraries=[],
                  optional_uses_libraries=[], uses_static_libraries=[],
                  uses_sdk_libraries=[], requested_permissions=[],
                  shared_user_id=None, signature_verified=None,
                  metadata_complete=False, requires_splits=False,
                  source_authenticity='unknown', warnings=warnings)
    if partition_path:
        result['partition_path'] = partition_path
    try:
        with _zip(path) as archive:
            result['abis'] = sorted({p[1] for i in archive.infolist()
                                     if len(p := i.filename.split('/')) == 3
                                     and p[0] == 'lib' and p[2].endswith('.so')})
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        warnings.append(f'APK archive rejected: {exc}')
        return result
    if not aapt2:
        warnings.append('aapt2 unavailable; manifest metadata unknown')
    else:
        try:
            badging = _run([aapt2, 'dump', 'badging', str(path)])
            package = re.search(r'^package: (.*)$', badging, re.M)
            attrs = dict(re.findall(r"([\w-]+)='([^']*)'", package[1])) if package else {}
            if not re.fullmatch(r'[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*', attrs.get('name', ''), re.ASCII):
                raise ValueError('missing or invalid package name')
            result['package'] = attrs['name']
            version = attrs.get('versionCode', '')
            major = attrs.get('versionCodeMajor', '0')
            if (len(version) <= 10 and len(major) <= 10
                    and version.isdecimal() and major.isdecimal()
                    and int(version) <= 0xffffffff and int(major) <= 0xffffffff):
                result['version_code'] = (int(major) << 32) | int(version)
            else:
                warnings.append('version_code: unknown or nonnumeric')
            if attrs.get('split'):
                result['split'] = attrs['split']
            for labels, key in ((('sdkVersion', 'minSdkVersion'), 'min_sdk'), (('targetSdkVersion',), 'target_sdk')):
                values = set(re.findall(rf"^(?:{'|'.join(labels)}):'([^']*)'", badging, re.M))
                value = _one(values, key, warnings)
                result[key] = _sdk(value, warnings)
                if result[key] is None:
                    warnings.append(f'{key}: unknown or preview SDK')
            for label, key in (('uses-library', 'uses_libraries'),
                               ('uses-library-not-required', 'optional_uses_libraries')):
                result[key] = sorted(set(re.findall(rf"^{label}:(?: name=)?'([^']+)'", badging, re.M)))
            result['requested_permissions'] = sorted(set(re.findall(
                r"^uses-permission(?:-sdk-\d+)?: name='([^']+)'", badging, re.M)))
            manifest = _run([aapt2, 'dump', 'xmltree', str(path), '--file', 'AndroidManifest.xml'])
            if not re.search(r'^\s*E: manifest(?:\s|$)', manifest, re.M):
                raise ValueError('manifest XML tree missing')
            shared = re.findall(r'(?:android:|http://schemas.android.com/apk/res/android:)sharedUserId(?:\([^)]*\))?="([^"]+)"', manifest)
            if shared:
                result['shared_user_id'] = _one(shared, 'shared_user_id', warnings)
            elif re.search(r'(?:android:|http://schemas.android.com/apk/res/android:)sharedUserId', manifest):
                warnings.append('shared_user_id: unresolved manifest value')
            result['requires_splits'] = _requires_splits(manifest, warnings)
            _manifest_libraries(manifest, result, warnings)
            permissions = _run([aapt2, 'dump', 'permissions', str(path)])
            if not re.search(rf'^package: {re.escape(result["package"])}\s*$', permissions, re.M):
                raise ValueError('permissions dump missing matching package')
            result['requested_permissions'] = sorted(set(result['requested_permissions']) | set(re.findall(
                r"^uses-permission(?:-sdk-\d+)?: name='([^']+)'", permissions, re.M)))
            if set(result['uses_libraries']) & set(result['optional_uses_libraries']):
                warnings.append('conflicting required/optional library declarations')
            result['metadata_complete'] = not warnings
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            warnings.append(f'aapt2 metadata incomplete: {exc}')
    if not apksigner:
        warnings.append('apksigner unavailable; signature not verified')
    else:
        try:
            output = _run([apksigner, 'verify', '--verbose', '--print-certs', str(path)])
            digests = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})\s*$', output, re.M)
            if not digests:
                raise ValueError('no signer certificate digest returned')
            result['signers_sha256'] = sorted({d.lower() for d in digests})
            result['signature_verified'] = True
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result['signature_verified'] = False
            warnings.append(f'APK signature not verified: {exc}')
    return result


def _tree(root, warnings):
    pending, seen, count = [root], set(), 0
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                count += 1
                if count > MAX_ENTRIES:
                    raise ValueError('directory entry limit exceeded')
                if entry.name.lower() in EXCLUDED or entry.name.startswith('._'):
                    continue
                path = Path(entry.path)
                try:
                    resolved = path.resolve()
                except (OSError, RuntimeError) as exc:
                    warnings.append(f'unresolvable path skipped: {path}: {exc}')
                    continue
                if not resolved.is_relative_to(root):
                    warnings.append(f'escaping symlink skipped: {path}')
                    continue
                if any(p.lower() in EXCLUDED for p in resolved.relative_to(root).parts):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_symlink() and resolved.is_dir():
                    warnings.append(f'directory symlink skipped: {path}')
                elif resolved.is_file():
                    inode = (resolved.stat().st_dev, resolved.stat().st_ino)
                    if inode in seen:
                        warnings.append(f'duplicate file alias skipped: {path}')
                        continue
                    seen.add(inode)
                    yield resolved, resolved.relative_to(root)


def _partition_path(relative, root):
    parts = relative.parts
    # system/product and system/system_ext are common extracted-tree layouts.
    for index, part in enumerate(parts):
        if part in PARTITIONS and index + 1 < len(parts):
            if parts[index + 1] in ('app', 'priv-app'):
                return PurePosixPath(*parts[index:]).as_posix()
    if root.name in PARTITIONS and parts[0] in ('app', 'priv-app'):
        return PurePosixPath(root.name, *parts).as_posix()
    return None


def _check_apk_sets(apks, warnings):
    packages = {}
    for apk in apks:
        if apk['package']:
            packages.setdefault(apk['package'], []).append(apk)
    for package, group in packages.items():
        splits = [apk.get('split') for apk in group]
        if len(splits) != len(set(splits)):
            warnings.append(f'{package}: duplicate package/split identity')
        if any(splits) and splits.count(None) != 1:
            warnings.append(f'{package}: split set missing a unique base APK')
        if len({apk['version_code'] for apk in group}) > 1:
            warnings.append(f'{package}: inconsistent split/package versions')
        certs = {tuple(apk['signers_sha256']) for apk in group if apk['signature_verified']}
        if len(certs) > 1:
            warnings.append(f'{package}: inconsistent split/package signers')
        if any(splits) and any(apk['signature_verified'] is not True for apk in group):
            warnings.append(f'{package}: split set signature evidence incomplete')


def scan(input_path: Path, *, aapt2: str | None = None,
         apksigner: str | None = None) -> dict:
    """Inventory one APK, APK directory, OTA ZIP, or extracted firmware tree.

    Invalid archives are returned with warnings and no trusted metadata. Missing
    paths, unsupported file types, and exceeded directory limits raise errors.
    Files are hashed by streaming; metadata reads and tool output are bounded.
    """
    root = Path(input_path).expanduser().resolve(strict=True)
    if not root.is_dir() and not root.is_file():
        raise ValueError('input must be a regular file or directory')
    warnings = ['source authenticity unknown; certificate verification does not establish firmware provenance']
    result = dict(kind='apk-directory', path=str(root), device=None, sdk=None,
                  incremental=None, fingerprint=None, abis=[], apks=[],
                  source_authenticity='unknown', warnings=warnings)
    if root.is_file():
        result['sha256'] = _sha256(root)
        if root.suffix.lower() == '.apk':
            result['kind'] = 'apk'
            result['apks'] = [_apk(root, _tool('aapt2', aapt2), _tool('apksigner', apksigner))]
        else:
            result['kind'] = 'ota'
            try:
                with _zip(root) as archive:
                    info = archive.getinfo(OTA_METADATA)
                    if info.file_size > MAX_METADATA:
                        raise ValueError('OTA metadata exceeds limit')
                    with archive.open(info) as source:
                        raw = source.read(MAX_METADATA + 1)
                    if len(raw) > MAX_METADATA:
                        raise ValueError('OTA metadata exceeds limit')
                    props = _properties(raw.decode('utf-8'), warnings, OTA_METADATA)
                    fingerprints = props.get('post-build', set())
                    result['fingerprint'] = _one(fingerprints, 'fingerprint', warnings)
                    devices = props.get('pre-device', set()) | _fingerprint_devices(fingerprints, warnings)
                    devices = {d for value in devices for d in value.split('|')}
                    result['device'] = _one(devices, 'device', warnings)
                    result['sdk'] = _sdk(_one(props.get('post-sdk-level', set()), 'sdk', warnings), warnings)
                    result['incremental'] = _one(props.get('post-build-incremental', set()), 'incremental', warnings)
            except (OSError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
                warnings.append(f'OTA metadata unavailable: {exc}')
            warnings.append('OTA payload not inspected or extracted; APKs and ABIs unknown')
            return result
    else:
        apk_paths, prop_files = [], []
        prop_count = prop_bytes = 0
        for path, relative in _tree(root, warnings):
            if path.suffix.lower() == '.apk':
                apk_paths.append((path, _partition_path(relative, root)))
                if len(apk_paths) > MAX_APKS:
                    raise ValueError('APK count limit exceeded')
            elif path.name in ('build.prop', 'default.prop'):
                result['kind'] = 'firmware-directory'
                prop_count += 1
                if prop_count > MAX_PROP_FILES:
                    raise ValueError('build.prop count limit exceeded')
                try:
                    prop_bytes += min(path.stat().st_size, MAX_METADATA + 1)
                    if prop_bytes > MAX_TOTAL_PROPERTIES:
                        raise ValueError('total build.prop metadata exceeds limit')
                    with path.open('rb') as source:
                        raw = source.read(MAX_METADATA + 1)
                    if len(raw) > MAX_METADATA:
                        raise ValueError('build.prop exceeds limit')
                    prop_files.append((relative, _properties(raw.decode('utf-8'), warnings, str(path))))
                except (OSError, ValueError) as exc:
                    warnings.append(f'build.prop unreadable: {path}: {exc}')
        if any(partition for _, partition in apk_paths):
            result['kind'] = 'firmware-directory'
        result.update(_firmware_properties(prop_files, root, warnings))
        tool_aapt, tool_signer = _tool('aapt2', aapt2), _tool('apksigner', apksigner)
        result['apks'] = [_apk(path, tool_aapt, tool_signer, partition)
                          for path, partition in sorted(apk_paths)]
    if result['kind'] == 'apk':
        warnings.append('device, sdk, incremental and fingerprint unknown for standalone APK')
    if result['kind'] in ('apk', 'apk-directory'):
        result['abis'] = sorted({abi for apk in result['apks'] for abi in apk['abis']})
    else:
        result['derived_abis'] = sorted({abi for apk in result['apks'] for abi in apk['abis']})
    if not result['apks']:
        warnings.append('no APKs found')
    _check_apk_sets(result['apks'], warnings)
    return result


def _protobuf(data):
    """Iterate bounded payload-manifest fields without decoding operations."""
    if not isinstance(data, bytes):
        raise ValueError('invalid payload manifest field type')
    position = count = 0

    def varint():
        nonlocal position
        value = 0
        for shift in range(0, 70, 7):
            if position >= len(data):
                raise ValueError('truncated payload manifest varint')
            byte = data[position]
            position += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value
        raise ValueError('oversized payload manifest varint')

    while position < len(data):
        count += 1
        if count > MAX_ENTRIES:
            raise ValueError('payload manifest field count exceeds limit')
        key = varint()
        number, wire = key >> 3, key & 7
        if not number:
            raise ValueError('invalid payload manifest field number')
        if wire == 0:
            value = varint()
        else:
            size = varint() if wire == 2 else 8 if wire == 1 else 4 if wire == 5 else -1
            if size < 0 or position + size > len(data):
                raise ValueError('invalid payload manifest field bounds')
            value = data[position:position + size]
            position += size
        yield number, value


def _payload_sizes(archive, partitions):
    with archive.open('payload.bin') as source:
        header = source.read(24)
        if len(header) != 24:
            raise ValueError('truncated OTA payload header')
        magic, version, size, _ = struct.unpack('>4sQQI', header)
        if magic != b'CrAU' or version != 2 or size > 16 * MAX_METADATA:
            raise ValueError('only bounded version-2 full OTA payloads supported')
        manifest = source.read(size)
        if len(manifest) != size:
            raise ValueError('truncated OTA payload manifest')
    sizes = {}
    for field, value in _protobuf(manifest):
        if field == 12 and value != 0:
            raise ValueError('incremental OTA extraction unsupported')
        if field != 13:
            continue
        name = None
        image_size = None
        for tag, content in _protobuf(value):
            if tag == 6:
                raise ValueError('incremental OTA extraction unsupported (old partition info)')
            if tag == 1:
                if not isinstance(content, bytes):
                    raise ValueError('invalid payload partition name field')
                name = content.decode('ascii')
            if tag == 7:
                for info_tag, info_value in _protobuf(content):
                    if info_tag == 1:
                        image_size = info_value
        if (not name or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name)
                or name in sizes or image_size is not None
                and (not isinstance(image_size, int) or image_size < 0)):
            raise ValueError('invalid or duplicate payload partition metadata')
        sizes[name] = image_size
    if not set(partitions) <= sizes.keys():
        raise ValueError('requested partitions absent from payload manifest')
    if any(not sizes[partition] for partition in partitions):
        raise ValueError('selected payload partition must have a positive image size')
    return sum(sizes[partition] for partition in partitions)


def extract_apks(input_path, output_dir, *, partitions=('product', 'system_ext', 'system'),
                 payload_dumper=None, fsck_erofs=None, aapt2=None, apksigner=None):
    """Explicit opt-in full EROFS extraction into a NEW directory; never automatic.

    Explicitly stages the payload on the OUTPUT filesystem, never system temp.
    Preflight reserves payload + images + 4x image bytes for trees + 1 GiB.
    Tree expansion is an estimate; callers must supply adequate disk capacity.
    No download, overwrite, incremental OTA support, or device operation.
    Native extractors process untrusted firmware; run only on trusted local OTAs.
    Images/staging are removed on failure; output appears only after success.
    Returns scan(output_dir). APK certificates still do not prove OTA provenance.
    """
    partitions = tuple(partitions)
    if not partitions or len(set(partitions)) != len(partitions) or any(p not in PARTITIONS for p in partitions):
        raise ValueError('partitions must be unique known Android partition names')
    source = Path(input_path).expanduser().resolve(strict=True)
    output = Path(output_dir).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    with _zip(source) as archive:
        payload_info = archive.getinfo('payload.bin')
        image_bytes = _payload_sizes(archive, partitions)
        required = payload_info.file_size + 5 * image_bytes + 1024 ** 3
        free = shutil.disk_usage(output.parent).free
        if free < required:
            raise ValueError(f'insufficient extraction space on {output.parent}: '
                             f'{free} bytes free; {required} bytes required '
                             '(payload + images + estimated trees + reserve)')
    dumper = _tool('payload-dumper-go', payload_dumper)
    erofs = _tool('fsck.erofs', fsck_erofs)
    if payload_dumper is None and not dumper:
        dumper = shutil.which('/opt/homebrew/bin/payload-dumper-go')
    if fsck_erofs is None and not erofs:
        erofs = shutil.which('/opt/homebrew/bin/fsck.erofs')
    if not dumper or not erofs:
        raise FileNotFoundError('installed payload-dumper-go and fsck.erofs required')
    with tempfile.TemporaryDirectory(prefix='.intake-', dir=output.parent) as staging:
        staging = Path(staging)
        images, tree = staging / 'images', staging / 'tree'
        images.mkdir()
        tree.mkdir()
        payload = staging / 'payload.bin'
        with _zip(source) as archive, archive.open('payload.bin') as packed, payload.open('xb') as target:
            copied = 0
            while True:
                chunk = packed.read(1024 * 1024)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > payload_info.file_size:
                    raise ValueError('payload exceeds advertised size')
                target.write(chunk)
            if copied != payload_info.file_size:
                raise ValueError('payload size mismatch')
        _run([dumper, '-p', ','.join(partitions), '-o', str(images), str(payload)], timeout=1800)
        for partition in partitions:
            image = images / f'{partition}.img'
            if image.is_symlink() or not image.is_file():
                raise ValueError(f'missing regular partition image: {partition}')
            _run([erofs, f'--extract={tree / partition}', '--no-preserve', str(image)], timeout=1800)
        # Check the resulting tree while it is still disposable staging.
        list(_tree(tree.resolve(), []))
        if output.exists() or output.is_symlink():
            raise FileExistsError(output)
        tree.rename(output)
    return scan(output, aapt2=aapt2, apksigner=apksigner)
