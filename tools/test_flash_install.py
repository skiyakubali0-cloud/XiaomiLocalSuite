"""Host execution of the real flash helper/controller/worker with synthetic payloads.

Only Android paths, payload identities and external commands are doubled. No
private ZIP, ADB, signing key or phone is used. Native nested KSU installation,
OverlayFS activation, Binder and actual reboot behavior are not qualified by
these fixtures. A simulated boot explicitly activates staged module fixtures.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest
import zipfile
from unittest.mock import patch

import recipe_assemble as assemble

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'suite/module'
_spec = importlib.util.spec_from_file_location('flash_controller_fixtures', ROOT / 'suite/test_control.py')
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)
IDS = ('market', 'assistant', 'xiaoai', 'phone', 'gallery', 'weather', 'disaster', 'wallet', 'clock', 'calendar', 'mipush')
TSM_CN = '567e8f05e4b2cbc7c203ce5f10672756ea8af0542c3fc5aafaa3e677ebcaa671'
TSM_EEA = 'c31f66629723c3c60a8d0862e68f2777b0187afe7271bbec2df7468bd5d350bb'
RUNTIME = {
    'system_ext/lib64/libhyper_os_core_system_private.dylib.so': 'a7de453780f33d2dec0cfca8832d218ee798f3208df06af36744f416313afa1f',
    'apex/com.android.runtime/lib64/bionic/libc.so': 'f6c25ea4d8b9a4dc76d6964f78edc9831cd676837a8f91d93a1cb4e87808e32e',
    'system_ext/framework/miui-services.jar': 'cef17afe99cfa6396922e2fe1dce6642ec86ddcf141589b8ef4d007d6920ecdb',
}

# Extend the public controller command double. Everything else runs the original
# fail-closed mock; the helper and controller functions themselves are not stubbed.
EXTRA = r'''
import hashlib,json,os,pathlib,sys
root=pathlib.Path(os.environ['TEST_ROOT'])
config_path=root/'flash-config.json'
config=json.loads(config_path.read_text())
name,args=pathlib.Path(sys.argv[0]).name,sys.argv[1:]
with (root/'trace').open('a') as f:f.write(json.dumps([name]+args)+'\n')
def record(command):
    with (root/'calls').open('a') as f:f.write(json.dumps(command)+'\n')
def save():config_path.write_text(json.dumps(config))
def done(code=0):sys.exit(code)
if 'packages' in config:os.environ['TEST_PACKAGES']=json.dumps(config['packages'])
if name=='busybox' and args[:2]==['unzip','-p']:
    import zipfile
    with zipfile.ZipFile(args[2]) as archive:sys.stdout.buffer.write(archive.read(args[3]))
    done()
elif name=='busybox' and args[:1]==['tee']:
    data=sys.stdin.buffer.read()
    pathlib.Path(args[1]).write_bytes(data)
    sys.stdout.buffer.write(data);sys.stdout.buffer.flush()
    done(24 if config.get('tee_fail') else 0)
elif name=='busybox' and args[:1]==['nohup']:
    record([name]+args);done()
elif name=='stat' and len(args)==3 and args[:2]==['-c','%Z']:
    print(config.get('market_ctime',1000));done()
elif name=='ksud' and args[:2]==['module','install']:
    record(args)
    key=pathlib.Path(args[2]).stem
    with (root/'native-cwds').open('a') as f:f.write(str(pathlib.Path.cwd())+'\n')
    print('synthetic native install '+key,flush=True)
    if config.get('fail_child')==key:done(23)
    module=root/'data/adb/modules_update'/('xuanyuan-os4-'+key)
    module.mkdir(parents=True,exist_ok=True)
    codes=json.loads(os.environ['FLASH_CODES'])
    (module/'module.prop').write_text('id=xuanyuan-os4-'+key+'\nversionCode='+codes[key]+'\n')
    done()
elif name=='ksud' and args[:2]==['module','enable']:
    record(args)
    state=root/'data/adb/xuanyuan-os4-suite-state'
    latest=pathlib.Path((state/'latest').read_text().strip())
    with (root/'enable-records').open('a') as f:
        f.write(json.dumps({'module':args[2],'locked':(state/'lock').is_dir(),
                            'flash_worker':os.environ.get('XLS_FLASH_WORKER'),
                            'job_state':(latest/'state').read_text().strip()})+'\n')
    if config.get('fail_enable')==args[2]:done(27)
    (root/'data/adb/modules'/args[2]/'disable').unlink(missing_ok=True);done()
elif name=='df' and config.get('race_latest'):
    manual=root/'data/adb/xuanyuan-os4-suite-state/jobs/manual-restore-race'
    manual.mkdir(parents=True,exist_ok=True);(manual/'state').write_text('succeeded\n')
    (root/'data/adb/xuanyuan-os4-suite-state/latest').write_text(str(manual)+'\n')
    config.pop('race_latest');save()
elif name=='df' and config.get('race_previous_state'):
    latest=root/'data/adb/xuanyuan-os4-suite-state/latest'
    (pathlib.Path(latest.read_text().strip())/'state').write_text('failed\n')
    config.pop('race_previous_state');save()
elif name=='date':
    if config.get('fail_date'):done(26)
    os.execv(os.environ['HOST_DATE'],['date']+args)
elif name=='getprop' and args==['sys.boot_completed'] and config.get('boot_incomplete'):
    print('0');done()
elif name=='pm' and args[:3]==['path','--user','0'] and args[3]=='com.miui.tsmclient':
    print('package:'+str(root/'product/app/MITSMClientGlobal/MITSMClientGlobal.apk'));done()
elif name=='pm' and args==['list','packages','-U','--user','0','com.miui.tsmclient']:
    print('package:com.miui.tsmclient uid:'+('10214' if config.get('wallet')=='eea' else '1027'));done()
elif name=='pm' and args==['list','libraries']:
    print('library:vendor.xiaomi.hardware.misys.V3_0');done()
elif name=='pm' and args[:1]==['install']:
    data=sys.stdin.buffer.read();record([name]+args)
    if config.get('pm_fail'):done(25)
    assert '-S' in args and int(args[args.index('-S')+1])==len(data)
    done()
elif name=='pm' and args[:2]==['uninstall','-k']:
    record([name]+args);done()
elif name=='pm' and args[:1]==['grant']:
    record([name]+args);done()
elif name=='dumpsys' and args==['package','com.miui.home']:
    print('    versionCode=801027654 minSdk=37');done()
elif name=='sha256sum' and not args:
    print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest()+'  -');done()
elif name=='sha256sum' and len(args)==1:
    path=pathlib.Path(args[0])
    try:key=str(path.relative_to(root))
    except ValueError:key=''
    if key in config.get('hashes',{}):
        print(config['hashes'][key]+'  '+args[0]);done()
    if key=='product/app/MITSMClientGlobal/MITSMClientGlobal.apk':
        print((os.environ['TSM_EEA'] if config.get('wallet')=='eea' else os.environ['TSM_CN'])+'  '+args[0]);done()
elif name=='sha256sum' and args[:1]==['-c']:
    try:
        for line in pathlib.Path(args[1]).read_text().splitlines():
            digest,path=line.split(None,1)
            if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()!=digest:done(1)
        done()
    except OSError:done(1)
elif name=='mountpoint':done(1 if config.get('unmounted') else 0)
elif name=='sleep':done()
'''


class FlashInstallTests(unittest.TestCase):
    calls = legacy.ControllerTests.calls

    def enable(self, mid, code=None):
        path=self.modules/mid;path.mkdir(parents=True,exist_ok=True)
        text=(SOURCE/'catalog.sh').read_text()
        match=re.search("MID='"+re.escape(mid)+"';.*?CODE='([^']*)'",text)
        code=code or ('13100' if mid=='meta-overlayfs' else match[1] if match else '1')
        (path/'module.prop').write_text('id='+mid+'\nversionCode='+code+'\n')
        return path

    def setUp(self):
        with patch.object(legacy,'SOURCE',SOURCE):
            legacy.ControllerTests.setUp(self)
        self.config={'wallet':'cn','hashes':dict(RUNTIME)}
        self.bin.joinpath('mock.py').write_text('#!'+sys.executable+'\n'+EXTRA+'\n'+legacy.MOCK)
        self.env['HOST_DATE']=shutil.which('date')
        for name in ('mountpoint','fastboot','su','sqlite3','sleep','date'):
            (self.bin/name).symlink_to(self.bin/'mock.py')
        self.env.update(TSM_CN=TSM_CN,TSM_EEA=TSM_EEA,KSU='true',PYTHONDONTWRITEBYTECODE='1')
        self.boot_stat=self.root/'boot-stat';self.boot_stat.write_text('btime 2000\n')
        for name in ('shared.sh','wallet.sh','preset.sh','runner.sh','service.sh'):
            (self.module/name).write_text(self.adapt((SOURCE/name).read_text()))
        self.controller.write_text(self.adapt((SOURCE/'control.sh').read_text()))
        (self.module/'module.prop').write_text('id=xuanyuan-os4-suite\nversionCode=2026101604\n')
        for name in ('zygisksu','zygisk_lsposed'):self.enable(name)
        codes={key:self.catalog(key,'CODE') for key in IDS if self.catalog(key,'KIND')=='module'}
        self.env['FLASH_CODES']=json.dumps(codes)
        global_apk=self.module/'payload/calendar-global.apk';global_apk.write_bytes(b'synthetic global calendar')
        control=self.controller.read_text()
        control=control.replace('ed8f4356bb7c44038abbe5f215f215277c114e75de4bd21ac0a65f77d75f75f0',self.catalog('calendar','SHA'))
        control=control.replace('e2f2e6f2cc5d5ab32480447c23b91c90b2c5db863a38907c6dff61fec80566e7',hashlib.sha256(global_apk.read_bytes()).hexdigest())
        self.controller.write_text(control)
        self.base_control=control
        shared=self.module/'shared.sh';shared.write_text(re.sub(r'^UNIFIED_SHA=.*$', 'UNIFIED_SHA='+self.catalog('clock','SHA'),shared.read_text(),flags=re.M))
        packages=json.loads(self.env['TEST_PACKAGES'])
        for row in (self.module/'owned-packages.txt').read_text().splitlines():
            _,package,digest=row.split('|');packages[package]=digest
        packages.update({'com.android.deskclock':'41defcfd640a3ba5d359c20004d9dced5f6c0810204c41c94530af2a2bc1e9f6',
                         'local.xuanyuan.mipushcompat':self.catalog('clock','SHA'),
                         'com.mipay.wallet':'c5fa1012886f21d9be2453d66e741d6821e9b94d39a6881318c3d1d196ddb058',
                         'com.android.calendar':self.catalog('calendar','SHA'),
                         'com.xiaomi.aicr':'f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520'})
        self.env['TEST_PACKAGES']=json.dumps(packages)
        for package in packages:
            path=self.root/'apks'/(package+'.apk');path.parent.mkdir(exist_ok=True);path.write_bytes(b'package identity fixture')
        tsm=self.root/'product/app/MITSMClientGlobal/MITSMClientGlobal.apk';tsm.parent.mkdir(parents=True);tsm.write_bytes(b'TSM identity fixture')
        self.protected={}
        for name in ('data/user/0/com.miui.tsmclient/keep','data/user_de/0/com.miui.tsmclient/keep',
                     'data/user/0/com.mipay.wallet/keep','data/user/0/com.xiaomi.xmsf/keep',
                     'data/adb/lspd/config/modules_config.db','data/adb/xuanyuan-unified-state/preferences'):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'preserve '+name.encode());self.protected[path]=path.read_bytes()
        self.addCleanup(self.assert_preserved)
        self.helper=self.module/'install-selected.sh'
        self.pending=self.module/'install-selected.pending'
        self.ok=self.module/'install-selected.ok'
        self.result=self.module/'install-selected.result'
        self.plan(IDS)

    def adapt(self,text):
        for old,new in (('/proc/sys/kernel/random/boot_id',str(self.boot)),('/proc/stat',str(self.boot_stat)),
                        ('/system_ext/',str(self.root/'system_ext')+'/'),('/apex/',str(self.root/'apex')+'/'),
                        ('/product/',str(self.root/'product')+'/'),('/data',str(self.root/'data'))):
            text=text.replace(old,new)
        text=re.sub(r'^K=.*$','K='+str(self.bin/'ksud'),text,flags=re.M)
        text=re.sub(r'^BB=.*$','BB='+str(self.bin/'busybox'),text,flags=re.M)
        # runner's literal busybox path is also confined to the command double.
        text=text.replace(str(self.root/'data/adb/ksu/bin/busybox'),str(self.bin/'busybox'))
        return text

    def catalog(self,key,field):
        row=next(line for line in (self.module/'catalog.sh').read_text().splitlines() if line.startswith(key+')'))
        return re.search(r'\b'+field+r"='([^']*)'",row)[1]

    def plan(self,ids):
        self.ids=tuple(ids)
        text=self.base_control
        self.controller.write_text(re.sub(r"^ORDER='[^']*'$","ORDER='"+' '.join(ids)+"'",text,flags=re.M))
        for name in ('install-selected.sh','customize.sh','service.sh'):
            (self.module/name).write_text((SOURCE/name).read_text())
        assemble.install_during_flash(self.module,ids)
        for name in ('install-selected.sh','customize.sh','service.sh'):
            p=self.module/name;p.write_text(self.adapt(p.read_text()))
        self.seal()

    def seal(self):
        names=sorted(p for p in self.module.iterdir() if p.is_file() and p.suffix in ('.sh','.prop','.txt'))
        (self.module/'control.sha256').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in names))

    def trace(self):
        p=self.root/'trace'
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def installed(self):
        return [Path(c[-1]).stem for c in self.calls() if c[:2]==['module','install']]

    def enable_records(self):
        path=self.root/'enable-records'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def run_helper(self,*args,success=None):
        (self.root/'flash-config.json').write_text(json.dumps(self.config))
        result=subprocess.run(['/bin/sh',str(self.helper),*args],cwd=self.root,env=self.env,capture_output=True,text=True,timeout=35)
        if success is not None:self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
        self.assert_preserved()
        return result

    def run_service(self,success=True):
        (self.root/'flash-config.json').write_text(json.dumps(self.config))
        result=subprocess.run(['/bin/sh',str(self.module/'service.sh')],cwd=self.root,env=self.env,capture_output=True,text=True,timeout=35)
        self.assertEqual(result.returncode==0,success,result.stdout+result.stderr)
        self.assert_preserved()
        return result

    def result_fields(self):
        return dict(line.split('=',1) for line in self.result.read_text().splitlines())

    def job(self):return Path((self.state_dir/'latest').read_text().strip())

    @property
    def state_dir(self):return self.root/'data/adb/xuanyuan-os4-suite-state'

    def completed(self):
        p=self.job()/'completed';return p.read_text().splitlines() if p.exists() else []

    def next_boot(self):
        self.boot.write_text('boot-B\n');self.boot_stat.write_text('btime 4000\n')
        staged=self.root/'data/adb/modules_update'
        if staged.exists():
            for folder in staged.iterdir():
                target=self.modules/folder.name
                if target.exists():shutil.rmtree(target)
                shutil.move(str(folder),str(target))
        self.config['market_ctime']=3000

    def assert_preserved(self):
        for path,raw in self.protected.items():self.assertEqual(path.read_bytes(),raw)
        self.assertFalse((self.root/'data/adb/xuanyuan-os4-wallet-reset-authorized').exists())
        forbidden={'adb','fastboot','reboot','su','sqlite3','settings'}
        for call in self.trace():
            self.assertNotIn(call[0],forbidden,call)
            self.assertNotEqual(call[:2],['pm','clear'],call)

    def test_all_eleven_cn_flash_split_phone_resume_once_after_boot(self):
        self.run_helper('flash',success=True)
        batch=[x for x in IDS if x!='phone']
        self.assertEqual(self.completed(),batch)
        self.assertEqual(self.installed(),[x for x in batch if x not in ('clock','calendar','mipush')])
        self.assertEqual(self.result_fields()['state'],'reboot-required');self.assertFalse(self.ok.exists())
        queue=self.pending.read_text().splitlines();self.assertEqual(len(queue),4)
        self.assertEqual(queue,[hashlib.sha256((self.module/'control.sha256').read_bytes()).hexdigest(),'boot-A',str(self.job()),'phone'])
        before=list(self.calls());self.run_helper('resume',success=True);self.assertEqual(self.calls(),before)
        self.next_boot();self.run_helper('resume',success=True)
        self.assertEqual(self.completed(),['phone']);self.assertEqual(self.installed()[-1],'phone')
        self.assertEqual(self.result_fields()['state'],'deployed');self.assertEqual(self.ok.read_text().strip(),','.join(IDS))
        self.assertFalse(self.pending.exists());before=list(self.calls())
        self.run_helper('resume',success=True);self.assertEqual(self.calls(),before)
        self.assertTrue(any(c[:2]==['pm','install'] for c in self.calls()))
        self.assertEqual({Path(x).resolve() for x in (self.root/'native-cwds').read_text().splitlines()},{self.module.resolve()})

    def test_wallet_eea_waits_without_reset_and_unselected_wallet_is_not_probed(self):
        self.plan(('wallet',));self.config['wallet']='eea';self.run_helper('flash',success=True)
        self.assertEqual(self.result_fields()['state'],'wallet-confirmation-required')
        self.assertEqual(self.installed(),[]);self.assertFalse(self.pending.exists());self.assertFalse(self.ok.exists())
        self.plan(('gallery',));(self.root/'trace').unlink();self.config['wallet']='unknown'
        self.run_helper('flash',success=True)
        probes=[c for c in self.trace() if c[0]=='pm' and any(p in c for p in ('com.miui.tsmclient','com.mipay.wallet'))]
        self.assertEqual(probes,[]);self.assertEqual(self.completed(),['gallery'])

    def test_platform_hash_and_pending_guards_precede_installs(self):
        self.plan(('gallery',))
        for mode in ('rom','payload','lock','pending','meta'):
            with self.subTest(mode=mode):
                undo=lambda:None
                if mode=='rom':self.env['TEST_PROPS']=json.dumps({'ro.build.version.incremental':'unknown'});undo=lambda:self.env.pop('TEST_PROPS')
                elif mode=='payload':
                    p=self.module/'payload/gallery.zip';old=p.read_bytes();p.write_bytes(b'changed');undo=lambda:p.write_bytes(old)
                elif mode=='meta':
                    p=self.modules/'meta-overlayfs/module.prop';old=p.read_bytes();p.write_text('versionCode=13000\n');undo=lambda:p.write_bytes(old)
                else:
                    p=self.state_dir/'lock' if mode=='lock' else self.root/'data/adb/modules_update/unrelated'
                    p.mkdir(parents=True);undo=lambda:p.rmdir()
                try:
                    self.run_helper('flash',success=False);self.assertEqual(self.installed(),[]);self.assertEqual(self.result_fields()['state'],'failed')
                finally:undo()

    def test_deferred_phone_payload_is_checked_before_first_install(self):
        self.plan(('market','phone'));(self.module/'payload/phone.zip').write_bytes(b'changed deferred payload')
        self.run_helper('flash',success=False);self.assertEqual(self.installed(),[]);self.assertFalse(self.pending.exists())

    def test_changed_queue_fingerprint_and_latest_restore_cancel_resume(self):
        self.plan(('market','phone'));self.run_helper('flash',success=True);self.next_boot()
        pending=self.pending.read_bytes();before=list(self.calls())
        lines=self.pending.read_text().splitlines();lines[0]='0'*64;self.pending.write_text('\n'.join(lines)+'\n')
        self.run_helper('resume',success=False);self.assertEqual(self.calls(),before);self.assertFalse(self.pending.exists())
        self.pending.write_bytes(pending)
        manual=self.state_dir/'jobs/manual-restore';manual.mkdir();(manual/'state').write_text('succeeded\n')
        (self.state_dir/'latest').write_text(str(manual)+'\n')
        self.run_helper('resume',success=True);self.assertEqual(self.result_fields()['state'],'cancelled');self.assertFalse(self.pending.exists());self.assertEqual(self.calls(),before)

    def test_worker_and_late_tee_failure_never_mark_complete_or_retry(self):
        self.plan(('gallery',))
        for failure in ('fail_child','tee_fail'):
            with self.subTest(failure=failure):
                self.config.pop('fail_child',None);self.config.pop('tee_fail',None)
                self.config[failure]='gallery' if failure=='fail_child' else True
                self.run_helper('flash',success=False)
                self.assertEqual((self.job()/'state').read_text().strip(),'failed')
                self.assertEqual(self.result_fields()['state'],'failed');self.assertFalse(self.ok.exists());self.assertFalse(self.pending.exists())
                self.assertFalse((self.state_dir/'lock').exists());before=list(self.calls())
                self.run_helper('resume',success=True);self.assertEqual(self.calls(),before)
                staged=self.root/'data/adb/modules_update'
                if staged.exists():shutil.rmtree(staged)

    def test_invalid_argv_and_plan_mismatch_rejected_without_install(self):
        self.plan(('market','phone'))
        for argv in ((),('flash','phone'),('unknown',),('resume','phone')):
            with self.subTest(argv=argv):self.run_helper(*argv,success=False)
        self.helper.write_text(self.helper.read_text().replace("AUTO_IDS='market,phone'","AUTO_IDS='phone,market'"));self.seal()
        self.run_helper('flash',success=False);self.assertEqual(self.installed(),[])

    def test_real_generated_service_resumes_phone_then_never_repeats(self):
        self.plan(('market','phone'));self.run_helper('flash',success=True)
        before=list(self.calls());self.run_service();self.assertEqual(self.calls(),before)
        self.next_boot();self.run_service()
        self.assertEqual(self.installed(),['market','phone']);self.assertEqual(self.completed(),['phone'])
        self.assertEqual(self.result_fields()['state'],'deployed');self.assertFalse(self.pending.exists())
        before=list(self.calls());self.run_service();self.assertEqual(self.calls(),before)

    def test_existing_market_same_boot_defers_but_previous_boot_installs_phone(self):
        self.plan(('market','phone'));self.enable('xuanyuan-os4-market')
        self.config['market_ctime']=2000;self.run_helper('flash',success=True)
        self.assertEqual(self.installed(),['market']);self.assertTrue(self.pending.exists())
        self.next_boot();self.run_helper('resume',success=True)
        self.assertEqual(self.installed(),['market','phone'])

    def test_selected_runtime_hashes_fail_before_first_native_write(self):
        self.plan(('assistant','xiaoai'))
        for name,digest in RUNTIME.items():
            with self.subTest(name=name):
                self.config['hashes'][name]='0'*64
                self.run_helper('flash',success=False)
                self.assertEqual(self.installed(),[]);self.assertFalse(self.pending.exists());self.assertFalse(self.ok.exists())
                self.config['hashes'][name]=digest

    def test_migration_lock_unknown_framework_pending_and_disabled_meta_stop(self):
        self.plan(('gallery',))
        for name in ('data/adb/xuanyuan-unified-state/lock','data/adb/modules/zygisksu/update',
                     'data/adb/modules/unrelated/remove','data/adb/modules/meta-overlayfs/disable'):
            with self.subTest(name=name):
                path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
                self.run_helper('flash',success=False);self.assertEqual(self.installed(),[])
                self.assertTrue(path.exists());path.unlink()

    def test_resume_requires_valid_queue_and_will_not_install_when_boot_incomplete(self):
        self.plan(('market','phone'));self.run_helper('flash',success=True);self.next_boot()
        pending=self.pending.read_text();before=list(self.calls())
        self.pending.write_text(pending+'unexpected fifth line\n')
        self.run_helper('resume',success=False);self.assertEqual(self.calls(),before)
        self.pending.write_text(pending);self.config['boot_incomplete']=True
        self.run_service(success=False)
        self.assertEqual(self.calls(),before);self.assertFalse(self.pending.exists());self.assertFalse(self.ok.exists())

    def test_resume_rechecks_latest_and_previous_success_after_preflight(self):
        self.plan(('market','phone'));self.run_helper('flash',success=True);self.next_boot()
        pending=self.pending.read_bytes();previous=self.job();before=list(self.calls())
        for hook in ('race_latest','race_previous_state'):
            with self.subTest(hook=hook):
                self.pending.write_bytes(pending);(self.state_dir/'latest').write_text(str(previous)+'\n')
                (previous/'state').write_text('succeeded\n');self.config[hook]=True
                self.run_helper('resume',success=True)
                self.assertEqual(self.result_fields()['state'],'cancelled');self.assertFalse(self.pending.exists())
                self.assertFalse((self.state_dir/'lock').exists());self.assertEqual(self.calls(),before)
                self.config.pop(hook)

    def paired_xiaoai(self,stage=True,live=False,wrong_stage=False):
        self.plan(('assistant','xiaoai'))
        privacy=b'#!/bin/sh\n# synthetic new paired privacy CLI\nexit 0\n'
        payload=self.module/'payload/xiaoai.zip';old=self.catalog('xiaoai','SHA')
        with zipfile.ZipFile(payload,'w') as archive:archive.writestr('privacy.sh',privacy)
        catalog=self.module/'catalog.sh';catalog.write_text(catalog.read_text().replace(old,hashlib.sha256(payload.read_bytes()).hexdigest()))
        code=self.catalog('xiaoai','CODE')
        if live:
            folder=self.enable('xuanyuan-os4-xiaoai',code);(folder/'privacy.sh').write_bytes(privacy)
        if stage:
            folder=self.root/'data/adb/modules_update/xuanyuan-os4-xiaoai';folder.mkdir(parents=True,exist_ok=True)
            (folder/'module.prop').write_text('id=xuanyuan-os4-xiaoai\nversionCode='+code+'\n')
            (folder/'privacy.sh').write_bytes(b'wrong stage' if wrong_stage else privacy)
        self.env['AUTO_PAIRED_XIAOAI']='true';self.seal()
        return folder,privacy

    def test_paired_xiaoai_stage_is_verified_and_not_installed_twice(self):
        folder,privacy=self.paired_xiaoai()
        self.run_helper('flash',success=True)
        self.assertEqual(self.installed(),['assistant']);self.assertEqual(self.completed(),['assistant'])
        self.assertEqual((folder/'privacy.sh').read_bytes(),privacy)
        self.assertEqual(self.ok.read_text().strip(),'assistant,xiaoai')
        self.assertTrue(any(c[:3]==['busybox','unzip','-p'] for c in self.trace()))

    def test_paired_xiaoai_live_fallback_only_without_stage(self):
        folder,privacy=self.paired_xiaoai(stage=False,live=True)
        (folder/'update').touch()
        self.run_helper('flash',success=True)
        self.assertEqual(self.installed(),['assistant']);self.assertEqual(self.completed(),['assistant'])
        self.assertEqual((folder/'privacy.sh').read_bytes(),privacy)

    def test_wrong_paired_stage_cannot_fall_back_to_matching_live(self):
        self.paired_xiaoai(stage=True,live=True,wrong_stage=True)
        self.run_helper('flash',success=False)
        self.assertEqual(self.installed(),[]);self.assertFalse(self.ok.exists());self.assertFalse(self.pending.exists())

    def test_pair_does_not_allow_unknown_pending_or_xiaoai_removal(self):
        folder,_=self.paired_xiaoai(stage=True,live=True)
        for name in ('data/adb/modules_update/unrelated','data/adb/modules/xuanyuan-os4-xiaoai/remove'):
            with self.subTest(name=name):
                path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
                self.run_helper('flash',success=False);self.assertEqual(self.installed(),[]);path.unlink()
        self.env.pop('AUTO_PAIRED_XIAOAI')
        self.run_helper('flash',success=False);self.assertEqual(self.installed(),[])

    def test_failure_after_own_lock_acquisition_releases_only_own_lock(self):
        self.plan(('gallery',));self.config['fail_date']=True
        self.run_helper('flash',success=False)
        self.assertFalse((self.state_dir/'lock').exists());self.assertEqual(self.installed(),[])
        self.assertFalse(self.ok.exists());self.assertEqual(self.result_fields()['state'],'failed')

    def test_flash_enable_of_disabled_selection_holds_worker_lock(self):
        self.plan(('disaster',))
        selected=self.enable('xuanyuan-os4-disaster');(selected/'disable').touch()
        unselected=self.enable('xuanyuan-os4-gallery');(unselected/'disable').touch()
        self.run_helper('flash',success=True)
        self.assertEqual(self.enable_records(),[{'module':'xuanyuan-os4-disaster',
            'locked':True,'flash_worker':'1','job_state':'running'}])
        self.assertFalse((selected/'disable').exists());self.assertTrue((unselected/'disable').exists())
        self.assertEqual(self.installed(),['disaster']);self.assertEqual(self.completed(),['disaster'])
        self.assertEqual((self.job()/'state').read_text().strip(),'succeeded')
        self.assertFalse((self.state_dir/'lock').exists());self.assertTrue(self.ok.exists())
        calls=self.calls()
        self.assertLess(next(i for i,c in enumerate(calls) if c[:2]==['module','install']),
                        calls.index(['module','enable','xuanyuan-os4-disaster']))

    def test_flash_enable_failure_stops_worker_before_later_selection(self):
        self.plan(('gallery','disaster'))
        selected=self.enable('xuanyuan-os4-gallery');(selected/'disable').touch()
        self.config['fail_enable']='xuanyuan-os4-gallery'
        self.run_helper('flash',success=False)
        self.assertEqual(self.enable_records(),[{'module':'xuanyuan-os4-gallery',
            'locked':True,'flash_worker':'1','job_state':'running'}])
        self.assertTrue((selected/'disable').exists());self.assertEqual(self.installed(),['gallery'])
        self.assertEqual(self.completed(),[]);self.assertEqual((self.job()/'started').read_text().splitlines(),['gallery'])
        self.assertEqual((self.job()/'state').read_text().strip(),'failed')
        self.assertEqual(self.result_fields()['state'],'failed')
        self.assertFalse(self.ok.exists());self.assertFalse(self.pending.exists());self.assertFalse((self.state_dir/'lock').exists())
        before=list(self.calls());self.run_service();self.assertEqual(self.calls(),before)

    def test_generic_controller_install_does_not_enable_disabled_module(self):
        self.plan(('disaster',))
        selected=self.enable('xuanyuan-os4-disaster');(selected/'disable').touch()
        (self.root/'flash-config.json').write_text(json.dumps(self.config))
        result=subprocess.run(['/bin/sh',str(self.controller),'start','install','disaster'],
                              env=self.env,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        result=subprocess.run(['/bin/sh',str(self.controller),'worker',str(self.job()),'install','disaster'],
                              env=self.env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(self.enable_records(),[]);self.assertTrue((selected/'disable').exists())
        self.assertEqual(self.completed(),['disaster']);self.assertFalse((self.state_dir/'lock').exists())
        self.assert_preserved()

    def test_direct_controller_restore_remains_separate_and_preserves_data(self):
        self.plan(('disaster',))
        (self.enable('xuanyuan-os4-disaster')/'disable').touch()
        self.run_helper('flash',success=True);self.next_boot()
        self.assertEqual(self.enable_records(),[{'module':'xuanyuan-os4-disaster',
            'locked':True,'flash_worker':'1','job_state':'running'}])
        (self.root/'flash-config.json').write_text(json.dumps(self.config))
        result=subprocess.run(['/bin/sh',str(self.controller),'start','restore','disaster'],env=self.env,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        job=self.job()
        result=subprocess.run(['/bin/sh',str(self.controller),'worker',str(job),'restore','disaster'],env=self.env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn(['module','disable','xuanyuan-os4-disaster'],self.calls())
        self.assertTrue((self.state_dir/'restored/disaster').exists());self.assert_preserved()
        disabled=self.modules/'xuanyuan-os4-disaster/disable'
        self.assertTrue(disabled.exists());before=list(self.calls());enables=self.enable_records()
        self.run_service();self.run_service()
        self.assertTrue(disabled.exists());self.assertEqual(self.calls(),before);self.assertEqual(self.enable_records(),enables)


if __name__=='__main__':unittest.main(verbosity=2)
