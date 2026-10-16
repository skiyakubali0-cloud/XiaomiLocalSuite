import unittest
from check_public_tree import check
class PublicTreeTests(unittest.TestCase):
 def test_detects_credentials_without_echoing_value(self):
  for value in [b'ghp_'+b'a'*30,b'github_pat_'+b'b'*40,b'-----BEGIN RSA '+b'PRIVATE KEY-----']:
   result=check('source.py',value);self.assertTrue(result);self.assertNotIn(value.decode(),str(result))
 def test_rejects_private_file_binary_and_symlink_payload_names(self):
  for n,raw in [('key.jks',b'test'),('private/preferences.xml',b'<prefs/>'),('payload.apk',b'PK\0test'),('._file',b'abc')]:self.assertTrue(check(n,raw))
 def test_removes_personal_paths_and_email_only(self):
  self.assertTrue(check('doc.md',('/'+'Users'+'/someone/project').encode()));self.assertTrue(check('doc.md',b'person'+b'@'+b'personal.invalid'))
  self.assertEqual(check('LICENSE',b'https://www.apache.org/ dev@example.com 2026 XiaomiLocalSuite contributors'),[])
 def test_keeps_software_protocol_hashes_and_android_paths(self):
  self.assertEqual(check('module.sh',b'com.mipay.wallet /data/adb/modules OS4.0.0.6.XOAEUXM '+b'a'*64),[])
if __name__=='__main__':unittest.main()
