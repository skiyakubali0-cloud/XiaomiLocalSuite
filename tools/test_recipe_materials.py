"""Policy/packing fixtures only; no real OEM material or signing key is distributed."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import recipe_materials as r


class RawRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        shutil.copytree(r.ROOT, self.source, ignore=shutil.ignore_patterns(
            '.git', 'build', 'deps', '__pycache__', '._*', '.test-work', 'releases'))
        self.target, self.inputs = self.root / 'target', self.root / 'inputs'
        (self.target / 'system').mkdir(parents=True)
        (self.target / 'system/build.prop').write_text('ro.product.device=xuanyuan\n'
            'ro.build.version.sdk=37\nro.build.version.incremental=OS4.0.0.6.XOAEUXM\nro.product.cpu.abilist=arm64-v8a\n')
        self.inputs.mkdir()
        self.apk = self.inputs / 'arbitrary filename with spaces.apk'
        self.library = b'native fixture bytes'
        with zipfile.ZipFile(self.apk, 'w') as z:
            z.writestr('lib/arm64-v8a/libfixture.so', self.library)
            z.writestr('res/Case.webp', b'resource one')
            z.writestr('res/case.webp', b'resource two')
        self.plugin = self.root / 'self-signed-fixture.apk'
        project = self.source / 'suite/unified-api102'
        with zipfile.ZipFile(self.plugin, 'w') as z:
            for path in (project / 'META-INF/xposed').iterdir():
                z.write(path, path.relative_to(project).as_posix())
        inputs = [project / name for name in ('AndroidManifest.xml', 'build_apk.py', 'fetch_dependencies.py', 'deps.lock.json')]
        inputs += list((project / 'src').rglob('*.java')) + list((project / 'META-INF/xposed').iterdir())
        self.evidence = self.plugin.with_suffix('.build-evidence.json')
        self.evidence.write_text(json.dumps(dict(apk_sha256=r.archive_tools.digest(self.plugin),
            sources={p.relative_to(project).as_posix(): r.archive_tools.digest(p) for p in inputs},
            dependencies={d['file']: d['sha256'] for d in json.loads((project / 'deps.lock.json').read_text())})))
        self.items = [self.item('market', 'system/product/app/Market/Market.apk', self.apk.read_bytes()),
                      self.item('market', 'system/product/app/Market/lib/arm64/libfixture.so', self.library)]
        original = json.loads((self.source / 'materials.lock.json').read_text())
        former = next(x for x in original['artifacts'] if x['path'] == 'payload/unified.apk')
        self.lock = dict(schema=1, target=dict(device='xuanyuan', rom='OS4.0.0.6.XOAEUXM', sdk=37),
            reference_suite=dict(sha256='a' * 64), original_unified_sha256=original['original_unified_sha256'],
            artifacts=self.items + [former,
                self.item('parent', 'payload/calendar.apk', b'calendar'),
                self.item('parent', 'payload/calendar-global.apk', b'global calendar')])
        self.write_lock()
        self.generator = SimpleNamespace(INPUTS={}, generate=lambda item, lookup: None)
        self.kw = dict(source=self.source, generator=self.generator, apk_checker=lambda path: None)

    def item(self, component, name, raw):
        return dict(component=component, path=name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))

    def write_lock(self):
        (self.source / 'materials.lock.json').write_text(json.dumps(self.lock))

    def check(self, ids=('market',)):
        return r.check(self.target, [self.inputs], list(ids), self.plugin, **self.kw)

    def test_raw_apk_and_embedded_library_resolve_without_reference_zip(self):
        with patch.object(r.archive_tools, 'build_suite', side_effect=AssertionError('no private reference')):
            report = self.check()
        self.assertEqual(report['state'], 'reviewed-raw-materials')
        self.assertFalse(report['private_reference_required'])
        self.assertFalse(report['wallet_reset'])
        self.assertEqual(report['missing'], [])
        self.assertEqual(r.selection(['phone']), ['market', 'phone'])
        self.assertEqual(r.selection(['xiaoai']), ['assistant', 'xiaoai'])

    def test_missing_selected_material_lists_exact_hash_and_unselected_calendar_not_required(self):
        missing = self.item('market', 'system/product/lib64/missing.so', b'unavailable')
        self.lock['artifacts'].append(missing); self.write_lock()
        result = self.check()
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(result['missing'][0]['sha256'], missing['sha256'])
        self.assertFalse(any(x['component'] == 'parent' for x in result['missing']))

    def test_wrong_rom_or_source_device_and_unknown_selection_rejected(self):
        with self.assertRaises(ValueError):
            r.selection(['unknown'])
        p = self.target / 'system/build.prop'
        p.write_text(p.read_text().replace('OS4.0.0.6.XOAEUXM', 'OS4.OTHER'))
        with self.assertRaises(ValueError):
            self.check()

    def test_plugin_missing_record_stale_source_and_bad_apk_hash_are_blocked(self):
        original = self.evidence.read_bytes()
        self.evidence.unlink(); self.assertEqual(self.check()['state'], 'blocked')
        self.evidence.write_bytes(original)
        project = self.source / 'suite/unified-api102'
        (project / 'src/new.java').write_text('changed public source')
        self.assertEqual(self.check()['state'], 'blocked')
        (project / 'src/new.java').unlink()
        with zipfile.ZipFile(self.plugin, 'a') as z: z.writestr('changed.txt', 'changed APK')
        self.assertEqual(self.check()['state'], 'blocked')

    def test_material_replacement_and_unsafe_apk_members_rejected(self):
        index = r.MaterialIndex({hashlib.sha256(self.library).hexdigest(): len(self.library)})
        index.scan([self.inputs])
        self.apk.write_bytes(b'replaced')
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            index.lookup(hashlib.sha256(self.library).hexdigest())
        with zipfile.ZipFile(self.apk, 'w') as z: z.writestr('../escape.so', self.library)
        with self.assertRaises(ValueError):
            r.resolve(self.target, [self.inputs], ['market'], self.source, self.generator)

    def test_partial_suite_contains_only_selected_payload_and_preserves_checksums(self):
        output = self.root / 'selected.zip'
        result = r.build(self.target, [self.inputs], ['market'], self.plugin, output, **self.kw)
        self.assertEqual(result['selected'], ['market'])
        self.assertFalse(result['wallet_reset'])
        with zipfile.ZipFile(output) as z:
            self.assertIn('payload/market.zip', z.namelist())
            self.assertNotIn('payload/wallet.zip', z.namelist())
            self.assertNotIn('payload/xiaoai.zip', z.namelist())
            self.assertEqual(z.read('payload/unified.apk'), self.plugin.read_bytes())
            for line in z.read('checksums.sha256').decode().splitlines():
                sha, name = line.split('  ', 1)
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), sha)
        with self.assertRaises(ValueError):
            r.build(self.target, [self.inputs], ['market'], self.plugin, output, **self.kw)


if __name__ == '__main__':
    unittest.main()
