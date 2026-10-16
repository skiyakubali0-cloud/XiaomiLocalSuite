"""Small fixture tests; no real APK build, large ZIP, ADB, or device commands.

Original controller tests are executed against the generated controller without
editing/importing files in the original suite. All fixtures stay in this scope.
"""
from pathlib import Path
import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

sys.dont_write_bytecode = True
import build as bundle

HERE = Path(__file__).resolve().parent
WORK = HERE / '.test-work'
WORK.mkdir(exist_ok=True)
tempfile.tempdir = str(WORK)
APK_BYTES = b'fixture unified API102 APK'
APK_SHA = hashlib.sha256(APK_BYTES).hexdigest()
# Reuse the original command mocks and full controller regression suite, with
# package installation and split/error controls added for the shared APK guard.
legacy = types.ModuleType('original_suite_tests')
legacy.__file__ = str(bundle.SUITE / 'test_control.py')
# exFAT creates AppleDouble beside fixture files. Ignore only those host
# metadata entries in original directory-content assertions.
original_tests = Path(legacy.__file__).read_text()
original_tests = original_tests.replace('list((self.state / "jobs").iterdir())', '[p for p in (self.state / "jobs").iterdir() if not p.name.startswith("._")]')
original_tests = original_tests.replace('sorted(p.name for p in lock.iterdir())', 'sorted(p.name for p in lock.iterdir() if not p.name.startswith("._"))')
exec(compile(original_tests, legacy.__file__, 'exec'), legacy.__dict__)
legacy.MOCK = legacy.MOCK.replace('package_state = root / "package-state.json"', '''
shared_state = root / "shared-package.json"
if shared_state.exists():
    packages.update(json.loads(shared_state.read_text()))
package_state = root / "package-state.json"
''')
legacy.MOCK = legacy.MOCK.replace('elif name == "pm" and args[:2] == ["list", "packages"]:', '''
elif name == "pm" and args[:1] == ["install"]:
    record([name] + args)
    data = sys.stdin.buffer.read()
    if os.environ.get("TEST_INSTALL_FAIL"):
        sys.exit(1)
    import hashlib
    package = "local.xuanyuan.mipushcompat"
    if not os.environ.get("TEST_INSTALL_NOOP"):
        shared_state.write_text(json.dumps({package: hashlib.sha256(data).hexdigest()}))
        (root / "apks").mkdir(exist_ok=True)
        (root / "apks" / (package + ".apk")).write_bytes(data)
    print("Success")
elif name == "pm" and args[:2] == ["list", "packages"]:
    if os.environ.get("TEST_PM_ERROR"):
        sys.exit(1)
''')
legacy.MOCK = legacy.MOCK.replace('    if args[3] in packages:\n        print("package:"', '''    if os.environ.get("TEST_SPLIT") and args[3] == "local.xuanyuan.mipushcompat":
        print("package:" + str(root / "apks/base.apk"))
        print("package:" + str(root / "apks/split.apk"))
    elif args[3] in packages:
        print("package:"''')
legacy.MOCK = legacy.MOCK.replace('for filename in ("control.sh", "profiles.sh"):', 'for filename in ("control.sh", "profiles.sh", "uninstall.sh"):')
legacy.MOCK = legacy.MOCK.replace('elif name == "am" and args == ["get-current-user"]:\n    print("0")', '''elif name == "am" and args == ["get-current-user"]:
    print(os.environ.get("TEST_USER", "0"))
elif name == "am" and args[:1] == ["start"]:
    record([name] + args)''')
legacy.MOCK = legacy.MOCK.replace('    print("UserInfo{0:Owner:13} running")', '''    print("UserInfo{0:Owner:13} running")
    if os.environ.get("TEST_MULTIUSER"):
        print("UserInfo{10:Other:10}")''')
legacy.MOCK = legacy.MOCK.replace('if args == ["-c", "control.sha256"]:', 'if args in (["-c", "control.sha256"], ["-c", "checksums.sha256"]):')


