"""Real SDK tools + signed APKs, not mocked inventories. No phone access."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile
import suite_builder as b
import intake

SDK = Path(os.environ.get('ANDROID_SDK_ROOT', '/opt/homebrew/share/android-commandlinetools'))
TOOLS = SDK / 'build-tools/36.0.0'
ANDROID = SDK / 'platforms/android-36/android.jar'
AVAILABLE = all(p.is_file() for p in (TOOLS / 'aapt2', TOOLS / 'apksigner', ANDROID)) and shutil.which('keytool')


@unittest.skipUnless(AVAILABLE, 'Real Android SDK tools not installed')
class SignedApkIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        cls.target = cls.root / 'target'
        cls.source = cls.root / 'source'
        cls.source.mkdir()
        cls.target.mkdir()
        cls.key = cls.root / 'private-test-signing.jks'
        def run(*args):
            return subprocess.run(list(map(str, args)), check=True, capture_output=True, text=True)
        run('keytool', '-genkeypair', '-noprompt', '-keystore', cls.key, '-storepass', 'fixture-signing-only',
            '-keypass', 'fixture-signing-only', '-alias', 'test', '-keyalg', 'RSA', '-keysize', '2048',
            '-validity', '2', '-dname', 'CN=Offline builder fixture only')
        cls.key.chmod(0o600)
        cls.target_apk = cls.target / 'product/app/Fixture/Fixture.apk'
        cls.target_apk.parent.mkdir(parents=True)
        cls.source_apk = cls.source / 'Fixture.apk'
        for code, destination in [(1, cls.target_apk), (2, cls.source_apk)]:
            manifest = cls.root / f'manifest-{code}.xml'
            manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
                'package="local.builder.fixture" android:versionCode="' + str(code) + '" android:versionName="1">'
                '<uses-sdk android:minSdkVersion="30" android:targetSdkVersion="36"/>'
                '<uses-permission android:name="android.permission.INTERNET"/>'
                '<application android:hasCode="false" android:label="Builder test"/></manifest>')
            unsigned = cls.root / f'unsigned-{code}.apk'
            run(TOOLS / 'aapt2', 'link', '-I', ANDROID, '--manifest', manifest, '-o', unsigned)
            run(TOOLS / 'apksigner', 'sign', '--ks', cls.key, '--ks-key-alias', 'test',
                '--ks-pass', 'pass:fixture-signing-only', '--key-pass', 'pass:fixture-signing-only',
                '--out', destination, unsigned)
        (cls.target / 'product/build.prop').write_text('ro.product.device=fixturephone\n'
            'ro.build.version.sdk=37\nro.build.version.incremental=OS4.FIXTURE\n'
            'ro.product.cpu.abilist=arm64-v8a\n')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_actual_manifest_signature_and_permissions(self):
        result = intake.scan(self.source_apk)
        apk = result['apks'][0]
        self.assertEqual(apk['package'], 'local.builder.fixture')
        self.assertEqual(apk['min_sdk'], 30)
        self.assertEqual(apk['requested_permissions'], ['android.permission.INTERNET'])
        self.assertTrue(apk['signature_verified'])
        self.assertTrue(apk['metadata_complete'])
        self.assertEqual(len(apk['signers_sha256']), 1)

    def test_full_cli_workflow_and_second_model(self):
        work = self.root / self._testMethodName
        work.mkdir()
        builder = b.HERE / 'suite_builder.py'
        import sys
        def cli(*args):
            run = subprocess.run([sys.executable, str(builder), *map(str, args)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            return json.loads(run.stdout)
        draft = work / 'draft.json'
        selected = work / 'selected.json'
        report = work / 'check.json'
        output = work / 'fixture.zip'
        d = cli('init', '--id', 'fixturephone-test', '--target', self.target, '--source', self.source, '--out', draft)
        self.assertEqual(d['target']['device'], 'fixturephone')
        self.assertFalse(d['components'][0]['enabled'])
        cli('select', '--profile', draft, '--packages', 'local.builder.fixture', '--out', selected)
        result = cli('check', '--profile', selected, '--out', report)
        self.assertEqual(result['state'], 'candidate-static-pass')
        result = cli('build', '--profile', selected, '--candidate', '--out', output)
        self.assertFalse(result['device_tested'])
        b.verify_archive(output)
        with zipfile.ZipFile(output) as z:
            self.assertEqual(z.read('system/product/app/Fixture/Fixture.apk'), self.source_apk.read_bytes())
            self.assertFalse(any('.jks' in n or 'private' in n for n in z.namelist()))
            self.assertNotIn(str(self.root), z.read('profile.json').decode())
            installer = z.read('customize.sh').decode()
            self.assertIn('fixturephone', installer)
            self.assertNotIn('pm clear', installer)
            self.assertNotIn('reset', installer)
            self.assertNotIn('pm uninstall', installer)

    def test_real_base_apk_requiring_split_rejected(self):
        work = self.root / self._testMethodName
        work.mkdir()
        manifest = work / 'AndroidManifest.xml'
        manifest.write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
            'package="local.builder.fixture" android:versionCode="3" android:isSplitRequired="true" '
            'android:requiredSplitTypes="abi">'
            '<uses-sdk android:minSdkVersion="30" android:targetSdkVersion="36"/>'
            '<uses-permission android:name="android.permission.INTERNET"/>'
            '<application android:hasCode="false"/></manifest>')
        unsigned = work / 'unsigned.apk'
        signed = work / 'base.apk'
        subprocess.run(list(map(str, [TOOLS / 'aapt2', 'link', '-I', ANDROID, '--manifest', manifest, '-o', unsigned])), check=True, capture_output=True)
        subprocess.run(list(map(str, [TOOLS / 'apksigner', 'sign', '--ks', self.key, '--ks-key-alias', 'test',
            '--ks-pass', 'pass:fixture-signing-only', '--key-pass', 'pass:fixture-signing-only',
            '--out', signed, unsigned])), check=True, capture_output=True)
        apk = intake.scan(signed)['apks'][0]
        self.assertTrue(apk['metadata_complete'])
        self.assertTrue(apk['signature_verified'])
        self.assertTrue(apk['requires_splits'])
        p = b.draft('split-base-test', self.target, signed)
        p['components'][0]['enabled'] = True
        report = b.check_profile(p, self.root)
        self.assertEqual(report['state'], 'blocked')
        self.assertIn('Split APK/base dependencies', str(report['components']))

    def test_same_apk_not_falsely_other_model_approved(self):
        p = b.draft('mismatch-model', self.target, self.source)
        p['components'][0]['enabled'] = True
        p['target']['device'] = 'unrelatedphone'
        with self.assertRaisesRegex(ValueError, 'firmware device'):
            b.check_profile(p, self.root)


if __name__ == '__main__':
    unittest.main()
