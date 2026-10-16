"""Exercise the fixed migration shell with real fixture hashes and mocked Android PM."""
from pathlib import Path
import hashlib,json,os,subprocess,tempfile,unittest
P=Path(__file__).resolve().parents[1]
MOCK='''#!/usr/bin/env python3
import sys,os,json,hashlib,pathlib
r=pathlib.Path(os.environ['FIXTURE']);s=json.loads((r/'pm.json').read_text());a=sys.argv[1:];cmd=pathlib.Path(sys.argv[0]).name
if cmd=='id':print('0')
elif cmd=='getprop':print({'ro.product.device':'xuanyuan','ro.build.version.sdk':'37','ro.build.version.incremental':'OS4.0.0.6.XOAEUXM'}.get(a[0],''))
elif cmd=='am':print('0')
elif cmd=='dumpsys':print('package state reference')
elif cmd=='pm':
 if a==['list','users']:print('UserInfo{0:Owner:13} running')
 elif a[:3]==['path','--user','0']:
  item=s.get(a[3]);print('package:'+item['path'] if item and item['installed'] else '',end='\\n')
 elif a[:4]==['uninstall','-k','--user','0']:
  with (r/'calls').open('a') as f:f.write(json.dumps(a)+'\\n')
  if os.environ.get('FAIL_REMOVE')==a[4]:sys.exit(1)
  s[a[4]]['installed']=False;(r/'pm.json').write_text(json.dumps(s));print('Success')
 elif a[:4]==['install','-r','--user','0']:
  data=sys.stdin.buffer.read();h=hashlib.sha256(data).hexdigest();matches=[k for k,v in s.items() if v['sha']==h]
  assert len(matches)==1 and a[4:5]==['-S'] and len(data)==int(a[5])
  s[matches[0]]['installed']=True;(r/'pm.json').write_text(json.dumps(s))
  with (r/'calls').open('a') as f:f.write(json.dumps(a)+'\\n')
  print('Success')
 else:raise SystemExit('UNEXPECTED ANDROID COMMAND '+repr(a))
else:raise SystemExit('UNKNOWN MOCK')
'''
class Migration(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='migration-');self.r=Path(self.temp.name);bin=self.r/'bin';bin.mkdir();self.bin=bin
  self.known=json.loads((P/'legacy-hooks.json').read_text());self.state={};self.data={}
  for pkg in [*self.known,'local.xuanyuan.mipushcompat']:
   apk=self.r/(pkg+'.apk');apk.write_bytes(('fixture APK '+pkg).encode());h=hashlib.sha256(apk.read_bytes()).hexdigest();self.state[pkg]={'path':str(apk),'sha':h,'installed':True}
   data=self.r/(pkg+'.userdata');data.write_bytes(('preserved private data '+pkg).encode());self.data[data]=data.read_bytes()
  (self.r/'pm.json').write_text(json.dumps(self.state));(self.r/'boot').write_text('boot-a\n')
  s=(P/'migrate-legacy.sh.in').read_text().replace('/data/adb/xuanyuan-unified-state',str(self.r/'state')).replace('/proc/sys/kernel/random/boot_id',str(self.r/'boot')).replace('/data/adb/lspd/config',str(self.r/'lsp')).replace('/data/adb/modules_update',str(self.r/'next')).replace('/data/adb/modules',str(self.r/'modules'))
  for pkg,h in self.known.items():s=s.replace(h,self.state[pkg]['sha'])
  s=s.replace('@UNIFIED_SHA@',self.state['local.xuanyuan.mipushcompat']['sha']);(self.r/'migration.sh').write_text(s)
  for cmd in ['id','getprop','am','pm','dumpsys']:
   q=bin/cmd;q.write_text(MOCK);q.chmod(0o755)
  # Android and BSD stat differ; only the fixture's file-size use is translated.
  q=bin/'stat';q.write_text('#!/bin/sh\n[ "$1" = -c ] && [ "$2" = %s ] || exit 90\n/usr/bin/stat -f %z "$3"\n');q.chmod(0o755)
  self.env={**os.environ,'PATH':str(bin)+os.pathsep+os.environ['PATH'],'FIXTURE':str(self.r)}
 def tearDown(self):
  for p,v in self.data.items():self.assertEqual(p.read_bytes(),v)
  self.temp.cleanup()
 def run_action(self,a,**env):return subprocess.run(['sh',str(self.r/'migration.sh'),a],capture_output=True,text=True,env={**self.env,**env})
 def calls(self):return [json.loads(x) for x in (self.r/'calls').read_text().splitlines()] if (self.r/'calls').exists() else []
 def test_roundtrip_keeps_data_and_excludes_wallet_xmsf(self):
  self.assertEqual(self.run_action('remove').returncode,0);calls=self.calls();self.assertEqual(len(calls),5)
  self.assertEqual({x[-1] for x in calls},set(self.known));self.assertTrue(all(x[:4]==['uninstall','-k','--user','0'] for x in calls))
  self.assertIn('REBOOT_REQUIRED',self.run_action('status').stdout);(self.r/'boot').write_text('boot-b\n');self.assertIn('MIGRATION_READY',self.run_action('status').stdout)
  self.assertEqual(self.run_action('restore').returncode,0);s=json.loads((self.r/'pm.json').read_text());self.assertTrue(all(x['installed'] for x in s.values()))
  self.assertTrue(all('com.mipay.wallet' not in x and 'com.xiaomi.xmsf' not in x for x in self.calls()))
 def test_r2_xiaoai_requires_reviewed_replacement_before_removal(self):
  live=self.r/'modules/xuanyuan-os4-xiaoai';live.mkdir(parents=True);(live/'module.prop').write_text('versionCode=2026101502\n')
  result=self.run_action('remove');self.assertNotEqual(result.returncode,0);self.assertEqual(self.calls(),[])
  (live/'module.prop').write_text('versionCode=2026101503\n');self.assertNotEqual(self.run_action('remove').returncode,0);self.assertEqual(self.calls(),[])
  nxt=self.r/'next/xuanyuan-os4-xiaoai';nxt.mkdir(parents=True);(nxt/'module.prop').write_text('versionCode=2026101504\n')
  self.assertEqual(self.run_action('remove').returncode,0)
 def test_unknown_old_hash_blocks_all_removal(self):
  Path(self.state[list(self.known)[-1]]['path']).write_bytes(b'unknown update');self.assertNotEqual(self.run_action('remove').returncode,0);self.assertEqual(self.calls(),[])
 def test_unified_hash_mismatch_blocks(self):
  Path(self.state['local.xuanyuan.mipushcompat']['path']).write_bytes(b'unknown unified');self.assertNotEqual(self.run_action('remove').returncode,0);self.assertEqual(self.calls(),[])
 def test_unknown_backup_blocks_all_restore(self):
  self.assertEqual(self.run_action('remove').returncode,0);(self.r/'calls').unlink();(self.r/'state/apks'/(next(iter(self.known))+'.apk')).write_bytes(b'broken');self.assertNotEqual(self.run_action('restore').returncode,0);self.assertEqual(self.calls(),[])
 def test_partial_failure_keeps_reboot_marker_and_backups(self):
  result=self.run_action('remove',FAIL_REMOVE=list(self.known)[1]);self.assertNotEqual(result.returncode,0)
  self.assertTrue((self.r/'state/migration-boot').is_file());self.assertEqual(len([p for p in (self.r/'state/apks').glob('*.apk') if not p.name.startswith('._')]),5);self.assertFalse((self.r/'state/lock').exists());self.assertIn('REBOOT_REQUIRED',self.run_action('status').stdout)
 def test_lock_and_unknown_action_do_not_modify_apps(self):
  (self.r/'state/lock').mkdir(parents=True);self.assertNotEqual(self.run_action('remove').returncode,0);self.assertNotEqual(self.run_action('evil').returncode,0);self.assertEqual(self.calls(),[])
 def test_old_root_service_blocks_before_any_uninstall(self):
  module=self.r/'modules/xuanyuan-os4-phone';module.mkdir(parents=True);(module/'module.prop').write_text('versionCode=2026101208\n')
  self.assertNotEqual(self.run_action('remove').returncode,0);self.assertEqual(self.calls(),[])
 def test_staged_modern_root_allows_migration(self):
  module=self.r/'modules/xuanyuan-os4-phone';module.mkdir(parents=True);(module/'module.prop').write_text('versionCode=2026101208\n')
  next=self.r/'next/xuanyuan-os4-phone';next.mkdir(parents=True);(next/'module.prop').write_text('versionCode=2026101502\n')
  self.assertEqual(self.run_action('remove').returncode,0);self.assertEqual(len(self.calls()),5)
 def test_no_legacy_installed_is_safe_noop(self):
  for p in self.known:self.state[p]['installed']=False
  (self.r/'pm.json').write_text(json.dumps(self.state));self.assertEqual(self.run_action('remove').returncode,0);self.assertEqual(self.calls(),[]);self.assertFalse((self.r/'state/migration-boot').exists())
if __name__=='__main__':unittest.main(verbosity=2)
