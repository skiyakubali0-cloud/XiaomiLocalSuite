"""Offline selection fixtures: real controller guards, intercepted Android commands.

Run python3 -B test_preset.py -v. Fixtures add the main-owned library dispatch and
current release metadata; they never build an APK, contact adb, or touch a device.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import types
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).absolute().parent
legacy = types.ModuleType('controller_fixtures')
legacy.__file__ = str(HERE.parent / 'test_control.py')
exec(compile(Path(legacy.__file__).read_text(), legacy.__file__, 'exec'), legacy.__dict__)
legacy.SOURCE = HERE / 'module'
PROFILE = 'market,assistant,xiaoai,phone,gallery,weather,disaster,wallet,clock,calendar,mipush'
FEATURES = 'phone,privacy,suggestions,warning,clock'
WALLET = 'c5fa1012886f21d9be2453d66e741d6821e9b94d39a6881318c3d1d196ddb058'
CLOCK = '41defcfd640a3ba5d359c20004d9dced5f6c0810204c41c94530af2a2bc1e9f6'
CN_CALENDAR = 'ed8f4356bb7c44038abbe5f215f215277c114e75de4bd21ac0a65f77d75f75f0'
GLOBAL_CALENDAR = 'e2f2e6f2cc5d5ab32480447c23b91c90b2c5db863a38907c6dff61fec80566e7'


class PresetTests(unittest.TestCase):
    calls = legacy.ControllerTests.calls
    enable = legacy.ControllerTests.enable

    def setUp(self):
        legacy.ControllerTests.setUp(self)
        # The original controller fixture intercepts every Android executable.
        mock = self.bin / 'mock.py'
        text = mock.read_text().replace('elif name == "ksud":', '''elif name == "reboot":
    record([name] + args)
elif name == "ksud":''')
        # A fixture can backdate mtime, but not inode ctime. Use its seeded
        # epoch for %Z, with an independent override for preserved ZIP dates.
        text = text.replace('("%s", "%Y")', '("%s", "%Y", "%Z")')
        text = text.replace('    # Android stat defaults', '''    if args[1] == "%Z" and args[2].endswith("xuanyuan-os4-market/module.prop") and os.environ.get("TEST_MARKET_CTIME"):
        print(os.environ["TEST_MARKET_CTIME"])
        sys.exit(0)
    # Android stat defaults''')
        text = text.replace('    record(args)\n    if args[:2]', '''    record(args)
    if args[:2] == ["module", "enable"]:
        (root / "data/adb/modules" / args[2] / "disable").unlink(missing_ok=True)
    if args[:2]''')
        text = text.replace('    if args[3] in packages:\n        print("package:"', '''    if os.environ.get("TEST_SPLIT") == args[3]:
        print("package:" + str(root / "apks/base.apk"))
        print("package:" + str(root / "apks/split.apk"))
    elif args[3] in packages:
        print("package:"''')
        text = text.replace('(root / "launch").touch()', '(root / "launch").touch()\n    (root / "launch-args").write_text(json.dumps(args))')
        mock.write_text(text)
        self.env['TEST_WALLET_MATCH'] = '1'
        for mid in ('zygisksu', 'zygisk_lsposed'):
            self.enable(mid)
        self.paths = {'/data': str(self.root / 'data'),
                      '/product/': str(self.root / 'product') + '/',
                      '/proc/stat': str(self.root / 'boot-stat')}
        (self.root / 'boot-stat').write_text('btime 2000\n')
        self.preset = self.module / 'preset.sh'
        self.preset.write_text(self.adapt((HERE / 'preset.sh').read_text()))
        catalog = (self.module / 'catalog.sh').read_text()
        catalog = re.sub(r"(^xiaoai\).*?CODE=)'[^']+'", r"\1'2026101504'", catalog, flags=re.M)
        (self.module / 'catalog.sh').write_text(catalog)
        self.apk_sha = self.catalog('clock', 'SHA')
        shared = (HERE / 'module/shared.sh').read_text()
        shared = re.sub(r'^UNIFIED_SHA=.*$', 'UNIFIED_SHA=' + self.apk_sha, shared, flags=re.M)
        (self.module / 'shared.sh').write_text(shared)
        # Keep the actual preflight/version/package checks. Only the source/target
        # identity transition and library dispatch belong to the pending main build.
        control = self.controller.read_text().rsplit('\ntest_module_version()', 1)[0]
        control = re.sub(r'(xuanyuan-os4-xiaoai\\\|[0-9]+\\\|)[0-9]+', r'\g<1>2026101504', control)
        previous = '  xuanyuan-os4-xiaoai\\|2026101503\\|2026101504\\|install) return 0;;\n'
        if previous not in control:
            control = control.replace(' case "$MID|$LIVE_CODE|$CODE|$OP" in\n',
                                      ' case "$MID|$LIVE_CODE|$CODE|$OP" in\n' + previous, 1)
        control = control.replace(CN_CALENDAR, self.catalog('calendar', 'SHA'))
        global_apk = self.module / 'payload/calendar-global.apk'
        global_apk.write_bytes(b'fixture global calendar')
        control = control.replace(GLOBAL_CALENDAR, hashlib.sha256(global_apk.read_bytes()).hexdigest())
        # Main's generated controller changes only install's gallery call. Its
        # worker reruns this same guard; no-argument restore stays strict.
        if 'gallery) gallery_check install;;' not in control:
            control = control.replace('gallery) gallery_check;;', 'gallery) gallery_check install;;', 1)
            control = control.replace('  H=$(pkg_sha "$P")', '''  if [ "${1:-}" = install ] && ! present "$P" && [ -z "$(path_of "$P")" ]; then continue; fi
  H=$(pkg_sha "$P")''', 1)
        dispatch = (HERE / 'module/control.sh').read_text().rsplit('\ncase "$1" in\n', 1)[1]
        self.controller.write_text(control + '\ncase "$1" in\n library) ;;\n' + dispatch)
        self.module.joinpath('module.prop').write_text('id=xuanyuan-os4-suite\nversion=1.4\nversionCode=2026101504\n')
        self.migration_state = self.root / 'data/adb/xuanyuan-unified-state'
        # Fixture migration has the same status/remove contract and boot marker;
        # migration implementation itself has separate controller/bundle tests.
        migration = '''#!/bin/sh
case "$1" in
 status) echo MIGRATION_READY;;
 remove)
  fixture-script migration remove
  mkdir -p STATE
  cat BOOT > STATE/migration-boot;;
 *) exit 91;;
esac
'''.replace('STATE', shlex.quote(str(self.migration_state))).replace('BOOT', shlex.quote(str(self.boot)))
        (self.module / 'migrate-legacy.sh').write_text(migration)
        packages = json.loads(self.env['TEST_PACKAGES'])
        for row in (self.module / 'owned-packages.txt').read_text().splitlines():
            _, package, digest = row.split('|')
            packages[package] = digest
        packages.update({'com.android.deskclock': CLOCK, 'com.mipay.wallet': WALLET,
                         'local.xuanyuan.mipushcompat': self.apk_sha,
                         'com.android.calendar': self.catalog('calendar', 'SHA')})
        self.packages(packages)
        self.rehash()

    def adapt(self, source):
        for old, new in self.paths.items():
            source = source.replace(old, new)
        return source

    def catalog(self, component, key):
        line = next(line for line in (self.module / 'catalog.sh').read_text().splitlines()
                    if line.startswith(component + ')'))
        return re.search(r'\b' + key + r"='([^']*)'", line)[1]

    def rehash(self):
        names = ('control.sh', 'catalog.sh', 'shared.sh', 'owned-packages.txt',
                 'module.prop', 'preset.sh', 'migrate-legacy.sh')
        (self.module / 'control.sha256').write_text(''.join(
            hashlib.sha256((self.module / name).read_bytes()).hexdigest() + '  ' + name + '\n'
            for name in names))

    def packages(self, values):
        self.env['TEST_PACKAGES'] = json.dumps(values)
        (self.root / 'apks').mkdir(exist_ok=True)
        for package in values:
            (self.root / 'apks' / (package + '.apk')).write_bytes(b'fixture package')

    def component(self, name, code=None, disabled=False):
        mid = self.catalog(name, 'MID')
        folder = self.modules / mid
        folder.mkdir(exist_ok=True)
        (folder / 'module.prop').write_text('id=' + mid + '\nversionCode=' + (code or self.catalog(name, 'CODE')) + '\n')
        os.utime(folder / 'module.prop', (1000, 1000))
        if disabled:
            (folder / 'disable').touch()
        return folder

    def all_current(self, skip=()):
        for name in PROFILE.split(','):
            if self.catalog(name, 'KIND') == 'module' and name not in skip:
                self.component(name)

    def stage(self, name, code=None, mid=None):
        mid = mid or self.catalog(name, 'MID')
        folder = self.root / 'data/adb/modules_update' / mid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'module.prop').write_text('id=' + mid + '\nversionCode=' + (code or self.catalog(name, 'CODE')) + '\n')
        return folder

    def run_preset(self, action='plan', state=None, batch=None, components=PROFILE,
                   features=FEATURES, ids=PROFILE, args=None, **env):
        command = [action, components, features] if args is None else args
        result = subprocess.run(['/bin/sh', str(self.preset), *command], text=True,
                                capture_output=True, env=dict(self.env, **env), timeout=20)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1, result.stdout + result.stderr)
        value = json.loads(lines[0])
        self.assertEqual(set(value) - {'job'}, {'state', 'ids', 'install_ids', 'wallet_pending', 'message', 'boot'})
        if ids is not None:
            self.assertEqual(value['ids'], ids)
        self.assertEqual(value['boot'], self.boot.read_text().strip())
        self.assertIs(type(value['wallet_pending']), bool)
        self.assertIsInstance(value['message'], str)
        if state is not None:
            self.assertEqual(value['state'], state, (value, result.stderr))
        if batch is not None:
            self.assertEqual(value['install_ids'], batch, value)
        self.assertEqual(result.returncode == 0, value['state'] != 'blocked', (value, result.stderr))
        return value

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file() and not p.name.startswith('._')}

    def test_empty_selection_is_readonly_and_ignores_unselected_state(self):
        self.component('phone', code='999')
        self.packages({key: '0' * 64 for key in json.loads(self.env['TEST_PACKAGES'])})
        # No selected legacy helper means no fixed-five migration status call.
        (self.module / 'migrate-legacy.sh').write_text('exit 91\n')
        self.rehash()
        before = self.snapshot()
        for action in ('plan', 'apply', 'migrate'):
            value = self.run_preset(action, components='-', features='-', ids='', state='ready', batch='')
            self.assertFalse(value['wallet_pending'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_weather_only_ignores_unrelated_apks_roots_and_wallet(self):
        self.component('phone', code='999')
        self.component('xiaoai', code='2026101302')
        self.component('market')
        packages = json.loads(self.env['TEST_PACKAGES'])
        for package in ('com.android.deskclock', 'com.android.calendar', 'com.miui.gallery',
                        'com.miui.voiceassist', 'local.xuanyuan.mipushcompat', 'com.mipay.wallet'):
            packages[package] = '0' * 64
        packages['local.xuanyuan.smscompat'] = '0' * 64
        self.packages(packages)
        before = self.snapshot()
        value = self.run_preset(components='weather', features='-', ids='weather', state='install',
                                batch='weather', TEST_MARKET_CTIME='2001')
        self.assertFalse(value['wallet_pending'])
        self.assertEqual(before, self.snapshot())
        self.run_preset('apply', components='weather', features='-', ids='weather',
                        state='running', batch='weather', TEST_MARKET_CTIME='2001')
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.migration_state.exists())
        self.assertFalse(any('wallet' in name or 'reset' in name
                             for name in set(self.snapshot()) - set(before)))

    def test_gallery_only_has_no_market_dependency_or_boot_barrier(self):
        self.run_preset(components='gallery', features='-', ids='gallery', state='install', batch='gallery')
        self.component('gallery')
        self.run_preset(components='gallery', features='-', ids='gallery', state='ready', batch='')
        self.assertFalse((self.modules / 'xuanyuan-os4-market').exists())
        self.assertEqual(self.calls(), [])

    def test_phone_and_xiaoai_component_dependency_closures(self):
        self.run_preset(components='phone', features='-', ids='market,phone', state='install', batch='market')
        market = self.component('market')
        self.run_preset(components='phone', features='-', ids='market,phone', state='install', batch='phone')
        os.utime(market / 'module.prop', (2001, 2001))
        self.run_preset(components='phone', features='-', ids='market,phone', state='reboot', batch='')
        self.run_preset(components='xiaoai', features='-', ids='assistant,xiaoai', state='install',
                        batch='assistant,xiaoai')
        self.assertEqual(self.calls(), [])

    def test_each_feature_adds_its_root_dependencies(self):
        for feature, ids, batch in (
                ('phone', 'market,phone', 'market'),
                ('privacy', 'assistant,xiaoai', 'assistant,xiaoai'),
                ('suggestions', 'assistant,xiaoai', 'assistant,xiaoai'),
                ('warning', 'disaster', 'disaster'),
                ('clock', 'clock', '')):
            with self.subTest(feature=feature):
                before = self.snapshot()
                self.run_preset(components='-', features=feature, ids=ids, batch=batch,
                                state='install' if batch else 'ready')
                self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_canonical_order_and_overlapping_dependencies(self):
        self.component('market')
        self.run_preset(components='weather,phone,xiaoai,assistant,market',
                        features='clock,warning,suggestions,privacy,phone',
                        ids='market,assistant,xiaoai,phone,weather,disaster,clock',
                        state='install', batch='assistant,xiaoai,phone,weather,disaster')

    def test_default_stable13_xiaoai_upgrade_only(self):
        self.all_current()
        self.component('xiaoai', code='2026101503')
        before = self.snapshot()
        self.run_preset(state='install', batch='xiaoai')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_all_features_canonicalized_allow_fixed_five_migration(self):
        self.all_current()
        packages = json.loads(self.env['TEST_PACKAGES'])
        packages['local.xuanyuan.clockcompat'] = '7c85575c3b32decdc5398d905d7a1d4f3655b9f1f3ee8cdbad59721d1521a073'
        self.packages(packages)
        ids = 'market,assistant,xiaoai,phone,disaster,clock'
        features = 'clock,warning,suggestions,privacy,phone'
        before = self.snapshot()
        self.run_preset(components='-', features=features, ids=ids, state='migrate', batch='')
        self.assertEqual(before, self.snapshot())
        self.run_preset('migrate', components='-', features=features, ids=ids, state='reboot', batch='')
        self.assertEqual(self.calls(), [['fixture-script', 'migration', 'remove']])

    def test_invalid_csv_injection_duplicates_and_argument_count_are_readonly(self):
        invalid = ('', ',', ',phone', 'phone,', 'phone,,clock', 'phone,phone',
                   'Phone', 'phone clock', 'phone\nclock', 'phone;reboot',
                   '$(reboot)', '`reboot`', 'phone/../wallet', '--', 'unknown')
        before = self.snapshot()
        for value in invalid:
            for args in (['apply', value, '-'], ['apply', '-', value]):
                with self.subTest(args=args):
                    self.run_preset(args=args, ids=None, state='blocked', batch='')
        for args in ([], ['plan'], ['plan', '-'], ['plan', '-', '-', 'extra'], ['unknown', '-', '-']):
            self.run_preset(args=args, ids='', state='blocked', batch='')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_selected_legacy_isolation_and_partial_migration_block(self):
        self.all_current()
        packages = json.loads(self.env['TEST_PACKAGES'])
        packages['local.xuanyuan.smscompat'] = '7bcafbdba0dc0acc54541e569ecc5c0c15680d433e4794f855b15dc6c6a1c2bb'
        packages['local.xuanyuan.aiprivacy'] = '0' * 64
        self.packages(packages)
        before = self.snapshot()
        for action in ('plan', 'apply', 'migrate'):
            value = self.run_preset(action, components='-', features='phone', ids='market,phone',
                                    state='blocked', batch='')
            self.assertIn('manual migration', value['message'])
            self.run_preset(action, components='phone', features='-', ids='market,phone', state='ready', batch='')
            self.run_preset(action, components='-', features='warning', ids='disaster', state='ready', batch='')
        self.run_preset(components='-', features='privacy', ids='assistant,xiaoai', state='blocked')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_subset_preserves_global_pending_and_migration_boot_guards(self):
        for components in ('-', 'weather'):
            ids = '' if components == '-' else components
            for name in ('phone', 'wallet', 'xiaoai'):
                staged = self.stage(name)
                before = self.snapshot()
                self.run_preset('apply', components=components, features='-', ids=ids, state='reboot', batch='')
                self.assertEqual(before, self.snapshot())
                shutil.rmtree(staged)
            for name, code, mid in (('phone', '999', None), ('market', '1', 'unknown')):
                staged = self.stage(name, code, mid)
                before = self.snapshot()
                self.run_preset('apply', components=components, features='-', ids=ids, state='blocked', batch='')
                self.assertEqual(before, self.snapshot())
                shutil.rmtree(staged)
        self.migration_state.mkdir(parents=True)
        (self.migration_state / 'migration-boot').write_text(self.boot.read_text())
        before = self.snapshot()
        self.run_preset('apply', components='-', features='-', ids='', state='reboot', batch='')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_market_first_and_batch_after_successful_boot(self):
        self.run_preset(state='install', batch='market')
        before = self.snapshot()
        self.run_preset(state='install', batch='market')
        self.assertEqual(before, self.snapshot())
        self.component('market')
        self.run_preset(state='install', batch='assistant,xiaoai,phone,gallery,weather,disaster,wallet')
        self.run_preset('apply', state='running')
        job = Path((self.state / 'latest').read_text().strip())
        self.assertTrue((job / 'state').exists())
        for _ in range(100):
            if (self.root / 'launch-args').exists():
                break
            time.sleep(.01)
        launched = json.loads((self.root / 'launch-args').read_text())
        self.assertEqual(launched[-2:], ['install', 'assistant,xiaoai,phone,gallery,weather,disaster,wallet'])
        before = self.snapshot()
        self.run_preset('apply', state='running', batch='')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])  # real start queued; worker intentionally intercepted

    def test_fresh_stock_and_missing_cn_packages_do_not_block_market(self):
        packages = json.loads(self.env['TEST_PACKAGES'])
        for package in ('com.hyper.gallery.plugin', 'com.android.contacts', 'com.android.incallui', 'com.android.mms'):
            packages.pop(package)
        packages['com.miui.personalassistant'] = 'stock-eea-fixture'
        packages['com.miui.voiceassist'] = 'stock-eea-fixture'
        self.packages(packages)
        self.run_preset('apply', state='running', batch='market')
        self.assertEqual(self.calls(), [])

    def test_fresh_postmarket_missing_gallery_plugin_starts_full_nonwallet_batch(self):
        self.component('market')
        self.env.pop('TEST_WALLET_MATCH')
        packages = json.loads(self.env['TEST_PACKAGES'])
        for package in ('com.hyper.gallery.plugin', 'com.android.contacts', 'com.android.incallui', 'com.android.mms',
                        'local.xuanyuan.mipushcompat', 'com.android.calendar'):
            packages.pop(package)
            (self.root / 'apks' / (package + '.apk')).unlink(missing_ok=True)
        packages['com.miui.personalassistant'] = 'stock-eea-fixture'
        packages['com.miui.voiceassist'] = 'stock-eea-fixture'
        packages['com.mipay.wallet'] = 'stock-eea-wallet'
        self.packages(packages)
        batch = 'assistant,xiaoai,phone,gallery,weather,disaster,clock,calendar,mipush'
        before = self.snapshot()
        value = self.run_preset(state='install', batch=batch)
        self.assertTrue(value['wallet_pending'])
        self.assertEqual(before, self.snapshot())
        # Re-enter the generated controller in another shell, as the worker
        # does, to catch process-local preset overrides that cannot protect it.
        result = subprocess.run(['/bin/sh', str(self.controller), 'plan', 'install', batch],
                                text=True, capture_output=True, env=self.env, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        restore = subprocess.run(['/bin/sh', '-c', 'set -- library; . "$0"; gallery_check', str(self.controller)],
                                 text=True, capture_output=True, env=self.env, timeout=20)
        self.assertNotEqual(restore.returncode, 0, restore.stdout + restore.stderr)
        self.assertEqual(before, self.snapshot())
        value = self.run_preset('apply', state='running', batch=batch)
        self.assertTrue(value['wallet_pending'])
        self.assertEqual(self.calls(), [])

    def test_market_same_boot_requires_explicit_reboot(self):
        market = self.component('market')
        os.utime(market / 'module.prop', (2001, 2001))
        self.run_preset('apply', state='reboot', batch='')
        self.assertFalse(self.state.exists())
        self.run_preset('reboot', state='reboot')
        self.assertEqual(self.calls(), [['reboot']])

    def test_market_zip_timestamp_cannot_bypass_boot_barrier(self):
        self.component('market')  # archived mtime predates boot, actual install does not
        before = self.snapshot()
        self.run_preset('apply', state='reboot', batch='', TEST_MARKET_CTIME='2001')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_staged_barrier_known_module_and_parent(self):
        for name in ('phone', 'wallet'):
            folder = self.stage(name)
            before = self.snapshot()
            self.run_preset('apply', state='reboot', batch='')
            self.assertEqual(before, self.snapshot())
            shutil.rmtree(folder)
        self.stage('market', code='2026101504', mid='xuanyuan-os4-suite')
        self.run_preset(state='reboot')
        self.assertEqual(self.calls(), [])

    def test_live_update_remove_and_staged_id_guards(self):
        self.all_current()
        phone = self.modules / 'xuanyuan-os4-phone'
        (phone / 'update').touch()
        before = self.snapshot()
        self.run_preset('apply', state='reboot')
        self.assertEqual(before, self.snapshot())
        (phone / 'update').unlink()
        (phone / 'remove').touch()
        self.run_preset('reboot', state='blocked')
        (phone / 'remove').unlink()
        staged = self.stage('phone')
        (staged / 'module.prop').write_text('id=other\nversionCode=2026101502\n')
        self.run_preset('reboot', state='blocked')
        self.assertEqual(self.calls(), [])

    def test_ready_idempotence_and_active_updated_wallet_no_changes(self):
        self.all_current()
        self.env.pop('TEST_WALLET_MATCH')  # active supported wallet does not need a reinstall gate
        before = self.snapshot()
        for action in ('plan', 'apply', 'migrate'):
            value = self.run_preset(action, state='ready', batch='')
            self.assertFalse(value['wallet_pending'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_wallet_unmigrated_skip_others_proceed(self):
        self.component('market')
        self.env.pop('TEST_WALLET_MATCH')
        packages = json.loads(self.env['TEST_PACKAGES'])
        packages['com.mipay.wallet'] = 'stock-global-wallet'
        self.packages(packages)
        value = self.run_preset(state='install', batch='assistant,xiaoai,phone,gallery,weather,disaster')
        self.assertTrue(value['wallet_pending'])
        self.all_current(skip=('wallet',))
        before = self.snapshot()
        value = self.run_preset('apply', state='ready', batch='')
        self.assertTrue(value['wallet_pending'])
        self.assertEqual(before, self.snapshot())

    def test_unknown_version_hash_and_pending_no_writes_even_without_market(self):
        phone = self.component('phone', code='999')
        for action in ('plan', 'apply', 'reboot', 'migrate'):
            before = self.snapshot()
            self.run_preset(action, state='blocked')
            self.assertEqual(before, self.snapshot())
        shutil.rmtree(phone)
        packages = json.loads(self.env['TEST_PACKAGES'])
        packages['local.xuanyuan.mipushcompat'] = '0' * 64
        self.packages(packages)
        self.run_preset('apply', state='blocked')
        packages['local.xuanyuan.mipushcompat'] = self.apk_sha
        self.packages(packages)
        for name, code, mid in (('phone', '999', None), ('market', '2026101503', 'unknown'),
                                ('market', '999', 'xuanyuan-os4-suite')):
            folder = self.stage(name, code, mid)
            before = self.snapshot()
            self.run_preset('reboot', state='blocked')
            self.assertEqual(before, self.snapshot())
            shutil.rmtree(folder)
        self.assertEqual(self.calls(), [])

    def test_unknown_active_owned_wallet_calendar_and_native_hashes(self):
        self.all_current()
        original = json.loads(self.env['TEST_PACKAGES'])
        for package in ('com.miui.voiceassist', 'com.mipay.wallet', 'com.android.calendar',
                        'com.android.deskclock', 'com.miui.weather2'):
            self.packages(dict(original, **{package: '0' * 64}))
            before = self.snapshot()
            self.run_preset('apply', state='blocked')
            self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_wrong_rom_and_integrity_block_every_action(self):
        for action in ('plan', 'apply', 'migrate', 'reboot', 'lsp'):
            before = self.snapshot()
            self.run_preset(action, state='blocked', TEST_PROPS=json.dumps({'ro.build.version.incremental': 'other'}))
            self.assertEqual(before, self.snapshot())
        (self.module / 'migrate-legacy.sh').write_text('tampered')
        self.run_preset('migrate', state='blocked')
        self.assertEqual(self.calls(), [])

    def test_running_and_stale_locks_are_never_reconciled(self):
        job = self.state / 'jobs/fixture'
        job.mkdir(parents=True)
        (self.state / 'latest').write_text(str(job))
        (job / 'state').write_text('running')
        (job / 'message').write_text('Quoted "message"\nand a newline')
        (job / 'log').write_text('fixture log')
        lock = self.state / 'lock'
        lock.mkdir()
        (lock / 'boot').write_text('old-boot')
        (lock / 'pid').write_text('99999999')
        for action in ('plan', 'apply', 'migrate', 'reboot'):
            before = self.snapshot()
            value = self.run_preset(action, state='running', batch='')
            self.assertEqual(value['job']['message'], 'Quoted "message"\nand a newline')
            self.assertEqual(before, self.snapshot())
            self.assertTrue(lock.is_dir())
        self.assertEqual(self.calls(), [])

    def test_migration_only_after_current_dependencies_and_requires_reboot(self):
        self.all_current()
        packages = json.loads(self.env['TEST_PACKAGES'])
        packages['local.xuanyuan.smscompat'] = '7bcafbdba0dc0acc54541e569ecc5c0c15680d433e4794f855b15dc6c6a1c2bb'
        self.packages(packages)
        before = self.snapshot()
        self.run_preset(state='migrate', batch='')
        self.run_preset('apply', state='migrate')
        self.assertEqual(before, self.snapshot())
        self.run_preset('migrate', state='reboot')
        self.run_preset('apply', state='reboot')
        self.assertEqual(self.calls(), [['fixture-script', 'migration', 'remove']])
        packages.pop('local.xuanyuan.smscompat')
        self.packages(packages)
        self.boot.write_text('boot-B\n')
        self.run_preset(state='ready')

    def test_migration_rejects_incomplete_dependencies_and_lock(self):
        before = self.snapshot()
        self.run_preset('migrate', state='blocked')
        self.assertEqual(before, self.snapshot())
        self.all_current()
        (self.migration_state / 'lock').mkdir(parents=True)
        before = self.snapshot()
        self.run_preset('migrate', state='blocked')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.calls(), [])

    def test_preflight_full_batch_before_enable_or_job(self):
        self.all_current()
        phone = self.component('phone', disabled=True)
        self.component('disaster', disabled=True)
        # Late component's invalid payload must block the entire chosen batch.
        payload = self.module / 'payload/disaster.zip'
        payload.write_bytes(b'tampered')
        before = self.snapshot()
        self.run_preset('apply', state='blocked', batch='phone,disaster')
        self.assertEqual(before, self.snapshot())
        self.assertTrue((phone / 'disable').exists())
        self.assertEqual(self.calls(), [])

    def test_reviewed_older_disabled_and_shared_previous_need_install(self):
        self.all_current()
        self.component('phone', code='2026101208', disabled=True)
        before = self.snapshot()
        self.run_preset(state='install', batch='phone')
        self.assertEqual(before, self.snapshot())
        self.run_preset('apply', state='running', batch='phone')
        self.assertIn(['module', 'enable', 'xuanyuan-os4-phone'], self.calls())

    def test_shared_previous_exact_target_split_and_lsp(self):
        self.all_current()
        packages = json.loads(self.env['TEST_PACKAGES'])
        for digest in ('fe2cc510d76aeca054582d20f092833a336e13b39686fb1d49f5a20a3a5688d7',
                       '221d9cf4691e12382d2a5eab8fabc4470ff5f8a635a75650fca9a6129397c59c'):
            packages['local.xuanyuan.mipushcompat'] = digest
            self.packages(packages)
            self.run_preset(state='install', batch='clock,mipush')
        packages['local.xuanyuan.mipushcompat'] = self.apk_sha
        self.packages(packages)
        self.run_preset(state='ready', batch='')
        self.run_preset('apply', state='blocked', TEST_SPLIT='local.xuanyuan.mipushcompat')
        self.run_preset('lsp', state='ready')
        self.assertEqual(self.calls(), [['module', 'action', 'zygisk_lsposed']])


if __name__ == '__main__':
    unittest.main()
