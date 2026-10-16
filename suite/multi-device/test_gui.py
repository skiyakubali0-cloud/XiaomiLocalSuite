"""Native Tk widget flow, including a real signed-APK check/build. No phone."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import zipfile

import gui
import test_integration as fixtures
AVAILABLE = fixtures.AVAILABLE


class UiHarness:

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = gui.App(self.root)
        self.root.update()

    def tearDown(self):
        deadline = time.monotonic() + 10
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.destroy()
        self.tmp.cleanup()

    def wait(self):
        deadline = time.monotonic() + 20
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.assertFalse(self.app.busy, 'worker did not complete')
        self.root.update()

    def draft(self):
        self.app.mode.set(gui.NEW_TITLE)
        self.app._mode_changed()
        self.app.session.profile = {'schema': 1, 'id': 'ui-test', 'mode': 'apk-overlay',
            'target': {'device': 'testphone', 'sdk': 37, 'incremental': 'OS4.TEST', 'abis': ['arm64-v8a']},
            'wallet_policy': 'separate-validation-no-reset', 'hooks': [],
            'components': [{'id': 'normal', 'package': 'local.example.app', 'enabled': False},
                           {'id': 'wallet', 'package': 'com.mipay.wallet', 'enabled': True}]}
        self.app._render_rows()
        self.app._refresh()


class NativeUiTests(UiHarness, unittest.TestCase):
    def test_selected_modules_dependency_and_changed_selection(self):
        self.app.mode.set(gui.SELECTED_TITLE)
        self.app._mode_changed()
        self.assertTrue(self.app.selected_suite)
        self.assertEqual(len(self.app.row_map), 3)
        self.assertTrue(self.app.analyse_button.instate(['disabled']))
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.app._toggle('2')
        selected = [c['id'] for c in self.app.session.profile['components'] if c['enabled']]
        self.assertEqual(selected, ['assistant', 'xiaoai'])
        self.app.session.report = {'state': 'reviewed-components'}
        self.app._refresh()
        self.assertFalse(self.app.build_button.instate(['disabled']))
        self.app.select_all(False)
        self.assertIsNone(self.app.session.report)
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.assertFalse(any(c['enabled'] for c in self.app.session.profile['components']))

    def test_initial_import_mode_needs_no_private_suite(self):
        self.assertEqual(self.app.mode.get(), gui.NEW_TITLE)
        self.assertIsNone(self.app.session.profile)
        self.assertEqual(self.app.table.get_children(), ())
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.assertFalse(self.app.analyse_button.instate(['disabled']))
        self.assertTrue(self.app.new_frame.winfo_manager())
        self.assertFalse(self.app.known_frame.winfo_manager())

    def test_legacy_reviewed_mode_requires_check(self):
        self.app.mode.set(gui.KNOWN_TITLE)
        self.app._mode_changed()
        self.assertTrue(self.app.reviewed)
        self.assertEqual(len(self.app.table.get_children()), 11)
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.assertTrue(self.app.all_button.instate(['disabled']))
        self.assertIn('手机', self.app.selection_note.get())
        self.assertEqual(self.app.table.item('7', 'values')[3], '单独验证')

    def test_environment_button_reports_missing_dependencies_without_changing_selection(self):
        self.draft()
        before = copy.deepcopy(self.app.session.profile)
        with patch.object(gui.environment, 'inspect', return_value={'ready': False, 'checks': [
                {'name': 'aapt2', 'ready': False, 'required': True, 'detail': 'SDK missing'}]}):
            self.app.environment_button.invoke()
            self.wait()
        self.assertIn('aapt2', self.app.report_text.get('1.0', 'end'))
        self.assertIn('环境尚未就绪', self.app.report_text.get('1.0', 'end'))
        self.assertEqual(self.app.session.profile, before)
        self.assertTrue(self.app.build_button.instate(['disabled']))

    def test_wallet_cannot_be_selected_and_all_toggle_invalidates(self):
        self.draft()
        self.assertFalse(self.app.session.profile['components'][1]['enabled'])
        self.app._toggle('1')
        self.assertFalse(self.app.session.profile['components'][1]['enabled'])
        self.app.select_all(True)
        self.assertTrue(self.app.session.profile['components'][0]['enabled'])
        self.assertFalse(self.app.session.profile['components'][1]['enabled'])
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.app.select_all(False)
        self.assertFalse(self.app.session.profile['components'][0]['enabled'])

    def test_changed_target_discards_old_profile_and_report(self):
        self.draft()
        self.app.session.report = {'state': 'candidate-static-pass'}
        self.app.target.set('/a/different/target')
        self.assertIsNone(self.app.session.profile)
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.assertEqual(self.app.table.get_children(), ())

    def test_busy_worker_locks_inputs_and_close_waits(self):
        self.app._start('busy', lambda: time.sleep(0.1), lambda _: None)
        self.assertTrue(self.app.mode_box.instate(['disabled']))
        self.assertTrue(self.app.check_button.instate(['disabled']))
        self.app.close()
        self.assertTrue(self.root.winfo_exists())
        self.assertIn('处理中', self.app.status.get())
        self.wait()
        self.assertFalse(self.app.mode_box.instate(['disabled']))

    def test_worker_failure_reports_and_recovers(self):
        def fail():
            raise ValueError('insufficient extraction space: sample')
        self.app._start('scan', fail, lambda _: self.fail('unexpected success'))
        self.wait()
        self.assertIn('解包空间不足', self.app.report_text.get('1.0', 'end'))
        self.assertFalse(self.app.mode_box.instate(['disabled']))

    def test_callback_failure_restores_inputs_and_polling(self):
        folder = Path(self.tmp.name).resolve()
        p = gui.builder.load(gui.REVIEWED)
        p.pop('artifact')
        path = folder / 'missing-artifact.json'
        path.write_text(json.dumps(p))
        with patch.object(gui.filedialog, 'askopenfilename', return_value=str(path)):
            self.app.open_profile()
            self.wait()
        self.assertFalse(self.app.updating)
        self.assertFalse(self.app.mode_box.instate(['disabled']))
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.assertIn('未能载入结果', self.app.report_text.get('1.0', 'end'))
        values = []
        self.app._start('subsequent action', lambda: 42, values.append)
        self.wait()
        self.assertEqual(values, [42])

    def test_loading_multiple_relative_sources_is_displayed_as_paths(self):
        folder = Path(self.tmp.name).resolve()
        p = {'schema': 1, 'id': 'imported-ui', 'mode': 'apk-overlay',
             'target': {'device': None, 'sdk': None, 'incremental': None, 'abis': []},
             'target_input': 'target', 'source_input': ['one.apk', 'two.apk'],
             'wallet_policy': 'separate-validation-no-reset', 'components': [], 'hooks': []}
        path = folder / 'profile.json'
        path.write_text(json.dumps(p))
        with patch.object(gui.filedialog, 'askopenfilename', return_value=str(path)):
            self.app.open_profile()
            self.wait()
        self.assertEqual(self.app.sources, [str(folder / 'one.apk'), str(folder / 'two.apk')])
        self.assertEqual(self.app.target.get(), str(folder / 'target'))
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.assertIn('已载入', self.app.report_text.get('1.0', 'end'))


@unittest.skipUnless(AVAILABLE, 'Android SDK tools unavailable')
class NativeSignedApkFlow(UiHarness, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SignedApkIntegration.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.SignedApkIntegration.tearDownClass()

    def test_real_native_buttons_analyse_select_check_build(self):
        self.app.mode.set(gui.NEW_TITLE)
        self.app._mode_changed()
        self.app.target.set(str(fixtures.SignedApkIntegration.target))
        self.app.sources = [str(fixtures.SignedApkIntegration.source_apk)]
        self.app._sources_changed()
        self.app.analyse_button.invoke()
        self.wait()
        self.assertEqual(len(self.app.row_map), 1)
        self.assertIn('fixturephone', self.app.identity_text.get())
        self.app._toggle('0')
        self.assertTrue(self.app.session.profile['components'][0]['enabled'])
        self.app.check_button.invoke()
        self.wait()
        self.assertEqual(self.app.session.report['state'], 'candidate-static-pass')
        self.assertFalse(self.app.build_button.instate(['disabled']))
        output = Path(self.tmp.name) / 'native-generated.zip'
        with patch.object(gui.filedialog, 'asksaveasfilename', return_value=str(output)):
            self.app.build_button.invoke()
            self.wait()
        self.assertTrue(output.is_file(), self.app.report_text.get('1.0', 'end'))
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(archive.read('system/product/app/Fixture/Fixture.apk'), fixtures.SignedApkIntegration.source_apk.read_bytes())
            self.assertFalse(json.loads(archive.read('profile.json'))['device_tested'])
        self.assertIn(str(output), self.app.report_text.get('1.0', 'end'))
        self.assertTrue(output.with_suffix('.build.json').is_file())
        # The real selection event invalidates a successful check/build.
        self.app._toggle('0')
        self.assertTrue(self.app.build_button.instate(['disabled']))


if __name__ == '__main__':
    unittest.main()
