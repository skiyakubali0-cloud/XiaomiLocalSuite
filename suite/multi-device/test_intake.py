"""Run with python3 -B -m unittest discover -s THIS_DIRECTORY -p test_intake.py."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile


SPEC = importlib.util.spec_from_file_location('intake_under_test', Path(__file__).with_name('intake.py'))
intake = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(intake)
CERT = 'ab' * 32
BADGING = """package: name='example.app' versionCode='42' versionName='1.0'
sdkVersion:'26'
targetSdkVersion:'35'
uses-library:'required.lib'
uses-library-not-required:'optional.lib'
"""
XML = """N: android=http://schemas.android.com/apk/res/android
  E: manifest (line=2)
    A: http://schemas.android.com/apk/res/android:sharedUserId(0x0101000b)="android.uid.system"
    E: application
      E: uses-library
        A: http://schemas.android.com/apk/res/android:name(0x01010003)="required.lib"
      E: uses-library
        A: android:name(0x01010003)="optional.lib"
        A: android:required(0x0101028e)=false
      E: uses-static-library
        A: android:name(0x01010003)="static.lib"
      E: uses-sdk-library
        A: android:name(0x01010003)="sdk.lib"
"""
PERMISSIONS = """package: example.app
uses-permission: name='android.permission.INTERNET'
uses-permission-sdk-23: name='android.permission.CAMERA'
permission: example.app.DEFINED_ONLY
"""
OTA = """pre-device=example
post-sdk-level=37
post-build-incremental=OS4.6
post-build=Brand/product/example:17/ID/OS4.6:user/release-keys
"""


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.badging, self.xml, self.permissions = BADGING, XML, PERMISSIONS
        self.signer_error = False
        self.commands = []

    def apk(self, relative='app.apk', native=True):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('AndroidManifest.xml', b'fixture')
            if native:
                archive.writestr('lib/arm64-v8a/libexample.so', b'fixture')
        return path

    def ota(self, text=OTA, extra=()):
        path = self.root / 'ota.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr(intake.OTA_METADATA, text)
                archive.writestr('payload.bin', b'not extracted')
                for name, data in extra:
                    archive.writestr(name, data)
        return path

    def run_tool(self, args, **kwargs):
        self.commands.append(args)
        if args[0] == '/tools/apksigner':
            if self.signer_error:
                raise ValueError('tool exited 1: DOES NOT VERIFY')
            return 'Verifies\nSigner #1 certificate SHA-256 digest: ' + CERT + '\n'
        return {'badging': self.badging, 'xmltree': self.xml, 'permissions': self.permissions}[args[2]]

    def scan(self, path):
        with patch.object(intake, '_tool', side_effect=lambda name, explicit=None: '/tools/' + name), patch.object(intake, '_run', side_effect=self.run_tool):
            result = intake.scan(path)
        json.dumps(result)  # Every result must remain serializable.
        return result

    def test_apk_all_contract_fields_and_tools_are_argument_lists(self):
        path = self.apk("shell;$(touch nope).apk")
        result = self.scan(path)
        apk = result['apks'][0]
        self.assertEqual(result['kind'], 'apk')
        self.assertEqual(result['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(apk['path'], str(path.resolve()))
        self.assertEqual(apk['package'], 'example.app')
        self.assertEqual(apk['version_code'], 42)
        self.assertEqual((apk['min_sdk'], apk['target_sdk']), (26, 35))
        self.assertEqual(apk['signers_sha256'], [CERT])
        self.assertTrue(apk['signature_verified'])
        self.assertTrue(apk['metadata_complete'])
        self.assertFalse(apk['requires_splits'])
        self.assertEqual(apk['source_authenticity'], 'unknown')
        self.assertEqual(result['source_authenticity'], 'unknown')
        self.assertEqual(apk['abis'], ['arm64-v8a'])
        self.assertEqual(apk['uses_libraries'], ['required.lib'])
        self.assertEqual(apk['optional_uses_libraries'], ['optional.lib'])
        self.assertEqual(apk['uses_static_libraries'], ['static.lib'])
        self.assertEqual(apk['uses_sdk_libraries'], ['sdk.lib'])
        self.assertEqual(apk['requested_permissions'], ['android.permission.CAMERA', 'android.permission.INTERNET'])
        self.assertEqual(apk['shared_user_id'], 'android.uid.system')
        self.assertTrue(all(isinstance(args, list) and args[-1] in (str(path), 'AndroidManifest.xml') for args in self.commands))
        self.assertTrue(any(args[1:3] == ['dump', 'permissions'] for args in self.commands))

    def test_alternate_min_sdk_and_conflict(self):
        path = self.apk()
        self.badging = BADGING.replace('sdkVersion:', 'minSdkVersion:')
        self.assertEqual(self.scan(path)['apks'][0]['min_sdk'], 26)
        self.badging += "sdkVersion:'35'\n"
        apk = self.scan(path)['apks'][0]
        self.assertIsNone(apk['min_sdk'])
        self.assertFalse(apk['metadata_complete'])

    def test_missing_tools_cannot_look_verified(self):
        path = self.apk()
        with patch.object(intake, '_tool', return_value=None):
            apk = intake.scan(path)['apks'][0]
        self.assertFalse(apk['metadata_complete'])
        self.assertIsNone(apk['signature_verified'])
        self.assertEqual(apk['uses_static_libraries'], [])
        self.assertTrue(apk['warnings'])

    def test_signature_error_does_not_erase_manifest_evidence(self):
        self.signer_error = True
        apk = self.scan(self.apk())['apks'][0]
        self.assertFalse(apk['signature_verified'])
        self.assertEqual(apk['signers_sha256'], [])
        self.assertTrue(apk['metadata_complete'])

    def test_xmltree_and_permissions_failure_are_incomplete(self):
        path = self.apk()
        for field in ('xml', 'permissions'):
            with self.subTest(field=field):
                old = getattr(self, field)
                setattr(self, field, 'unusable output')
                apk = self.scan(path)['apks'][0]
                self.assertEqual(apk['package'], 'example.app')
                self.assertFalse(apk['metadata_complete'])
                setattr(self, field, old)

    def test_conflicting_shared_user_and_unknown_library_name(self):
        self.xml += '    A: android:sharedUserId="other.uid"\n'
        apk = self.scan(self.apk())['apks'][0]
        self.assertIsNone(apk['shared_user_id'])
        self.assertFalse(apk['metadata_complete'])
        self.xml = 'E: manifest\n  E: uses-static-library\n'
        self.assertFalse(self.scan(self.apk('second.apk'))['apks'][0]['metadata_complete'])

    def test_unresolved_shared_user_cannot_look_complete(self):
        self.xml = 'E: manifest\n A: android:sharedUserId(0x0101000b)=@0x7f010001\n'
        apk = self.scan(self.apk())['apks'][0]
        self.assertIsNone(apk['shared_user_id'])
        self.assertFalse(apk['metadata_complete'])

    def test_no_libraries_or_shared_user_is_valid(self):
        self.badging = '\n'.join(BADGING.splitlines()[:3])
        self.xml = 'E: manifest\n E: application\n'
        self.permissions = 'package: example.app\n'
        apk = self.scan(self.apk())['apks'][0]
        self.assertTrue(apk['metadata_complete'])
        self.assertEqual(apk['requested_permissions'], [])
        self.assertIsNone(apk['shared_user_id'])

    def test_split_without_base_and_duplicate_identity(self):
        self.badging = BADGING.replace("versionCode='42'", "versionCode='42' split='config.en'")
        self.apk('one.apk')
        self.apk('two.apk')
        result = self.scan(self.root)
        self.assertEqual(result['apks'][0]['split'], 'config.en')
        self.assertTrue(any('duplicate package/split' in w for w in result['warnings']))
        self.assertTrue(any('missing a unique base' in w for w in result['warnings']))

    def test_base_apk_split_requirements_do_not_need_a_split_name(self):
        path = self.apk()
        for declaration in (
                ' A: android:isSplitRequired(0x01010591)=true\n',
                ' A: http://schemas.android.com/apk/res/android:requiredSplitTypes="abi"\n',
                ' E: uses-split\n  A: android:name="feature.required"\n'):
            with self.subTest(declaration=declaration):
                self.xml = 'E: manifest\n' + declaration
                apk = self.scan(path)['apks'][0]
                self.assertNotIn('split', apk)
                self.assertTrue(apk['metadata_complete'])
                self.assertTrue(apk['requires_splits'])

    def test_ambiguous_split_requirement_is_incomplete(self):
        path = self.apk()
        for declaration in (
                ' A: android:isSplitRequired=true\n A: android:isSplitRequired=false\n',
                ' A: android:isSplitRequired=@0x7f000001\n',
                ' A: android:requiredSplitTypes=@0x7f000002\n',
                ' A: android:requiredSplitTypes="abi"\n A: android:requiredSplitTypes=""\n',
                ' E: uses-split\n'):
            with self.subTest(declaration=declaration):
                self.xml = 'E: manifest\n' + declaration
                apk = self.scan(path)['apks'][0]
                self.assertFalse(apk['metadata_complete'])
                self.assertTrue(apk['requires_splits'])
        self.xml = 'E: manifest\n A: android:isSplitRequired=false\n A: android:requiredSplitTypes=""\n'
        apk = self.scan(path)['apks'][0]
        self.assertTrue(apk['metadata_complete'])
        self.assertFalse(apk['requires_splits'])

    def test_split_version_and_signer_conflicts(self):
        path = self.apk()
        base = self.scan(path)['apks'][0]
        split = dict(base, split='config.en', version_code=43, signers_sha256=['cd' * 32])
        messages = []
        intake._check_apk_sets([base, split], messages)
        self.assertTrue(any('versions' in w for w in messages))
        self.assertTrue(any('signers' in w for w in messages))

    def test_ota_metadata_without_tools_or_payload_extraction(self):
        with patch.object(intake, '_run', side_effect=AssertionError('must not execute tools')):
            result = intake.scan(self.ota())
        self.assertEqual(result['kind'], 'ota')
        self.assertEqual((result['device'], result['sdk'], result['incremental']), ('example', 37, 'OS4.6'))
        self.assertEqual(result['apks'], [])
        self.assertEqual(result['abis'], [])
        self.assertTrue(any('not inspected' in w for w in result['warnings']))

    def test_ota_ambiguous_and_invalid_properties(self):
        result = self.scan(self.ota(OTA + 'pre-device=another\npost-sdk-level=preview\n'))
        self.assertIsNone(result['device'])
        self.assertIsNone(result['sdk'])
        self.assertTrue(any('duplicate property' in w for w in result['warnings']))
        self.assertTrue(any('conflicting' in w for w in result['warnings']))

    def test_zip_malicious_names_and_duplicate_metadata(self):
        for name in ('../escape', '/absolute', 'C:/absolute', 'a\\b', 'a/./b', 'a//b', intake.OTA_METADATA):
            with self.subTest(name=name):
                result = self.scan(self.ota(extra=[(name, b'bad')]))
                self.assertIsNone(result['device'])
                self.assertTrue(any('OTA metadata unavailable' in w for w in result['warnings']))

    def test_zip_symlink_rejected(self):
        path = self.ota()
        with zipfile.ZipFile(path, 'a') as archive:
            link = zipfile.ZipInfo('link')
            link.create_system = 3
            link.external_attr = 0o120777 << 16
            archive.writestr(link, '../outside')
        self.assertIsNone(self.scan(path)['device'])

    def test_zip_directory_and_metadata_limits(self):
        path = self.ota('x' * (intake.MAX_METADATA + 1))
        self.assertTrue(any('exceeds limit' in w for w in self.scan(path)['warnings']))
        path = self.ota()
        raw = bytearray(path.read_bytes())
        end = raw.rfind(b'PK\x05\x06')
        struct.pack_into('<L', raw, end + 12, 17 * intake.MAX_METADATA)
        path.write_bytes(raw)
        self.assertTrue(any('exceeds limit' in w for w in self.scan(path)['warnings']))

    def test_extracted_firmware_properties_and_partition_paths(self):
        path = self.apk('system/product/priv-app/X/X.apk')
        props = self.root / 'system/build.prop'
        props.write_text('ro.product.device=example\nro.build.version.sdk=37\nro.build.version.incremental=OS4.6\nro.product.cpu.abilist=arm64-v8a,armeabi-v7a\n')
        result = self.scan(self.root)
        self.assertEqual(result['kind'], 'firmware-directory')
        self.assertEqual(result['device'], 'example')
        self.assertEqual(result['sdk'], 37)
        self.assertEqual(result['abis'], ['arm64-v8a', 'armeabi-v7a'])
        self.assertEqual(result['apks'][0]['partition_path'], 'product/priv-app/X/X.apk')
        self.assertEqual(result['apks'][0]['path'], str(path.resolve()))
        self.assertEqual(self.scan(self.root / 'system/product')['apks'][0]['partition_path'], 'product/priv-app/X/X.apk')

    def test_firmware_unknown_abi_is_not_inferred_from_apks(self):
        self.apk('product/app/X/X.apk')
        result = self.scan(self.root)
        self.assertEqual(result['kind'], 'firmware-directory')
        self.assertEqual(result['abis'], [])
        self.assertEqual(result['derived_abis'], ['arm64-v8a'])

    def test_partition_device_priority_and_unknown_canonical_sdk(self):
        for part, device, sdk in (('system', 'one', 36), ('product', 'two', 37)):
            directory = self.root / part
            directory.mkdir()
            (directory / 'build.prop').write_text(f'ro.product.{part}.device={device}\nro.{part}.build.version.sdk={sdk}\n')
        result = self.scan(self.root)
        self.assertEqual(result['device'], 'two')
        self.assertIsNone(result['sdk'])
        self.assertTrue(any('conflicting' in w for w in result['warnings']))

    def props(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_real_partition_shapes_resolve_canonical_identity_and_load_order(self):
        self.props('system/build.prop', 'ro.product.system.device=missi\n'
                   'ro.build.version.incremental=internal17\nro.build.version.sdk=37\n'
                   'ro.product.property_source_order=odm,vendor,product,system_ext,system\n'
                   'ro.system.product.cpu.abilist=arm64-v8a\n')
        self.props('system_ext/etc/build.prop', 'ro.product.system_ext.device=missi\n'
                   'ro.system_ext.build.version.incremental=internal17\n'
                   'ro.system_ext.build.fingerprint=Brand/missi/missi:17/ID/internal17:user/release-keys\n')
        self.props('product/etc/build.prop', 'ro.product.product.device=miproduct\n'
                   'ro.build.version.incremental=OS4.6\nro.build.version.sdk=37\n'
                   'ro.product.build.fingerprint=Brand/product/miproduct:17/ID/OS4.6:user/release-keys\n')
        self.props('odm/etc/build.prop', 'ro.product.odm.device=example\n'
                   'ro.build.fingerprint=Brand/product/example:17/ID/OS4.6:user/release-keys\n')
        self.props('vendor/build.prop', 'ro.product.vendor.device=mivendor\n'
                   'ro.vendor.build.version.sdk=35\nro.vendor.product.cpu.abilist=arm64-v8a\n')
        result = self.scan(self.root)
        self.assertEqual((result['device'], result['sdk'], result['incremental']), ('example', 37, 'OS4.6'))
        self.assertEqual(result['abis'], ['arm64-v8a'])
        self.assertEqual(result['fingerprint'], 'Brand/product/example:17/ID/OS4.6:user/release-keys')
        self.assertFalse(any('conflicting' in w for w in result['warnings']))

    def test_explicit_device_precedes_partitions_but_canonical_conflicts_stay_unknown(self):
        self.props('product/etc/build.prop', 'ro.product.device=example\nro.product.product.device=generic\n')
        self.props('vendor/build.prop', 'ro.product.vendor.device=vendor\n')
        self.assertEqual(self.scan(self.root)['device'], 'example')
        self.props('product/etc/build.prop', 'ro.product.device=example\nro.product.device=other\n'
                   'ro.build.fingerprint=Brand/product/example:17/ID/OS4.6:user/release-keys\n')
        self.assertIsNone(self.scan(self.root)['device'])
        self.props('product/etc/build.prop', 'ro.product.device=example\n'
                   'ro.build.fingerprint=Brand/product/other:17/ID/OS4.6:user/release-keys\n')
        self.assertIsNone(self.scan(self.root)['device'])
        self.props('product/etc/build.prop', 'ro.product.device=example\n'
                   'ro.build.fingerprint=Brand/product/example:17/ID/OS4.6:user/release-keys\n'
                   'ro.build.fingerprint=Brand/product/other:17/ID/OS4.6:user/release-keys\n')
        result = self.scan(self.root)
        self.assertIsNone(result['device'])
        self.assertIsNone(result['fingerprint'])

    def test_configured_device_order_and_ambiguous_order(self):
        self.props('build.prop', 'ro.product.property_source_order=system,product\n'
                   'ro.product.system.device=example\nro.product.product.device=generic\n')
        self.assertEqual(self.scan(self.root)['device'], 'example')
        for order in ('system,invalid', 'system,product\nro.product.property_source_order=product,system'):
            self.props('build.prop', 'ro.product.property_source_order=' + order + '\n'
                       'ro.product.system.device=example\nro.product.product.device=generic\n')
            self.assertIsNone(self.scan(self.root)['device'])

    def test_conflicting_canonical_version_is_not_hidden_by_load_priority(self):
        self.props('system/build.prop', 'ro.build.version.incremental=one\nro.build.version.incremental=two\n')
        self.props('product/etc/build.prop', 'ro.build.version.incremental=final\n')
        self.assertIsNone(self.scan(self.root)['incremental'])
        self.props('system/build.prop', 'ro.build.version.incremental=one\n')
        self.props('unrecognized/build.prop', 'ro.build.version.incremental=unknown\n')
        self.assertIsNone(self.scan(self.root)['incremental'])

    def test_canonical_abi_overrides_partition_abi_and_conflicts_stay_unknown(self):
        self.props('build.prop', 'ro.product.cpu.abilist=arm64-v8a\n'
                   'ro.vendor.product.cpu.abilist=armeabi-v7a\n')
        self.assertEqual(self.scan(self.root)['abis'], ['arm64-v8a'])
        self.props('build.prop', 'ro.product.cpu.abilist=arm64-v8a\nro.product.cpu.abilist=armeabi-v7a\n'
                   'ro.vendor.product.cpu.abilist=arm64-v8a\n')
        self.assertEqual(self.scan(self.root)['abis'], [])

    def test_empty_property_does_not_erase_conflicting_evidence(self):
        (self.root / 'build.prop').write_text('ro.product.device=example\nro.product.device=\n')
        self.assertIsNone(self.scan(self.root)['device'])

    def test_properties_read_size_and_count_bounded(self):
        (self.root / 'build.prop').write_bytes(b'a' * 100)
        with patch.object(intake, 'MAX_METADATA', 10):
            self.assertTrue(any('build.prop exceeds' in w for w in self.scan(self.root)['warnings']))
        with patch.object(intake, 'MAX_PROP_FILES', 0):
            with self.assertRaisesRegex(ValueError, 'count limit'):
                self.scan(self.root)

    def test_private_paths_links_and_duplicates(self):
        source = self.apk('visible/original.apk')
        for excluded in ('private', 'data', 'user', 'testkeys'):
            self.apk(excluded + '/hidden.apk')
        (self.root / 'alias.apk').symlink_to(source)
        os.link(source, self.root / 'hardlink.apk')
        (self.root / 'private-alias.apk').symlink_to(self.root / 'private/hidden.apk')
        (self.root / 'loop').symlink_to(self.root)
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'escape').symlink_to(outside, target_is_directory=True)
            root_link = Path(outside) / 'source-link'
            root_link.symlink_to(self.root, target_is_directory=True)
            result = self.scan(root_link)
        self.assertEqual(len(result['apks']), 1)
        self.assertEqual(result['path'], str(self.root.resolve()))
        self.assertTrue(any('escaping symlink' in w for w in result['warnings']))
        self.assertTrue(any('duplicate file alias' in w for w in result['warnings']))

    def test_directory_entry_and_apk_count_limits(self):
        self.apk()
        with patch.object(intake, 'MAX_ENTRIES', 0):
            with self.assertRaisesRegex(ValueError, 'entry limit'):
                self.scan(self.root)
        with patch.object(intake, 'MAX_APKS', 0):
            with self.assertRaisesRegex(ValueError, 'APK count limit'):
                self.scan(self.root)

    def test_tool_discovery_from_sdk_env_and_path(self):
        tool = self.root / 'build-tools/36.0.0/aapt2'
        tool.parent.mkdir(parents=True)
        tool.write_text('not executed')
        tool.chmod(0o755)
        with patch.dict(os.environ, {'ANDROID_SDK_ROOT': str(self.root)}):
            self.assertEqual(intake._tool('aapt2'), str(tool))
        with patch.object(intake.shutil, 'which', return_value='/trusted/tool'):
            self.assertEqual(intake._tool('apksigner', 'explicit'), '/trusted/tool')

    def test_subprocess_output_exit_and_timeout_limits(self):
        with patch.object(intake, 'MAX_OUTPUT', 100):
            with self.assertRaisesRegex(ValueError, 'output exceeds'):
                intake._run([sys.executable, '-c', 'print("x" * 1000)'])
        with self.assertRaisesRegex(ValueError, 'exited 2'):
            intake._run([sys.executable, '-c', 'raise SystemExit(2)'])
        with self.assertRaisesRegex(ValueError, 'timed out'):
            intake._run([sys.executable, '-c', 'import time; time.sleep(2)'], timeout=0.05)

    def full_payload(self, image_bytes=100, other_partitions=()):
        def varint(value):
            data = bytearray()
            while value > 127:
                data.append((value & 127) | 128)
                value >>= 7
            return bytes(data) + bytes([value])

        def blob(tag, value):
            return varint((tag << 3) | 2) + varint(len(value)) + value

        partition = blob(1, b'product') + blob(7, b'\x08' + varint(image_bytes))
        manifest = blob(13, partition)
        for name, size in other_partitions:
            partition = blob(1, name.encode('ascii'))
            if size is not None:
                partition += blob(7, b'\x08' + varint(size))
            manifest += blob(13, partition)
        return struct.pack('>4sQQI', b'CrAU', 2, len(manifest), 0) + manifest

    def test_payload_hyphenated_and_empty_unselected_partitions(self):
        source = self.root / 'special.zip'
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('payload.bin', self.full_payload(other_partitions=(('vm-bootsys', 100), ('deleted', 0), ('absent_info', None))))
        with intake._zip(source) as archive:
            self.assertEqual(intake._payload_sizes(archive, ('product',)), 100)
            with self.assertRaisesRegex(ValueError, 'positive image size'):
                intake._payload_sizes(archive, ('deleted',))
            with self.assertRaisesRegex(ValueError, 'positive image size'):
                intake._payload_sizes(archive, ('absent_info',))

    def full_ota(self, image_bytes=100):
        source = self.root / 'full.zip'
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('payload.bin', self.full_payload(image_bytes))
        return source

    def test_extract_stages_payload_on_output_disk_and_cleans_up_failure(self):
        source = self.full_ota()
        output = self.root / 'extracted'
        calls = []

        def extract(args, **kwargs):
            calls.append(args)
            if args[0] == '/tools/payload-dumper-go':
                self.assertEqual(Path(args[-1]).name, 'payload.bin')
                self.assertEqual(Path(args[-1]).parent.parent, output.parent)
                self.assertEqual(Path(args[-1]).read_bytes(), self.full_payload())
                (Path(args[4]) / 'product.img').write_bytes(b'erofs')
            else:
                raise ValueError('unsupported incremental or non-EROFS image')

        with patch.object(intake, '_tool', side_effect=lambda name, explicit=None: '/tools/' + name), patch.object(intake, '_run', side_effect=extract), patch.object(intake.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 10 ** 12})()):
            with self.assertRaisesRegex(ValueError, 'unsupported incremental'):
                intake.extract_apks(source, output, partitions=('product',))
        self.assertEqual(calls[0][1:3], ['-p', 'product'])
        self.assertNotEqual(calls[0][-1], str(source))
        self.assertIn('--no-preserve', calls[1])
        self.assertFalse(output.exists())
        self.assertEqual(list(self.root.glob('.intake-*')), [])

    def test_extract_low_space_rejects_before_native_tools_or_staging(self):
        source = self.full_ota(image_bytes=3 * 1024 ** 3)
        with patch.object(intake.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 9 * 1024 ** 3})()), patch.object(intake, '_run') as native:
            with self.assertRaisesRegex(ValueError, 'insufficient extraction space'):
                intake.extract_apks(source, self.root / 'output', partitions=('product',))
            native.assert_not_called()
        self.assertFalse((self.root / 'output').exists())
        self.assertEqual(list(self.root.glob('.intake-*')), [])

    def test_extract_incremental_rejected_before_native_tools(self):
        source = self.root / 'incremental.zip'
        payload = self.full_payload()
        manifest = payload[24:] + b'\x60\x01'
        with zipfile.ZipFile(source, 'w') as archive:
            archive.writestr('payload.bin', struct.pack('>4sQQI', b'CrAU', 2, len(manifest), 0) + manifest)
        with patch.object(intake, '_run') as native:
            with self.assertRaisesRegex(ValueError, 'incremental OTA'):
                intake.extract_apks(source, self.root / 'output', partitions=('product',))
            native.assert_not_called()
        self.assertFalse((self.root / 'output').exists())

    def test_extract_success_returns_inventory_of_published_tree(self):
        source = self.full_ota()
        output = self.root / 'output'

        def extract(args, **kwargs):
            if args[0] == '/tools/payload-dumper-go':
                (Path(args[4]) / 'product.img').write_bytes(b'erofs')
            elif args[0] == '/tools/fsck.erofs':
                target = Path(args[1].split('=', 1)[1])
                target.mkdir()
                (target / 'build.prop').write_text('ro.product.device=example\nro.build.version.sdk=37\n')
            else:
                return self.run_tool(args, **kwargs)

        with patch.object(intake, '_tool', side_effect=lambda name, explicit=None: '/tools/' + name), patch.object(intake, '_run', side_effect=extract), patch.object(intake.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 10 ** 12})()):
            result = intake.extract_apks(source, output, partitions=('product',))
        self.assertTrue(output.is_dir())
        self.assertEqual((result['kind'], result['sdk'], result['device']), ('firmware-directory', 37, 'example'))
        self.assertEqual(result['path'], str(output))
        self.assertEqual(list(self.root.glob('.intake-*')), [])

    def test_extract_validates_partition_names_and_refuses_existing_output(self):
        source = self.ota()
        with self.assertRaisesRegex(ValueError, 'partition names'):
            intake.extract_apks(source, self.root / 'out', partitions=('../system',))
        with self.assertRaises(FileExistsError):
            intake.extract_apks(source, self.root)


if __name__ == '__main__':
    unittest.main()
