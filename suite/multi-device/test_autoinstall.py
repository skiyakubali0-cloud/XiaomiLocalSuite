"""Host-only execution of generated customize -> helper -> real control CLI worker.

Run: python3 -B -m unittest test_autoinstall -v
Reads only the three reviewed children from pinned real 1.4, never wallet.
Android absolute paths are relocated; small opaque payload fixtures replace ZIPs
and their catalog digests. Guards/dispatch/worker/tee/exit traps are unchanged.
Command doubles cannot qualify native nested KSU, OverlayFS, or reboot behavior.
"""
from __future__ import annotations
from contextlib import contextmanager
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import gui_session
import selected_suite as s
import suite_builder as b

SOURCE = Path(os.environ.get('SELECTED_SUITE_SOURCE', str(
    b.HERE.parent / 'unified-bundle/xuanyuan-os4-suite-1.4.zip')))
PIN = 'a9e08dd1a312b1824e28903828a71c82f31a63e045a0ed01e25251cc0752d2e7'
RUNTIME = {
    '/system_ext/lib64/libhyper_os_core_system_private.dylib.so':
        'a7de453780f33d2dec0cfca8832d218ee798f3208df06af36744f416313afa1f',
    '/apex/com.android.runtime/lib64/bionic/libc.so':
        'f6c25ea4d8b9a4dc76d6964f78edc9831cd676837a8f91d93a1cb4e87808e32e',
    '/system_ext/framework/miui-services.jar':
        'cef17afe99cfa6396922e2fe1dce6642ec86ddcf141589b8ef4d007d6920ecdb',
    '/apks/com.xiaomi.aicr.apk':
        'f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520',
    '/data/adb/metamodule/mnt/xuanyuan-os4-assistant/product/priv-app/MiuiHome/MiuiHome.apk':
        'b5e9aaa1ef1f052e3b9e31c685ff201436700728d5fc52d9d56d0c9326fdfa9c',
}
MOCK = r'''
import hashlib, json, os, pathlib, sys
root = pathlib.Path(os.environ['AUTO_TEST_ROOT'])
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
config = json.loads((root / 'config.json').read_text())
with (root / 'calls').open('a') as out:
    out.write(json.dumps([name] + args) + '\n')
def unexpected():
    with (root / 'unexpected').open('a') as out:
        out.write(repr([name] + args) + '\n')
    sys.exit(97)
def sha(path):
    key = '/' + str(pathlib.Path(path).relative_to(root))
    if key in config.get('hashes', {}): return config['hashes'][key]
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
if name == 'getprop':
    props = {'ro.product.device':'xuanyuan', 'ro.build.version.sdk':'37',
             'ro.build.version.incremental':'OS4.0.0.6.XOAEUXM', 'sys.boot_completed':'1'}
    props.update(config.get('props', {}))
    print(props.get(args[0], ''))
elif name == 'id' and args == ['-u']: print(config.get('uid', '0'))
elif name == 'am' and args == ['get-current-user']: print(config.get('user', '0'))
elif name == 'pm' and args == ['list', 'users']:
    print('UserInfo{0:Owner:13} running')
    if config.get('multiuser'): print('UserInfo{10:Other:10}')
elif name == 'pm' and args == ['list', 'libraries']:
    if not config.get('no_misys'): print('library:vendor.xiaomi.hardware.misys.V3_0')
elif name == 'pm' and args[:3] == ['path', '--user', '0']:
    pkg = args[3]
    if pkg == 'local.xuanyuan.mipushcompat':
        if config.get('shared') in ('unknown', 'split') or (root / 'shared-installed').exists():
            print('package:' + str(root / 'apks/shared.apk'))
            if config.get('shared') == 'split': print('package:' + str(root / 'apks/split.apk'))
    elif pkg == 'com.xiaomi.aicr':
        if not config.get('no_engine'):
            print('package:' + str(root / 'apks/com.xiaomi.aicr.apk'))
            if config.get('split_engine'): print('package:' + str(root / 'apks/split.apk'))
    else: unexpected()
elif name == 'pm' and args[:2] == ['list', 'packages']:
    pkg = args[-1]
    if pkg == 'local.xuanyuan.mipushcompat':
        if config.get('shared') == 'uninstalled': print('package:' + pkg)
    elif pkg in ('com.xiaomi.market', 'com.miui.personalassistant', 'com.miui.voiceassist'):
        print('package:' + pkg)
    elif not pkg.startswith('com.'): unexpected()
elif name == 'pm' and args[:1] == ['install']:
    raw = sys.stdin.buffer.read()
    if config.get('fail_pm_install'): print('Failure [fixture]'); sys.exit(1)
    (root / 'apks/shared.apk').write_bytes(raw)
    (root / 'shared-installed').touch()
    print('Success')
elif name == 'pm' and args[:1] in (['unhide'], ['enable']):
    if config.get('fail_pm') == ':'.join(args): sys.exit(1)
elif name == 'dumpsys' and args == ['package', 'com.miui.home']:
    print('    versionCode=' + config.get('launcher', '801027654') + ' minSdk=37')
elif name == 'cmd' and args[:2] == ['role', 'get-role-holders']: pass
elif name == 'ksud' and args == ['module', 'list']: print('[]')
elif name == 'ksud' and len(args) == 3 and args[:2] == ['module', 'install']:
    key = pathlib.Path(args[2]).stem
    with (root / 'native-cwds').open('a') as out: out.write(str(pathlib.Path.cwd()) + '\n')
    if config.get('clear_nested_tmp'):
        import shutil
        shutil.rmtree(root / 'dev/tmp', ignore_errors=True)
    print('fixture native install ' + key, flush=True)
    if config.get('fail_child') == key: sys.exit(23)
elif name == 'busybox' and args[:1] in (['awk'], ['tee']):
    if args[0] == 'tee' and config.get('tee_fail'): sys.exit(24)
    if args[0] == 'tee' and config.get('leave_lock'):
        raw = sys.stdin.buffer.read()
        pathlib.Path(args[1]).write_bytes(raw)
        sys.stdout.buffer.write(raw)
        (root / 'data/adb/xuanyuan-os4-suite-state/lock').mkdir(exist_ok=True)
    else: os.execv('/usr/bin/' + args[0], [args[0]] + args[1:])
elif name == 'mountpoint': sys.exit(1 if config.get('unmounted') else 0)
elif name == 'df' and args == ['-Pk', str(root / 'data')]:
    print('Filesystem 1024-blocks Used Available Capacity Mounted on')
    print('/dev/mock 67108864 1 ' + str(config.get('free', 16777216)) + ' 1% ' + str(root / 'data'))
elif name == 'stat' and len(args) == 3 and args[:1] == ['-c']:
    info = pathlib.Path(args[2]).stat()
    print(info.st_size if args[1] == '%s' else int(info.st_mtime))
elif name == 'sha256sum':
    try:
        if args[:1] == ['-c']:
            for line in pathlib.Path(args[1]).read_text().splitlines():
                expected, filename = line.split(None, 1)
                if sha(pathlib.Path(filename).absolute()) != expected: sys.exit(1)
        elif len(args) == 1: print(sha(args[0]) + '  ' + args[0])
        else: unexpected()
    except (OSError, ValueError): sys.exit(1)
else: unexpected()
'''


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class AutoinstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The open-source distribution excludes private OEM-containing archives.
        if not SOURCE.exists() and os.environ.get("RUN_SELECTED_SUITE_INTEGRATION") != "1":
            raise unittest.SkipTest("Private reference1.4 archive not supplied; set RUN_SELECTED_SUITE_INTEGRATION=1 to require it")
        # Explicit private-material integration runs still fail if input is unavailable.
        if b.sha(SOURCE) != PIN:
            raise AssertionError('Real 1.4 source differs from pinned reviewed archive')
        with zipfile.ZipFile(SOURCE) as archive:
            for key in s.IDS:
                h = hashlib.sha256()
                with archive.open('payload/' + key + '.zip') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''): h.update(chunk)
                if h.hexdigest() != s.CHILD_SHA[key]: raise AssertionError(key)
            if digest(archive.read('payload/unified.apk')) != s.UNIFIED_SHA:
                raise AssertionError('Shared APK differs')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='autoinstall-host-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = {'hashes': dict(RUNTIME)}
        self.module = self.root / 'module'
        self.state = self.root / 'data/adb/xuanyuan-os4-suite-state'
        self.modules = self.root / 'data/adb/modules'
        self.bin = self.root / 'bin'
        for p in (self.module, self.modules, self.bin, self.root / 'apks', self.root / 'dev/tmp'):
            p.mkdir(parents=True, exist_ok=True)
        self.mock = self.bin / 'mock.py'
        self.mock.write_text('#!' + sys.executable + '\n' + MOCK)
        self.mock.chmod(0o700)
        for name in ('getprop', 'id', 'am', 'pm', 'dumpsys', 'cmd', 'ksud', 'busybox',
                     'mountpoint', 'df', 'stat', 'sha256sum', 'reboot', 'adb', 'fastboot',
                     'settings', 'sqlite3', 'su'):
            (self.bin / name).symlink_to(self.mock)
        # This whitelist excludes host adb/su/reboot and all Android tools.
        for name in ('cat', 'cut', 'sed', 'head', 'tail', 'grep', 'tr', 'mkdir', 'rmdir',
                     'rm', 'date', 'awk', 'sh', 'tee'):
            (self.bin / name).symlink_to(shutil.which(name))
        for path in ('data/adb/ksud', 'data/adb/ksu/bin/busybox',
                     'data/adb/metamodule/meta-overlayfs'):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(self.mock)
        for key in ('meta-overlayfs', 'zygisksu', 'zygisk_lsposed'):
            self.enable(key, '13100' if key == 'meta-overlayfs' else '1')
        self.boot = self.root / 'boot-id'
        self.boot.write_text('fixture-boot\n')
        (self.root / 'apks/com.xiaomi.aicr.apk').write_bytes(b'engine fixture')
        (self.root / 'apks/shared.apk').write_bytes(b'unknown shared fixture')
        self.protected = {}
        for relative in ('data/user/0/com.mipay.wallet/databases/sentinel',
                         'data/user/0/com.xiaomi.xmsf/shared_prefs/sentinel',
                         'data/adb/lspd/config/modules_config.db',
                         'data/adb/xuanyuan-unified-state/prefs.xml'):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            self.protected[path] = b'untouched ' + relative.encode()
            path.write_bytes(self.protected[path])
        self.env = {'PATH': str(self.bin), 'AUTO_TEST_ROOT': str(self.root),
                    'MODPATH': str(self.module), 'KSU': 'true', 'TMPDIR': str(self.root / 'dev/tmp')}
        self.ids = list(s.IDS)

    def enable(self, key, code='1'):
        path = self.modules / key
        path.mkdir(exist_ok=True)
        (path / 'module.prop').write_text('id=' + key + '\nversionCode=' + code + '\n')
        return path

    def generate(self, ids=None):
        self.ids = list(ids if ids is not None else s.IDS)
        with zipfile.ZipFile(SOURCE) as archive:
            data = s.files(archive, self.ids)
        self.assertIn('install-selected.sh', data, 'Production integration is not present')
        for key in self.ids:
            raw = b'opaque reviewed child fixture: ' + key.encode()
            data['payload/' + key + '.zip'] = raw
            data['catalog.sh'] = data['catalog.sh'].replace(s.CHILD_SHA[key].encode(), digest(raw).encode())
        shared = b'opaque shared APK fixture'
        data['payload/unified.apk'] = shared
        data['shared.sh'] = data['shared.sh'].replace(s.UNIFIED_SHA.encode(), digest(shared).encode())
        self.original = dict(data)
        for name, raw in data.items():
            if name.endswith('.sh'):
                text = raw.decode()
                for prefix in ('/data', '/system_ext/', '/apex/', '/dev/tmp'):
                    text = text.replace(prefix, str(self.root) + prefix)
                text = text.replace('/proc/sys/kernel/random/boot_id', str(self.boot))
                raw = text.encode()
            target = self.module / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        self.seal()

    def seal(self):
        files = {str(p.relative_to(self.module)): p.read_bytes() for p in self.module.rglob('*')
                 if p.is_file() and p.name not in ('checksums.sha256', 'control.sha256', 'install-selected.ok')}
        controls = {name: raw for name, raw in files.items() if name != 'customize.sh' and not name.startswith('payload/')}
        control = ''.join(digest(raw) + '  ' + name + '\n' for name, raw in sorted(controls.items())).encode()
        (self.module / 'control.sha256').write_bytes(control)
        files['control.sha256'] = control
        (self.module / 'checksums.sha256').write_text(''.join(
            digest(raw) + '  ' + name + '\n' for name, raw in sorted(files.items())))

    def calls(self):
        path = self.root / 'calls'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def writes(self):
        return [c for c in self.calls() if c[:3] == ['ksud', 'module', 'install'] or
                c[:2] in (['pm', 'install'], ['pm', 'enable'], ['pm', 'unhide'])]

    def installed(self):
        return [Path(c[-1]).stem for c in self.calls() if c[:3] == ['ksud', 'module', 'install']]

    def run_entry(self, success=None):
        (self.root / 'calls').unlink(missing_ok=True)
        (self.root / 'config.json').write_text(json.dumps(self.config))
        script = 'abort() { echo "ABORT: $*" >&2; exit 1; }; ' \
                 'ui_print() { printf "%s\\n" "$*"; }; ' \
                 'set_perm() { :; }; set_perm_recursive() { :; }; . "$MODPATH/customize.sh"; ' \
                 'pwd > "$AUTO_TEST_ROOT/parent-cwd"'
        result = subprocess.run(['/bin/sh', '-c', script], cwd=self.root / 'dev/tmp', env=self.env,
                                text=True, capture_output=True, timeout=20)
        self.assertFalse((self.root / 'unexpected').exists(),
                         (self.root / 'unexpected').read_text() if (self.root / 'unexpected').exists() else '')
        for path, raw in self.protected.items():
            self.assertEqual(path.read_bytes(), raw)
        for call in self.calls():
            self.assertNotIn(call[0], ('reboot', 'adb', 'fastboot', 'settings', 'sqlite3', 'su'))
            self.assertNotIn('wallet', ' '.join(call).lower())
            if call[0] == 'pm': self.assertIn(call[1], ('list', 'path', 'install', 'enable', 'unhide'))
            if call[0] == 'busybox': self.assertIn(call[1], ('awk', 'tee'))
        if success is not None:
            self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def job(self):
        return Path((self.state / 'latest').read_text().strip())

    @contextmanager
    def isolated(self, ids=None):
        case = AutoinstallTests()
        case.setUp()
        try:
            case.generate(ids)
            yield case
        finally:
            case.doCleanups()

    def assert_prewrite_rejection(self):
        marker = self.module / 'install-selected.ok'
        previous = marker.read_bytes() if marker.exists() else None
        self.run_entry(False)
        self.assertEqual(self.writes(), [])
        self.assertEqual(marker.read_bytes() if marker.exists() else None, previous)

    def test_all_eight_gui_combinations_and_five_closed_runtime_selections(self):
        for flags in itertools.product((False, True), repeat=3):
            requested = [key for key, enabled in zip(s.IDS, flags) if enabled]
            with self.subTest(requested=requested):
                session = gui_session.Session()
                session.profile = s.new_profile()
                session.set_selected(requested)
                if not requested:
                    with self.assertRaises(ValueError): s.selected(session.profile)
                else:
                    expected = set(requested) | ({'assistant'} if 'xiaoai' in requested else set())
                    self.assertEqual(s.selected(session.profile), [x for x in s.IDS if x in expected])
        for ids in (['market'], ['assistant'], ['market', 'assistant'], ['assistant', 'xiaoai'], list(s.IDS)):
            with self.subTest(runtime=ids):
                # Fresh isolated Android filesystem for every actual generated entry.
                case = AutoinstallTests('test_all_eight_gui_combinations_and_five_closed_runtime_selections')
                case.setUp()
                try:
                    case.generate(ids)
                    case.config['clear_nested_tmp'] = True
                    case.run_entry(True)
                    case.assertEqual(case.installed(), ids)
                    case.assertEqual((case.job() / 'completed').read_text().splitlines(), ids)
                    case.assertEqual((case.job() / 'state').read_text().strip(), 'succeeded')
                    case.assertFalse((case.state / 'lock').exists())
                    case.assertEqual((case.module / 'install-selected.ok').read_text().strip(), ','.join(ids))
                    case.assertEqual(len([c for c in case.calls() if c[:2] == ['pm', 'install']]), int('xiaoai' in ids))
                    case.assertTrue((case.job() / 'log').stat().st_size)
                    case.assertEqual((case.root / 'parent-cwd').read_text().strip(), str(case.module))
                    case.assertEqual((case.root / 'native-cwds').read_text().splitlines(), [str(case.module)] * len(ids))
                    case.assertEqual(case.original['selection.json'].decode().count('during-flash'), 1)
                finally: case.doCleanups()

    def test_each_native_failure_stops_order_even_when_tee_succeeds(self):
        for failed in s.IDS:
            with self.subTest(failed=failed):
                self.generate()
                self.config['fail_child'] = failed
                self.run_entry(False)
                index = list(s.IDS).index(failed)
                self.assertEqual(self.installed(), list(s.IDS)[:index + 1])
                job = self.job()
                completed = job / 'completed'
                self.assertEqual(completed.read_text().splitlines() if completed.exists() else [], list(s.IDS)[:index])
                self.assertEqual((job / 'started').read_text().splitlines(), list(s.IDS)[:index + 1])
                self.assertEqual((job / 'state').read_text().strip(), 'failed')
                self.assertIn('fixture native install ' + failed, (job / 'log').read_text())
                self.assertFalse((self.module / 'install-selected.ok').exists())
                self.assertFalse((self.state / 'lock').exists())
                shutil.rmtree(self.state)
                (self.root / 'calls').unlink()
                (self.root / 'shared-installed').unlink(missing_ok=True)

    def test_platform_prechecks_before_any_install(self):
        cases = [{'props': {key: value}} for key, value in (
            ('ro.product.device', 'other'), ('ro.build.version.sdk', '36'),
            ('ro.build.version.incremental', 'unknown'), ('sys.boot_completed', '0'))]
        cases += [{'uid': '2000'}, {'user': '10'}, {'multiuser': True}, {'free': 1}]
        for changes in cases:
            with self.subTest(changes=changes):
                self.generate()
                self.config = dict(hashes=dict(RUNTIME), **changes)
                self.assert_prewrite_rejection()
        self.env['KSU'] = 'false'
        self.assert_prewrite_rejection()

    def test_missing_cli_meta_disabled_removed_unknown_pending_and_unmounted(self):
        self.generate()
        cli = self.root / 'data/adb/ksud'
        cli.unlink()
        self.assert_prewrite_rejection()
        cli.symlink_to(self.mock)
        meta = self.modules / 'meta-overlayfs'
        for marker in ('disable', 'remove', 'update'):
            with self.subTest(marker=marker):
                (meta / marker).touch()
                self.assert_prewrite_rejection()
                (meta / marker).unlink()
        for code in ('13000', 'unknown'):
            self.enable('meta-overlayfs', code)
            self.assert_prewrite_rejection()
        self.enable('meta-overlayfs', '13100')
        pending = self.root / 'data/adb/modules_update/meta-overlayfs'
        pending.mkdir(parents=True)
        self.assert_prewrite_rejection()
        pending.rmdir()
        image = self.root / 'data/adb/metamodule/modules.img'
        image.touch()
        self.config['unmounted'] = True
        self.assert_prewrite_rejection()

    def test_child_pending_versions_and_xiaoai_dependencies(self):
        for key in s.IDS:
            for marker in ('remove', 'update'):
                with self.subTest(key=key, marker=marker), self.isolated() as case:
                    child = case.enable('xuanyuan-os4-' + key, {'market':'2026101101', 'assistant':'2026101105', 'xiaoai':'2026101504'}[key])
                    (child / marker).touch()
                    case.assert_prewrite_rejection()
            with self.subTest(key=key, marker='modules_update'), self.isolated() as case:
                (case.root / ('data/adb/modules_update/xuanyuan-os4-' + key)).mkdir(parents=True)
                case.assert_prewrite_rejection()
            with self.subTest(key=key, marker='unknown version'), self.isolated() as case:
                case.enable('xuanyuan-os4-' + key, '999999')
                case.assert_prewrite_rejection()
        for key in ('zygisk_lsposed', 'zygisksu'):
            for marker in ('disable', 'remove', 'update', 'modules_update', 'missing'):
                with self.subTest(key=key, marker=marker), self.isolated() as case:
                    if marker == 'modules_update':
                        (case.root / ('data/adb/modules_update/' + key)).mkdir(parents=True)
                    elif marker == 'missing':
                        shutil.rmtree(case.modules / key)
                    else:
                        (case.modules / key / marker).touch()
                    case.assert_prewrite_rejection()

    def test_all_additional_runtime_checks_happen_before_first_child(self):
        self.generate()
        for key in RUNTIME:
            if 'MiuiHome.apk' in key: continue
            with self.subTest(key=key):
                self.config['hashes'][key] = '0' * 64
                self.assert_prewrite_rejection()
                self.config['hashes'][key] = RUNTIME[key]
        for key, value in (('launcher', '999'), ('no_misys', True), ('no_engine', True), ('split_engine', True),
                           ('shared', 'unknown'), ('shared', 'split'), ('shared', 'uninstalled')):
            with self.subTest(key=key, value=value):
                self.config[key] = value
                self.assert_prewrite_rejection()
                self.config.pop(key)
        retired = next(key for key in RUNTIME if 'MiuiHome.apk' in key)
        path = self.root / retired.lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'unknown retired launcher')
        self.config['hashes'][retired] = '0' * 64
        self.assert_prewrite_rejection()
        self.assertEqual(path.read_bytes(), b'unknown retired launcher')

    def test_existing_lock_and_queued_running_job_preserved_without_reconcile(self):
        self.generate()
        lock = self.state / 'lock'
        lock.mkdir(parents=True)
        (lock / 'boot').write_text('stale-boot')
        (lock / 'pid').write_text('9999999')
        before = {p.name: p.read_bytes() for p in lock.iterdir()}
        self.assert_prewrite_rejection()
        self.assertEqual({p.name: p.read_bytes() for p in lock.iterdir()}, before)
        shutil.rmtree(lock)
        job = self.state / 'jobs/previous'
        job.mkdir(parents=True)
        (self.state / 'latest').write_text(str(job))
        for state in ('queued', 'running'):
            (job / 'state').write_text(state)
            self.assert_prewrite_rejection()
            self.assertEqual((job / 'state').read_text(), state)
            self.assertEqual((self.state / 'latest').read_text(), str(job))

    def test_tampered_file_payload_and_forged_success_marker_rejected(self):
        for name in ('payload/market.zip', 'payload/unified.apk', 'selection.json', 'install-selected.sh', 'control.sh'):
            with self.subTest(name=name):
                self.generate()
                target = self.module / name
                target.write_bytes(target.read_bytes() + b'\ncorrupt')
                self.assert_prewrite_rejection()
        self.generate()
        (self.module / 'install-selected.ok').write_text(','.join(s.IDS) + '\n')
        self.assert_prewrite_rejection()

    def test_unknown_wallet_injection_duplicate_reordered_nonboolean_profiles(self):
        original = s.new_profile()
        for row in original['components']: row['enabled'] = True
        cases = []
        for value in ('wallet', 'unknown', '../wallet', 'market;reboot', '$(reboot)'):
            p = copy.deepcopy(original)
            p['components'][0]['id'] = value
            cases.append(p)
        for value in (None, 1, 'true'):
            p = copy.deepcopy(original)
            p['components'][0]['enabled'] = value
            cases.append(p)
        for rows in (original['components'][::-1], [original['components'][0]] * 3,
                     original['components'] + [{'id': 'wallet', 'enabled': True}]):
            cases.append(dict(original, components=rows))
        for profile in cases:
            with self.subTest(profile=profile), self.assertRaises(ValueError): s.selected(profile)
        for ids in ([], ['xiaoai'], ['market', 'xiaoai']):
            profile = copy.deepcopy(original)
            for row in profile['components']: row['enabled'] = row['id'] in ids
            with self.subTest(unclosed=ids), self.assertRaises(ValueError): s.selected(profile)
        for invalid in ('wallet', 'unknown', 'market,market', 'assistant,market', 'market;reboot', '$(reboot)'):
            with self.subTest(invalid=invalid):
                self.generate()
                helper = self.module / 'install-selected.sh'
                helper.write_text(helper.read_text().replace("AUTO_IDS='market,assistant,xiaoai'", 'AUTO_IDS=' + shlex.quote(invalid)))
                # Re-seal deliberately to exercise ID/order guards, independent of hashes.
                self.seal()
                self.assert_prewrite_rejection()

    def test_shared_install_failure_stops_xiaoai_and_keeps_prior_completed(self):
        self.generate()
        self.config['fail_pm_install'] = True
        self.run_entry(False)
        self.assertEqual(self.installed(), ['market', 'assistant'])
        self.assertEqual((self.job() / 'completed').read_text().splitlines(), ['market', 'assistant'])
        self.assertEqual((self.job() / 'state').read_text().strip(), 'failed')
        self.assertFalse((self.module / 'install-selected.ok').exists())

    def test_pm_enable_failure_does_not_continue_to_next_child(self):
        self.generate()
        self.config['fail_pm'] = 'enable:--user:0:com.miui.personalassistant'
        self.run_entry(False)
        self.assertEqual(self.installed(), ['market', 'assistant'])
        self.assertEqual((self.job() / 'completed').read_text().splitlines(), ['market'])
        self.assertEqual((self.job() / 'state').read_text().strip(), 'failed')

    def test_tee_failure_or_unreleased_lock_never_confirms_success(self):
        for key in ('tee_fail', 'leave_lock'):
            with self.subTest(key=key):
                self.generate(['market'])
                self.config[key] = True
                self.run_entry(False)
                self.assertFalse((self.module / 'install-selected.ok').exists())
                self.config.pop(key)
                if self.state.exists(): shutil.rmtree(self.state)
                (self.root / 'calls').unlink(missing_ok=True)

    def test_helper_rejects_all_arguments_before_commands(self):
        self.generate()
        for args in (['market'], ['wallet'], ['install', 'market'], ['$(reboot)'], ['']):
            result = subprocess.run(['/bin/sh', str(self.module / 'install-selected.sh'), *args],
                                    cwd=self.root, env=self.env, capture_output=True, text=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('no arguments', result.stderr)
            self.assertEqual(self.calls(), [])

    def test_customize_rejects_zero_helper_exit_with_missing_or_wrong_marker(self):
        for marker in (None, 'market', 'market,assistant,xiaoai,unknown'):
            with self.subTest(marker=marker), self.isolated() as case:
                text = '#!/system/bin/sh\n'
                if marker is not None:
                    text += 'printf "%s\\n" ' + shlex.quote(marker) + ' > "$MODPATH/install-selected.ok"\n'
                (case.module / 'install-selected.sh').write_text(text + 'exit 0\n')
                # This is a helper-exit fault injection; customize itself is unchanged.
                case.seal()
                result = case.run_entry(False)
                self.assertIn('组件安装结果未确认', result.stderr)
                self.assertEqual(case.writes(), [])


if __name__ == '__main__':
    unittest.main()
