"""Run the real stock-app helper and controller library with host Android doubles.

Only absolute Android paths and fixture APK identities are adapted. No device,
release payload, role write, installation or application data operation is used.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / 'suite/module'
OLD = {'phone': 'com.google.android.dialer', 'sms': 'com.google.android.apps.messaging'}
NEW = {'phone': 'com.android.contacts', 'sms': 'com.android.mms'}
INCALL = 'com.android.incallui'

MOCK = r'''
import hashlib, json, os, pathlib, sys, time
root = pathlib.Path(os.environ['TEST_ROOT'])
config = root / 'config.json'
c = json.loads(config.read_text())
name, args = pathlib.Path(sys.argv[0]).name, sys.argv[1:]
command = [name] + args
with (root / 'trace').open('a') as f: f.write(json.dumps(command) + '\n')
if command in c.get('fail', []) or (c.get('did_disable') and command in c.get('post_fail', [])):
    print('synthetic query failure', file=sys.stderr); sys.exit(23)
if command in c.get('malformed', []):
    print('Error: synthetic query failure'); sys.exit(0)
state = root / 'data/adb/xuanyuan-os4-suite-state'
packages = c['packages']
if name == 'id' and args == ['-u']: print(c.get('uid', 0))
elif name == 'getprop':
    props = {'ro.product.device': 'xuanyuan', 'ro.build.version.sdk': '37',
             'ro.build.version.incremental': 'OS4.0.0.6.XOAEUXM', 'sys.boot_completed': '1'}
    props.update(c.get('props', {})); print(props.get(args[0], ''))
elif name == 'am' and args == ['get-current-user']: print(c.get('user', 0))
elif name == 'pm' and args == ['list', 'users']:
    print('UserInfo{0:Owner:13} running')
    if c.get('multiuser'): print('UserInfo{10:Other:0}')
elif name == 'pm' and args in (['list', 'packages', '--user', '0'],
                              ['list', 'packages', '-e', '--user', '0'],
                              ['list', 'packages', '-d', '--user', '0']):
    for p, v in packages.items():
        if '-e' in args and v: continue
        if '-d' in args and not v: continue
        print('package:' + p)
elif name == 'pm' and args[:3] == ['path', '--user', '0'] and len(args) == 4:
    if args[3] in packages:
        print('package:' + str(root / 'apks' / (args[3] + '.apk')))
        if c.get('split') == args[3]: print('package:/missing/split.apk')
elif name == 'cmd' and args[:4] == ['role', 'get-role-holders', '--user', '0'] and len(args) == 5:
    print(c['roles'].get(args[4], ''))
elif name == 'pm' and len(args) == 4 and args[:3] in (
        ['enable', '--user', '0'], ['disable-user', '--user', '0']):
    p = args[3]
    assert p in ('com.google.android.dialer', 'com.google.android.apps.messaging'), command
    app = 'phone' if p == 'com.google.android.dialer' else 'sms'
    lock = state / 'lock'
    entry = {'command': command, 'marker': (state / 'stock-apps' / (app + '.disabled')).exists(),
             'lock': {key: (lock / key).read_text().strip() for key in ('boot', 'pid', 'created')}}
    with (root / 'actions').open('a') as f: f.write(json.dumps(entry) + '\n')
    mode = c.get('disable_mode' if args[0] == 'disable-user' else 'enable_mode', '')
    if mode == 'fail': sys.exit(24)
    if mode != 'noop': packages[p] = args[0] == 'disable-user'
    if args[0] == 'disable-user':
        c['did_disable'] = True
        if mode == 'role': c['roles']['android.app.role.DIALER' if app == 'phone' else 'android.app.role.SMS'] = p
    config.write_text(json.dumps(c))
    sys.exit(25 if mode == 'fail-after' else 0)
elif name == 'sha256sum':
    if args == ['-c', 'control.sha256']:
        for line in pathlib.Path(args[1]).read_text().splitlines():
            digest, path = line.split(None, 1)
            if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() != digest: sys.exit(26)
    elif not args:
        print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest() + '  -')
    elif len(args) == 1:
        print(hashlib.sha256(pathlib.Path(args[0]).read_bytes()).hexdigest() + '  ' + args[0])
    else: sys.exit(90)
elif name == 'busybox' and args[:1] == ['awk']:
    os.execv('/usr/bin/awk', ['awk'] + args[1:])
elif name == 'busybox' and args[:2] == ['unzip', '-p'] and len(args) == 4:
    import zipfile
    with zipfile.ZipFile(args[2]) as archive: sys.stdout.buffer.write(archive.read(args[3]))
elif name == 'date' and args == ['+%s']:
    hook = c.get('lock_hook')
    if hook == 'pending':
        job = state / 'jobs/race'; job.mkdir(parents=True)
        (state / 'latest').write_text(str(job)); (job / 'state').write_text('queued')
    elif hook == 'migration':
        path = root / 'data/adb/xuanyuan-unified-state/lock'; path.parent.mkdir(parents=True); path.touch()
    elif hook == 'phone': (root / 'data/adb/modules/xuanyuan-os4-phone/disable').touch()
    elif hook == 'role': c['roles']['android.app.role.DIALER'] = 'com.google.android.dialer'; config.write_text(json.dumps(c))
    elif hook == 'hash': (root / 'apks/com.android.contacts.apk').write_bytes(b'changed under lock')
    elif hook == 'integrity': (root / 'module/shared.sh').write_text('tampered')
    print(int(time.time()))
else:
    print('Unexpected Android command: ' + repr(command), file=sys.stderr); sys.exit(91)
'''


class StockAppsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='stock-apps-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.module = self.root / 'module'
        self.module.mkdir()
        self.modules = self.root / 'data/adb/modules'
        self.state = self.root / 'data/adb/xuanyuan-os4-suite-state'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        mock = self.bin / 'mock'
        mock.write_text('#!' + sys.executable + '\n' + MOCK)
        mock.chmod(0o700)
        for name in ('id', 'getprop', 'am', 'pm', 'cmd', 'busybox', 'sha256sum', 'date'):
            (self.bin / name).symlink_to(mock)
        ksu = self.root / 'data/adb/ksud'
        ksu.parent.mkdir(parents=True)
        ksu.symlink_to(mock)
        overlay = self.root / 'data/adb/metamodule/meta-overlayfs'
        overlay.parent.mkdir(parents=True)
        overlay.symlink_to(mock)
        self.phone = self.modules / 'xuanyuan-os4-phone'
        self.phone.mkdir(parents=True)
        catalog = (SOURCE / 'catalog.sh').read_text()
        self.code = re.search(r"phone\).*?CODE='([^']+)'", catalog)[1]
        self.phone_prop = 'id=xuanyuan-os4-phone\nversionCode=' + self.code + '\n'
        (self.phone / 'module.prop').write_text(self.phone_prop)
        meta = self.modules / 'meta-overlayfs'
        meta.mkdir()
        (meta / 'module.prop').write_text('versionCode=13100\n')
        (self.root / 'boot-id').write_text('test-boot\n')
        self.helper = self.module / 'stock-apps.sh'
        for name in ('stock-apps.sh', 'control.sh', 'catalog.sh', 'shared.sh', 'module.prop'):
            text = (SOURCE / name).read_text().replace('/data/', str(self.root / 'data') + '/')
            text = text.replace('/proc/sys/kernel/random/boot_id', str(self.root / 'boot-id'))
            text = re.sub(r'^BB=.*$', 'BB=' + shlex.quote(str(self.bin / 'busybox')), text, flags=re.M)
            (self.module / name).write_text(text)
        (self.module / 'payload').mkdir()
        with zipfile.ZipFile(self.module / 'payload/phone.zip', 'w') as archive:
            for name in ('restore-stock.sh', 'uninstall.sh'):
                raw = (SOURCE.parents[1] / 'components/phone' / name).read_bytes()
                archive.writestr(name, raw)
                (self.phone / name).write_bytes(raw)
        phone_sha = re.search(r"phone\).*?SHA='([^']+)'", catalog)[1]
        catalog = catalog.replace(phone_sha, hashlib.sha256((self.module / 'payload/phone.zip').read_bytes()).hexdigest())
        (self.module / 'catalog.sh').write_text(catalog)
        self.config = {'packages': {p: False for p in (*OLD.values(), *NEW.values(), INCALL)},
                       'roles': {'android.app.role.DIALER': NEW['phone'], 'android.app.role.SMS': NEW['sms']}}
        apks = self.root / 'apks'
        apks.mkdir()
        owned = []
        for p in self.config['packages']:
            content = ('fixture APK ' + p).encode()
            (apks / (p + '.apk')).write_bytes(content)
            owned.append('phone|' + p + '|' + hashlib.sha256(content).hexdigest())
        (self.module / 'owned-packages.txt').write_text('\n'.join(owned) + '\n')
        self.seal()
        self.sentinels = []
        for name in ('user/0/com.google.android.dialer/calls.db',
                     'user/0/com.google.android.apps.messaging/messages.db',
                     'user/0/com.android.providers.telephony/mmssms.db',
                     'user/0/com.android.contacts/contacts.db', 'user/0/com.android.mms/sms.db',
                     'user/0/com.xiaomi.xmsf/state', 'adb/lspd/config/modules.db', 'misc/roles.xml'):
            path = self.root / 'data' / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('preserve ' + name).encode())
            self.sentinels.append((path, path.read_bytes()))
        self.env = dict(os.environ, PATH=str(self.bin) + ':/usr/bin:/bin', LC_ALL='C', TEST_ROOT=str(self.root))

    def seal(self):
        (self.module / 'control.sha256').write_text(''.join(
            hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n'
            for p in sorted(self.module.iterdir()) if p.is_file() and p.name != 'control.sha256'))

    def run_helper(self, *args, ok=True):
        (self.root / 'config.json').write_text(json.dumps(self.config))
        result = subprocess.run(['/bin/sh', str(self.helper), *args], env=self.env,
                                text=True, capture_output=True, timeout=12)
        self.config = json.loads((self.root / 'config.json').read_text())
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        for path, content in self.sentinels:
            self.assertEqual(path.read_bytes(), content)
        return result

    def marker(self, app='phone'):
        return self.state / 'stock-apps' / (app + '.disabled')

    def actions(self):
        path = self.root / 'actions'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                for p in (self.root / 'data').rglob('*')}

    def test_status_is_readonly_strict_json_and_escapes_holder(self):
        before = self.snapshot()
        result = json.loads(self.run_helper('status').stdout)
        self.assertEqual(result, {app: dict(installed=True, disabled=False, holder=NEW[app], can_disable=True)
                                  for app in OLD})
        self.assertEqual(self.snapshot(), before)
        holder = 'quoted"\\role\nnext\t\x01'
        self.config['roles']['android.app.role.SMS'] = holder
        result = json.loads(self.run_helper('status').stdout)
        self.assertEqual(result['sms']['holder'], holder)
        self.assertFalse(result['sms']['can_disable'])
        self.assertEqual(self.actions(), [])

    def test_disable_enable_both_apps_only_and_mark_before_mutation(self):
        for app in OLD:
            self.run_helper('disable', app)
            self.assertTrue(self.config['packages'][OLD[app]])
            self.assertTrue(self.marker(app).is_file())
            self.assertTrue(json.loads(self.run_helper('status').stdout)[app]['disabled'])
            self.run_helper('enable', app)
            self.assertFalse(self.config['packages'][OLD[app]])
            self.assertFalse(self.marker(app).exists())
        for action in self.actions():
            self.assertTrue(action['marker'])
            self.assertEqual(action['lock']['boot'], 'test-boot')
            self.assertTrue(action['lock']['pid'].isdigit())
            self.assertTrue(action['lock']['created'].isdigit())
        self.assertFalse((self.state / 'lock').exists())

    def test_role_hash_disabled_missing_replacement_and_incall_gates(self):
        cases = ('role', 'multi-role', 'hash', 'missing', 'disabled', 'incall-hash', 'incall-disabled', 'split')
        baseline = json.loads(json.dumps(self.config))
        for app in ('phone',):
            for case in cases:
                with self.subTest(app=app, case=case):
                    self.config = json.loads(json.dumps(baseline))
                    p = INCALL if case.startswith('incall') else NEW[app]
                    apk = self.root / 'apks' / (p + '.apk')
                    raw = apk.read_bytes()
                    if case in ('role', 'multi-role'):
                        self.config['roles']['android.app.role.DIALER' if app == 'phone' else 'android.app.role.SMS'] = OLD[app] if case == 'role' else NEW[app] + '\n' + OLD[app]
                    elif case.endswith('hash'): apk.write_bytes(b'unknown update')
                    elif case == 'missing': del self.config['packages'][p]
                    elif case.endswith('disabled'): self.config['packages'][p] = True
                    elif case == 'split': self.config['split'] = p
                    # SMS deliberately has no incall dependency.
                    blocked = not (app == 'sms' and case.startswith('incall'))
                    try:
                        status = self.run_helper('status', ok=case != 'split')
                        if case != 'split': self.assertEqual(json.loads(status.stdout)[app]['can_disable'], not blocked)
                        self.run_helper('disable', app, ok=not blocked)
                        self.assertEqual(self.marker(app).exists(), not blocked)
                        if not blocked: self.run_helper('enable', app)
                    finally:
                        apk.write_bytes(raw)
        self.config = baseline

    def test_module_selection_exact_version_parent_and_phone_pending_gates(self):
        prop = self.phone / 'module.prop'
        for version in ('2026101208', '2026101501', 'unknown'):
            prop.write_text(self.phone_prop.replace(self.code, version))
            self.assertFalse(json.loads(self.run_helper('status').stdout)['phone']['can_disable'])
            self.run_helper('disable', 'phone', ok=False)
        prop.write_text(self.phone_prop)
        for directory in (self.phone, self.module):
            for flag in ('disable', 'remove', 'update'):
                path = directory / flag
                path.touch()
                self.run_helper('disable', 'phone', ok=False)
                path.unlink()
        for module in ('xuanyuan-os4-suite', 'xuanyuan-os4-phone'):
            path = self.root / 'data/adb/modules_update' / module
            path.mkdir(parents=True)
            self.run_helper('disable', 'phone', ok=False)
            path.rmdir()
        catalog = self.module / 'control.sh'
        catalog.write_text(catalog.read_text().replace('xiaoai phone gallery', 'xiaoai gallery'))
        self.seal()
        self.run_helper('disable', 'phone', ok=False)
        self.assertEqual(self.actions(), [])

    def test_same_code_old_or_changed_recovery_hooks_and_payload_rejected(self):
        before = self.snapshot()
        self.assertTrue(json.loads(self.run_helper('status').stdout)['phone']['can_disable'])
        self.assertEqual(self.snapshot(), before)
        for name in ('restore-stock.sh', 'uninstall.sh'):
            path = self.phone / name
            raw = path.read_bytes()
            for replacement in (None, b'#!/system/bin/sh\n# old child without recovery\n', raw + b'\n'):
                if replacement is None: path.unlink()
                else: path.write_bytes(replacement)
                self.assertFalse(json.loads(self.run_helper('status').stdout)['phone']['can_disable'])
                self.run_helper('disable', 'phone', ok=False)
                path.write_bytes(raw)
        prop = self.phone / 'module.prop'
        for text in ('versionCode=' + self.code + '\n', self.phone_prop.replace('xuanyuan-os4-phone', 'wrong-id')):
            prop.write_text(text)
            self.run_helper('disable', 'phone', ok=False)
        prop.write_text(self.phone_prop)
        payload = self.module / 'payload/phone.zip'
        payload.write_bytes(payload.read_bytes() + b'tampered')
        trace = self.root / 'trace'
        trace.unlink()
        self.assertFalse(json.loads(self.run_helper('status').stdout)['phone']['can_disable'])
        self.run_helper('disable', 'phone', ok=False)
        calls = [json.loads(line) for line in trace.read_text().splitlines()]
        self.assertFalse(any(call[:3] == ['busybox', 'unzip', '-p'] for call in calls))
        self.assertEqual(self.actions(), [])

    def test_stale_new_and_migration_locks_never_reconciled(self):
        for lock in (self.state / 'lock', self.root / 'data/adb/xuanyuan-unified-state/lock'):
            lock.mkdir(parents=True)
            (lock / 'boot').write_text('old boot')
            (lock / 'pid').write_text('99999999')
            before = self.snapshot()
            status = json.loads(self.run_helper('status').stdout)
            self.assertFalse(status['phone']['can_disable'])
            self.assertFalse(status['sms']['can_disable'])
            for op in ('enable', 'disable'): self.run_helper(op, 'phone', ok=False)
            self.assertEqual(self.snapshot(), before)
            (lock / 'boot').unlink(); (lock / 'pid').unlink(); lock.rmdir()
        lock = self.state / 'lock'
        lock.mkdir()
        self.run_helper('disable', 'phone', ok=False)
        self.assertEqual(list(lock.iterdir()), [])
        self.assertEqual(self.actions(), [])

    def test_queued_running_latest_without_lock_blocks(self):
        job = self.state / 'jobs/existing'
        job.mkdir(parents=True)
        (self.state / 'latest').write_text(str(job))
        for state in ('queued', 'running'):
            (job / 'state').write_text(state)
            before = self.snapshot()
            self.assertFalse(json.loads(self.run_helper('status').stdout)['phone']['can_disable'])
            for op in ('enable', 'disable'): self.run_helper(op, 'sms', ok=False)
            self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.actions(), [])

    def test_rechecks_under_controller_lock(self):
        for hook in ('pending', 'migration', 'phone', 'role', 'hash', 'integrity'):
            with self.subTest(hook=hook):
                # Each hook needs an independent fixture because it corrupts state.
                fixture = StockAppsTests()
                fixture.setUp()
                try:
                    fixture.config['lock_hook'] = hook
                    fixture.run_helper('disable', 'phone', ok=False)
                    self.assertEqual(fixture.actions(), [])
                    self.assertFalse((fixture.state / 'lock').exists())
                finally: fixture.doCleanups()

    def test_missing_original_and_external_disable_no_marker_claim(self):
        for app in OLD:
            del self.config['packages'][OLD[app]]
            status = json.loads(self.run_helper('status').stdout)[app]
            self.assertFalse(status['installed']); self.assertFalse(status['can_disable'])
            for op in ('enable', 'disable'):
                result = self.run_helper(op, app, ok=False)
                self.assertIn('not installed', result.stderr)
            self.config['packages'][OLD[app]] = True
            self.run_helper('disable', app)
            self.assertFalse(self.marker(app).exists())
            self.run_helper('enable', app)
        self.assertEqual([a['command'][1] for a in self.actions()], ['enable', 'enable'])

    def test_enable_survives_missing_disabled_or_pending_replacement(self):
        for flag in ('absent', 'disable', 'remove', 'update'):
            prop = self.phone / 'module.prop'
            if flag == 'absent': prop.unlink()
            else: (self.phone / flag).touch()
            self.config['packages'] = {OLD['phone']: True}
            self.config['roles'] = {}
            self.marker().parent.mkdir(parents=True, exist_ok=True)
            self.marker().write_text(OLD['phone'])
            self.run_helper('enable', 'phone')
            self.assertFalse(self.marker().exists())
            if flag == 'absent': prop.write_text(self.phone_prop)
            else: (self.phone / flag).unlink()

    def test_badargs_platform_integrity_fail_without_mutation(self):
        for args in ((), ('status', 'phone'), ('status', ''), ('disable',), ('enable',),
                     ('disable', 'phone', 'sms'), ('enable', 'other'), ('disable', 'phone;sms'),
                     ('library',), ('enable', '$(touch injected)')):
            self.run_helper(*args, ok=False)
        for key, value in (('uid', 2000), ('user', 10), ('multiuser', True),
                           ('props', {'ro.product.device': 'nezha'}),
                           ('props', {'ro.build.version.sdk': '36'}),
                           ('props', {'ro.build.version.incremental': 'wrong'})):
            self.config[key] = value
            self.run_helper('status', ok=False)
            self.run_helper('enable', 'phone', ok=False)
            del self.config[key]
        self.helper.write_text(self.helper.read_text() + '\n# tampered\n')
        self.run_helper('status', ok=False)
        self.run_helper('enable', 'phone', ok=False)
        self.assertEqual(self.actions(), [])
        self.assertFalse(self.state.exists())

    def test_query_failures_no_partial_status_or_disable(self):
        queries = [['pm', 'list', 'packages', '--user', '0'],
                   ['pm', 'list', 'packages', '-e', '--user', '0'],
                   ['pm', 'list', 'packages', '-d', '--user', '0'],
                   ['pm', 'path', '--user', '0', NEW['phone']],
                   ['cmd', 'role', 'get-role-holders', '--user', '0', 'android.app.role.DIALER'],
                   ['cmd', 'role', 'get-role-holders', '--user', '0', 'android.app.role.SMS']]
        for query in queries:
            self.config['fail'] = [query]
            result = self.run_helper('status', ok=False)
            self.assertEqual(result.stdout, '')
            self.run_helper('disable', 'sms' if query[-1].endswith('SMS') else 'phone', ok=False)
        self.config.pop('fail')
        self.config['malformed'] = [queries[0]]
        self.assertEqual(self.run_helper('status', ok=False).stdout, '')
        self.assertEqual(self.actions(), [])

    def test_disable_failure_noop_and_role_change_roll_back(self):
        for mode in ('fail', 'fail-after', 'noop', 'role'):
            with self.subTest(mode=mode):
                self.config['disable_mode'] = mode
                self.config['roles']['android.app.role.DIALER'] = NEW['phone']
                self.run_helper('disable', 'phone', ok=False)
                self.assertFalse(self.config['packages'][OLD['phone']])
                self.assertFalse(self.marker().exists())
                self.assertEqual([a['command'][1] for a in self.actions()[-2:]], ['disable-user', 'enable'])
        self.assertEqual(self.config['roles']['android.app.role.DIALER'], OLD['phone'])

    def test_uncertain_rollback_enable_noop_and_queryfail_retain_marker(self):
        self.config.update(disable_mode='role', enable_mode='noop')
        self.run_helper('disable', 'phone', ok=False)
        self.assertTrue(self.marker().exists())
        self.run_helper('enable', 'phone', ok=False)
        self.assertTrue(self.marker().exists())
        self.config['enable_mode'] = 'fail'
        self.run_helper('enable', 'phone', ok=False)
        self.assertTrue(self.marker().exists())
        self.config.pop('enable_mode')
        self.run_helper('enable', 'phone')
        self.assertFalse(self.marker().exists())
        self.config['disable_mode'] = ''
        self.config['roles']['android.app.role.DIALER'] = NEW['phone']
        self.config['post_fail'] = [['pm', 'list', 'packages', '-e', '--user', '0']]
        self.config.pop('did_disable', None)
        self.run_helper('disable', 'phone', ok=False)
        self.assertFalse(self.config['packages'][OLD['phone']])
        self.assertTrue(self.marker().exists())
        self.config.pop('post_fail')
        self.run_helper('enable', 'phone')
        self.assertFalse(self.marker().exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
