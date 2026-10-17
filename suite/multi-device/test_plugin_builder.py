"""Bounded plugin-build adapter tests; no SDK, signing, network, or phone required."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import plugin_builder as p


class BuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.unified = self.root / 'suite/unified-api102'
        self.unified.mkdir(parents=True)
        self.key = self.root / 'caller key.jks'
        self.key.write_bytes(b'caller-owned-key-fixture')
        self.sdk = self.root / 'offline sdk'
        self.deps = self.root / 'offline aars'
        self.inputs = (self.root, self.key, 'caller alias', 'store-secret', 'key-secret',
                       self.sdk, self.deps)

    def built(self, command, **kwargs):
        output = Path(command[command.index('--output') + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(b'new-apk-fixture')
        evidence = output.with_suffix('.build-evidence.json')
        with evidence.open('x', encoding='utf-8') as stream:
            json.dump({'apk': str(output.relative_to(self.unified)),
                       'apk_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}, stream)
        return subprocess.CompletedProcess(command, 0, stdout=b'not-the-output.apk', stderr=b'')

    def test_env_only_passwords_exact_offline_command_and_actual_output(self):
        with patch.dict(os.environ, {'SUITE_STORE_PASSWORD': 'old-store',
                                     'SUITE_KEY_PASSWORD': 'old-key'}):
            before = dict(os.environ)
            with patch.object(p.subprocess, 'run', side_effect=self.built) as run:
                output = p.run_build(*self.inputs)
            self.assertEqual(dict(os.environ), before)
        command = run.call_args.args[0]
        self.assertEqual(command, [sys.executable, '-B', str(self.unified / 'build_apk.py'),
            '--wallet-selectable', '--sdk', str(self.sdk), '--deps-dir', str(self.deps),
            '--keystore', str(self.key), '--key-alias', 'caller alias', '--output', str(output)])
        self.assertEqual(run.call_count, 1)
        options = run.call_args.kwargs
        self.assertTrue(options['capture_output'])
        self.assertTrue(options['check'])
        self.assertEqual(options['cwd'], self.root)
        self.assertEqual(options['env']['SUITE_STORE_PASSWORD'], 'store-secret')
        self.assertEqual(options['env']['SUITE_KEY_PASSWORD'], 'key-secret')
        self.assertNotIn('store-secret', str(command))
        self.assertNotIn('key-secret', str(command))
        self.assertEqual(output.parent, self.unified / 'build')
        self.assertRegex(output.name, r'^unified-\d{8}T\d{12}Z-[0-9a-f]{32}\.apk$')
        evidence = output.with_suffix('.build-evidence.json').read_text()
        self.assertNotIn('store-secret', evidence)
        self.assertNotIn('key-secret', evidence)
        self.assertEqual(self.key.read_bytes(), b'caller-owned-key-fixture')
        self.assertEqual({path for path in self.root.rglob('*') if path.is_file()},
                         {self.key, output, output.with_suffix('.build-evidence.json')})

    def test_repeated_builds_have_distinct_outputs_even_at_same_timestamp(self):
        with patch.object(p, 'datetime') as clock, patch.object(p.subprocess, 'run', side_effect=self.built):
            clock.now.return_value.strftime.return_value = 'same-time'
            first = p.run_build(*self.inputs)
            second = p.run_build(*self.inputs)
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_existing_apk_or_evidence_including_dangling_links_is_never_overwritten(self):
        build = self.unified / 'build'
        build.mkdir()
        with patch.object(p, 'datetime') as clock, patch.object(p, 'uuid4', return_value=Mock(hex='fixed')):
            clock.now.return_value.strftime.return_value = 'fixed-time'
            for suffix in ('.apk', '.build-evidence.json'):
                for symlink in (False, True):
                    with self.subTest(suffix=suffix, symlink=symlink):
                        existing = build / ('unified-fixed-time-fixed' + suffix)
                        if symlink:
                            existing.symlink_to(build / 'absent')
                        else:
                            existing.write_bytes(b'preserve-existing')
                        with patch.object(p.subprocess, 'run') as run:
                            with self.assertRaisesRegex(ValueError, p.BUILD_FAILED):
                                p.run_build(*self.inputs)
                            run.assert_not_called()
                        if symlink:
                            self.assertTrue(existing.is_symlink())
                        else:
                            self.assertEqual(existing.read_bytes(), b'preserve-existing')
                        existing.unlink()

    def test_build_directory_cannot_redirect_outside_project(self):
        for directory in (self.unified / 'build', self.root / 'suite'):
            with self.subTest(directory=directory):
                if directory.name == 'suite':
                    self.unified.rmdir()
                    directory.rmdir()
                directory.symlink_to(self.root.parent, target_is_directory=True)
                with patch.object(p.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, p.BUILD_FAILED):
                        p.run_build(*self.inputs)
                    run.assert_not_called()
                directory.unlink()

    def test_missing_inputs_do_not_start_build_or_prepare_dependencies(self):
        for index in range(1, len(self.inputs)):
            with self.subTest(index=index):
                values = list(self.inputs)
                values[index] = ''
                with patch.object(p.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, p.BUILD_FAILED):
                        p.run_build(*values)
                    run.assert_not_called()

    def test_subprocess_errors_are_generic_and_never_relay_output(self):
        for failure in (subprocess.CalledProcessError(1, ['secret-command'],
                        output=b'store-secret', stderr=b'key-secret'), OSError('store-secret')):
            with self.subTest(failure=type(failure)), patch.object(p.subprocess, 'run', side_effect=failure):
                with self.assertRaises(ValueError) as raised:
                    p.run_build(*self.inputs)
                self.assertEqual(str(raised.exception), p.BUILD_FAILED)
                self.assertTrue(raised.exception.__suppress_context__)

    def test_missing_invalid_or_mismatched_evidence_cannot_succeed(self):
        def invalid_build(kind, command, **kwargs):
            self.built(command, **kwargs)
            output = Path(command[command.index('--output') + 1])
            evidence = output.with_suffix('.build-evidence.json')
            if kind == 'missing-apk':
                output.unlink()
            elif kind == 'missing-evidence':
                evidence.unlink()
            elif kind in ('symlink-apk', 'symlink-evidence'):
                path = output if kind == 'symlink-apk' else evidence
                target = path.with_suffix('.target')
                path.rename(target)
                path.symlink_to(target)
            elif kind == 'bad-json':
                evidence.write_text('store-secret is not JSON')
            elif kind == 'wrong-type':
                evidence.write_text('[]')
            else:
                report = json.loads(evidence.read_text())
                if kind == 'hash-mismatch':
                    output.write_bytes(b'changed-after-build')
                else:
                    report['apk'] = 'build/another.apk'
                evidence.write_text(json.dumps(report))
            return subprocess.CompletedProcess(command, 0)

        for kind in ('missing-apk', 'missing-evidence', 'symlink-apk', 'symlink-evidence',
                     'bad-json', 'wrong-type', 'hash-mismatch', 'wrong-output'):
            with self.subTest(kind=kind), patch.object(p.subprocess, 'run',
                    side_effect=lambda command, **kw: invalid_build(kind, command, **kw)):
                with self.assertRaises(ValueError) as raised:
                    p.run_build(*self.inputs)
                self.assertEqual(str(raised.exception), p.BUILD_FAILED)


class DependencyTests(unittest.TestCase):
    def test_only_explicit_preparation_runs_both_pinned_scripts_in_order(self):
        with patch.dict(os.environ, {'SUITE_STORE_PASSWORD': 'parent-secret',
                                     'SUITE_KEY_PASSWORD': 'parent-key'}):
            before = dict(os.environ)
            with patch.object(p.subprocess, 'run') as run:
                message = p.prepare_dependencies(p.ROOT)
            self.assertEqual(dict(os.environ), before)
        self.assertEqual([call.args[0] for call in run.call_args_list], [
            [sys.executable, '-B', str(p.ROOT / script), '--download'] for script in
            ('suite/unified-api102/fetch_dependencies.py', 'tools/recipe_tools.py')])
        for call in run.call_args_list:
            self.assertEqual(call.kwargs['cwd'], p.ROOT)
            self.assertTrue(call.kwargs['capture_output'])
            self.assertTrue(call.kwargs['check'])
            self.assertNotIn('SUITE_STORE_PASSWORD', call.kwargs['env'])
            self.assertNotIn('SUITE_KEY_PASSWORD', call.kwargs['env'])
        self.assertIn('3 个 libxposed AAR', message)
        self.assertIn('4 个预警 DEX JAR', message)

    def test_download_failure_short_circuits_and_hides_both_scripts_output(self):
        for failed_step in (0, 1):
            failure = subprocess.CalledProcessError(1, ['download'],
                                                  output=b'private stdout', stderr=b'private stderr')
            results = [failure] if failed_step == 0 else [subprocess.CompletedProcess([], 0), failure]
            with self.subTest(step=failed_step), patch.object(p.subprocess, 'run', side_effect=results) as run:
                with self.assertRaises(ValueError) as raised:
                    p.prepare_dependencies()
                self.assertEqual(str(raised.exception), p.PREPARE_FAILED)
                self.assertEqual(run.call_count, failed_step + 1)


class DialogTests(unittest.TestCase):
    def setUp(self):
        self.variables, self.entries, self.buttons = [], [], []
        self.app, self.on_built, self.window = Mock(), Mock(), Mock()

        def variable(**kwargs):
            value = Mock()
            value.get.return_value = kwargs['value']
            value.set.side_effect = lambda new: setattr(value.get, 'return_value', new)
            self.variables.append(value)
            return value

        def entry(*args, **kwargs):
            self.entries.append(kwargs)
            return Mock()

        def button(*args, **kwargs):
            self.buttons.append(kwargs)
            return Mock()

        patches = [patch.object(p.tk, 'Toplevel', return_value=self.window),
                   patch.object(p.tk, 'StringVar', side_effect=variable),
                   patch.object(p.ttk, 'Frame'), patch.object(p.ttk, 'Label'),
                   patch.object(p.ttk, 'Entry', side_effect=entry),
                   patch.object(p.ttk, 'Button', side_effect=button)]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def button(self, text):
        return next(button['command'] for button in self.buttons if button['text'] == text)

    def test_open_does_not_build_or_download_and_has_masked_passwords_and_defaults(self):
        with patch.dict(os.environ, {'ANDROID_SDK_ROOT': '/sdk-root', 'ANDROID_HOME': '/sdk-home'}), \
                patch.object(p.subprocess, 'run') as run:
            self.assertIs(p.open_dialog(self.app, self.on_built), self.window)
            run.assert_not_called()
        self.app._start.assert_not_called()
        self.assertEqual([entry['show'] for entry in self.entries], ['', '', '*', '*', '', ''])
        self.assertEqual(self.variables[4].get(), '/sdk-root')
        self.assertEqual(self.variables[5].get(), str(p.ROOT / 'suite/unified-api102/build/deps'))
        self.assertEqual(p.ROOT, Path(p.__file__).resolve().parents[2])

    def test_sdk_falls_back_to_android_home(self):
        with patch.dict(os.environ, {'ANDROID_SDK_ROOT': '', 'ANDROID_HOME': '/sdk-home'}):
            p.open_dialog(self.app, self.on_built)
        self.assertEqual(self.variables[4].get(), '/sdk-home')

    def test_build_closes_and_clears_before_worker_and_callback_receives_actual_path(self):
        p.open_dialog(self.app, self.on_built)
        values = ('/caller/key.jks', 'alias', 'store-secret', 'key-secret', '/sdk', '/aars')
        for variable, value in zip(self.variables, values):
            variable.set(value)

        def started(*args):
            self.window.destroy.assert_called_once()
            self.assertTrue(all(variable.get() == '' for variable in self.variables))

        self.app._start.side_effect = started
        self.button('本地构建')()
        _, work, callback = self.app._start.call_args.args
        # The background worker must never read destroyed Tk widgets/variables.
        for variable in self.variables:
            variable.get.side_effect = AssertionError('Tk read in worker')
        actual = p.ROOT / 'suite/unified-api102/build/actual.apk'
        with patch.object(p, 'run_build', return_value=actual) as build, \
                patch.object(p, 'prepare_dependencies') as prepare:
            callback(work())
            build.assert_called_once_with(p.ROOT, *values)
            prepare.assert_not_called()
        self.on_built.assert_called_once_with(actual)

    def test_prepare_is_explicit_clears_dialog_and_uses_worker_generic_message(self):
        with patch.object(p, 'prepare_dependencies', return_value='safe completion') as prepare:
            p.open_dialog(self.app, self.on_built)
            prepare.assert_not_called()
            self.button('联网准备依赖')()
            self.window.destroy.assert_called_once()
            self.assertTrue(all(variable.get() == '' for variable in self.variables))
            prepare.assert_not_called()
            _, work, callback = self.app._start.call_args.args
            callback(work())
            prepare.assert_called_once_with(p.ROOT)
        self.app._show.assert_called_once_with('safe completion')
        self.on_built.assert_not_called()

    def test_choosers_select_existing_keystore_and_offline_directories(self):
        p.open_dialog(self.app, self.on_built)
        choosers = [button['command'] for button in self.buttons if button['text'] == '选择…']
        with patch.object(p.filedialog, 'askopenfilename', return_value='/existing/key.jks') as choose:
            choosers[0]()
            self.assertEqual(choose.call_args.kwargs['parent'], self.window)
        with patch.object(p.filedialog, 'askdirectory', side_effect=['/offline/sdk', '/offline/aars']):
            choosers[1]()
            choosers[2]()
        self.assertEqual(self.variables[0].get(), '/existing/key.jks')
        self.assertEqual(self.variables[4].get(), '/offline/sdk')
        self.assertEqual(self.variables[5].get(), '/offline/aars')
        self.app._start.assert_not_called()

    def test_cancel_or_window_close_clears_passwords_without_starting_work(self):
        p.open_dialog(self.app, self.on_built)
        self.variables[2].set('store-secret')
        self.variables[3].set('key-secret')
        self.window.protocol.assert_called_once()
        self.assertEqual(self.window.protocol.call_args.args[0], 'WM_DELETE_WINDOW')
        self.assertIs(self.window.protocol.call_args.args[1], self.button('取消'))
        self.button('取消')()
        self.assertTrue(all(variable.get() == '' for variable in self.variables))
        self.window.destroy.assert_called_once()
        self.app._start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
