"""Offline behavior checks using real full controller/preset and Android command doubles."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import unittest
import zipfile

import build as full
spec=importlib.util.spec_from_file_location('preset_fixtures',full.HERE.parent/'unified-bundle/test_preset.py')
pf=importlib.util.module_from_spec(spec);spec.loader.exec_module(pf)
PROFILE=','.join(full.IDS)
FEATURES=pf.FEATURES


class FullSuiteTests(unittest.TestCase):
    def setUp(self):
        self.c=pf.PresetTests();self.c.setUp();self.addCleanup(self.c.doCleanups)
        c=self.c
        c.controller.write_text(full.controller(c.controller.read_text()))
        c.preset.write_text(full.preset(c.preset.read_text()))
        cat=''.join(x+'\n' for x in (c.module/'catalog.sh').read_text().splitlines() if not x.startswith('wallet)'))
        cat=cat.replace("CODE='2026101504'","CODE='"+full.CODE+"'")
        (c.module/'catalog.sh').write_text(cat)
        (c.module/'module.prop').write_text('id=xuanyuan-os4-suite\nversion=1.6.1-selectable\nversionCode='+full.PARENT_CODE+'\n')
        c.rehash()
        self.protected={}
        for name in ['data/user/0/com.mipay.wallet/credentials','data/user/0/com.miui.tsmclient/preferences','data/adb/modules/xuanyuan-os4-wallet/private-state','data/user/0/com.xiaomi.xmsf/files/mipush_region','data/adb/lspd/config/modules_config.db','data/user/0/local.xuanyuan.mipushcompat/shared_prefs/selection.xml']:
            path=c.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'protected-sentinel:'+name.encode());self.protected[path]=path.read_bytes()

    def tearDown(self):
        for p,raw in self.protected.items():self.assertEqual(p.read_bytes(),raw)

    def plan(self,components=PROFILE,features=FEATURES,**kwargs):
        return self.c.run_preset(components=components,features=features,**kwargs)

    def test_all_ten_first_plan_installs_market_only_before_boot(self):
        r=self.plan(ids=PROFILE,state='install',batch='market')
        self.assertFalse(r['wallet_pending']);self.assertEqual(self.c.calls(),[])
        self.c.component('market')
        r=self.plan(ids=PROFILE,state='install')
        self.assertNotIn('wallet',r['install_ids'].split(','))
        self.assertIn('phone',r['install_ids'].split(','))

    def test_wallet_injected_selection_and_direct_root_actions_fail_without_writes(self):
        before=self.c.snapshot()
        for action in ['plan','apply','migrate']:
            self.plan(components='wallet',features='-',ids=None,action=action,state='blocked')
        for action in [('plan','install','wallet'),('plan','restore','wallet'),('start','install','wallet'),('open','wallet')]:
            p=subprocess.run(['/bin/sh',str(self.c.controller),*action],env=self.c.env,capture_output=True)
            self.assertNotEqual(p.returncode,0)
        self.assertEqual(before,self.c.snapshot());self.assertEqual(self.c.calls(),[])

    def test_single_weather_gallery_and_clock_selection(self):
        self.plan(components='weather',features='-',ids='weather',state='install',batch='weather')
        self.plan(components='gallery',features='-',ids='gallery',state='install',batch='gallery')
        self.plan(components='clock',features='clock',ids='clock',state='ready',batch='')
        self.assertEqual(self.c.calls(),[])

    def test_reviewed_market_4127_is_exact_and_unknown_update_still_blocks(self):
        c=self.c
        for key in full.IDS:
            if c.catalog(key,'KIND')=='module':c.component(key)
        packages=json.loads(c.env['TEST_PACKAGES']);packages['com.xiaomi.market']=full.MARKET_4127_SHA;c.packages(packages)
        self.plan(ids=PROFILE,state='ready',batch='')
        packages['com.xiaomi.market']='0'+full.MARKET_4127_SHA[1:];c.packages(packages)
        self.plan(ids=PROFILE,state='blocked')
        self.assertEqual(c.calls(),[])

    def test_dependencies_and_market_boot_barrier_retained(self):
        self.plan(components='phone',features='-',ids='market,phone',state='install',batch='market')
        market=self.c.component('market');os.utime(market/'module.prop',(2001,2001))
        self.plan(components='phone',features='-',ids='market,phone',state='reboot',batch='')
        self.plan(components='xiaoai',features='privacy,suggestions',ids='assistant,xiaoai',state='install',batch='assistant,xiaoai')

    def test_old_xiaoai_reviewed_upgrade_and_unknown_version_rejected(self):
        self.c.component('assistant')
        x=self.c.component('xiaoai',code='2026101601')
        self.plan(components='xiaoai',features='-',ids='assistant,xiaoai',state='install',batch='xiaoai')
        (x/'module.prop').write_text('id=xuanyuan-os4-xiaoai\nversionCode=999\n')
        self.plan(components='xiaoai',features='-',ids='assistant,xiaoai',state='blocked')
        self.assertEqual(self.c.calls(),[])

    def test_reboot_and_unknown_pending_guards_retained(self):
        self.c.stage('xiaoai')
        self.plan(components='weather',features='-',ids='weather',state='reboot')
        self.c.stage('phone',code='999')
        self.plan(components='weather',features='-',ids='weather',state='blocked')
        self.assertEqual(self.c.calls(),[])

    def test_all_current_ten_ready_does_not_modify_configuration(self):
        for key in full.IDS:
            if self.c.catalog(key,'KIND')=='module':self.c.component(key)
        before=self.c.snapshot()
        self.plan(ids=PROFILE,state='ready',batch='')
        self.assertEqual(before,self.c.snapshot());self.assertEqual(self.c.calls(),[])

    def test_individual_restore_plans_and_dependency_barriers_preserved(self):
        c=self.c
        c.component('weather');c.component('gallery');c.component('market');c.component('phone')
        packages=json.loads(c.env['TEST_PACKAGES'])
        packages.update({'com.miui.weather2':'2a8faed30ce5ffe4ae0229dce0d520d882dff990f6ef158e5fbb555153b7e887','com.miui.core':'5abe56881dafbe3540e11c4ff4a450ae7bcd19d93753a251326f09314a2bb9e9'})
        c.packages(packages)
        state=c.root/'data/adb/xuanyuan-weather-state';state.mkdir(parents=True);(state/'restore.sh').write_text('exit 0\n')
        before=c.snapshot()
        for key in ['weather','gallery']:
            p=subprocess.run(['/bin/sh',str(c.controller),'plan','restore',key],env=c.env,capture_output=True)
            self.assertEqual(p.returncode,0,(key,p.stdout,p.stderr))
        for key in ['market','clock']:
            p=subprocess.run(['/bin/sh',str(c.controller),'plan','restore',key],env=c.env,capture_output=True)
            self.assertNotEqual(p.returncode,0)
        self.assertEqual(before,c.snapshot());self.assertEqual(c.calls(),[])

    def test_generated_controls_remove_wallet_and_update_all_identity_gates(self):
        with zipfile.ZipFile(full.BASE/'releases/xuanyuan-os4-suite-1.4.zip') as z:
            data={n:z.read(n) for n in z.namelist() if not n.startswith('payload/') and n not in ['control.sha256','checksums.sha256']}
        apk='b'*64;child='c'*64;result=full.changes(data,apk,12,child,34)
        rows=json.loads(result['webroot/catalog.json']);self.assertEqual([r['id'] for r in rows],full.IDS)
        self.assertNotIn(b'wallet)',result['catalog.sh']);self.assertNotIn(b'wallet|',result['owned-packages.txt'])
        self.assertIn(('SELF_SHA='+apk).encode(),result['migrate-legacy.sh'])
        self.assertIn(('xiaoai) REQUIRED='+full.CODE).encode(),result['migrate-legacy.sh'])
        for row in rows:
            if row['id'] in ['clock','mipush']:self.assertEqual(row['sha256'],apk)
            if row['id']=='xiaoai':self.assertEqual(row['versionCode'],full.CODE)
        for name in ['runner.sh','service.sh','webroot/index.html']:
            self.assertEqual(result[name],data[name])
        for name,raw in result.items():
            if name.endswith('.sh'):
                p=subprocess.run(['/bin/sh','-n'],input=raw,capture_output=True);self.assertEqual(p.returncode,0,(name,p.stderr))

    def test_android_classic_zip_metadata_and_rewritten_payload_headers(self):
        import struct
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);src=root/'forced.zip';dst=root/'classic.zip'
            with zipfile.ZipFile(src,'w') as z:
                with z.open('module.prop','w',force_zip64=True) as out:out.write(b'id=fixture\n')
                with z.open('system/app.apk','w',force_zip64=True) as out:out.write(b'opaque signed bytes')
                z.writestr('checksums.sha256',b'not used in source fixture')
            with zipfile.ZipFile(src) as z:full.write_archive(z,dst,{'module.prop':b'id=reviewed-fixture\n'})
            raw=dst.read_bytes()
            with zipfile.ZipFile(dst) as z:
                for info in z.infolist():
                    self.assertEqual(info.extract_version,20)
                    fields=struct.unpack_from('<4s5H3I2H',raw,info.header_offset)
                    self.assertEqual(fields[1],20)
                    self.assertNotEqual(fields[7],0xffffffff);self.assertNotEqual(fields[8],0xffffffff)
                self.assertEqual(z.read('system/app.apk'),b'opaque signed bytes')

    def test_regenerated_child_identity_matches_catalog_and_bridge(self):
        with zipfile.ZipFile(full.BASE/'releases/xuanyuan-os4-suite-1.4.zip') as parent,parent.open('payload/xiaoai.zip') as stream,zipfile.ZipFile(stream) as child:
            changes=full.child_changes(child,'b'*64)
        props=dict(row.split('=',1) for row in changes['module.prop'].decode().splitlines() if '=' in row)
        self.assertEqual(props['versionCode'],full.CODE)
        self.assertNotEqual(props['versionCode'],full.PARENT_CODE)
        self.assertEqual(props['id'],'xuanyuan-os4-xiaoai')

    def test_bad_source_never_publishes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'bad').write_bytes(b'not a release')
            with self.assertRaises(ValueError):full.build(p/'bad',p/'bad',p/'output.zip','a'*64)
            self.assertFalse((p/'output.zip').exists())



class BridgeTests(unittest.TestCase):
    def case(self,code=None,disabled=False,pending=False,lock=False,modified=False,fail=False):
        with tempfile.TemporaryDirectory() as temp:
            t=Path(temp);data=t/'data';module=data/'adb/modules/xuanyuan-os4-xiaoai';staged=data/'adb/modules_update/xuanyuan-os4-suite';staged.mkdir(parents=True)
            hashes={code:hashlib.sha256(code.encode()).hexdigest() for code in ['2026101504','2026101601','2026101602']}
            if code:
                module.mkdir(parents=True);(module/'module.prop').write_text('id=xuanyuan-os4-xiaoai\nversionCode='+code+'\n');(module/'privacy.sh').write_text('modified' if modified else code)
                if disabled:(module/'disable').touch()
                if pending:(module/'update').touch()
            if lock:(data/'adb/xuanyuan-os4-suite-state/lock').mkdir(parents=True)
            cli=data/'adb/ksud';cli.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> '+str(t/'calls')+'\nexit '+('1' if fail else '0')+'\n');cli.chmod(0o700)
            protected=t/'wallet-sentinel';protected.write_bytes(b'wallet-credentials-untouched')
            body=full.bridge(*[hashes[x] for x in ['2026101504','2026101601','2026101602']]).replace('/data/',str(data)+'/')
            script=t/'custom.sh';script.write_text('abort(){ echo "$*" >&2; exit 1; }; ui_print(){ :; }; MODPATH='+str(staged)+'\n'+body+'\necho apk-update > '+str(t/'apk-write')+'\n')
            p=subprocess.run(['/bin/sh',str(script)],capture_output=True)
            self.assertEqual(protected.read_bytes(),b'wallet-credentials-untouched')
            return p.returncode,(t/'calls').read_text().splitlines() if (t/'calls').exists() else [],(t/'apk-write').exists()

    def test_fresh_current_and_disabled_do_not_install_unselected_components(self):
        for code,disabled in [(None,False),('2026101602',False),('2026101601',True)]:
            with self.subTest(code=code,disabled=disabled):
                status,calls,apk=self.case(code=code,disabled=disabled);self.assertEqual(status,0);self.assertEqual(calls,[]);self.assertTrue(apk)

    def test_only_enabled_exact_old_xiaoai_is_paired_before_apk_update(self):
        for code in ['2026101504','2026101601']:
            with self.subTest(code=code):
                status,calls,apk=self.case(code=code);self.assertEqual(status,0);self.assertTrue(apk);self.assertEqual(len(calls),1);self.assertTrue(calls[0].endswith('/payload/xiaoai.zip'))

    def test_unknown_changed_pending_and_locks_stop_before_writes(self):
        for args in [dict(code='999'),dict(code='2026101601',modified=True),dict(code='2026101601',pending=True),dict(lock=True)]:
            with self.subTest(args=args):
                status,calls,apk=self.case(**args);self.assertNotEqual(status,0);self.assertEqual(calls,[]);self.assertFalse(apk)

    def test_pairing_failure_does_not_update_shared_apk(self):
        status,calls,apk=self.case(code='2026101601',fail=True);self.assertNotEqual(status,0);self.assertEqual(len(calls),1);self.assertFalse(apk)


if __name__=='__main__':unittest.main()
