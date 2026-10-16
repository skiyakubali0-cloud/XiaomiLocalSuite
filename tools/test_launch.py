"""Check runtime gates and portable launcher argument handling without a GUI."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('xls_launch', ROOT / 'launch.py')
launch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launch)


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.stdout))
        self.enterContext(contextlib.redirect_stderr(self.stderr))
        self.enterContext(patch.object(sys, 'dont_write_bytecode', True))
        self.enterContext(patch.object(sys, 'path', list(sys.path)))
        self.tk = types.SimpleNamespace(TkVersion=8.6, TclError=type('TclError', (Exception,), {}),
                                        Tk=Mock(side_effect=AssertionError('check must not open windows')))
        self.gui = types.SimpleNamespace(main=Mock())

    def imports(self, name):
        return {'tkinter': self.tk, 'gui': self.gui}[name]

    def test_check_imports_core_without_windows_or_external_commands(self):
        with patch.object(launch.importlib, 'import_module', side_effect=self.imports), \
                patch.object(subprocess, 'run', side_effect=AssertionError('no external commands')):
            self.assertEqual(launch.main(['--check']), 0)
        self.tk.Tk.assert_not_called()
        self.gui.main.assert_not_called()
        self.assertIn('external build/extraction tools were not checked', self.stdout.getvalue())
        self.assertIn(str(ROOT / 'suite/multi-device'), sys.path)

    def test_gui_launch_calls_existing_entry(self):
        with patch.object(launch.importlib, 'import_module', side_effect=self.imports):
            self.assertEqual(launch.main([]), 0)
        self.gui.main.assert_called_once_with()

    def test_old_python_rejected_before_importing_tk(self):
        with patch.object(sys, 'version_info', (3, 10, 0)), \
                patch.object(launch.importlib, 'import_module') as load:
            self.assertEqual(launch.main(['--check']), 1)
        load.assert_not_called()
        self.assertIn('Python 3.11+', self.stderr.getvalue())

    def test_missing_tk_old_tk_and_missing_core_are_diagnostic_failures(self):
        with patch.object(launch.importlib, 'import_module', side_effect=ImportError('Tk not available')):
            self.assertEqual(launch.main(['--check']), 1)
        self.assertIn('Tk 8.6+', self.stderr.getvalue())
        self.tk.TkVersion = 8.5
        with patch.object(launch.importlib, 'import_module', side_effect=self.imports):
            self.assertEqual(launch.main(['--check']), 1)
        self.tk.TkVersion = 8.6
        with patch.object(launch.importlib, 'import_module', side_effect=[self.tk, ImportError('core missing')]):
            self.assertEqual(launch.main(['--check']), 1)
        self.gui.main.assert_not_called()

    def test_display_failure_is_readable(self):
        self.gui.main.side_effect = self.tk.TclError('no display')
        with patch.object(launch.importlib, 'import_module', side_effect=self.imports):
            self.assertEqual(launch.main([]), 1)
        self.assertIn('graphical desktop', self.stderr.getvalue())

    def test_native_windows_check_warns_about_full_flow(self):
        with patch.object(sys, 'platform', 'win32'), \
                patch.object(launch.importlib, 'import_module', side_effect=self.imports):
            self.assertEqual(launch.main(['--check']), 0)
        self.assertIn('WSL2', self.stdout.getvalue())
        self.assertIn('not validated', self.stdout.getvalue())


@unittest.skipIf(os.name == 'nt', 'POSIX shell launchers; Windows launcher reviewed separately')
class ShellLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='portable launch ')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'tool folder with spaces'
        (self.root / 'launchers').mkdir(parents=True)
        for name in ('macOS.command', 'linux.sh'):
            shutil.copy2(ROOT / 'launchers' / name, self.root / 'launchers' / name)
        (self.root / 'launch.py').write_text(
            'import json, os, sys\n'
            'print(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd()}))\n', encoding='utf-8')
        self.python = self.base / 'python executable with spaces'
        self.python.symlink_to(sys.executable)
        self.env = dict(os.environ, XLS_PYTHON=str(self.python))

    def run_launcher(self, name, args=(), env=None):
        return subprocess.run(['/bin/sh', str(self.root / 'launchers' / name), *args],
                              cwd=self.base, env=env or self.env, capture_output=True,
                              text=True, timeout=10, stdin=subprocess.DEVNULL)

    def test_shell_syntax(self):
        for name in ('macOS.command', 'linux.sh'):
            subprocess.run(['/bin/sh', '-n', str(ROOT / 'launchers' / name)], check=True)

    def test_override_handles_spaces_and_argument_boundaries(self):
        import json
        for name in ('macOS.command', 'linux.sh'):
            with self.subTest(name=name):
                result = self.run_launcher(name, ('--check', 'a path with spaces', '$(literal)'))
                self.assertEqual(result.returncode, 0, result.stderr)
                value = json.loads(result.stdout)
                self.assertEqual(value['args'], ['--check', 'a path with spaces', '$(literal)'])
                self.assertEqual(Path(value['cwd']).resolve(), self.root.resolve())

    def test_automatic_candidate_probe_and_launch(self):
        import json
        binary = self.base / 'bin'
        binary.mkdir()
        for name, command in [('python3.13', 'exit 1'),
                              ('python3.12', 'exec ' + shlex.quote(sys.executable) + ' "$@"')]:
            path = binary / name
            path.write_text('#!/bin/sh\n' + command + '\n', encoding='utf-8')
            path.chmod(0o755)
        env = dict(self.env, PATH=str(binary) + os.pathsep + os.environ['PATH'])
        env.pop('XLS_PYTHON')
        for name in ('macOS.command', 'linux.sh'):
            result = self.run_launcher(name, ('--check',), env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['args'], ['--check'])

    def test_bad_override_does_not_silently_fallback(self):
        for name in ('macOS.command', 'linux.sh'):
            result = self.run_launcher(name, ('--check',), dict(self.env, XLS_PYTHON=str(self.base / 'missing')))
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
