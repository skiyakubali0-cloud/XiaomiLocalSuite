"""Exercise release boundaries in disposable Git repositories, without OEM data."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_tool as p


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tool package ')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / 'source repo'
        self.repo.mkdir()
        p.git(self.repo, 'init', '-q')
        p.git(self.repo, 'config', 'user.name', 'Tool test')
        p.git(self.repo, 'config', 'user.email', 'test@example.invalid')
        for name in sorted(p.REQUIRED_FILES):
            self.write(name, '{}\n' if name.endswith('.json') else '# Synthetic public source\n')
        for name in p.POSIX_LAUNCHERS:
            (self.repo / name).chmod(0o755)
        self.write('.gitignore', 'releases/\n*.zip\n')
        self.write('README.md', 'Public source\n')
        self.write('suite/multi-device/gui.py', 'def main():\n    pass\n')
        self.write('launchers/linux.sh', '#!/bin/sh\nexit 0\n')
        (self.repo / 'launchers/linux.sh').chmod(0o755)
        self.commit()
        self.head = p.git(self.repo, 'rev-parse', 'HEAD').decode().strip()

    def write(self, name, raw):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw.encode() if isinstance(raw, str) else raw)

    def commit(self):
        p.git(self.repo, 'add', '-f', '.')
        p.git(self.repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Synthetic fixture')

    def output(self, name='tool.zip'):
        return self.base / name

    def build(self, name='tool.zip', ref='HEAD'):
        return p.package(self.repo, ref, self.output(name))

    def rewrite(self, path, transform):
        with zipfile.ZipFile(path) as archive:
            entries = [(info, archive.read(info)) for info in archive.infolist()]
        with zipfile.ZipFile(path, 'w') as archive:
            for info, raw in transform(entries):
                archive.writestr(info, raw)

    def test_deterministic_exact_blobs_manifest_metadata_and_classic_zip(self):
        first = self.build('one.zip')
        self.write('README.md', 'Dirty local contents\n')
        self.write('suite/multi-device/gui.py', 'Staged local contents\n')
        p.git(self.repo, 'add', 'suite/multi-device/gui.py')
        self.write('docs/temporary.md', 'Untracked local contents\n')
        (self.repo / 'README.md').unlink()
        second = self.build('two.zip')
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with zipfile.ZipFile(first) as archive:
            members = archive.namelist()
            self.assertEqual(members, sorted(members))
            self.assertEqual(archive.read(p.TITLE + '/README.md'), b'Public source\n')
            self.assertNotIn(p.TITLE + '/docs/temporary.md', members)
            self.assertFalse(any('/.git' in name for name in members))
            self.assertTrue(all(p.TITLE + '/' + name in members for name in p.REQUIRED_FILES))
            sums = archive.read(p.TITLE + '/' + p.MANIFEST).decode().splitlines()
            expected = {name[len(p.TITLE) + 1:] for name in members} - {p.MANIFEST}
            self.assertEqual({line.split('  ', 1)[1] for line in sums}, expected)
            for line in sums:
                digest, name = line.split('  ', 1)
                self.assertEqual(digest, hashlib.sha256(archive.read(p.TITLE + '/' + name)).hexdigest())
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertLess(info.extract_version, 45)
                self.assertEqual(info.extra, b'')
            self.assertEqual(archive.getinfo(p.TITLE + '/launchers/linux.sh').external_attr >> 16, 0o100755)
        self.assertEqual(p.verify(first), {'softwarecommit': self.head, 'buildversion': '0.7.0'})

    def test_allowlist_excludes_even_tracked_outputs_deps_private_and_oem(self):
        banned = ['.env', '.github/token.txt', 'materials/stock.apk', 'releases/previous.zip',
                  'suite/build/generated.py', 'suite/deps/vendor.py', 'suite/private/local.py',
                  'suite/.git/config', 'suite/dist/local.py', 'suite/gui-workspace/report.json',
                  'suite/test-work-old/source.py', 'suite/host-old/temp.py', 'suite/tmp/stale.md',
                  'suite/input.apk', 'suite/kernel.img', 'tools/native.exe', 'docs/photo.png',
                  'recipes/stock.apk', 'recipes/stock.so', 'recipes/warning.dex',
                  'recipes/dependency.jar', 'recipes/dependency.aar', 'recipes/reference.zip',
                  'recipes/signing.jks', 'recipes/build/generated.py', 'recipes/private/material.json',
                  'suite/unified-api102/build/plugin.apk', 'build/recipe-tools/dependency.jar',
                  'native/assistant/live/stock.so', 'components/weather/system/lib64/stock.so']
        # Git refuses nested .git entries, so a hidden local input represents that boundary here.
        banned.remove('suite/.git/config')
        banned.append('suite/.env')
        for name in banned:
            self.write(name, b'\x00OEM or local generated bytes')
        self.write('native/assistant/source.cpp', '// public source\n')
        self.write('suite/module/skip_mount', b'')
        self.commit()
        with zipfile.ZipFile(self.build()) as archive:
            names = {name[len(p.TITLE) + 1:] for name in archive.namelist()}
        self.assertFalse(set(banned) & names)
        self.assertIn('native/assistant/source.cpp', names)
        self.assertIn('suite/module/skip_mount', names)

    def test_full_recipe_json_and_own_patch_sources_are_required_and_packaged_exactly(self):
        sources = {
            'materials.lock.json', 'recipes/xuanyuan-1.7.json', 'recipes/generated.json',
            'recipes/apk-materials.json', 'tools/build_suite.py', 'tools/recipe_materials.py',
            'tools/recipe_assemble.py', 'tools/recipe_generated.py', 'tools/recipe_tools.py',
            'native/assistant/assistant-route.S', 'native/assistant/build-runtime-route.py',
            'suite/multi-device/plugin_builder.py', 'docs/FULL_RECIPE.md',
            'suite/unified-api102/build_apk.py', 'suite/unified-api102/fetch_dependencies.py',
            'suite/unified-api102/deps.lock.json', 'suite/unified-api102/AndroidManifest.xml',
            'suite/unified-api102/META-INF/xposed/java_init.list',
            'suite/unified-api102/META-INF/xposed/module.prop',
            'suite/unified-api102/META-INF/xposed/scope.list',
            'suite/module/control.sh', 'suite/module/preset.sh', 'suite/module/webroot/catalog.json',
        }
        self.assertTrue(sources <= p.REQUIRED_FILES)
        contents = {name: (p.ROOT / name).read_bytes() for name in sources}
        for name, raw in contents.items():
            self.write(name, raw)
        self.commit()
        output = self.build()
        with zipfile.ZipFile(output) as archive:
            for name, raw in contents.items():
                with self.subTest(name=name):
                    actual = archive.read(p.TITLE + '/' + name)
                    self.assertEqual(actual, raw)
                    if name.endswith('.json'):
                        self.assertEqual(json.loads(actual), json.loads(raw))
        self.assertEqual(p.verify(output)['buildversion'], '0.7.0')

    def test_autoinstall_script_and_validation_doc_are_required_and_packaged(self):
        names = {'suite/module/install-selected.sh', 'docs/AUTOINSTALL_VALIDATION.md'}
        self.assertTrue(names <= p.REQUIRED_FILES)
        # setUp creates safe placeholders only in this disposable fixture repository.
        with zipfile.ZipFile(self.build()) as archive:
            for name in sorted(names):
                self.assertEqual(archive.read(p.TITLE + '/' + name), b'# Synthetic public source\n')
        for name in sorted(names):
            with self.subTest(name=name):
                (self.repo / name).unlink()
                self.commit()
                with self.assertRaisesRegex(ValueError, 'Incomplete tool source'):
                    self.build('missing-' + Path(name).name + '.zip')
                self.write(name, '# Synthetic public source\n')
                self.commit()

    def test_explicit_old_ref_uses_original_commit(self):
        self.write('README.md', 'Later source\n')
        self.commit()
        metadata = p.verify(self.build(ref=self.head))
        self.assertEqual(metadata['softwarecommit'], self.head)

    def test_audit_rejects_binary_and_secrets_before_creating_output(self):
        for name in ('docs/input.txt', 'recipes/input.json', 'recipes/patch.py'):
            for raw in (b'\x00binary', b'ghp_' + b'a' * 30, b'\xffinvalid UTF8'):
                with self.subTest(name=name, raw_kind=raw[:4]):
                    self.write(name, raw)
                    self.commit()
                    with self.assertRaisesRegex(ValueError, 'Public-tree audit failed') as caught:
                        self.build()
                    self.assertNotIn(repr(raw), str(caught.exception))
                    self.assertFalse(self.output().exists())
            (self.repo / name).unlink()

    def test_symlink_is_rejected_without_reading_target(self):
        (self.repo / 'docs/link.txt').symlink_to('missing-private-target')
        self.commit()
        with self.assertRaisesRegex(ValueError, 'Non-regular Git entry'):
            self.build()

    def test_gitlink_is_rejected(self):
        p.git(self.repo, 'update-index', '--add', '--cacheinfo', '160000,' + self.head + ',suite/submodule')
        p.git(self.repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Synthetic gitlink')
        with self.assertRaisesRegex(ValueError, 'Non-regular Git entry'):
            self.build()

    def test_nonportable_and_case_colliding_paths_rejected(self):
        for name in ('docs/CON.txt', 'docs/name:stream.txt', 'docs/line\nbreak.txt'):
            with self.subTest(name=name):
                self.assertFalse(p.safe_name(name))
        # Git objects allow case collisions even on a case-insensitive host filesystem.
        oid = p.git(self.repo, 'hash-object', '-w', '--stdin', input=b'Another source\n').decode().strip()
        p.git(self.repo, 'update-index', '--add', '--cacheinfo', '100644,' + oid + ',docs/Test.md')
        p.git(self.repo, 'update-index', '--add', '--cacheinfo', '100644,' + oid + ',docs/test.md')
        p.git(self.repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Synthetic collision')
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.build()

    def test_output_policy_no_overwrite_and_ignored_releases(self):
        self.write('tracked.zip', 'Tracked sentinel\n')
        self.commit()
        (self.repo / 'tracked.zip').unlink()
        for target in ('tracked.zip', 'README.md/child.zip', '.git/result.zip', 'new.zip'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                p.package(self.repo, 'HEAD', self.repo / target)
        output = p.package(self.repo, 'HEAD', self.repo / 'releases/new.zip')
        original = output.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            p.package(self.repo, 'HEAD', output)
        self.assertEqual(output.read_bytes(), original)
        link = self.output('link.zip')
        link.symlink_to(self.output('missing.zip'))
        with self.assertRaisesRegex(ValueError, 'already exists'):
            p.package(self.repo, 'HEAD', link)

    def test_nonignored_releases_are_rejected(self):
        self.write('.gitignore', '')
        with self.assertRaisesRegex(ValueError, 'Git-ignored'):
            p.package(self.repo, 'HEAD', self.repo / 'releases/tool.zip')

    def test_failed_write_cleans_partial_output(self):
        with patch.object(zipfile.ZipFile, 'writestr', side_effect=zipfile.LargeZipFile('classic limit')):
            with self.assertRaises(zipfile.LargeZipFile):
                self.build()
        self.assertFalse(self.output().exists())

    def test_missing_runtime_or_docs_rejected_in_snapshot_and_verify(self):
        for name in ('launch.py', 'suite/multi-device/environment.py', 'docs/USER_GUIDE.md',
                     'recipes/xuanyuan-1.7.json', 'recipes/generated.json', 'recipes/apk-materials.json',
                     'native/assistant/assistant-route.S', 'tools/recipe_generated.py',
                     'suite/multi-device/plugin_builder.py', 'docs/FULL_RECIPE.md',
                     'suite/module/install-selected.sh', 'docs/AUTOINSTALL_VALIDATION.md'):
            with self.subTest(name=name):
                output = self.build(name.replace('/', '-') + '.zip')

                def remove_and_rehash(entries):
                    entries = [(info, raw) for info, raw in entries if info.filename != p.TITLE + '/' + name]
                    files = {info.filename[len(p.TITLE) + 1:]: (raw, info.external_attr >> 16)
                             for info, raw in entries if not info.filename.endswith('/' + p.MANIFEST)}
                    return [(info, p.manifest(files) if info.filename.endswith('/' + p.MANIFEST) else raw)
                            for info, raw in entries]

                self.rewrite(output, remove_and_rehash)
                with self.assertRaisesRegex(ValueError, 'Incomplete tool source'):
                    p.verify(output)
        (self.repo / 'launch.py').unlink()
        self.commit()
        with self.assertRaisesRegex(ValueError, 'Incomplete tool source'):
            self.build()

    def test_nonexecutable_posix_launcher_rejected_in_snapshot_and_verify(self):
        output = self.build()

        def change_mode(entries):
            for info, raw in entries:
                if info.filename.endswith('/launchers/linux.sh'):
                    info.external_attr = 0o100644 << 16
            return entries

        self.rewrite(output, change_mode)
        with self.assertRaisesRegex(ValueError, 'must be executable'):
            p.verify(output)
        p.git(self.repo, 'update-index', '--chmod=-x', 'launchers/linux.sh')
        p.git(self.repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Synthetic nonexecutable launcher')
        with self.assertRaisesRegex(ValueError, 'must be executable'):
            self.build('nonexecutable.zip')

    def test_verify_rejects_tamper_missing_extra_duplicate_and_symlink(self):
        def tamper(entries):
            return [(info, b'changed' if info.filename.endswith('/README.md') else raw) for info, raw in entries]

        def missing(entries):
            return [(info, raw) for info, raw in entries if not info.filename.endswith('/README.md')]

        def extra(entries):
            info = zipfile.ZipInfo(p.TITLE + '/docs/extra.md')
            info.external_attr = 0o100644 << 16
            return entries + [(info, b'Added')]

        def symlink(entries):
            for info, raw in entries:
                if info.filename.endswith('/README.md'):
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
            return entries

        def duplicate(entries):
            return entries + [(copy.copy(entries[0][0]), entries[0][1])]

        for index, transform in enumerate((tamper, missing, extra, symlink, duplicate)):
            with self.subTest(case=index):
                output = self.build(str(index) + '.zip')
                with self.assertWarns(UserWarning) if index == 4 else self.subTest(rewrite=True):
                    self.rewrite(output, transform)
                with self.assertRaises(ValueError):
                    p.verify(output)

    def test_cli_defaults_to_head_and_verifies_without_git(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with patch.object(p, 'ROOT', self.repo):
                self.assertEqual(p.main(['--output', str(self.output())]), 0)
            with patch.object(p, 'git', side_effect=AssertionError('verification must not invoke Git')):
                self.assertEqual(p.main(['--verify', str(self.output())]), 0)


if __name__ == '__main__':
    unittest.main()
