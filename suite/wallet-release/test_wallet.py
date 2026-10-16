"""Real shell migration/control tests; Android commands intercepted, no ADB."""
from pathlib import Path
import hashlib, importlib.util, json, os, subprocess, tempfile, unittest, zipfile
import build as w
spec=importlib.util.spec_from_file_location('pf',w.HERE.parent/'unified-bundle/test_preset.py');pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)

class PlanTests(unittest.TestCase):
 def setUp(self):
  c=self.c=pf.PresetTests();c.setUp();self.addCleanup(c.doCleanups)
  c.controller.write_text(w.controller(w.full.controller(c.controller.read_text().replace(str(c.root)+'/product/','/product/'))).replace('/product/',str(c.root)+'/product/').replace('W_MARK=/data/adb/','W_MARK='+str(c.root)+'/data/adb/'))
  c.preset.write_text(w.preset(w.full.preset(c.preset.read_text())))
  cat=(c.module/'catalog.sh').read_text().replace("CODE='2026101504'","CODE='"+w.CHILD_CODE+"'").replace("CODE='2026101101'; FILE='wallet.zip'","CODE='"+w.WALLET_CODE+"'; FILE='wallet.zip'")
  (c.module/'catalog.sh').write_text(cat)
  (c.module/'module.prop').write_text('id=xuanyuan-os4-suite\nversionCode='+w.PARENT_CODE+'\n')
  (c.module/'wallet.sh').write_text('echo "${TEST_MODE:-cn}"\n')
  packages=json.loads(c.env['TEST_PACKAGES']);packages.pop('com.mipay.wallet');c.packages(packages);c.rehash()
 def test_first_migration_plan_is_read_only_and_requires_consent(self):
  c=self.c;before=c.snapshot()
  p=c.run_preset(components='wallet',features='-',ids='wallet',state='install',batch='wallet',TEST_MODE='eea')
  self.assertTrue(p['wallet_pending']);self.assertEqual(before,c.snapshot());self.assertEqual(c.calls(),[])
  c.run_preset(action='apply',components='wallet',features='-',ids='wallet',state='blocked',TEST_MODE='eea')
  self.assertFalse((c.root/'launch').exists());self.assertEqual(c.calls(),[])
 def test_first_market_batch_does_not_prompt_for_wallet_migration_yet(self):
  c=self.c;p=c.run_preset(components='market,wallet',features='-',ids='market,wallet',state='install',batch='market',TEST_MODE='eea');self.assertFalse(p['wallet_pending']);self.assertEqual(c.calls(),[])
 def test_explicit_consent_queues_one_migration_job(self):
  c=self.c;c.run_preset(action='apply-wallet',components='wallet',features='-',ids='wallet',state='running',TEST_MODE='eea')
  args=json.loads((c.root/'launch-args').read_text());self.assertEqual(args[-2:],['install-wallet','wallet'])
 def test_cn_repeat_install_never_needs_reset_authorization(self):
  c=self.c;p=c.run_preset(action='apply',components='wallet',features='-',ids='wallet',state='running')
  self.assertFalse(p['wallet_pending']);self.assertEqual(json.loads((c.root/'launch-args').read_text())[-2:],['install','wallet'])
 def test_old_wallet_module_upgrades_and_unknown_is_blocked(self):
  c=self.c;c.component('wallet',code='2026101101');c.run_preset(components='wallet',features='-',ids='wallet',state='install',batch='wallet')
  c.component('wallet',code='999');c.run_preset(components='wallet',features='-',ids='wallet',state='blocked');self.assertEqual(c.calls(),[])
 def test_unselected_wallet_does_not_enter_job(self):
  c=self.c;c.run_preset(action='apply',components='weather',features='-',ids='weather',state='running');self.assertEqual(json.loads((c.root/'launch-args').read_text())[-2:],['install','weather'])
 def test_all_eleven_current_ready_and_nonwallet_dependencies_remain(self):
  c=self.c
  for key in w.IDS:
   if c.catalog(key,'KIND')=='module':c.component(key)
  packages=json.loads(c.env['TEST_PACKAGES']);packages['com.mipay.wallet']=pf.WALLET;c.packages(packages)
  c.run_preset(components=','.join(w.IDS),features=pf.FEATURES,ids=','.join(w.IDS),state='ready',batch='');self.assertEqual(c.calls(),[])
  c.run_preset(components='phone',features='-',ids='market,phone',state='ready',batch='')
 def test_wallet_restore_remains_blocked(self):
  c=self.c;c.component('wallet');r=subprocess.run(['/bin/sh',str(c.controller),'plan','restore','wallet'],env=c.env,capture_output=True);self.assertNotEqual(r.returncode,0);self.assertEqual(c.calls(),[])

 def test_worker_consumes_single_job_consent_and_cleans_marker_on_success_or_failure(self):
  c=self.c
  for fail in [False,True]:
   mode=dict(c.env,TEST_MODE='eea')
   c.run_preset(action='apply-wallet',components='wallet',features='-',ids='wallet',state='running',TEST_MODE='eea')
   job=Path((c.root/'data/adb/xuanyuan-os4-suite-state/latest').read_text().strip())
   if fail:
    mock=c.bin/'mock.py';text=mock.read_text();text=text.replace('elif name == "ksud":','elif name == "ksud" and args[:2] == ["module", "install"]:\n    record(args)\n    sys.exit(37)\nelif name == "ksud":');mock.write_text(text)
   result=subprocess.run(['/bin/sh',str(c.controller),'worker',str(job),'install-wallet','wallet'],env=mode,capture_output=True)
   self.assertEqual(result.returncode==0,not fail,(result.stdout,result.stderr))
   self.assertEqual((job/'state').read_text().strip(),'failed' if fail else 'succeeded')
   self.assertFalse((c.root/'data/adb/xuanyuan-os4-wallet-reset-authorized').exists())
   self.assertEqual((job/'started').read_text().strip(),'wallet')

