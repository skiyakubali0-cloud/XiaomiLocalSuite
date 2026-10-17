import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import recipe_tools


class RecipeToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'recipes').mkdir()
        self.local = self.root / 'local'
        self.local.mkdir()
        raw = b'fixture tool archive'
        (self.local / 'tool.jar').write_bytes(raw)
        self.item = dict(file='tool.jar', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                         url='https://repo.maven.apache.org/example/tool.jar')
        self.lock()

    def lock(self):
        (self.root / 'recipes/generated.json').write_text(json.dumps({'tools': [self.item]}))

    def test_requires_explicit_source_and_offline_preparation_never_downloads(self):
        with patch.object(recipe_tools.urllib.request, 'urlopen', side_effect=AssertionError('no network')):
            with self.assertRaises(ValueError):
                recipe_tools.prepare(root=self.root)
            self.assertEqual(recipe_tools.prepare(self.local, root=self.root), 1)
            self.assertEqual(recipe_tools.prepare(self.local, root=self.root), 1)
        self.assertEqual((self.root / 'build/recipe-tools/tool.jar').read_bytes(), (self.local / 'tool.jar').read_bytes())

    def test_bad_input_bad_cache_and_symlink_do_not_get_replaced(self):
        (self.local / 'tool.jar').write_bytes(b'wrong')
        with self.assertRaises(ValueError):
            recipe_tools.prepare(self.local, root=self.root)
        self.assertFalse((self.root / 'build').exists())
        cache = self.root / 'build/recipe-tools/tool.jar'
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b'preserve')
        self.item.update(bytes=5, sha256=hashlib.sha256(b'wrong').hexdigest()); self.lock()
        with self.assertRaises(ValueError):
            recipe_tools.prepare(self.local, root=self.root)
        self.assertEqual(cache.read_bytes(), b'preserve')
        cache.unlink(); cache.symlink_to(self.local / 'tool.jar')
        with self.assertRaises(ValueError):
            recipe_tools.prepare(self.local, root=self.root)