def fixture_catalog():
    text = (bundle.SOURCE_MODULE / 'catalog.sh').read_text()
    for key, (previous, code, _, _) in bundle.CHILDREN.items():
        text = re.sub(r'(^' + key + r'\).*?CODE=)\x27' + previous + "'", r"\g<1>'" + code + "'", text, flags=re.M)
    text = re.sub(r"^clock\).*", "clock) MID=''; PKG='local.xuanyuan.mipushcompat'; CODE=''; FILE='unified.apk'; SHA='" + APK_SHA + "'; TITLE='时钟法定节假日'; KIND='apk';;", text, flags=re.M)
    text = text.replace('*) return 1;;', "mipush) MID=''; PKG='local.xuanyuan.mipushcompat'; CODE=''; FILE='unified.apk'; SHA='" + APK_SHA + "'; TITLE='MiPush 推送配置'; KIND='apk';;\n*) return 1;;")
    return text


class ControllerTests(legacy.ControllerTests):
    @classmethod
    def setUpClass(cls):
        cls.source_tmp = tempfile.TemporaryDirectory(prefix='source-')
        cls.source = Path(cls.source_tmp.name)
        legacy.SOURCE = cls.source
        (cls.source / 'control.sh').write_text(bundle.controller((bundle.SOURCE_MODULE / 'control.sh').read_text()))
        (cls.source / 'catalog.sh').write_text(fixture_catalog())
        owned = (bundle.SOURCE_MODULE / 'owned-packages.txt').read_text()
        (cls.source / 'owned-packages.txt').write_text(''.join(line + '\n' for line in owned.splitlines() if '|local.xuanyuan.' not in line))

    @classmethod
    def tearDownClass(cls):
        cls.source_tmp.cleanup()

    def setUp(self):
        super().setUp()
        # Original tests replace payload digests with fixture hashes. Bind the
        # actual shared template to that same fixture hash, never a fake bypass.
        apk = self.module / 'payload/unified.apk'
        self.apk_sha = bundle.digest(apk)
        shared = bundle.shared((HERE / 'shared.sh.in').read_text(), self.apk_sha)
        (self.module / 'shared.sh').write_text(shared)
        self.rehash()

    def rehash(self):
        (self.module / 'control.sha256').write_text(''.join(
            f'{bundle.digest(self.module / name)}  {name}\n'
            for name in ('control.sh', 'catalog.sh', 'shared.sh', 'owned-packages.txt')))

    def installed(self, sha):
        apk = self.root / 'apks' / (bundle.PKG + '.apk')
        apk.parent.mkdir(exist_ok=True)
        apk.write_bytes(b'fixture live package')
        return {'TEST_PACKAGES': json.dumps({bundle.PKG: sha})}

    def test_exact_previous_upgrade_only_install_and_exact_target(self):
        for key, (previous, code, _, _) in bundle.CHILDREN.items():
            self.enable('xuanyuan-os4-' + key)
            prop = self.modules / ('xuanyuan-os4-' + key) / 'module.prop'
            cases = [(previous, code, 'install', True),
                     (previous, code, 'restore', False),
                     (previous, '2026101599', 'install', False),
                     ('1', code, 'install', False),
                     ('', code, 'install', False),
                     (code, code, 'restore', True)]
            if key in ('phone', 'xiaoai'):
                cases += [('2026101501', code, 'install', True),
                          ('2026101501', code, 'restore', False),
                          ('2026101501', '2026101599', 'install', False),
                          (previous, '2026101501', 'install', False),
                          ('2026101500', code, 'install', False)]
            for live, target, op, allowed in cases:
                prop.write_text('versionCode=' + live + '\n')
                command = f'lookup {key}; CODE={shlex.quote(target)}; OP={op}; module_version_ok'
                result = subprocess.run(['/bin/sh', '-c', '. "$1" >/dev/null 2>&1; ' + command, 'fixture', str(self.controller)],
                                        env=self.env, text=True, capture_output=True)
                self.assertEqual(result.returncode == 0, allowed, (key, live, target, op, result.stderr))
        self.assertEqual(self.calls(), [])

    def test_gallery_known_versions_and_unknown_versions_before_mutation(self):
        # Installation may supply absent CN packages; restore still requires
        # the complete known set. Unknown present packages always stop first.
        packages = {p: hashes[0] for p, hashes in legacy.GALLERY_HASHES.items()}
        for package, hashes in legacy.GALLERY_HASHES.items():
            for digest in hashes:
                self.passes("gallery_check", TEST_PACKAGES=json.dumps(dict(packages, **{package: digest})))
        self.enable("xuanyuan-os4-gallery")
        database = self.root / "data/user/0/com.miui.gallery/photos.db"
        database.parent.mkdir(parents=True)
        database.write_bytes(b"photos must survive")
        for operation in ("install", "restore"):
            for package in packages:
                for digest in ("0" * 64, None):
                    unknown = dict(packages)
                    if digest is None: del unknown[package]
                    else: unknown[package] = digest
                    if operation == "install" and digest is None:
                        self.passes("preflight", "install", "gallery", TEST_PACKAGES=json.dumps(unknown))
                        continue
                    job = self.queued()
                    self.rejects("未经验证的相册更新", "worker", job, operation, "gallery", TEST_PACKAGES=json.dumps(unknown))
                    self.assertFalse((job / "started").exists())
                    self.assertFalse((job / "completed").exists())
                    self.assertEqual(self.calls(), [])
                    self.assertEqual(database.read_bytes(), b"photos must survive")
        job = self.queued()
        self.passes("worker", job, "restore", "gallery")
        self.assertIn(["module", "disable", "xuanyuan-os4-gallery"], self.calls())
        self.assertIn(["fixture-script", "extracted-gallery", "restore"], self.calls())
        self.assertEqual(database.read_bytes(), b"photos must survive")

    def test_reviewed_r2_xiaoai_upgrade_and_preset_entry(self):
        self.enable('xuanyuan-os4-xiaoai')
        (self.modules / 'xuanyuan-os4-xiaoai/module.prop').write_text('versionCode=2026101502\n')
        result = subprocess.run(['/bin/sh', '-c', '. "$1" >/dev/null 2>&1; lookup xiaoai; OP=install; module_version_ok', 'fixture', str(self.controller)], env=self.env, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('preset) [ "$#" = 1 ]', bundle.controller((bundle.SOURCE_MODULE / 'control.sh').read_text()))

    def test_shared_absent_known_previous_and_same_hash(self):
        self.passes('shared_check')
        self.passes('shared_check', **self.installed(bundle.PREVIOUS_SHA))
        self.passes('shared_check', **self.installed('fe2cc510d76aeca054582d20f092833a336e13b39686fb1d49f5a20a3a5688d7'))
        self.passes('shared_check', **self.installed(bundle.REVISION_12_SHA))
        self.passes('shared_check', **self.installed(self.apk_sha))
        self.assertEqual(self.calls(), [])

    def test_initial_12_apk_upgrade_installs_final_once(self):
        self.passes('shared_install', **self.installed('fe2cc510d76aeca054582d20f092833a336e13b39686fb1d49f5a20a3a5688d7'))
        self.passes('shared_install')
        installs = [c for c in self.calls() if c[:2] == ['pm', 'install']]
        self.assertEqual(len(installs), 1, self.calls())
        self.assertEqual(bundle.digest(self.root / 'apks' / (bundle.PKG + '.apk')), self.apk_sha)

    def test_shared_unknown_split_and_pm_failure_before_install(self):
        for env in (self.installed('0' * 64), dict(self.installed(self.apk_sha), TEST_SPLIT='1'), {'TEST_PM_ERROR': '1'}):
            result = self.run_control('shared_install', **env)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), [])

    def test_shared_install_once_and_failure_postcondition(self):
        self.passes('shared_install')
        self.passes('shared_install')
        self.passes('install_one', 'clock')
        self.passes('install_one', 'mipush')
        installs = [c for c in self.calls() if c[:2] == ['pm', 'install']]
        self.assertEqual(len(installs), 1, self.calls())
        self.assertIn('-r', installs[0])
        self.assertFalse(any('uninstall' in c or 'disable-user' in c for c in self.calls()))
        (self.root / 'shared-package.json').unlink()
        self.assertNotEqual(self.run_control('shared_install', **self.installed(bundle.PREVIOUS_SHA), TEST_INSTALL_NOOP='1').returncode, 0)

    def test_payload_hash_error_before_shared_write(self):
        (self.module / 'payload/unified.apk').write_bytes(b'tampered')
        self.assertNotEqual(self.run_control('shared_install').returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_new_clock_detection_shared_install_and_guard(self):
        self.enable('zygisk_lsposed')
        self.enable('zygisksu')
        packages = {bundle.PKG: self.apk_sha, 'com.android.deskclock': '41defcfd640a3ba5d359c20004d9dced5f6c0810204c41c94530af2a2bc1e9f6'}
        self.installed(self.apk_sha)
        self.env['TEST_PACKAGES'] = json.dumps(packages)
        status = json.loads(self.passes('status').stdout)
        states = {x['id']: x['state'] for x in status['components']}
        self.assertEqual(states['clock'], 'installed')
        self.assertEqual(states['mipush'], 'installed')
        self.passes('preflight', 'install', 'clock,mipush')
        self.rejects('法定重复规则', 'preflight', 'restore', 'clock')
        packages['com.android.deskclock'] = '0' * 64
        self.rejects('时钟版本不匹配', 'preflight', 'install', 'clock', TEST_PACKAGES=json.dumps(packages))
        self.assertEqual(self.calls(), [])

    def test_restore_xiaoai_and_disaster_never_change_shared_or_legacy_apks(self):
        for component in ('xiaoai', 'disaster'):
            self.enable('xuanyuan-os4-' + component)
            self.passes('preflight', 'restore', component)
            self.passes('restore_one', component)
            self.assertTrue((self.modules / ('xuanyuan-os4-' + component) / 'disable').is_file())
        calls = self.calls()
        self.assertEqual(len([c for c in calls if c[:2] == ['module', 'disable']]), 2)
        self.assertFalse(any(bundle.PKG in str(c) or 'local.xuanyuan.' in str(c) for c in calls), calls)
        self.assertFalse(any('uninstall' in c for c in calls), calls)

    def test_phone_restore_does_not_touch_shared_package(self):
        self.enable('xuanyuan-os4-phone')
        before = self.root / 'data/adb/xuanyuan-os4-phone-state'
        before.mkdir(parents=True)
        for name in ('before-dialer', 'before-sms'):
            (before / name).write_text('')
        self.state.mkdir(parents=True)
        job = self.state / 'phone-restore'
        job.mkdir()
        # restore_one normally receives J from the worker; set it only in this
        # wrapper to exercise the real restore_one body with command mocks.
        command = '. "$1" >/dev/null 2>&1; J="$2"; restore_one phone'
        env = dict(self.env, TEST_PACKAGES=json.dumps({
            bundle.PKG: self.apk_sha,
            'com.miui.yellowpage': '0c5c655fe93ffc0eade6a77dc56c05754d4a3afab8a6c122acd3a2f8a160c0ba',
            'com.miui.audiomonitor': 'f84954e6ef361a8204c565bfe365e66344e2984036febe784c1485e113d1ba71'}))
        result = subprocess.run(['/bin/sh', '-c', command, 'fixture', str(self.controller), str(job)], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(['module', 'disable', 'xuanyuan-os4-phone'], self.calls())
        self.assertTrue((self.modules / 'xuanyuan-os4-phone/disable').is_file())
        self.assertFalse(any('local.xuanyuan.' in str(c) or 'uninstall' in c for c in self.calls()), self.calls())

    def test_open_routes_use_explicit_shared_components(self):
        self.passes('open_component', 'mipush')
        self.passes('open_component', 'disaster')
        self.assertIn(['am', 'start', '-n', bundle.PKG + '/.Manager'], self.calls())
        self.assertIn(['am', 'start', '-n', bundle.PKG + '/local.xuanyuan.disastercompat.EntryActivity'], self.calls())

    def test_parent_guards_before_writes_and_no_migration(self):
        # Run the actual parent installer with mocked Android commands. chmod,
        # permission setup and UI calls are local record-only functions.
        custom = self.module / 'customize.sh'
        custom.write_text((HERE / 'customize.sh').read_text())
        def sums():
            (self.module / 'checksums.sha256').write_text(''.join(
                f'{bundle.digest(self.module / name)}  {name}\n'
                for name in ('customize.sh', 'shared.sh', 'payload/unified.apk')))
        sums()
        wrapper = self.root / 'customize-wrapper.sh'
        wrapper.write_text('abort() { echo "$*" >&2; exit 1; }\n'
                           'set_perm_recursive() { :; }\nset_perm() { :; }\nui_print() { :; }\n'
                           '. "$MODPATH/customize.sh"\n')
        def run(**env):
            return subprocess.run(['/bin/sh', str(wrapper)], env=dict(self.env, KSU='true', MODPATH=str(self.module), **env), text=True, capture_output=True)
        for env in ({'TEST_USER': '10'}, {'TEST_MULTIUSER': '1'},
                    {'TEST_PROPS': json.dumps({'ro.build.version.incremental': 'wrong'})},
                    self.installed('0' * 64), dict(self.installed(self.apk_sha), TEST_SPLIT='1')):
            self.assertNotEqual(run(**env).returncode, 0)
            self.assertEqual(self.calls(), [])
        (self.module / 'payload/unified.apk').write_bytes(b'tampered')
        self.assertNotEqual(run().returncode, 0)
        self.assertEqual(self.calls(), [])
        (self.module / 'payload/unified.apk').write_bytes(b'test payload: unified.apk')
        sums()
        result = run(**self.installed(bundle.PREVIOUS_SHA))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len([c for c in self.calls() if c[:2] == ['pm', 'install']]), 1)
        result = run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(self.calls()), 1)


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='transform-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self, key):
        # Real reviewed scripts with tiny opaque binary substitutes. Never build
        # a copy of the hundreds of MB of Xiaomi payload for these tests.
        item = next(x for x in json.loads((bundle.SOURCE_MODULE / 'webroot/catalog.json').read_text()) if x['id'] == key)
        entries = {}
        with zipfile.ZipFile(bundle.RELEASE / item['source']) as source:
            for name in source.namelist():
                if name.endswith(('.sh', '.prop', '.txt', '.js', '.html', '.xml')):
                    entries[name] = source.read(name)
                elif not name.endswith('/') and name != 'checksums.sha256':
                    entries[name] = b'opaque Xiaomi-signed bytes: ' + name.encode()
        entries['checksums.sha256'] = b'old checksums replaced\n'
        path = self.root / (key + '-source.zip')
        with zipfile.ZipFile(path, 'w') as z:
            for name, data in entries.items():
                z.writestr(name, data)
        return path, entries

    def test_revision2_child_versions_and_feature_xml_preserve_permissions_and_markers(self):
        expected = {'phone': ('1.8.1', '2026101502'),
                    'xiaoai': ('1.7.3', '2026101504'),
                    'disaster': ('1.2', '2026101501')}
        for key, (version, code) in expected.items():
            source, original = self.fixture(key)
            target = self.root / (key + '.zip')
            report = bundle.transform_child(key, source, target, bundle.digest(source), APK_SHA)
            with zipfile.ZipFile(target) as z:
                props = bundle.properties(z.read('module.prop').decode())
                self.assertEqual(props['version'], version + ' (unified API102)')
                self.assertEqual(props['versionCode'], code)
                self.assertEqual(report['versionCode'], code)
                features = []
                for name in z.namelist():
                    if name.endswith('.xml'):
                        root = ET.fromstring(z.read(name))
                        for feature in root.findall('feature'):
                            features.append((name, feature.attrib))
                if key == 'disaster':
                    self.assertEqual(features, [])
                else:
                    name = f'system/product/etc/permissions/xuanyuan-os4-{key}.xml'
                    feature = f'local.xuanyuan.compat.{key}'
                    self.assertEqual(features, [(name, {'name': feature, 'version': '1'})])
                    declaration = f'<feature name="{feature}" version="1"/>'
                    self.assertEqual(z.read(name).decode().replace(declaration, ''), original[name].decode())
                    self.assertIn(name, report['changed'])
                for name in original:
                    if name.endswith('.enabled'):
                        self.assertEqual(z.read(name), original[name])
                if key == 'phone':
                    self.assertEqual(z.read(bundle.MARKER), b'unified-api102\n')

    def test_feature_xml_source_contract_drift_rejected(self):
        for key in ('phone', 'xiaoai'):
            source, entries = self.fixture(key)
            name = f'system/product/etc/permissions/xuanyuan-os4-{key}.xml'
            entries[name] = entries[name].replace(b'</permissions>', b'</unexpected>')
            with zipfile.ZipFile(source, 'w') as z:
                for entry, data in entries.items():
                    z.writestr(entry, data)
            target = self.root / (key + '.zip')
            with self.assertRaisesRegex(ValueError, 'Source contract drift'):
                bundle.transform_child(key, source, target, bundle.digest(source), APK_SHA)
            self.assertFalse(target.exists())

    def test_three_transforms_preserve_all_opaque_entries_and_restore_logic(self):
        for key in bundle.CHILDREN:
            source, original = self.fixture(key)
            target = self.root / (key + '.zip')
            report = bundle.transform_child(key, source, target, bundle.digest(source), APK_SHA)
            with zipfile.ZipFile(target) as z:
                self.assertFalse(any(Path(n).name in bundle.LEGACY_LEAVES for n in z.namelist()))
                for name in original:
                    if name not in bundle.CHILDREN[key][3] | set(report['changed']) | {'checksums.sha256'}:
                        self.assertEqual(z.read(name), original[name], name)
                for line in z.read('checksums.sha256').decode().splitlines():
                    expected, name = line.split('  ', 1)
                    self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), expected)
                for name in z.namelist():
                    if name.endswith('.sh'):
                        script = self.root / ('syntax-' + Path(name).name)
                        script.write_bytes(z.read(name))
                        subprocess.run(['/bin/sh', '-n', str(script)], check=True)
                text = '\n'.join(z.read(n).decode() for n in z.namelist() if n.endswith('.sh'))
                for leaf in bundle.LEGACY_LEAVES:
                    self.assertNotIn(leaf, text)
                self.assertNotRegex(text, r'pm (?:install|enable|disable-user|uninstall).*local\.xuanyuan\.')
                if key == 'phone':
                    self.assertIn(bundle.MARKER, z.namelist())
                    old = original['uninstall.sh'].decode().replace('pm disable-user --user 0 local.xuanyuan.smscompat', '')
                    self.assertTrue(z.read('uninstall.sh').decode().startswith(old.rstrip()))
                if key == 'xiaoai':
                    privacy = z.read('privacy.sh').decode()
                    self.assertIn('pm path --user 0 local.xuanyuan.mipushcompat', privacy)
                    self.assertIn(APK_SHA, privacy)
                    self.assertIn('local.xuanyuan.aiprivacy.Manager "$1"', privacy)
                if key == 'disaster':
                    self.assertEqual(z.read('restore.sh'), original['restore.sh'])
                    self.assertIn(b'local.xuanyuan.mipushcompat/local.xuanyuan.disastercompat.EntryActivity', z.read('action.sh'))

    def test_child_source_hash_and_version_fail_closed(self):
        for key in bundle.CHILDREN:
            source, entries = self.fixture(key)
            out = self.root / (key + '.zip')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                bundle.transform_child(key, source, out, '0' * 64, APK_SHA)
            self.assertFalse(out.exists())
            entries['module.prop'] = entries['module.prop'].replace(bundle.CHILDREN[key][0].encode(), b'999')
            with zipfile.ZipFile(source, 'w') as z:
                for name, data in entries.items():
                    z.writestr(name, data)
            with self.assertRaisesRegex(ValueError, 'Unreviewed child version'):
                bundle.transform_child(key, source, out, bundle.digest(source), APK_SHA)
            self.assertFalse(out.exists())

    def test_source_contract_drift_rejected(self):
        source, entries = self.fixture('phone')
        entries['service.sh'] = entries['service.sh'].replace(b'HOOK_PATH=', b'OTHER_PATH=')
        with zipfile.ZipFile(source, 'w') as z:
            for name, data in entries.items():
                z.writestr(name, data)
        with self.assertRaises(ValueError):
            bundle.transform_child('phone', source, self.root / 'out.zip', bundle.digest(source), APK_SHA)

    def test_unsafe_archive_entries_rejected(self):
        for name in ('../escape', '/absolute', 'payload/._apple', 'private/state.db', 'keys/test.jks', '__MACOSX/x'):
            path = self.root / 'unsafe.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr(name, b'x')
            with zipfile.ZipFile(path) as z:
                with self.assertRaises(ValueError):
                    bundle.archive_members(z)

    def test_webui_and_controller_wallet_clock_no_shared_removal_contract(self):
        original = (bundle.SOURCE_MODULE / 'control.sh').read_text()
        control = bundle.controller(original)
        for line in original.splitlines():
            if 'wallet)' in line:
                self.assertIn(line, control)
        self.assertNotIn('remove_hook', control)
        self.assertNotIn('local.xuanyuan.clockcompat', control)
        self.assertIn('settings) platform; am start -n local.xuanyuan.mipushcompat/local.xuanyuan.unified.SettingsActivity', control)
        html = bundle.webui((bundle.SOURCE_MODULE / 'webroot/index.html').read_text())
        self.assertIn('统一兼容与推送设置', html)
        self.assertIn("await exec('settings')", html)
        js = self.root / 'webui.js'
        js.write_text(html.split('<script>', 1)[1].split('</script>', 1)[0])
        subprocess.run(['node', '--check', str(js)], check=True)
        self.assertIn('let catalog = [], byId = new Map(), selected = new Set()', html)
        syntax = self.root / 'control.sh'
        syntax.write_text(control)
        subprocess.run(['/bin/sh', '-n', str(syntax)], check=True)
        self.assertNotIn('migrate-legacy.sh', (HERE / 'customize.sh').read_text())
        self.assertNotIn('migrate-legacy.sh', control)

    def test_miniature_end_to_end_package_catalog_hashes_and_symlinks(self):
        out = self.root / 'output'
        out.mkdir()
        release = self.root / 'releases'
        release.mkdir()
        for name in ('customize.sh', 'shared.sh.in', 'GUIDE.txt', 'ROOT-README.txt', 'preset.sh'):
            shutil.copyfile(HERE / name, out / name)
        for name in ('国行天气模块说明.txt', '国行相册模块说明.txt', '国行日历安装复用说明.txt'):
            (release / name).write_text('fixture guide')
        catalog = json.loads((bundle.SOURCE_MODULE / 'webroot/catalog.json').read_text())
        source_paths = {}
        for item in catalog:
            key = item['id']
            path = release / item['source']
            if key in bundle.CHILDREN:
                fixture, _ = self.fixture(key)
                shutil.copyfile(fixture, path)
            elif item['kind'] == 'module':
                with zipfile.ZipFile(bundle.RELEASE / item['source']) as z:
                    prop = z.read('module.prop')
                with zipfile.ZipFile(path, 'w') as z:
                    z.writestr('module.prop', prop)
                    z.writestr('system/Xiaomi.apk', b'opaque signed fixture ' + key.encode())
            else:
                path.write_bytes(b'opaque signed fixture ' + key.encode())
            item['sha256'] = bundle.digest(path)
            item['bytes'] = path.stat().st_size
            source_paths[key] = path
        apk = self.root / 'unified.apk'
        apk.write_bytes(APK_BYTES)
        helper = self.root / 'migrate-legacy.sh'
        helper.write_text('#!/system/bin/sh\necho fixture-helper\n')
        calendar = self.root / 'calendar'
        calendar.mkdir()
        (calendar / 'global-original.apk').write_bytes(b'opaque global calendar')
        with patch.multiple(bundle, HERE=out, RELEASE=release, APK=apk, MIGRATION=helper, BASE=self.root), \
             patch.object(bundle, 'baseline', return_value=catalog), \
             patch.object(bundle, 'calendar_restore_source', return_value=calendar / 'global-original.apk'), \
             patch.object(bundle, 'check_apk', return_value=APK_SHA):
            bundle.build(APK_SHA)
        module = out / 'module'
        props = bundle.properties((module / 'module.prop').read_text())
        self.assertEqual(props['version'], '1.4')
        self.assertEqual(props['versionCode'], '2026101504')
        self.assertIn('fe2cc510d76aeca054582d20f092833a336e13b39686fb1d49f5a20a3a5688d7',
                      (module / 'shared.sh').read_text())
        # Features belong only to child overlays. Restore disables those modules;
        # after reboot their XML is absent from the mounted permissions paths.
        # This checks archive placement, not Android SystemConfig/PackageManager.
        self.assertTrue((module / 'skip_mount').is_file())
        self.assertFalse((module / 'system').exists())
        rendered = json.loads((module / 'webroot/catalog.json').read_text())
        self.assertEqual(len(rendered), 11)
        by_id = {x['id']: x for x in rendered}
        self.assertEqual(by_id['clock']['file'], 'payload/unified.apk')
        self.assertEqual(by_id['mipush']['file'], 'payload/unified.apk')
        self.assertEqual(by_id['clock']['sha256'], APK_SHA)
        self.assertEqual(by_id['mipush']['sha256'], APK_SHA)
        self.assertFalse(by_id['clock']['restoreSupported'])
        self.assertFalse(by_id['wallet']['restoreSupported'])
        for key in ('market', 'assistant', 'gallery', 'weather', 'wallet', 'calendar'):
            target = module / by_id[key]['file']
            self.assertTrue(target.is_symlink(), key)
            self.assertEqual(target.read_bytes(), source_paths[key].read_bytes())
            self.assertEqual(bundle.digest(target), by_id[key]['sha256'])
        self.assertEqual((module / 'migrate-legacy.sh').read_bytes(), helper.read_bytes())
        self.assertIn('local.xuanyuan.unified.UnifiedModule', (module / 'README.txt').read_text())
        for guide in (module / 'guides').glob('*.txt'):
            if guide.name.startswith('.') or guide.name == '统一套件1.4说明.txt':
                continue
            self.assertTrue(guide.read_text().startswith('【统一套件1.4 API102说明】'))
        with zipfile.ZipFile(out / 'xuanyuan-os4-suite-1.4.zip') as z:
            self.assertEqual(z.namelist().count('payload/unified.apk'), 1)
            self.assertFalse(any(Path(n).name in bundle.LEGACY_LEAVES or n.startswith('private/') for n in z.namelist()))
            self.assertEqual(z.read('migrate-legacy.sh'), helper.read_bytes())
            for line in z.read('checksums.sha256').decode().splitlines():
                sha, name = line.split('  ', 1)
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), sha)
        report = json.loads((out / 'build-evidence.json').read_text())
        self.assertFalse(report['device_verified'])
        for key in bundle.CHILDREN:
            self.assertEqual(report['sources'][key]['sha256'], by_id[key]['sha256'])
            self.assertEqual(by_id[key]['versionCode'], bundle.CHILDREN[key][1])
        artifact = out / 'xuanyuan-os4-suite-1.4.zip'
        before = artifact.read_bytes()
        with patch.multiple(bundle, HERE=out, APK=apk, MIGRATION=helper), \
             patch.object(bundle, 'baseline', return_value=catalog), \
             patch.object(bundle, 'check_apk', return_value=APK_SHA), \
             patch.object(bundle, 'stage', return_value=(module, [], {})):
            with self.assertRaisesRegex(ValueError, 'Refusing to overwrite'):
                bundle.build(APK_SHA)
        self.assertEqual(artifact.read_bytes(), before)

    def test_build_requires_main_hash_before_any_stage_even_if_apk_exists(self):
        apk = self.root / 'unified.apk'
        apk.write_bytes(APK_BYTES)
        with patch.object(bundle, 'APK', apk), patch.object(bundle, 'stage') as stage:
            for expected in (None, '', '0' * 64):
                with self.assertRaises(ValueError):
                    bundle.build(expected)
            stage.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'not ready'):
            bundle.check_apk(self.root / 'missing.apk')

    def test_apk_identity_api102_legacy_and_version_checks_with_fixtures(self):
        path = self.root / 'unified.apk'
        def apk(extra=None):
            files = {'META-INF/xposed/java_init.list': b'local.xuanyuan.unified.UnifiedModule\n',
                     'META-INF/xposed/module.prop': b'minApiVersion=102\ntargetApiVersion=102\nstaticScope=false\n',
                     'META-INF/xposed/scope.list': b'', 'classes.dex': b'opaque fixture dex'}
            files.update(extra or {})
            with zipfile.ZipFile(path, 'w') as z:
                for name, data in files.items():
                    z.writestr(name, data)
        def command(args, **kwargs):
            if 'badging' in args:
                return types.SimpleNamespace(stdout="package: name='local.xuanyuan.mipushcompat' versionCode='13'\n")
            if 'xmltree' in args:
                return types.SimpleNamespace(stdout='".Manager" "local.xuanyuan.unified.SettingsActivity" "local.xuanyuan.unified.PresetActivity" "local.xuanyuan.disastercompat.EntryActivity"')
            return types.SimpleNamespace(stdout='')
        apk()
        with patch.object(bundle.subprocess, 'run', side_effect=command):
            self.assertEqual(bundle.check_apk(path), bundle.digest(path))
            for change in ({'assets/xposed_init': b'old'}, {'classes.dex': b'de/robv/android/xposed/IXposedHookLoadPackage'},
                           {'META-INF/xposed/java_init.list': b'old.Entry'}, {'META-INF/xposed/scope.list': b'android'},
                           {'META-INF/xposed/module.prop': b'minApiVersion=93\ntargetApiVersion=102'}):
                apk(change)
                with self.assertRaises(ValueError):
                    bundle.check_apk(path)
        apk()
        with patch.object(bundle.subprocess, 'run', return_value=types.SimpleNamespace(stdout="package: name='local.xuanyuan.mipushcompat' versionCode='10'")):
            with self.assertRaisesRegex(ValueError, 'v13'):
                bundle.check_apk(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
