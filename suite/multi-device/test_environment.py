from unittest import TestCase
from unittest.mock import patch

import environment


class EnvironmentTests(TestCase):
    def test_missing_sdk_is_not_ready_and_does_not_download(self):
        with patch.object(environment.intake, '_tool', return_value=None), \
             patch.object(environment.shutil, 'which', return_value=None):
            result = environment.inspect()
        self.assertFalse(result['ready'])
        self.assertIn('aapt2', environment.format_report(result))
        self.assertIn('不会自动下载', environment.format_report(result))

    def test_optional_extractors_not_required_for_apk_flow(self):
        tools = {'aapt2': '/tools/aapt2', 'apksigner': '/tools/apksigner'}
        with patch.object(environment.intake, '_tool', side_effect=tools.get), \
             patch.object(environment.shutil, 'which', side_effect=lambda name: '/tools/java' if name == 'java' else None), \
             patch.object(environment.intake, '_run', side_effect=['openjdk version "17.0.1"', 'aapt2 version', '0.9']), \
             patch.object(environment.sys, 'platform', 'linux'):
            result = environment.inspect()
        self.assertTrue(result['ready'])
        self.assertFalse(any(c['ready'] for c in result['checks'][-2:]))

    def test_broken_signer_or_old_java_is_not_ready(self):
        with patch.object(environment.intake, '_tool', return_value='/tools/tool'), \
             patch.object(environment.shutil, 'which', return_value='/tools/java'), \
             patch.object(environment.intake, '_run', side_effect=['java version "1.8.0"', 'v1', ValueError('tool failed')]):
            result = environment.inspect()
        self.assertFalse(result['ready'])
        self.assertFalse(next(c for c in result['checks'] if c['name'] == 'Java')['ready'])
        self.assertFalse(next(c for c in result['checks'] if c['name'] == 'apksigner')['ready'])
