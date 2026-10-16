from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import call, patch
import zipfile

import gui_session as g
import suite_builder as b


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.target = self.root / 'target'
        self.stock = self.target / 'product/app/Example/Example.apk'
        self.stock.parent.mkdir(parents=True)
        self.stock.write_bytes(b'stock-signed-fixture')
        self.source = self.root / 'source.apk'
        self.source.write_bytes(b'source-signed-fixture')
        self.model = {'device': 'testphone', 'sdk': 37, 'incremental': 'OS4.TEST', 'abis': ['arm64-v8a']}
        self.meta = {'package': 'com.example.app', 'version_code': 10, 'min_sdk': 30,
                     'signers_sha256': ['a' * 64], 'abis': ['arm64-v8a'], 'shared_user_id': None,
                     'uses_libraries': [], 'requested_permissions': [], 'uses_static_libraries': [],
                     'uses_sdk_libraries': [], 'requires_splits': False, 'split': None,
                     'signature_verified': True, 'metadata_complete': True}
        self.scanner = patch.object(g.intake, 'scan', side_effect=self.scan).start()
        self.addCleanup(patch.stopall)
        self.session = g.Session()

    def scan(self, path):
        path = Path(path).resolve()
        if path == self.target:
            return {'kind': 'firmware-directory', **copy.deepcopy(self.model), 'apks': [
                dict(self.meta, path=str(self.stock), sha256=b.sha(self.stock),
                     partition_path='product/app/Example/Example.apk')], 'warnings': []}
        return {'kind': 'apk', 'device': None, 'apks': [
            dict(self.meta, path=str(path), sha256=b.sha(path))], 'warnings': []}

    def analyse(self):
        return self.session.analyse(self.target, [self.source], 'testphone-gui')

    def selected(self):
        self.analyse()
        self.session.set_selected(['app1'])

    def passed(self):
        self.selected()
        self.assertEqual(self.session.check()['state'], 'candidate-static-pass')

    def reviewed(self):
        path = b.HERE / 'profiles/xuanyuan-eea-os4.0.0.6.json'
        self.session.use_reviewed(path, self.root)
        artifact = self.root / self.session.profile['artifact']
        artifact.write_bytes(b'reviewed-artifact-fixture')
        return artifact

    def test_initial_and_empty_check(self):
        self.assertIsNone(self.session.profile)
        self.assertIsInstance(self.session.base, Path)
        self.assertIsNone(self.session.materials)
        self.assertEqual(self.session.rows(), [])
        self.assertEqual(self.session.check()['state'], 'blocked')
        self.assertTrue(self.session.report['errors'])

    def test_multiple_apks_and_directory_scan_each_input_once(self):
        second = self.root / 'second.apk'
        second.write_bytes(b'another-source')
        directory = self.root / 'apks'
        directory.mkdir()
        (directory / 'third.apk').write_bytes(b'third-source')
        original_scan = self.scan

        def scan(path):
            result = original_scan(directory / 'third.apk' if path == directory else path)
            if path == directory:
                result['kind'] = 'apk-directory'
            return result

        self.scanner.side_effect = scan
        profile = self.session.analyse(self.target, [self.source, second, directory], 'multi')
        self.assertEqual(self.scanner.call_args_list, [call(self.target), call(self.source), call(second), call(directory)])
        self.assertEqual(profile['target'], self.model)
        self.assertEqual(profile['source_input'], str(self.source))
        self.assertEqual(profile['source_inputs'], [str(self.source), str(second), str(directory)])
        self.assertEqual([r['id'] for r in profile['components']], ['app1', 'app2', 'app3'])
        self.assertTrue(all(r['enabled'] is False for r in profile['components']))
        self.assertTrue(all(r['target_path'] == 'product/app/Example/Example.apk' for r in profile['components']))
        self.assertEqual(self.source.read_bytes(), b'source-signed-fixture')

    def test_single_source_matches_builder_draft(self):
        draft = b.draft('testphone-gui', self.target, self.source)
        profile = self.analyse()
        self.assertEqual({k: v for k, v in profile.items() if k != 'warnings'}, draft)

    def test_wrong_source_device_rejected(self):
        def scan(path):
            result = self.scan(path)
            if path == self.source:
                result.update(kind='firmware-directory', device='otherphone')
            return result
        self.scanner.side_effect = scan
        with self.assertRaisesRegex(ValueError, 'different device'):
            self.analyse()
        self.assertIsNone(self.session.profile)

    def test_ota_metadata_returned_without_extracting_or_components(self):
        for ota_path in (self.target, self.source):
            with self.subTest(ota_path=ota_path):
                def scan(path):
                    result = self.scan(path)
                    if path == ota_path:
                        result.update(kind='ota', apks=[], warnings=['payload not inspected'])
                        if path == self.target:
                            result['abis'] = []
                    return result
                self.scanner.side_effect = scan
                with patch.object(g.intake, 'extract_apks', side_effect=AssertionError('no extraction')):
                    profile = self.analyse()
                self.assertEqual(profile['components'], [])
                self.assertTrue(any('no automatic extraction' in w for w in profile['warnings']))
                self.assertEqual(profile['target']['device'], self.model['device'])
                if ota_path == self.target:
                    self.assertEqual(profile['target']['abis'], [])

    def test_selection_and_material_changes_invalidate_report(self):
        self.passed()
        self.session.set_selected([])
        self.assertIsNone(self.session.report)
        with self.assertRaisesRegex(ValueError, 'successful check'):
            self.session.build(self.root / 'out.zip', candidate=True)
        self.session.set_selected(['app1'])
        self.assertEqual(self.session.check()['state'], 'candidate-static-pass')
        self.session.configure_materials(self.root)
        self.assertIsNone(self.session.report)
        self.assertIsNone(self.session._checked)

    def test_unknown_and_duplicate_ids_are_not_selectable(self):
        self.selected()
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.session.set_selected(['app1', 'absent'])
        self.session.profile['components'].append(copy.deepcopy(self.session.profile['components'][0]))
        self.assertTrue(all(not r['selectable'] for r in self.session.rows()))
        with self.assertRaisesRegex(ValueError, 'invalid'):
            self.session.set_selected(['app1'])

    def test_wallet_import_and_hand_edit_are_forced_disabled(self):
        for package in ('com.mipay.wallet', 'com.android.nfc', 'com.miui.tsmclient', 'com.example.secureelement'):
            with self.subTest(package=package):
                profile = self.analyse()
                profile['components'][0].update(package=package, enabled=True)
                path = self.root / (package + '.json')
                b.write_new(path, profile)
                self.session.load_profile(path)
                row = self.session.rows()[0]
                self.assertFalse(row['enabled'])
                self.assertFalse(row['selectable'])
                self.assertIn('separate validation', row['reason'])
                with self.assertRaisesRegex(ValueError, 'wallet-locked'):
                    self.session.set_selected(['app1'])
                self.session.profile['components'][0]['enabled'] = True
                self.assertEqual(self.session.check()['state'], 'blocked')
                self.assertFalse(self.session.profile['components'][0]['enabled'])

    def test_critical_xmsf_is_rejected_by_builder(self):
        self.selected()
        self.session.profile['components'][0]['package'] = 'com.xiaomi.xmsf'
        report = self.session.check()
        self.assertEqual(report['state'], 'blocked')
        self.assertIn('Critical', str(report['errors']))

    def test_wallet_hand_edit_after_check_blocks_build(self):
        self.selected()
        wallet = dict(self.session.profile['components'][0], id='wallet',
                      package='com.miui.tsmclient', enabled=False)
        self.session.profile['components'].append(wallet)
        self.assertEqual(self.session.check()['state'], 'candidate-static-pass')
        wallet['enabled'] = True
        with patch.object(b, 'build') as build:
            with self.assertRaisesRegex(ValueError, 'successful check'):
                self.session.build(self.root / 'out.zip', candidate=True)
            build.assert_not_called()
        self.assertFalse(wallet['enabled'])
        self.assertEqual(self.session.report['state'], 'blocked')

    def test_build_rechecks_changed_source_and_clears_pass(self):
        self.passed()
        self.source.write_bytes(b'changed-after-check')
        with patch.object(b, 'check_profile', wraps=b.check_profile) as check:
            with self.assertRaisesRegex(ValueError, 'Compatibility checks failed'):
                self.session.build(self.root / 'out.zip', candidate=True)
        check.assert_called_once()
        self.assertEqual(self.session.report['state'], 'blocked')
        self.assertIsNone(self.session._checked)
        self.assertFalse((self.root / 'out.zip').exists())

    def test_candidate_flag_and_real_archive_bytes(self):
        self.passed()
        with self.assertRaisesRegex(ValueError, '--candidate'):
            self.session.build(self.root / 'out.zip')
        self.assertEqual(self.session.report['state'], 'blocked')
        self.assertEqual(self.session.check()['state'], 'candidate-static-pass')
        result = self.session.build(self.root / 'out.zip', candidate=True)
        self.assertEqual(result, self.session.report)
        b.verify_archive(self.root / 'out.zip')
        with zipfile.ZipFile(self.root / 'out.zip') as archive:
            self.assertEqual(archive.read('system/product/app/Example/Example.apk'), self.source.read_bytes())

    def test_build_requires_private_check_and_exact_fingerprint(self):
        self.selected()
        self.session.report = {'state': 'candidate-static-pass'}
        with patch.object(b, 'build') as build:
            with self.assertRaisesRegex(ValueError, 'successful check'):
                self.session.build(self.root / 'out.zip', candidate=True)
            build.assert_not_called()
        for change in ('profile', 'base', 'materials'):
            with self.subTest(change=change):
                self.passed()
                if change == 'profile':
                    self.session.profile['components'][0]['enabled'] = False
                elif change == 'base':
                    self.session.base = self.root / 'other'
                else:
                    self.session.materials = str(self.root)
                with patch.object(b, 'build') as build:
                    with self.assertRaisesRegex(ValueError, 'successful check'):
                        self.session.build(self.root / 'out.zip', candidate=True)
                    build.assert_not_called()

    def test_failed_check_never_retains_a_passed_report(self):
        for error in (ValueError('bad profile'), OSError('unreadable'), subprocess.TimeoutExpired('tool', 1)):
            self.passed()
            with patch.object(b, 'check_profile', side_effect=error):
                report = self.session.check()
            self.assertEqual(report['state'], 'blocked')
            self.assertTrue(report['errors'])
            self.assertIsNone(self.session._checked)
        self.passed()
        self.session.profile['target']['device'] = 'wrong'
        self.assertEqual(self.session.check()['state'], 'blocked')

    def test_failed_profile_load_invalidates_previous_success(self):
        malformed = self.root / 'malformed.json'
        malformed.write_text('{broken')
        not_object = self.root / 'not-object.json'
        not_object.write_text('[]')
        for path in (self.root / 'missing.json', malformed, not_object):
            with self.subTest(path=path):
                self.passed()
                with self.assertRaises((ValueError, OSError)):
                    self.session.load_profile(path)
                self.assertIsNone(self.session.report)
                self.assertIsNone(self.session._checked)
                with patch.object(b, 'build') as build:
                    with self.assertRaisesRegex(ValueError, 'successful check'):
                        self.session.build(self.root / 'out.zip', candidate=True)
                    build.assert_not_called()

    def test_check_uses_snapshot_and_detects_midcheck_change(self):
        self.selected()
        def check(profile, base, materials):
            self.assertIsNot(profile, self.session.profile)
            self.assertIsNot(profile['components'], self.session.profile['components'])
            self.session.profile['id'] = 'changed'
            return {'state': 'candidate-static-pass'}
        with patch.object(b, 'check_profile', side_effect=check):
            self.assertEqual(self.session.check()['state'], 'blocked')
        self.assertIsNone(self.session._checked)

    def assert_bad_profile(self, profile):
        self.passed()
        previous = self.session.profile
        path = self.root / 'invalid.json'
        path.write_text(json.dumps(profile))
        with self.assertRaises(ValueError):
            self.session.load_profile(path)
        self.assertIs(self.session.profile, previous)
        self.assertIsNone(self.session.report)
        self.assertIsNone(self.session._checked)

    def test_load_rejects_bad_profile_identity_shape(self):
        profile = copy.deepcopy(self.analyse())
        for key, value in (('schema', 2), ('schema', None), ('id', 5), ('id', '../escape'),
                           ('mode', 'unknown'), ('wallet_policy', 'auto-reset')):
            with self.subTest(key=key, value=value):
                self.assert_bad_profile(dict(profile, **{key: value}))

    def test_load_rejects_bad_target_and_component_shapes_but_allows_draft(self):
        profile = copy.deepcopy(self.analyse())
        for key, value in (('target', None), ('target', []), ('components', None),
                           ('components', {}), ('components', ['bad']), ('components', [None])):
            with self.subTest(key=key, value=value):
                self.assert_bad_profile(dict(profile, **{key: value}))
        profile['target']['sdk'] = None
        profile['components'] = []
        path = self.root / 'draft.json'
        b.write_new(path, profile)
        self.assertIsNone(self.session.load_profile(path)['target']['sdk'])

    def test_load_rejects_bad_source_path_shapes(self):
        profile = copy.deepcopy(self.analyse())
        for key, value in (('source_input', None), ('source_input', 1), ('source_input', [1]),
                           ('source_inputs', 'source.apk'), ('source_inputs', None), ('source_inputs', [None])):
            with self.subTest(key=key, value=value):
                self.assert_bad_profile(dict(profile, **{key: value}))
        profile['source_input'] = [str(self.source)]
        profile['source_inputs'] = [str(self.source)]
        path = self.root / 'source-list.json'
        b.write_new(path, profile)
        self.assertEqual(self.session.load_profile(path)['source_input'], [str(self.source)])

    def test_reviewed_exact_target_cannot_be_renamed(self):
        self.reviewed()
        self.assertEqual(self.session.rows(), [])
        with self.assertRaisesRegex(ValueError, 'phone selection UI'):
            self.session.set_selected([])
        digest = self.session.profile['artifact_sha256']
        with patch.object(b, 'sha', return_value=digest), patch.object(b, 'verify_archive'):
            self.assertEqual(self.session.check()['state'], 'reviewed-recipe')
            self.session.profile['target']['device'] = 'renamed'
            report = self.session.check()
        self.assertEqual(report['state'], 'blocked')
        self.assertIn('No reviewed recipe', str(report['errors']))

    def test_save_load_resolves_paths_without_rebasing_active_profile(self):
        profile = self.analyse()
        profile['target_input'] = 'target'
        profile['source_input'] = 'source.apk'
        profile['source_inputs'] = ['source.apk']
        profile['components'][0]['source_apk'] = 'source.apk'
        profile['components'][0]['target_apk'] = 'target/product/app/Example/Example.apk'
        original = copy.deepcopy(profile)
        base = self.session.base
        output = self.root / 'elsewhere/profile.json'
        saved = self.session.save_profile(output)
        self.assertEqual(self.session.profile, original)
        self.assertEqual(self.session.base, base)
        self.assertEqual(saved['source_input'], str(self.source))
        self.assertEqual(saved['source_inputs'], [str(self.source)])
        self.assertEqual(saved['target_input'], str(self.target))
        self.assertEqual(saved['components'][0]['target_apk'], str(self.stock))
        with self.assertRaises(FileExistsError):
            self.session.save_profile(output)
        other = g.Session()
        self.assertEqual(other.load_profile(output), saved)
        other.set_selected(['app1'])
        self.assertEqual(other.check()['state'], 'candidate-static-pass')

    def test_reviewed_save_load_preserves_registry_and_material_context(self):
        artifact = self.reviewed()
        digest = self.session.profile['artifact_sha256']
        output = self.root / 'elsewhere/reviewed.json'
        saved = self.session.save_profile(output)
        self.assertEqual(saved['artifact'], artifact.name)
        other = g.Session()
        other.use_reviewed(output)
        self.assertEqual(other.materials, str(self.root))
        with patch.object(b, 'sha', return_value=digest), patch.object(b, 'verify_archive'):
            report = other.check()
        self.assertEqual(report['state'], 'reviewed-recipe')
        self.assertEqual(report['artifact'], str(artifact))

    def test_reviewed_material_is_rechecked_on_build(self):
        self.reviewed()
        digest = self.session.profile['artifact_sha256']
        with patch.object(b, 'sha', side_effect=[digest, '0' * 64]), patch.object(b, 'verify_archive'):
            self.assertEqual(self.session.check()['state'], 'reviewed-recipe')
            with self.assertRaisesRegex(ValueError, 'artifact hash differs'):
                self.session.build(self.root / 'out.zip')
        self.assertEqual(self.session.report['state'], 'blocked')
        self.assertFalse((self.root / 'out.zip').exists())


if __name__ == '__main__':
    unittest.main()
