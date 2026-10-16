from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import suite_builder as b


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.src = self.root / 'cn.apk'
        self.stock = self.root / 'product/app/Example/Example.apk'
        self.stock.parent.mkdir(parents=True)
        self.src.write_bytes(b'CN-signed-fixture')
        self.stock.write_bytes(b'EEA-signed-fixture')
        self.profile = {'schema': 1, 'id': 'testphone-os4', 'mode': 'apk-overlay',
            'target': {'device': 'testphone', 'sdk': 37, 'incremental': 'OS4.1.TEST', 'abis': ['arm64-v8a']},
            'wallet_policy': 'separate-validation-no-reset', 'hooks': [], 'target_input': str(self.root),
            'components': [{'id': 'example', 'enabled': True, 'package': 'com.example.app',
                'source_apk': str(self.src), 'target_apk': str(self.stock),
                'source_sha256': b.sha(self.src), 'target_sha256': b.sha(self.stock),
                'target_path': 'product/app/Example/Example.apk'}]}
        self.meta = {'package': 'com.example.app', 'version_code': 10, 'min_sdk': 30,
                     'target_sdk': 37, 'signers_sha256': ['a' * 64], 'abis': ['arm64-v8a'],
                     'uses_libraries': ['android.test.base'], 'requested_permissions': ['android.permission.INTERNET'],
                     'shared_user_id': None, 'metadata_complete': True, 'signature_verified': True, 'requires_splits': False, 'split': None, 'uses_static_libraries': [], 'uses_sdk_libraries': []}
        self.srcmeta = copy.deepcopy(self.meta)
        self.stockmeta = copy.deepcopy(self.meta)
        self.scanner = patch.object(b.intake, 'scan', side_effect=self.scan)
        self.scanner.start()
        self.addCleanup(self.scanner.stop)
        self.addCleanup(self.tmp.cleanup)

    def scan(self, path):
        path = Path(path).resolve()
        if path == self.root:
            return {'kind': 'firmware-directory', **self.profile['target'], 'apks': [
                dict(self.stockmeta, path=str(self.stock), partition_path='product/app/Example/Example.apk')]}
        meta = self.srcmeta if path == self.src else self.stockmeta
        return {'kind': 'apk', 'apks': [dict(meta, path=str(path), sha256=b.sha(path))]}

    def check(self):
        return b.check_profile(self.profile, self.root)

    def blocked_component(self, fragment):
        report = self.check()
        self.assertEqual(report['state'], 'blocked')
        self.assertIn(fragment, str(report['components']))

    def test_incomplete_manifest_blocked(self):
        self.srcmeta['metadata_complete'] = False
        self.blocked_component('metadata incomplete')

    def test_unverified_signature_flag_blocked(self):
        self.srcmeta['signature_verified'] = False
        self.blocked_component('signature verification incomplete')

    def test_inferred_firmware_abi_not_accepted(self):
        self.profile['target']['abis'] = ['x86_64']
        original_scan = self.scan
        def scanner(path):
            result = original_scan(path)
            if result.get('kind') == 'firmware-directory':
                result['abis'] = ['arm64-v8a']
            return result
        b.intake.scan.side_effect = scanner
        with self.assertRaisesRegex(ValueError, 'ABI list unknown or differs'):
            self.check()

    def test_split_required_base_blocked(self):
        self.srcmeta['requires_splits'] = True
        self.blocked_component('Split APK/base dependencies')

    def test_same_profile_image_content_blocks_disjoint_selection(self):
        # A was previously selected; current selection B owns a different path.
        prior = self.root / ('image-content/xiaomi-profile-' + self.profile['id'])
        prior.mkdir(parents=True)
        (prior / 'old-A.apk').write_bytes(b'keep')
        run = self.shell()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('already has module/image content', run.stdout)
        self.assertNotIn('MUTATION', run.stdout)
        self.assertEqual((prior / 'old-A.apk').read_bytes(), b'keep')

    def test_postfs_boot_guard_disables_only_self_on_wrong_rom(self):
        report = self.check()
        text = b.overlay_files(self.profile, report)['post-fs-data.sh'].decode()
        script = self.root / 'post-fs-data.sh'
        prefix = 'getprop() { case "$1" in ro.product.device) echo testphone;; ro.build.version.sdk) echo 37;; *) echo WRONG_ROM;; esac; }\n'
        script.write_text(prefix + text)
        subprocess.run(['/bin/sh', '-n', script], check=True)
        subprocess.run(['/bin/sh', script], check=True)
        self.assertTrue((self.root / 'disable').is_file())
        self.assertTrue((self.root / 'compatibility-blocked.txt').is_file())

    def test_postfs_boot_guard_preserves_matching_rom(self):
        report = self.check()
        text = b.overlay_files(self.profile, report)['post-fs-data.sh'].decode()
        script = self.root / 'post-fs-data.sh'
        prefix = 'getprop() { case "$1" in ro.product.device) echo testphone;; ro.build.version.sdk) echo 37;; *) echo OS4.1.TEST;; esac; }\n'
        script.write_text(prefix + text)
        subprocess.run(['/bin/sh', script], check=True)
        self.assertFalse((self.root / 'disable').exists())
        self.assertFalse((self.root / 'compatibility-blocked.txt').exists())

    def test_new_model_static_candidate(self):
        result = self.check()
        self.assertEqual(result['state'], 'candidate-static-pass')
        self.assertFalse(result['device_tested'])
        self.assertEqual(result['wallet'], 'separate-validation-no-reset')

    def test_no_implicit_candidate_build(self):
        with self.assertRaisesRegex(ValueError, '--candidate'):
            b.build(self.profile, self.root, self.root / 'out.zip')
        self.assertFalse((self.root / 'out.zip').exists())

    def test_actual_zip_binary_preservation(self):
        out = self.root / 'out.zip'
        result = b.build(self.profile, self.root, out, candidate=True)
        b.verify_archive(out)
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.read('system/product/app/Example/Example.apk'), self.src.read_bytes())
            public = json.loads(z.read('profile.json'))
            self.assertFalse(public['device_tested'])
            self.assertNotIn(str(self.root), z.read('profile.json').decode())
            self.assertNotIn('service.sh', z.namelist())
        self.assertEqual(result['sha256'], b.sha(out))
        self.assertEqual(json.loads(out.with_suffix('.build.json').read_text())['sha256'], b.sha(out))

    def test_component_unselected_means_not_packaged(self):
        other = dict(self.profile['components'][0], id='skip', package='com.unknown.wallet', enabled=False,
                     source_apk='/does-not-exist', target_path='../../private/key')
        self.profile['components'].append(other)
        self.assertEqual(self.check()['state'], 'candidate-static-pass')

    def test_no_selection_rejected(self):
        self.profile['components'][0]['enabled'] = False
        with self.assertRaisesRegex(ValueError, 'Select at least'):
            self.check()

    def test_wallets_never_enter_generic_recipe(self):
        for package in ['com.mipay.wallet', 'com.miui.tsmclient', 'com.android.nfc', 'com.example.secureelement']:
            with self.subTest(package=package):
                self.profile['components'][0]['package'] = package
                self.blocked_component('separate validation')

    def test_critical_framework_packages_blocked(self):
        self.profile['components'][0]['package'] = 'com.android.phone'
        self.blocked_component('Critical')

    def test_signer_mismatch_blocked(self):
        self.srcmeta['signers_sha256'] = ['b' * 64]
        self.blocked_component('certificate differs')

    def test_unverified_signer_blocked(self):
        self.srcmeta['signers_sha256'] = []
        self.blocked_component('signer missing')

    def test_split_blocked(self):
        self.srcmeta['split'] = 'config.arm64_v8a'
        self.blocked_component('Split APK')

    def test_downgrade_blocked(self):
        self.srcmeta['version_code'] = 9
        self.blocked_component('Downgrade')

    def test_sdk_blocked(self):
        self.srcmeta['min_sdk'] = 38
        self.blocked_component('minSDK')

    def test_abi_blocked(self):
        self.srcmeta['abis'] = ['x86_64']
        self.blocked_component('ABI')

    def test_shared_uid_blocked(self):
        self.srcmeta['shared_user_id'] = 'android.uid.system'
        self.blocked_component('sharedUserId')

    def test_new_permission_blocked(self):
        self.srcmeta['requested_permissions'].append('android.permission.READ_CONTACTS')
        self.blocked_component('New requested_permissions')

    def test_new_library_blocked(self):
        self.srcmeta['uses_libraries'].append('unknown.vendor.library')
        self.blocked_component('New uses_libraries')

    def test_static_library_blocked(self):
        self.srcmeta['uses_static_libraries'] = ['vendor.foo']
        self.blocked_component('Static/SDK')

    def test_source_changed_invalidates_report(self):
        self.assertEqual(self.check()['state'], 'candidate-static-pass')
        self.src.write_bytes(b'altered')
        self.blocked_component('Material changed')

    def test_runtime_qualification_cannot_be_self_promoted(self):
        self.profile['device_tested'] = True
        self.assertFalse(self.check()['device_tested'])

    def test_api102_does_not_imply_other_device_hooks(self):
        self.profile['hooks'] = ['phone-api102']
        with self.assertRaisesRegex(ValueError, 'API102 alone'):
            self.check()

    def test_no_model_renaming_of_reviewed_suite(self):
        p = b.load(b.HERE / 'profiles/xuanyuan-eea-os4.0.0.6.json')
        p['target']['device'] = 'anotherphone'
        with self.assertRaisesRegex(ValueError, 'No reviewed recipe'):
            b.check_profile(p, self.root)

    def test_reset_policy_cannot_be_enabled(self):
        self.profile['wallet_policy'] = 'auto-reset'
        with self.assertRaisesRegex(ValueError, 'separate'):
            self.check()

    def test_destination_traversal_blocked(self):
        for path in ['../private.apk', 'product/../../data/app/E.apk', '/product/app/E/E.apk',
                     'vendor/app/E/E.apk', 'product/data-app/E/E.apk', 'product/app/E/$(touch pwned).apk']:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    b.system_path(path)

    def test_target_path_must_exist_in_target_firmware(self):
        self.profile['components'][0]['target_path'] = 'product/app/Other/Other.apk'
        self.blocked_component('not at this path')

    def test_arbitrary_target_apk_not_accepted(self):
        self.profile['components'][0]['target_apk'] = str(self.src)
        self.blocked_component('not at this path')

    def test_duplicate_package_blocked(self):
        self.profile['components'].append(dict(self.profile['components'][0], id='another'))
        with self.assertRaisesRegex(ValueError, 'Duplicate package'):
            self.check()

    def test_overwrite_forbidden(self):
        out = self.root / 'old.zip'
        out.write_bytes(b'precious')
        with self.assertRaisesRegex(ValueError, 'never overwritten'):
            b.build(self.profile, self.root, out, candidate=True)
        self.assertEqual(out.read_bytes(), b'precious')

    def test_duplicate_profile_json_keys(self):
        p = self.root / 'duplicate.json'
        p.write_text('{"id":"good","id":"evil"}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'):
            b.load(p)

    def test_unsafe_archive_and_checksum_rejected(self):
        out = self.root / 'malicious.zip'
        with zipfile.ZipFile(out, 'w') as z:
            z.writestr('../private', b'key')
            z.writestr('checksums.sha256', '')
        with self.assertRaisesRegex(ValueError, 'Unsafe archive'):
            b.verify_archive(out)

    def test_checksum_tamper_rejected(self):
        out = self.root / 'bad.zip'
        with zipfile.ZipFile(out, 'w') as z:
            z.writestr('module.prop', b'fake')
            z.writestr('checksums.sha256', 'a' * 64 + '  module.prop\n')
        with self.assertRaisesRegex(ValueError, 'checksum failed'):
            b.verify_archive(out)

    def shell(self, *, device='testphone', live_path=None, live_sha=None, meta=True, api='37', rom='OS4.1.TEST'):
        report = self.check()
        text = b.overlay_files(self.profile, report)['customize.sh'].decode()
        # Fake read-only system inventory and abort before perm writes on mismatch.
        text = text.replace('/data/adb/metamodule/mnt', str(self.root / 'image-content'))
        text = text.replace('/data/adb/metamodule/modules.img', str(self.root / 'modules.img'))
        text = text.replace('/data/adb/modules/xiaomi-profile-', str(self.root / 'existing-modules/xiaomi-profile-'))
        text = text.replace('/data/adb/modules/*', str(self.root / 'other-modules/*'))
        text = text.replace('/data/adb/modules_update/*', str(self.root / 'pending-modules/*'))
        text = text.replace('/data/adb/metamodule/meta-overlayfs', str(self.root / 'meta'))
        text = text.replace('/data/adb/modules/meta-overlayfs', str(self.root / 'meta-module'))
        if meta:
            (self.root / 'meta').touch(mode=0o755, exist_ok=True)
            (self.root / 'meta-module').mkdir(exist_ok=True)
            (self.root / 'meta-module/module.prop').write_text('versionCode=13100\n')
        prefix = '\n'.join(['KSU=true', 'abort() { echo "$*"; exit 1; }',
            'getprop() { case "$1" in ro.product.device) echo ' + b.q(device) + ';; ro.build.version.sdk) echo ' + b.q(api) + ';; *) echo ' + b.q(rom) + ';; esac; }',
            'am() { echo 0; }',
            'pm() { case "$1" in list) echo "UserInfo{0:Owner}";; path) echo ' + b.q('package:' + (live_path or '/product/app/Example/Example.apk')) + ';; esac; }',
            'sha256sum() { case "$1" in -c) return 0;; *) echo ' + b.q(live_sha or b.sha(self.stock)) + '"  $1";; esac; }',
            'set_perm() { :; }', 'set_perm_recursive() { echo MUTATION; }', 'ui_print() { :; }', 'MODPATH=' + b.q(str(self.root))])
        script = self.root / 'installer-test.sh'
        script.write_text(prefix + '\n' + text)
        subprocess.run(['/bin/sh', '-n', script], check=True)
        return subprocess.run(['/bin/sh', script], text=True, capture_output=True)

    def test_runtime_guard_positive_control(self):
        run = self.shell()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('MUTATION', run.stdout)

    def test_conflicting_root_overlay_no_mutation(self):
        path = self.root / 'pending-modules/other/system/product/app/Example/Example.apk'
        path.parent.mkdir(parents=True)
        path.touch()
        run = self.shell()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('Another root module', run.stdout)
        self.assertNotIn('MUTATION', run.stdout)

    def test_wrong_device_no_mutation(self):
        run = self.shell(device='otherphone')
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn('MUTATION', run.stdout)

    def test_wrong_rom_no_mutation(self):
        run = self.shell(rom='OS4.2.NEW')
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn('MUTATION', run.stdout)

    def test_unknown_live_update_no_mutation(self):
        run = self.shell(live_path='/data/app/update/base.apk')
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn('MUTATION', run.stdout)

    def test_wrong_live_hash_no_mutation(self):
        run = self.shell(live_sha='b' * 64)
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn('MUTATION', run.stdout)

    def test_metaframework_missing_no_mutation(self):
        run = self.shell(meta=False)
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn('MUTATION', run.stdout)


if __name__ == '__main__':
    unittest.main()
