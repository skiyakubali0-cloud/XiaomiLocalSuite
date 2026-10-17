"""Native FULL-mode widgets with mocked material check/build; no OEM inputs or phone."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch

import gui
import gui_session
from test_gui import UiHarness


IDS = ['market', 'assistant', 'xiaoai', 'phone', 'gallery', 'weather',
       'disaster', 'wallet', 'clock', 'calendar', 'mipush']


@unittest.skipIf(tk.TkVersion < 8.6, 'Native GUI requires Tk 8.6+')
class FullRecipeGuiTests(UiHarness, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.folder = Path(self.tmp.name).resolve()
        self.target = self.folder / 'eea'
        self.source = self.folder / 'cn'
        self.target.mkdir()
        self.source.mkdir()
        self.extra = self.folder / 'extra.apk'
        self.plugin = self.folder / 'current-unified.apk'
        self.extra.write_bytes(b'synthetic source placeholder; never inspected as APK')
        self.plugin.write_bytes(b'synthetic plugin placeholder; never installed')
        self.sources = [self.source, self.extra]

    def analyse_full(self):
        self.app.mode.set(gui.FULL_TITLE)
        self.app._mode_changed()
        self.app.target.set(str(self.target))
        self.app.sources = list(map(str, self.sources))
        self.app._sources_changed()
        self.app.unified.set(str(self.plugin))
        with patch.object(gui_session.full, 'validate_target', return_value=(
                copy.deepcopy(gui_session.full.recipe()['target']), [])) as validate:
            self.app.analyse_button.invoke()
            self.wait()
        validate.assert_called_once_with(self.target)
        self.assertEqual(self.app.session.profile['mode'], 'xuanyuan-1.7')

    def selected(self):
        return [c['id'] for c in self.app.session.profile['components'] if c['enabled']]

    def toggle(self, component):
        iid = next(iid for iid, row in self.app.row_map.items() if row['id'] == component)
        self.app._toggle(iid)

    def checked_report(self):
        return {'state': 'reviewed-raw-materials', 'mode': 'xuanyuan-1.7',
                'selected': self.selected(), 'device_tested': False, 'wallet_reset': False,
                'components': [{'id': cid, 'state': 'reviewed-materials', 'errors': []}
                               for cid in self.selected()], 'errors': [], 'missing': []}

    def test_full_analysis_loads_eleven_rows_with_nothing_selected(self):
        self.analyse_full()
        self.assertTrue(self.app.full_recipe)
        self.assertFalse(self.app.reviewed)
        self.assertFalse(self.app.selected_suite)
        self.assertEqual([row['id'] for row in self.app.row_map.values()], IDS)
        self.assertEqual(self.selected(), [])
        self.assertTrue(all(not row['enabled'] for row in self.app.row_map.values()))
        self.assertTrue(all(row['selectable'] for row in self.app.row_map.values()))
        self.assertTrue(self.app.plugin_frame.winfo_manager())
        self.assertFalse(self.app.known_frame.winfo_manager())
        self.assertTrue(self.app.profile_entry.instate(['disabled']))
        self.assertTrue(self.app.build_button.instate(['disabled']))
        self.assertIn('默认不选', self.app.report_text.get('1.0', 'end'))

    def test_phone_and_xiaoai_include_their_dependencies(self):
        self.analyse_full()
        for component, dependency in [('phone', 'market'), ('xiaoai', 'assistant')]:
            with self.subTest(component=component):
                self.app.select_all(False)
                self.toggle(component)
                self.assertEqual(set(self.selected()), {component, dependency})
                self.toggle(dependency)
                self.assertEqual(set(self.selected()), {component, dependency})
                self.assertIsNone(self.app.session.report)
                self.assertTrue(self.app.build_button.instate(['disabled']))

    def test_bulk_selection_skips_wallet_and_manual_selection_is_allowed(self):
        self.analyse_full()
        wallet = next(row for row in self.app.row_map.values() if row['id'] == 'wallet')
        self.assertTrue(wallet['selectable'])
        self.assertFalse(wallet['bulk_selectable'])
        self.app.all_button.invoke()
        self.assertEqual(self.selected(), [cid for cid in IDS if cid != 'wallet'])
        self.toggle('wallet')
        self.assertEqual(self.selected(), IDS)
        self.app.all_button.invoke()
        self.assertIn('wallet', self.selected())
        self.app.none_button.invoke()
        self.assertEqual(self.selected(), [])
        self.toggle('wallet')
        self.assertEqual(self.selected(), ['wallet'])
        self.assertIsNone(self.app.session.report)
        self.assertTrue(self.app.build_button.instate(['disabled']))

    def test_plugin_chooser_preserves_selection_and_invalidates_successful_check(self):
        self.analyse_full()
        self.toggle('phone')
        self.toggle('wallet')
        before = copy.deepcopy(self.app.session.profile['components'])
        with patch.object(gui_session.full, 'check', return_value=self.checked_report()) as check:
            self.app.check_button.invoke()
            self.wait()
            self.assertFalse(self.app.build_button.instate(['disabled']))
            replacement = self.folder / 'replacement-unified.apk'
            with patch.object(gui.filedialog, 'askopenfilename', return_value=str(replacement)):
                self.app.choose_unified()
            self.assertEqual(check.call_count, 1)
        self.assertEqual(self.app.unified.get(), str(replacement))
        self.assertEqual(self.app.session.profile['unified_apk'], str(replacement))
        self.assertEqual(self.app.session.profile['components'], before)
        self.assertEqual([row['id'] for row in self.app.row_map.values() if row['enabled']], self.selected())
        self.assertIsNone(self.app.session.report)
        self.assertIsNone(self.app.session._checked)
        self.assertTrue(self.app.build_button.instate(['disabled']))

    def test_profile_save_and_open_restore_full_mode_paths_and_explicit_wallet(self):
        self.analyse_full()
        for cid in ['phone', 'xiaoai', 'wallet']:
            self.toggle(cid)
        selected = self.selected()
        with patch.object(gui_session.full, 'check', return_value=self.checked_report()):
            self.app.check_button.invoke()
            self.wait()
        profile = self.folder / 'full-profile.json'
        with patch.object(gui.filedialog, 'asksaveasfilename', return_value=str(profile)):
            self.app.save_button.invoke()
            self.wait()
        saved = json.loads(profile.read_text())
        self.assertEqual(saved['mode'], 'xuanyuan-1.7')
        self.assertEqual(saved['target_input'], str(self.target))
        self.assertEqual(saved['source_inputs'], list(map(str, self.sources)))
        self.assertEqual(saved['unified_apk'], str(self.plugin))
        self.assertEqual([c['id'] for c in saved['components'] if c['enabled']], selected)
        self.app.mode.set(gui.NEW_TITLE)
        self.app._mode_changed()
        with patch.object(gui.filedialog, 'askopenfilename', return_value=str(profile)):
            self.app.open_profile()
            self.wait()
        self.assertEqual(self.app.mode.get(), gui.FULL_TITLE)
        self.assertTrue(self.app.full_recipe)
        self.assertEqual(len(self.app.row_map), 11)
        self.assertEqual(self.selected(), selected)
        self.assertIn('wallet', self.selected())
        self.assertEqual(self.app.target.get(), str(self.target))
        self.assertEqual(self.app.sources, list(map(str, self.sources)))
        self.assertEqual(self.app.unified.get(), str(self.plugin))
        self.assertTrue(self.app.plugin_frame.winfo_manager())
        self.assertIsNone(self.app.session.report)
        self.assertIsNone(self.app.session._checked)
        self.assertTrue(self.app.build_button.instate(['disabled']))

    def test_check_and_build_buttons_dispatch_to_full_backend_with_current_selection(self):
        self.analyse_full()
        self.toggle('phone')
        self.toggle('xiaoai')
        selected = ['market', 'assistant', 'xiaoai', 'phone']
        output = self.folder / 'mock-full-parent.zip'
        result = {**self.checked_report(), 'output': str(output), 'bytes': 123, 'sha256': 'a' * 64}
        with patch.object(gui_session.full, 'check', return_value=self.checked_report()) as check, \
                patch.object(gui_session.full, 'build', return_value=result) as build, \
                patch.object(gui.builder, 'check_profile', side_effect=AssertionError('generic check used')), \
                patch.object(gui.builder, 'build', side_effect=AssertionError('generic build used')):
            self.app.check_button.invoke()
            self.wait()
            check.assert_called_once_with(self.target, self.sources, selected, self.plugin)
            self.assertEqual(self.app.session.report['state'], 'reviewed-raw-materials')
            self.assertFalse(self.app.build_button.instate(['disabled']))
            with patch.object(gui.filedialog, 'asksaveasfilename', return_value=str(output)):
                self.app.build_button.invoke()
                self.wait()
            build.assert_called_once_with(self.target, self.sources, selected, self.plugin, output)
        self.assertEqual(self.app.session.report, result)
        self.assertEqual(self.app.last_output, str(output))
        self.assertIn(str(output), self.app.report_text.get('1.0', 'end'))
        self.assertIn('a' * 64, self.app.report_text.get('1.0', 'end'))
        self.assertFalse(output.exists(), 'mock flow must not create a real module ZIP')
        self.toggle('phone')
        self.assertIsNone(self.app.session.report)
        self.assertTrue(self.app.build_button.instate(['disabled']))

    def test_blocked_material_check_displays_missing_sha_and_keeps_build_disabled(self):
        self.analyse_full()
        self.toggle('calendar')
        missing = '缺少精确材料：payload/calendar.apk · SHA256 ' + 'b' * 64
        result = {'state': 'blocked', 'errors': [], 'components': [
            {'id': 'calendar', 'state': 'blocked', 'errors': [missing]}]}
        with patch.object(gui_session.full, 'check', return_value=result), \
                patch.object(gui_session.full, 'build', side_effect=AssertionError('blocked build used')) as build:
            self.app.check_button.invoke()
            self.wait()
            self.assertIn(missing, self.app.report_text.get('1.0', 'end'))
            self.assertIsNone(self.app.session._checked)
            self.assertTrue(self.app.build_button.instate(['disabled']))
            self.app.build_button.invoke()
            build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