MOCK=r'''
import os,sys,json,pathlib,hashlib,stat
r=pathlib.Path(os.environ['W_ROOT']);n=pathlib.Path(sys.argv[0]).name;a=sys.argv[1:]
def record():
 with (r/'calls').open('a') as f:f.write(json.dumps([n]+a)+'\n')
def installed():return (r/'installed').exists() or os.environ.get('W_PRESENT')=='1'
def walletpath():return str(r/'wallet.apk')
if n=='id':print('0')
elif n=='getprop':print({'ro.product.device':'xuanyuan','ro.build.version.sdk':'37','ro.build.version.incremental':os.environ.get('W_ROM','OS4.0.0.6.XOAEUXM'),'sys.boot_completed':'1'}.get(a[0],''))
elif n=='am':print('0')
elif n=='pm' and a==['list','users']:print('UserInfo{0:Owner:13} running')
elif n=='pm' and a[:3]==['path','--user','0']:
 if a[3]=='com.miui.tsmclient':print('package:'+os.environ.get('W_TSM_PATH',str(r/'product/app/MITSMClientGlobal/MITSMClientGlobal.apk')))
 elif a[3]=='com.mipay.wallet' and installed():
  print('package:'+walletpath())
  if os.environ.get('W_SPLIT'):print('package:'+str(r/'split.apk'))
elif n=='pm' and a[:3]==['list','packages','-U']:print('package:com.miui.tsmclient uid:'+os.environ.get('W_UID','1027'))
elif n=='pm' and a[:2]==['list','packages']:
 if a[-1]=='com.mipay.wallet' and installed() and ('-d' not in a or os.environ.get('W_DISABLED')):print('package:com.mipay.wallet')
elif n=='pm' and a==['clear','--user','0','com.miui.tsmclient']:
 record();print('Failure' if os.environ.get('W_CLEAR_FAIL') else 'Success')
elif n=='pm' and a[:1]==['install']:
 if os.environ.get('W_REQUIRE_PIPE') and not all(stat.S_ISFIFO(os.fstat(fd).st_mode) for fd in [1,2]):sys.exit(97)
 record();data=sys.stdin.buffer.read()
 if os.environ.get('W_INSTALL_FAIL'):print('Failure [fixture]');sys.exit(1)
 (r/'installed').touch();(r/'wallet.apk').write_bytes(data);print('Success')
elif n=='pm' and a==['enable','--user','0','com.mipay.wallet']:record();print('enabled')
elif n=='cmd':
 if os.environ.get('W_ROLE_FAIL'):sys.exit(1)
 if os.environ.get('W_REQUIRE_PIPE') and not stat.S_ISFIFO(os.fstat(1).st_mode):sys.exit(97)
 print('com.google.android.gms')
elif n=='settings':
 if os.environ.get('W_PAYMENT_FAIL'):sys.exit(1)
 if os.environ.get('W_REQUIRE_PIPE') and not stat.S_ISFIFO(os.fstat(1).st_mode):sys.exit(97)
 print('google/default')
elif n=='sha256sum':
 p=pathlib.Path(a[0])
 if not p.is_file():sys.exit(1)
 if 'MITSMClientGlobal.apk' in a[0]:h=os.environ.get('W_TSM_HASH','567e8f05e4b2cbc7c203ce5f10672756ea8af0542c3fc5aafaa3e677ebcaa671')
 elif p.read_bytes()==b'good-mipay':h='2aa4d85ae0e23764fdc96d0d5d4b314a5a90e915f0ed02a85093522e216e7d51'
 else:h=hashlib.sha256(p.read_bytes()).hexdigest()
 print(h+'  '+str(p))
else:print('unknown mock '+n+repr(a),file=sys.stderr);sys.exit(99)
'''
class LifecycleTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=Path(self.tmp.name);self.bin=self.r/'bin';self.bin.mkdir()
  self.env=dict(os.environ,W_ROOT=str(self.r),PATH=str(self.bin)+':'+os.environ['PATH'])
  mock=self.bin/'mock';mock.write_text('#!'+os.sys.executable+'\n'+MOCK);mock.chmod(0o755)
  for n in ['id','getprop','am','pm','cmd','settings','sha256sum']:(self.bin/n).symlink_to(mock)
  script=(w.HERE/'wallet.sh').read_text()
  for old in ['/data','/product','/proc/sys/kernel/random/boot_id']:script=script.replace(old,str(self.r)+old)
  self.script=self.r/'wallet.sh';self.script.write_text(script)
  for name,raw in [('product/app/MITSMClientGlobal/MITSMClientGlobal.apk',b'tsm'),('proc/sys/kernel/random/boot_id',b'boot-fixture\n'),('payload/Mipay.apk',b'good-mipay'),('wallet.apk',b'good-mipay'),('data/user/0/com.miui.tsmclient/existing',b'tsm-data'),('data/user/0/com.xiaomi.xmsf/files/mipush_region',b'global-sentinel')]:
   p=self.r/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
  self.mark=self.r/'data/adb/xuanyuan-os4-wallet-reset-authorized';self.mark.parent.mkdir(parents=True)
 def run_action(self,action,ok=True,**env):
  p=subprocess.run(['/bin/sh',str(self.script),action],env=dict(self.env,**env),text=True,capture_output=True)
  self.assertEqual(p.returncode==0,ok,(p.stdout,p.stderr));self.assertEqual((self.r/'data/user/0/com.xiaomi.xmsf/files/mipush_region').read_bytes(),b'global-sentinel');return p
 def calls(self):return [json.loads(x) for x in (self.r/'calls').read_text().splitlines()] if (self.r/'calls').exists() else []
 def consent(self,boot='boot-fixture'):
  self.mark.write_text('RESET_XIAOMI_TSM_ONLY:'+boot+':c31f66629723c3c60a8d0862e68f2777b0187afe7271bbec2df7468bd5d350bb\n')
 def eea(self):return dict(W_UID='10214',W_TSM_HASH='c31f66629723c3c60a8d0862e68f2777b0187afe7271bbec2df7468bd5d350bb')
 def test_cn_migrate_does_not_clear_even_with_marker(self):
  self.consent();self.run_action('migrate');self.assertEqual(self.calls(),[]);self.assertTrue(self.mark.exists())
 def test_eea_mode_does_not_write(self):
  p=self.run_action('mode',**self.eea());self.assertEqual(p.stdout.strip(),'eea');self.assertEqual(self.calls(),[]);self.assertFalse(self.mark.exists())
 def test_first_migration_requires_current_boot_consent(self):
  self.run_action('migrate',ok=False,**self.eea());self.consent('oldboot');self.run_action('migrate',ok=False,**self.eea());self.assertEqual(self.calls(),[])
 def test_first_migration_consumes_marker_backs_up_then_clears_tsm_only(self):
  self.consent();self.run_action('migrate',**self.eea());self.assertFalse(self.mark.exists());self.assertEqual(self.calls(),[['pm','clear','--user','0','com.miui.tsmclient']]);back=list((self.r/'data/adb/xuanyuan-os4-wallet-state').glob('first-migration-*/tsm-ce.tar'));self.assertEqual(len(back),1);self.assertEqual(back[0].stat().st_mode&0o777,0o600)
  self.run_action('migrate',ok=False,**self.eea());self.assertEqual(len(self.calls()),1)
 def test_failed_clear_is_not_success_and_consent_is_consumed(self):
  self.consent();self.run_action('migrate',ok=False,W_CLEAR_FAIL='1',**self.eea());self.assertFalse(self.mark.exists());self.assertFalse((self.r/'data/adb/xuanyuan-os4-wallet-state/phase').exists())
 def test_snapshot_failure_stops_before_consuming_or_clearing(self):
  for key in ['W_ROLE_FAIL','W_PAYMENT_FAIL']:
   self.consent();self.run_action('migrate',ok=False,**self.eea(),**{key:'1'});self.assertTrue(self.mark.exists());self.assertEqual(self.calls(),[])
 def test_snapshot_binder_receives_pipes_not_private_files(self):
  self.consent();self.run_action('migrate',W_REQUIRE_PIPE='1',**self.eea());self.assertFalse(self.mark.exists());self.assertEqual(len(self.calls()),1)
 def test_boot_service_gives_binder_pipe_fds_and_preserves_exit_status(self):
  service=self.r/'service.sh';service.write_text((w.HERE/'service-wallet.sh').read_text().replace('/data/',str(self.r)+'/data/'))
  p=subprocess.run(['/bin/sh',str(service)],env=dict(self.env,W_REQUIRE_PIPE='1'),capture_output=True)
  self.assertEqual(p.returncode,0,p.stderr);self.assertIn('READY:',(self.r/'data/adb/xuanyuan-os4-wallet-state/status.log').read_text());self.assertEqual((self.r/'data/adb/xuanyuan-os4-wallet-state/last-exit').read_text().strip(),'0')
  (self.r/'installed').unlink();p=subprocess.run(['/bin/sh',str(service)],env=dict(self.env,W_INSTALL_FAIL='1',W_REQUIRE_PIPE='1'),capture_output=True)
  self.assertNotEqual(p.returncode,0);self.assertNotEqual((self.r/'data/adb/xuanyuan-os4-wallet-state/last-exit').read_text().strip(),'0');self.assertNotIn('READY:',(self.r/'data/adb/xuanyuan-os4-wallet-state/status.log').read_text())
 def test_unknown_tsm_uid_rom_or_updated_path_reject_without_clear(self):
  for env in [dict(W_UID='10214'),dict(W_TSM_HASH='0'*64),dict(W_ROM='OS4.0.0.7.XOAEUXM'),dict(W_TSM_PATH=str(self.r/'other.apk'))]:self.run_action('migrate',ok=False,**env)
  self.assertEqual(self.calls(),[])
 def test_prepare_installs_exact_missing_wallet_by_stdin_and_ready(self):
  self.run_action('prepare');calls=self.calls();self.assertEqual(calls[0][:2],['pm','install']);self.assertEqual(calls[1],['pm','enable','--user','0','com.mipay.wallet']);self.run_action('status');self.assertEqual((self.r/'wallet.apk').read_bytes(),b'good-mipay')
 def test_repeat_prepare_does_not_reinstall_or_clear(self):
  self.run_action('prepare',W_PRESENT='1');self.assertEqual(self.calls(),[['pm','enable','--user','0','com.mipay.wallet']])
 def test_unknown_or_split_existing_wallet_blocks(self):
  (self.r/'wallet.apk').write_bytes(b'unknown');self.run_action('prepare',ok=False,W_PRESENT='1');(self.r/'wallet.apk').write_bytes(b'good-mipay');self.run_action('prepare',ok=False,W_PRESENT='1',W_SPLIT='1');self.assertEqual(self.calls(),[])
 def test_missing_or_disabled_wallet_is_not_ready(self):
  self.run_action('status',ok=False);self.run_action('status',ok=False,W_PRESENT='1',W_DISABLED='1');self.assertEqual(self.calls(),[])
 def test_install_failure_or_corrupt_payload_is_not_ready(self):
  self.run_action('prepare',ok=False,W_INSTALL_FAIL='1');self.assertFalse((self.r/'installed').exists());(self.r/'payload/Mipay.apk').write_bytes(b'corrupt');self.run_action('prepare',ok=False);self.assertEqual(len(self.calls()),1)
 def test_eea_prepare_never_installs_before_reboot(self):
  self.run_action('prepare',ok=False,**self.eea());self.assertEqual(self.calls(),[])
if __name__=='__main__':unittest.main()
