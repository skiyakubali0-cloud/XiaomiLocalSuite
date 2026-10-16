"""Host-only selected-suite regressions; no device tools or APK compilation.

Run: python3 -B -m unittest test_selected_suite -v
Optional real pinned 1.4: RUN_SELECTED_SUITE_INTEGRATION=1 (one whole-file hash).
Core fixtures retain small parent scripts but substitute tiny opaque payloads.
Only the pinned reviewed-suite result and fixture digests are mocked in tests.
"""
from __future__ import annotations
import copy
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import gui_session
import selected_suite as s
import suite_builder as b

MODULE = b.HERE.parent / 'unified-bundle/module'
if not MODULE.is_dir():
    MODULE = b.HERE / 'test-fixtures/selected-parent'
PIN = 'a9e08dd1a312b1824e28903828a71c82f31a63e045a0ed01e25251cc0752d2e7'
EXCLUDED = ('phone', 'gallery', 'weather', 'disaster', 'wallet', 'clock', 'calendar', 'mipush')


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SelectedSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Never read real child archives or wallet payload in core tests.
        cls.original = {n: (MODULE / n).read_bytes() for n in
                        (*s.SMALL, 'webroot/catalog.json', 'owned-packages.txt')}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='selected-suite-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'fixture.zip'
        self.payloads = {'payload/' + key + '.zip': b'opaque-child\x00' + key.encode()
                         for key in s.IDS}
        self.payloads['payload/unified.apk'] = b'original-API102-fixture\x00not-recompiled'
        self.payloads['payload/wallet.zip'] = b'wallet-must-not-be-opened'
        self.data = dict(self.original)
        catalog = json.loads(self.data['webroot/catalog.json'])
        for row in catalog:
            if row['id'] in s.IDS:
                row['sha256'] = digest(self.payloads['payload/' + row['id'] + '.zip'])
        self.data['webroot/catalog.json'] = json.dumps(catalog).encode()
        self.valid_data = dict(self.data)
        self.write_source()
        self.profile = s.new_profile()
        self.choose(*s.IDS)
        self.real_check = b.check_profile
        self.pinned = self.enterContext(patch.object(b, 'check_profile', side_effect=self.pinned_check))
        self.enterContext(patch.object(s, 'CHILD_SHA', {
            key: digest(self.payloads['payload/' + key + '.zip']) for key in s.IDS}))
        self.enterContext(patch.object(s, 'UNIFIED_SHA', digest(self.payloads['payload/unified.apk'])))

    # TestCase.enterContext was added after the system Python 3.9.
    def enterContext(self, context):
        value = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        return value

    def write_source(self):
        with zipfile.ZipFile(self.source, 'w') as z:
            for name, data in {**self.data, **self.payloads}.items():
                z.writestr(name, data)

    def choose(self, *ids):
        for row in self.profile['components']:
            row['enabled'] = row['id'] in ids

    def pinned_check(self, profile, base, materials=None):
        if profile['mode'] != 'reviewed-suite':
            return self.real_check(profile, base, materials)
        self.assertEqual(profile['artifact_sha256'], PIN)
        b.identity(profile)
        return {'artifact': str(self.source), 'artifact_sha256': b.sha(self.source),
                'state': 'reviewed-recipe', 'device_tested': True}

    def transformed(self, ids=None):
        with zipfile.ZipFile(self.source) as z:
            return s.files(z, list(ids or s.selected(self.profile)))

    def test_reuse_exact_children_and_api102_bytes_and_checksums(self):
        out = self.root / 'selected.zip'
        real_open = zipfile.ZipFile.open
        def guarded_open(archive, name, *args, **kwargs):
            self.assertNotEqual(getattr(name, 'filename', name), 'payload/wallet.zip')
            return real_open(archive, name, *args, **kwargs)
        with patch.object(zipfile.ZipFile, 'open', guarded_open):
            result = s.build(self.profile, self.root, out)
        self.assertFalse(result['device_tested'])
        self.assertTrue(result['reused_payloads_from_device_tested_suite'])
        self.assertEqual(self.pinned.call_count, 1)
        b.verify_archive(out)
        with zipfile.ZipFile(out) as z:
            self.assertEqual({n for n in z.namelist() if n.startswith('payload/')},
                             set(self.payloads) - {'payload/wallet.zip'})
            for name, data in self.payloads.items():
                if name != 'payload/wallet.zip':
                    self.assertEqual(z.read(name), data)
            for line in z.read('control.sha256').decode().splitlines():
                sha, name = line.split('  ', 1)
                self.assertEqual(digest(z.read(name)), sha, name)
            self.assertEqual(json.loads(z.read('selection.json'))['components'], list(s.IDS))
        self.assertEqual(json.loads(out.with_suffix('.build.json').read_text())['sha256'], b.sha(out))
        self.assertFalse(list(self.root.glob('*.partial')))

    def test_all_selections_and_session_dependency_closure(self):
        session = gui_session.Session()
        session.profile = self.profile
        for count in range(1, 4):
            for requested in itertools.combinations(s.IDS, count):
                with self.subTest(requested=requested):
                    session.set_selected(list(requested))
                    expected = set(requested) | ({'assistant'} if 'xiaoai' in requested else set())
                    self.assertEqual(s.selected(session.profile), [x for x in s.IDS if x in expected])
        self.choose('xiaoai')
        with self.assertRaisesRegex(ValueError, '依赖'):
            s.check(self.profile, self.root)

    def test_build_selection_matrix_omits_unselected_children_keeps_required_apk(self):
        for ids in (['market'], ['assistant'], ['market', 'assistant'],
                    ['assistant', 'xiaoai'], list(s.IDS)):
            with self.subTest(ids=ids):
                self.choose(*ids)
                before = copy.deepcopy(self.profile)
                output = self.root / ('-'.join(ids) + '.zip')
                result = s.build(self.profile, self.root, output)
                self.assertEqual(self.profile, before)
                self.assertEqual([c['id'] for c in result['components']], ids)
                with zipfile.ZipFile(output) as archive:
                    expected = {'payload/' + key + '.zip' for key in ids} | {'payload/unified.apk'}
                    self.assertEqual({n for n in archive.namelist() if n.startswith('payload/')}, expected)
                    for name in expected:
                        self.assertEqual(archive.read(name), self.payloads[name])

    def test_wallet_unknown_duplicate_reordered_nonboolean_config_rejected(self):
        original = copy.deepcopy(self.profile)
        cases = []
        for value in ('wallet', 'mipush', '../wallet', 'market;wallet', 'unknown'):
            changed = copy.deepcopy(original)
            changed['components'][0]['id'] = value
            cases.append(changed)
        for rows in ([*original['components'], {'id': 'wallet', 'enabled': False}],
                     original['components'][::-1], original['components'][:2],
                     [original['components'][0]] * 3):
            cases.append(dict(original, components=rows))
        for value in (None, 1, 'true'):
            changed = copy.deepcopy(original)
            changed['components'][0]['enabled'] = value
            cases.append(changed)
        cases.extend([dict(original, components=None),
                      dict(original, components=[dict(c, enabled=False) for c in original['components']])])
        for profile in cases:
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                s.check(profile, self.root)
        self.pinned.assert_not_called()
        session = gui_session.Session()
        session.profile = copy.deepcopy(original)
        for value in ('wallet', 'unknown', 'market;wallet'):
            with self.assertRaises(ValueError):
                session.set_selected([value])
        session.profile['components'].append({'id': 'wallet', 'enabled': True})
        self.assertEqual(session.check()['state'], 'blocked')

    def test_unmocked_pin_rejects_hand_edited_identity_before_large_file_read(self):
        for key, value in (('artifact_sha256', '0' * 64), ('artifact', 'wallet.zip'),
                           ('target', dict(self.profile['target'], device='other')),
                           ('wallet_policy', 'auto-reset')):
            changed = dict(self.profile, **{key: value})
            with self.subTest(key=key), patch.object(b, 'check_profile', self.real_check), \
                    patch.object(b, 'sha', side_effect=AssertionError('must reject before file hash')):
                with self.assertRaises(ValueError):
                    s.check(changed, self.root)

    def test_catalog_order_owned_migration_filtered_for_each_valid_subset(self):
        for ids in (['market'], ['assistant'], ['market', 'assistant'],
                    ['assistant', 'xiaoai'], list(s.IDS)):
            with self.subTest(ids=ids):
                data = self.transformed(ids)
                self.assertEqual([c['id'] for c in json.loads(data['webroot/catalog.json'])], ids)
                self.assertEqual(re.findall(r"^ORDER='(.*)'$", data['control.sh'].decode(), re.M), [' '.join(ids)])
                self.assertEqual(re.findall(r'^([a-z]+)\)', data['catalog.sh'].decode(), re.M), ids)
                self.assertTrue(all(line.split('|')[0] in ids for line in
                                    data['owned-packages.txt'].decode().splitlines()))
                packages = re.findall(r"^PACKAGES='([^']*)'$", data['migrate-legacy.sh'].decode(), re.M)
                self.assertEqual(packages, ['local.xuanyuan.aiprivacy local.xuanyuan.suggestioncompat'
                                          if 'xiaoai' in ids else ''])
                ui = data['webroot/index.html'].decode()
                self.assertIn("prepare('install',catalog.map(item => item.id))", ui)
                self.assertNotIn("await exec('preset')", ui)
                self.assertEqual(data['shared.sh'], self.original['shared.sh'])
                installer = data['customize.sh'].decode()
                self.assertNotIn('shared_install', installer)
                self.assertIn('sh "$MODPATH/install-selected.sh"', installer)
                self.assertIn('install-selected.ok', installer)
                self.assertIn("AUTO_IDS='" + ','.join(ids) + "'", data['install-selected.sh'].decode())
                self.assertNotIn('PresetActivity', installer)
                self.assertNotIn('preset.sh', installer)
                self.assertIn('for R in ASSISTANT; do', data['control.sh'].decode())
                readme = data['README.txt'].decode()
                for disclosure in ('不要点击', '迁移/恢复', '全部五', '推送作用域'):
                    self.assertIn(disclosure, readme)

    def shell_environment(self):
        sandbox = self.root / 'shell'
        sandbox.mkdir(exist_ok=True)
        bin_dir = sandbox / 'bin'
        bin_dir.mkdir(exist_ok=True)
        journal = sandbox / 'commands'
        for name in ('am', 'pm', 'cmd', 'settings', 'reboot', 'ksud', 'adb', 'fastboot', 'su'):
            command = bin_dir / name
            command.write_text('#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$COMMAND_JOURNAL"\nexit 0\n')
            command.chmod(0o755)
        # Do not inherit host/device tools. Only these host utilities are needed.
        for name in ('cat', 'tr', 'rm', 'date'):
            link = bin_dir / name
            if not link.exists():
                link.symlink_to(shutil.which(name))
        return sandbox, journal, dict(os.environ, PATH=str(bin_dir), COMMAND_JOURNAL=str(journal))

    def test_preset_shim_all_actions_arguments_inert(self):
        sandbox, journal, env = self.shell_environment()
        preset = sandbox / 'preset.sh'
        preset.write_bytes(self.transformed()['preset.sh'])
        sentinel = sandbox / 'state'
        sentinel.write_bytes(b'preserved prefs scope wallet')
        cases = [(), ('',)]
        for action in ('plan', 'apply', 'migrate', 'reboot', 'lsp', 'unknown'):
            cases.extend(((action,), (action, '-', '-'),
                          (action, s.ORDER.replace(' ', ','), 'phone,privacy,suggestions,warning,clock'),
                          (action, '$(touch sentinel);wallet', 'privacy', 'extra')))
        for args in cases:
            with self.subTest(args=args):
                result = subprocess.run(['/bin/sh', str(preset), *args], env=env, cwd=sandbox,
                                        capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(sentinel.read_bytes(), b'preserved prefs scope wallet')
        self.assertEqual(set(p.name for p in sandbox.iterdir()), {'bin', 'preset.sh', 'state'})
        self.assertFalse(journal.exists(), 'preset invoked an external/device command')

    def migration_harness(self, ids):
        sandbox, journal, env = self.shell_environment()
        apk = sandbox / 'unified.apk'
        apk.write_bytes(self.payloads['payload/unified.apk'])
        boot = sandbox / 'boot-id'
        boot.write_text('current-boot\n')
        state = sandbox / 'android/xuanyuan-unified-state'
        state.mkdir(parents=True, exist_ok=True)
        (state / 'preserved-prefs').write_bytes(b'phone warning clock AI push wallet unchanged')
        text = self.transformed(ids)['migrate-legacy.sh'].decode()
        # Keep the complete original status block, platform guards and hashing logic.
        status = 'if [ "$1" = status ]; then\n'
        original_status = self.original['migrate-legacy.sh'].decode().split(status, 1)[1].split('\nfi\n', 1)[0]
        self.assertEqual(text.split(status, 1)[1].split('\nfi\n', 1)[0], original_status)
        text = text.replace('/data/adb', str(sandbox / 'android'))
        text = text.replace('/proc/sys/kernel/random/boot_id', str(boot))
        expected_sha = re.search(r'^SELF_SHA=(\w+)$', text, re.M).group(1)
        text = text.replace('SELF_SHA=' + expected_sha, 'SELF_SHA=' + digest(apk.read_bytes()))
        script = sandbox / 'migrate-legacy.sh'
        script.write_text(text)
        # These host doubles supply Android read responses; no real device command.
        mock = sandbox / 'mock.py'
        mock.write_text('''#!''' + sys.executable + '''
import hashlib, json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['COMMAND_JOURNAL'], 'a') as journal:
    journal.write(json.dumps([name] + args) + '\\n')
if name == 'id' and args == ['-u']:
    print(os.environ.get('MOCK_UID', '0'))
elif name == 'getprop':
    props = {'ro.product.device':'xuanyuan', 'ro.build.version.sdk':'37',
             'ro.build.version.incremental':'OS4.0.0.6.XOAEUXM'}
    props.update(json.loads(os.environ.get('MOCK_PROPS', '{}')))
    print(props.get(args[0], ''))
elif name == 'am' and args == ['get-current-user']:
    print(os.environ.get('MOCK_USER', '0'))
elif name == 'pm' and args == ['list', 'users']:
    print('UserInfo{0:Owner:13} running')
    if os.environ.get('MOCK_MULTIUSER') == '1': print('UserInfo{10:Second:10}')
elif name == 'pm' and args == ['path', '--user', '0', 'local.xuanyuan.mipushcompat']:
    if os.environ.get('MOCK_NO_APK') != '1':
        print('package:' + os.environ['MOCK_APK'])
elif name == 'sha256sum' and len(args) == 1:
    print(hashlib.sha256(pathlib.Path(args[0]).read_bytes()).hexdigest() + '  ' + args[0])
else:
    sys.exit(97)
''')
        mock.chmod(0o755)
        for name in ('id', 'getprop', 'am', 'pm', 'sha256sum', 'mkdir', 'chmod', 'cp', 'rmdir',
                     'reboot', 'settings', 'dumpsys', 'su', 'adb', 'fastboot'):
            path = sandbox / 'bin' / name
            path.unlink(missing_ok=True)
            path.symlink_to(mock)
        for name in ('sed', 'grep', 'cut'):
            (sandbox / 'bin' / name).symlink_to(shutil.which(name))
        env.update(MOCK_APK=str(apk))
        return script, state, journal, env

    @staticmethod
    def migration_state(state):
        return {str(p.relative_to(state)): ('directory' if p.is_dir() else p.read_bytes())
                for p in state.rglob('*')}

    def test_migration_status_retains_real_lock_boot_and_identity_checks(self):
        script, state, journal, env = self.migration_harness(list(s.IDS))
        cases = [('', False, {}, 'MIGRATION_READY'),
                 ('current-boot\n', False, {}, 'MIGRATION_REBOOT_REQUIRED'),
                 ('older-boot\n', False, {}, 'MIGRATION_READY'),
                 ('current-boot\n', True, {}, '迁移任务仍在运行或已中断'),
                 ('', False, {'MOCK_UID': '2000'}, '需要Root'),
                 ('', False, {'MOCK_PROPS': '{"ro.product.device":"other"}'}, '不支持此机型或系统'),
                 ('', False, {'MOCK_PROPS': '{"ro.build.version.sdk":"36"}'}, '不支持此机型或系统'),
                 ('', False, {'MOCK_PROPS': '{"ro.build.version.incremental":"other"}'}, '不支持此机型或系统'),
                 ('', False, {'MOCK_USER': '10'}, '只支持机主单用户0'),
                 ('', False, {'MOCK_MULTIUSER': '1'}, '只支持机主单用户0'),
                 ('', False, {'MOCK_NO_APK': '1'}, '统一插件不是本套件精确版本')]
        for boot, locked, overrides, expected in cases:
            with self.subTest(boot=boot, locked=locked, overrides=overrides):
                marker = state / 'migration-boot'
                marker.unlink(missing_ok=True)
                if boot:
                    marker.write_text(boot)
                lock = state / 'lock'
                if lock.exists():
                    lock.rmdir()
                if locked:
                    lock.mkdir()
                before = self.migration_state(state)
                result = subprocess.run(['/bin/sh', str(script), 'status'], env=dict(env, **overrides),
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode == 0, expected.startswith('MIGRATION_'), result.stderr)
                self.assertIn(expected, result.stdout + result.stderr)
                self.assertEqual(self.migration_state(state), before)
        # Actual changed fixture bytes must fail the real sha() comparison.
        Path(env['MOCK_APK']).write_bytes(b'unknown shared APK')
        before = self.migration_state(state)
        result = subprocess.run(['/bin/sh', str(script), 'status'], env=env,
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('统一插件不是本套件精确版本', result.stderr)
        self.assertEqual(self.migration_state(state), before)
        for line in journal.read_text().splitlines():
            call = json.loads(line)
            self.assertTrue(call[0] in ('id', 'getprop', 'am', 'sha256sum') or
                            call[:3] == ['pm', 'path', '--user'] or call == ['pm', 'list', 'users'], call)

    def test_migration_remove_restore_and_extra_arguments_fail_before_any_command_or_write(self):
        for ids in (['market'], list(s.IDS)):
            with self.subTest(ids=ids):
                # Isolate both artifacts' filesystem and command journals.
                script, state, journal, env = self.migration_harness(ids)
                for package in ('smscompat', 'aiprivacy', 'suggestioncompat', 'disastercompat', 'clockcompat'):
                    backup = state / 'apks' / (package + '.apk')
                    backup.parent.mkdir(exist_ok=True)
                    backup.write_bytes(b'preserve old backup ' + package.encode())
                before = self.migration_state(state)
                for action in ('remove', 'restore'):
                    for extras in ([], [''], ['status'], ['wallet'], ['privacy,suggestions'],
                                   ['$(reboot);wallet'], ['remove', 'restore'], ['x'] * 20):
                        with self.subTest(action=action, extras=extras):
                            result = subprocess.run(['/bin/sh', str(script), action, *extras], env=env,
                                                    capture_output=True, text=True, timeout=5)
                            self.assertNotEqual(result.returncode, 0)
                            self.assertIn('需要一个固定操作' if extras else '精选包不迁移旧插件', result.stderr)
                            self.assertEqual(self.migration_state(state), before)
                            self.assertFalse(journal.exists(), 'gate ran a command before refusing mutation')
                for args in ([], [''], ['unknown'], ['status', 'extra']):
                    result = subprocess.run(['/bin/sh', str(script), *args], env=env,
                                            capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(self.migration_state(state), before)
                    self.assertFalse(journal.exists())
                # Reuse the shell sandbox for the next artifact without accumulated links.
                shutil.rmtree(script.parent)

    def test_controller_rejects_wallet_forged_ids_with_valid_worker_lock(self):
        sandbox, journal, env = self.shell_environment()
        data = self.transformed()
        module = sandbox / 'module'
        module.mkdir()
        for name in ('catalog.sh', 'shared.sh'):
            (module / name).write_bytes(data[name])
        text = data['control.sh'].decode().replace('/data/adb', str(sandbox / 'android'))
        # Bypass only environment guards. ID validation and dispatch remain real.
        marker = '\ncase "$1" in\n'
        self.assertEqual(text.count(marker), 1)
        text = text.replace(marker, '\nplatform() { :; }\nintegrity() { :; }\n'
                            'reconcile() { :; }\n' + marker)
        controller = module / 'control.sh'
        controller.write_text(text)
        state = sandbox / 'android/xuanyuan-os4-suite-state'
        job = state / 'jobs/valid'
        job.mkdir(parents=True)
        for selected_id in (*EXCLUDED, 'market,wallet', 'wallet,market', '../wallet',
                            'wallet;reboot', '$(reboot)', 'market,,wallet'):
            for action in ('open', 'plan', 'start', 'worker'):
                with self.subTest(action=action, id=selected_id):
                    (state / 'lock').mkdir(exist_ok=True)
                    (state / 'latest').write_text(str(job))
                    args = {'open': ['open', selected_id], 'plan': ['plan', 'install', selected_id],
                            'start': ['start', 'install', selected_id],
                            'worker': ['worker', str(job), 'install', selected_id]}[action]
                    result = subprocess.run(['/bin/sh', str(controller), *args], env=env,
                                            capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn('组件', result.stderr, result.stderr)
        self.assertFalse(journal.exists(), 'rejected ID reached an Android command')
        result = subprocess.run(['/bin/sh', str(controller), 'open', 'market'], env=env,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('com.xiaomi.market', journal.read_text())
        result = subprocess.run(['/bin/sh', str(controller), 'preset'], env=env,
                                capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('PresetActivity', journal.read_text())

    def test_damaged_source_contract_rejected_without_output(self):
        mutations = [('control.sh', b"ORDER='" + s.ORDER.encode() + b"'", b"ORDER='wallet'"),
                     ('control.sh', b'for R in DIALER SMS ASSISTANT WALLET; do', b'for R in WALLET; do'),
                     ('webroot/index.html', '一键配置当前方案'.encode(), b'changed-label'),
                     ('migrate-legacy.sh', b"PACKAGES='local.xuanyuan.smscompat", b"PACKAGES='changed"),
                     ('migrate-legacy.sh', b'case "$1" in status|remove|restore)', b'case "$1" in status)'),
                     ('module.prop', b'version=1.4\n', b'version=9\n')]
        for name, old, new in mutations:
            with self.subTest(name=name, old=old):
                self.data = dict(self.valid_data)
                self.assertEqual(self.data[name].count(old), 1)
                self.data[name] = self.data[name].replace(old, new)
                self.write_source()
                output = self.root / 'must-not-exist.zip'
                with self.assertRaisesRegex(ValueError, 'source contract changed'):
                    s.build(self.profile, self.root, output)
                self.assertFalse(output.exists())
                self.assertFalse(output.with_suffix('.build.json').exists())
                self.assertFalse(list(self.root.glob('*.partial')))

    def test_wrong_shared_apk_and_child_bytes_never_publish(self):
        for member in ('payload/unified.apk', 'payload/xiaoai.zip'):
            with self.subTest(member=member):
                previous = self.payloads[member]
                self.payloads[member] = previous + b'corrupt'
                self.write_source()
                output = self.root / 'corrupt.zip'
                with self.assertRaisesRegex(ValueError, 'Shared API102 APK differs|Child changed'):
                    s.build(self.profile, self.root, output)
                self.assertFalse(output.exists())
                self.assertFalse(list(self.root.glob('*.partial')))
                self.payloads[member] = previous


@unittest.skipUnless(os.environ.get('RUN_SELECTED_SUITE_INTEGRATION') == '1',
                     'Optional real 1.4; set RUN_SELECTED_SUITE_INTEGRATION=1')
class PinnedReleaseIntegration(unittest.TestCase):
    def test_real_pin_source_contract_original_payloads(self):
        source = Path(os.environ.get('SELECTED_SUITE_SOURCE',
                      str(b.HERE.parent / 'unified-bundle/xuanyuan-os4-suite-1.4.zip')))
        # One archive hash. Do not call production check/build repeatedly on 1.4.
        self.assertEqual(b.sha(source), PIN)
        with zipfile.ZipFile(source) as z:
            transformed = s.files(z, list(s.IDS))
            self.assertEqual([c['id'] for c in json.loads(transformed['webroot/catalog.json'])], list(s.IDS))
            for key in s.IDS:
                h = hashlib.sha256()
                with z.open('payload/' + key + '.zip') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        h.update(chunk)
                self.assertEqual(h.hexdigest(), s.CHILD_SHA[key])
            self.assertEqual(digest(z.read('payload/unified.apk')), s.UNIFIED_SHA)
            self.assertNotIn('wallet', json.loads(transformed['selection.json'])['components'])
        # No child archive, especially wallet.zip, is expanded or inspected.


if __name__ == '__main__':
    unittest.main()
