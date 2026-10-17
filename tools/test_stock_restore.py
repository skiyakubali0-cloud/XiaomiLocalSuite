"""Execute marker-owned original-app recovery without an Android device."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ('com.google.android.dialer', 'com.google.android.apps.messaging')
MOCK = r'''
import json,os,pathlib,sys
root=pathlib.Path(os.environ['TEST_ROOT']);args=sys.argv[1:];name=pathlib.Path(sys.argv[0]).name
config=json.loads((root/'config.json').read_text())
with (root/'calls').open('a') as f:f.write(json.dumps([name]+args)+'\n')
if name=='pm' and args[:2]==['list','packages']:
    for pkg,state in config['packages'].items():
        if pkg==args[-1] and ('-e' not in args or state=='enabled'):print('package:'+pkg)
elif name=='pm' and args[:3]==['enable','--user','0']:
    if config.get('fail_enable'):sys.exit(1)
    if not config.get('noop_enable'):config['packages'][args[3]]='enabled'
    (root/'config.json').write_text(json.dumps(config))
elif name=='pm' and args[:1]==['path']:pass
elif name=='cmd' and args[:2]==['role','get-role-holders']:
    print('com.android.contacts' if args[-1].endswith('DIALER') else 'com.android.mms')
elif name=='cmd' and args[:2] in (['role','add-role-holder'],['overlay','disable']):
    if config.get('require_lock') and not (root/'data/adb/xuanyuan-os4-suite-state/lock').is_dir():sys.exit(93)
else:sys.exit(92)
'''


class StockRestoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='stock-recovery-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        mock = self.bin / 'mock.py'
        mock.write_text('#!' + sys.executable + '\n' + MOCK)
        mock.chmod(0o700)
        for command in ('pm', 'cmd', 'ksud'):
            (self.bin / command).symlink_to(mock)
        self.state = self.root / 'data/adb/xuanyuan-os4-suite-state/stock-apps'
        self.state.mkdir(parents=True)
        self.phone_state = self.root / 'data/adb/xuanyuan-os4-phone-state'
        self.phone_state.mkdir()
        for key, pkg in zip(('before-dialer', 'before-sms'), PACKAGES):
            (self.phone_state / key).write_text(pkg + '\n')
        self.env = dict(os.environ, TEST_ROOT=str(self.root), PATH=str(self.bin)+':/usr/bin:/bin')
        self.config = {'packages': dict.fromkeys(PACKAGES, 'disabled')}
        self.boot = self.root / 'boot-id'
        self.boot.write_text('boot-A\n')
        for name in ('restore-stock.sh', 'uninstall.sh'):
            raw = (ROOT / 'components/phone' / name).read_text()
            raw = raw.replace('/data/', str(self.root / 'data') + '/')
            (self.root / name).write_text(raw.replace('/proc/sys/kernel/random/boot_id', str(self.boot)))
        self.sentinel = self.root / 'app-data'
        self.sentinel.write_bytes(b'sms contacts calllog wallet and credentials sentinel')

    def mark(self, *ids):
        for key in ids:
            (self.state / (key + '.disabled')).touch()

    def run_script(self, name='restore-stock.sh'):
        (self.root / 'config.json').write_text(json.dumps(self.config))
        result = subprocess.run(['/bin/sh', str(self.root / name)], env=self.env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(self.sentinel.read_bytes(), b'sms contacts calllog wallet and credentials sentinel')
        self.config = json.loads((self.root / 'config.json').read_text())
        return result

    def calls(self):
        path = self.root / 'calls'
        return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []

    def test_unowned_disable_is_not_changed(self):
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertEqual(set(self.config['packages'].values()), {'disabled'})

    def test_only_marked_original_is_restored_and_repeat_is_noop(self):
        self.mark('sms')
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.config['packages'][PACKAGES[0]], 'disabled')
        self.assertEqual(self.config['packages'][PACKAGES[1]], 'enabled')
        self.assertFalse((self.state / 'sms.disabled').exists())
        before = self.calls()
        self.assertEqual(self.run_script().returncode, 0)
        self.assertEqual(self.calls(), before)

    def test_enable_failure_or_noop_retains_marker(self):
        for failure in ('fail_enable', 'noop_enable'):
            with self.subTest(failure=failure):
                self.mark('phone')
                self.config[failure] = True
                self.assertNotEqual(self.run_script().returncode, 0)
                self.assertTrue((self.state / 'phone.disabled').exists())
                self.config.pop(failure)

    def test_missing_original_retains_marker(self):
        self.mark('sms')
        self.config['packages'].pop(PACKAGES[1])
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertTrue((self.state / 'sms.disabled').exists())
        self.assertFalse(any(row[1]=='enable' for row in self.calls()))

    def test_uninstall_enables_originals_before_restoring_roles(self):
        self.mark('phone', 'sms')
        self.config['require_lock'] = True
        result = self.run_script('uninstall.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        for role, pkg in zip(('DIALER', 'SMS'), PACKAGES):
            self.assertLess(calls.index(['pm', 'enable', '--user', '0', pkg]),
                            calls.index(['cmd', 'role', 'add-role-holder', '--user', '0', 'android.app.role.'+role, pkg, '0']))
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertFalse((self.state.parent / 'lock').exists())

    def test_uninstall_stops_before_role_or_overlay_changes_on_recovery_failure(self):
        self.mark('phone')
        self.config['fail_enable'] = True
        self.assertNotEqual(self.run_script('uninstall.sh').returncode, 0)
        self.assertFalse(any(row[0]=='cmd' for row in self.calls()))

    def test_controller_stops_before_disabling_module_when_original_enable_fails(self):
        # Run the original restore_one, replacing extraction and Android paths only.
        self.mark('phone')
        self.config['fail_enable'] = True
        source = ROOT / 'suite/module'
        for name in ('catalog.sh', 'shared.sh'):
            (self.root / name).write_bytes((source / name).read_bytes())
        prefix = (source / 'control.sh').read_text().rsplit('\ncase "$1" in\n', 1)[0]
        prefix = prefix.replace('M=${0%/*}', 'M='+shlex.quote(str(self.root)))
        prefix = prefix.replace('/data/', str(self.root / 'data') + '/')
        prefix = re.sub(r'^K=.*$', 'K='+shlex.quote(str(self.bin / 'ksud')), prefix, flags=re.M)
        lock = shlex.quote(str(self.state.parent / 'lock'))
        (self.root / 'restore-controller.sh').write_text(prefix+'\nextract() { E='+shlex.quote(str(self.root))+'; }\nmkdir '+lock+'\nprintf "%s\\n" "$$" > '+lock+'/pid\ncat '+shlex.quote(str(self.boot))+' > '+lock+'/boot\nrestore_one phone\n')
        result = self.run_script('restore-controller.sh')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('未停用电话模块', result.stderr)
        self.assertIn(['pm', 'enable', '--user', '0', PACKAGES[0]], self.calls())
        self.assertFalse(any(row[0] in ('ksud', 'cmd') for row in self.calls()))

    def test_recovery_refuses_foreign_lock_and_leaves_marker_untouched(self):
        self.mark('phone')
        lock = self.state.parent / 'lock'
        lock.mkdir()
        (lock / 'pid').write_text('987654\n')
        result = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.state / 'phone.disabled').exists())
        self.assertEqual((lock / 'pid').read_text(), '987654\n')

    def test_parent_worker_can_recover_and_uninstall_without_releasing_its_lock(self):
        self.mark('phone', 'sms')
        self.config['require_lock'] = True
        lock = shlex.quote(str(self.state.parent / 'lock'))
        script = 'mkdir '+lock+'\nprintf "%s\\n" "$$" > '+lock+'/pid\ncat '+shlex.quote(str(self.boot))+' > '+lock+'/boot\n'
        for name in ('restore-stock.sh', 'uninstall.sh'):
            script += 'XLS_STOCK_PARENT=$$ sh '+shlex.quote(str(self.root / name))+' || exit 1\n[ -d '+lock+' ] || exit 1\n'
        (self.root / 'parent.sh').write_text(script)
        result = self.run_script('parent.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertTrue((self.state.parent / 'lock').is_dir())

    def test_invalid_parent_claim_cannot_skip_lock(self):
        self.mark('sms')
        self.env['XLS_STOCK_PARENT'] = '987654'
        self.assertNotEqual(self.run_script().returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.state / 'sms.disabled').exists())


if __name__ == '__main__':
    unittest.main()
