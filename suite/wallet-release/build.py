"""Build 1.7 wallet-selectable suite from exact verified 1.6.1, offline only."""
from pathlib import Path
import argparse, copy, hashlib, importlib.util, json, os, re, subprocess, tempfile, zipfile
HERE=Path(__file__).resolve().parent
BASE=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('full161',HERE.parent/'full-release/build.py')
full=importlib.util.module_from_spec(spec);spec.loader.exec_module(full)
sha=full.ui.sha;digest=full.ui.digest;once=full.ui.once
SOURCE_SHA='336572b6105722a64c39449f48f6128ec8d6ab7a52915ed5c262e7e1b8142a95'
OLD_APK='f51432bb665ba68c1e5232170baea2d8e9d320e83804000e54b13ebdba4c5858'
WALLET_SHA='d4d717ed5f49b5fd16d9919ccc04c6138267166090c9a8dac9938f1896ad2b8f'
PARENT_CODE='2026101604';CHILD_CODE='2026101603';WALLET_CODE='2026101602'
IDS=full.IDS[:7]+['wallet']+full.IDS[7:]
XIAOAI_NAME='xuanyuan-os4-xiaoai-1.7.6-wallet-api102.zip'
WALLET_NAME='xuanyuan-os4-wallet-1.1-integrated.zip'
APK_NAME='XuanyuanUnifiedCompat-1.6-wallet-selectable-api102.apk'

def archive(source,dest,changes,additions=None):
    additions=additions or {};sums={}
    if set(additions)&set(source.namelist()):raise ValueError('Addition already exists')
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as out:
        entries=[(copy.copy(i),changes.get(i.filename)) for i in source.infolist() if i.filename!='checksums.sha256']
        for name,raw in additions.items():
            i=zipfile.ZipInfo(name);i.compress_type=zipfile.ZIP_DEFLATED;i.external_attr=(0o100755 if name.endswith('.sh') else 0o100644)<<16
            entries.append((i,raw))
        for info,raw in entries:
            info.extract_version=info.create_version=20
            # Source entry size no longer describes rewritten content.
            if isinstance(raw,bytes):info.file_size=len(raw)
            elif isinstance(raw,Path):info.file_size=raw.stat().st_size
            if info.file_size>=2**31:raise ValueError('Classic Android ZIP only')
            h=hashlib.sha256()
            with out.open(info,'w') as dst:
                if isinstance(raw,bytes):dst.write(raw);h.update(raw)
                else:
                    with raw.open('rb') if isinstance(raw,Path) else source.open(info.filename) as stream:
                        for block in iter(lambda:stream.read(1024*1024),b''):dst.write(block);h.update(block)
            sums[info.filename]=h.hexdigest()
        out.writestr('checksums.sha256',''.join(h+'  '+n+'\n' for n,h in sorted(sums.items())))
    full.ui.verify(dest)

def controller(text):
    text=once(text,"ORDER='"+' '.join(full.IDS)+"'","ORDER='"+' '.join(IDS)+"'")
    text=once(text," case \"$OP\" in install|restore) ;; *) fail '未知操作';; esac", " case \"$OP\" in install-wallet) WALLET_MIGRATION=1; OP=install;; install|restore) WALLET_MIGRATION=0;; *) fail '未知操作';; esac")
    old="    wallet) [ \"$(sha /product/app/MITSMClientGlobal/MITSMClientGlobal.apk)\" = 567e8f05e4b2cbc7c203ce5f10672756ea8af0542c3fc5aafaa3e677ebcaa671 ] || fail '钱包首次凭据迁移须单独处理，本套件不生成重置标记';;"
    text=once(text,old,"    wallet) W_MODE=$(wallet_check) || fail '钱包或TSM版本未核对'; [ \"$W_MODE\" != eea ] || [ \"$WALLET_MIGRATION\" = 1 ] || fail '请从统一插件确认首次TSM迁移';;")
    text=once(text,'  "$K" module install "$M/payload/$FILE" || fail "$TITLE 安装失败"','  if [ "$ID" = wallet ]; then wallet_install; else "$K" module install "$M/payload/$FILE" || fail "$TITLE 安装失败"; fi')
    text=once(text,'  xuanyuan-os4-xiaoai\\|2026101601\\|2026101602\\|install) return 0;;','  xuanyuan-os4-xiaoai\\|2026101601\\|2026101602\\|install) return 0;;\n  xuanyuan-os4-wallet\\|2026101101\\|'+WALLET_CODE+'\\|install) return 0;;')
    text=re.sub(r'(xuanyuan-os4-xiaoai\\\|[0-9]+\\\|)2026101602',r'\g<1>'+CHILD_CODE,text)
    line='  xuanyuan-os4-xiaoai\\|2026101601\\|'+CHILD_CODE+'\\|install) return 0;;'
    text=once(text,line,line+'\n  xuanyuan-os4-xiaoai\\|2026101602\\|'+CHILD_CODE+'\\|install) return 0;;')
    text=once(text," echo '任务不会自动接受协议、启用录音/报警或重置钱包。LSPosed作用域需在管理器中核对。'", " echo '任务不操作支付、卡片或全局XMSF。首次EEA TSM迁移仅在明确确认后清除旧TSM数据；已有CN TSM保留。'")
    return once(text,'install_one() {',(HERE/'controller-wallet.sh').read_text()+'\ninstall_one() {')

def preset(text):
    text=once(text,"P_ORDER='"+' '.join(full.IDS)+"'","P_ORDER='"+' '.join(IDS)+"'")
    text=once(text,'plan|apply|migrate|reboot|lsp)', 'plan|apply|apply-wallet|migrate|reboot|lsp)')
    text=text.replace('2026101603',PARENT_CODE).replace('Requires suite 1.6.1','Requires suite 1.7')
    text=once(text,'xiaoai:2026101602','xiaoai:'+CHILD_CODE)
    start=text.index(' if [ "$P_ID" = wallet ]; then\n');end=text.index('\n [ "$P_MISSING" = false ]',start)
    text=text[:start]+''' if [ "$P_ID" = wallet ]; then
  W_MODE=$(wallet_check) || blocked 'Unknown wallet/TSM identity; preserved'
  if [ "$W_MODE" = eea ]; then P_WALLET=true; P_MISSING=true; fi
  if ! present com.mipay.wallet || pkg_disabled com.mipay.wallet; then P_MISSING=true; fi
 fi'''+text[end:]
    text=once(text,'if [ -n "$P_BATCH" ]; then', 'case ",$P_BATCH," in *,wallet,*) ;; *) P_WALLET=false;; esac\nif [ -n "$P_BATCH" ]; then')
    text=once(text,' check preflight install "$P_BATCH"',' check preflight install-wallet "$P_BATCH"')
    text=once(text,' if [ "$ACTION" = apply ]; then',' if [ "$ACTION" = apply ] || [ "$ACTION" = apply-wallet ]; then\n  [ "$P_WALLET" != true ] || [ "$ACTION" = apply-wallet ] || blocked \'Confirm first Xiaomi TSM migration in the unified app\'')
    text=once(text,'  check start install "$P_BATCH"','  if [ "$ACTION" = apply-wallet ]; then check start install-wallet "$P_BATCH"; else check start install "$P_BATCH"; fi')
    return text

def parent_changes(data,apk,child,wallet,wallet_row,wallet_owned,old_privacy,new_privacy):
    apk_hash=sha(apk);out=dict(data)
    for name in ['shared.sh','migrate-legacy.sh','catalog.sh']:
        out[name]=out[name].replace(OLD_APK.encode(),apk_hash.encode())
    out['shared.sh']=once(out['shared.sh'].decode(),' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] ||',' [ "$UNIFIED_LIVE_SHA" = "$UNIFIED_SHA" ] || [ "$UNIFIED_LIVE_SHA" = "'+OLD_APK+'" ] ||').encode()
    out['migrate-legacy.sh']=out['migrate-legacy.sh'].replace(b'xiaoai) REQUIRED=2026101602',('xiaoai) REQUIRED='+CHILD_CODE).encode())
    out['control.sh']=controller(out['control.sh'].decode()).encode()
    out['preset.sh']=preset(out['preset.sh'].decode()).encode()
    catalog=once(out['catalog.sh'].decode(),"CODE='2026101602'", "CODE='"+CHILD_CODE+"'")
    wallet_row=re.sub(r"CODE='[^']+'","CODE='"+WALLET_CODE+"'",wallet_row)
    wallet_row=re.sub(r"SHA='[^']+'","SHA='"+sha(wallet)+"'",wallet_row)
    catalog=once(catalog,'clock)',wallet_row+'\nclock)')
    catalog=once(catalog,'0d0af6c852500930cff982dfa69a9927d8744731c450d7ba6e6857cb3039229c',sha(child))
    out['catalog.sh']=catalog.encode()
    out['owned-packages.txt']+=wallet_owned.encode()
    rows=json.loads(out['webroot/catalog.json']);rows.insert(7,{'id':'wallet','title':'小米钱包与 NFC','kind':'module','module':'xuanyuan-os4-wallet','file':'payload/wallet.zip','description':'国行钱包与TSM，首次迁移明确确认；已有CN数据保留','dependencies':[],'scopes':[],'restoreSupported':False,'restoreLabel':'凭据迁移需核对','restoreNote':'反向切换共享UID仍需单独核对；重复安装不清除CN数据','version':'1.1 integrated','versionCode':WALLET_CODE,'sha256':sha(wallet),'bytes':wallet.stat().st_size,'source':WALLET_NAME})
    for row in rows:
        if row['id']=='xiaoai':row.update(sha256=sha(child),bytes=child.stat().st_size,version='1.7.6 wallet API102',versionCode=CHILD_CODE,source=XIAOAI_NAME)
        elif row['id'] in ['clock','mipush']:row.update(sha256=apk_hash,bytes=apk.stat().st_size,version='1.6 wallet API102',source=APK_NAME)
    if [r['id'] for r in rows]!=IDS:raise ValueError('Catalog order')
    out['webroot/catalog.json']=(json.dumps(rows,ensure_ascii=False,indent=2)+'\n').encode()
    prop=out['module.prop'].decode().replace('version=1.6.1-selectable','version=1.7-wallet-selectable').replace('versionCode=2026101603','versionCode='+PARENT_CODE).replace('10项可选组件，钱包排除','11项可选组件，含钱包首次迁移')
    out['module.prop']=prop.encode()
    custom=out['customize.sh'].decode();start=custom.index('\n# Updating the shared APK');end=custom.index('\nshared_install || abort',start)
    bridge=full.bridge('unused','unused',new_privacy)
    # 1.7 only pairs the reviewed active 1.7.5; other versions require the prior release.
    a=bridge.index(' case "$XC:$XH" in');b=bridge.index('\n esac',a)
    bridge=bridge[:a]+' case "$XC:$XH" in\n  2026101602:'+old_privacy+') PAIR_XIAOAI=true;;\n  '+CHILD_CODE+':'+new_privacy+') ;;\n  *) abort \'请先使用已验证1.6.1升级小爱，再安装1.7；原插件保留\';;'+bridge[b:]
    custom=custom[:start]+bridge+custom[end:]
    out['customize.sh']=custom.encode()
    out['wallet.sh']=(HERE/'wallet.sh').read_bytes()
    out['README.txt']=('小米本地化统一套件1.7：11项按需勾选，含钱包；统一API102 APK1.6/code17。\n'
      '仅xuanyuan EEA OS4.0.0.6.XOAEUXM Android17 API37 owner0；Root/Zygisk/API102 LSPosed/已重启OverlayFS必需。\n'
      '刷入安装管理器；重启后启用一个统一插件，组件配置勾选并应用，按依赖分批重启。\n'
      '钱包默认不选；首次EEA TSM迁移须在应用内确认，会清除小米TSM本地数据及UID关联密钥，已有卡需重录；备份不保证密钥恢复。\n'
      '仅精确EEA TSM UID10214可首次迁移到CN UID1027；已有CN TSM升级不清数据。未知APK/UID拒绝；失败清理一次授权并停止。\n'
      '钱包新APK只在国行TSM生效后安装/启用，不自动打开，不操作支付/卡片，不改Google钱包默认项或全局XMSF。\n'
      '钱包恢复仍拦截共享UID反向切换，避免把已有凭据误当可无损恢复。\n'
      '支付、门卡、真实通知和全新系统首装须单独验证；主机测试不能替代实机。\n').encode()
    out['guides/统一套件1.4说明.txt']=out['README.txt']
    return out

def build(apk,expected,output):
    apk=Path(apk);output=Path(output);source=BASE/'releases/xuanyuan-os4-suite-1.6.1-selectable-nonwallet.zip';wallet_source=BASE/'releases/xuanyuan-os4-wallet-1.0.zip'
    if sha(source)!=SOURCE_SHA or sha(wallet_source)!=WALLET_SHA or sha(apk)!=expected:raise ValueError('Pinned inputs differ')
    sdk=Path(os.environ.get('ANDROID_SDK_ROOT','/opt/homebrew/share/android-commandlinetools'))/'build-tools/36.0.0'
    cert=subprocess.check_output([str(sdk/'apksigner'),'verify','--print-certs',str(apk)],text=True)
    badging=subprocess.check_output([str(sdk/'aapt2'),'dump','badging',str(apk)],text=True)
    if full.CERT not in cert or not re.search(r"^package: name='local.xuanyuan.mipushcompat' versionCode='17'",badging,re.M):raise ValueError('APK signer/package/version')
    with zipfile.ZipFile(apk) as z:
        if z.read('META-INF/xposed/java_init.list').strip()!=b'local.xuanyuan.unified.UnifiedModule' or z.read('META-INF/xposed/scope.list').strip() or b'targetApiVersion=102' not in z.read('META-INF/xposed/module.prop'):raise ValueError('API102 entry')
    targets=[output,output.with_suffix('.build.json'),output.with_name(XIAOAI_NAME),output.with_name(WALLET_NAME)]
    if any(p.exists() for p in targets):raise ValueError('Never overwrite releases')
    full.ui.verify(source);full.ui.verify(wallet_source)
    with tempfile.TemporaryDirectory(prefix='.wallet17-',dir=output.parent) as temp,zipfile.ZipFile(source) as z:
        temp=Path(temp);child=temp/XIAOAI_NAME;wallet=temp/WALLET_NAME;pending=temp/output.name
        with z.open('payload/xiaoai.zip') as stream,zipfile.ZipFile(stream) as x:
            old=x.read('privacy.sh');new=once(old.decode(),OLD_APK+') ;;',OLD_APK+'|'+expected+') ;;').encode()
            prop=x.read('module.prop').replace(b'1.7.5 (full API102)',b'1.7.6 (wallet API102)').replace(b'2026101602',CHILD_CODE.encode())
            archive(x,child,{'privacy.sh':new,'module.prop':prop})
        with zipfile.ZipFile(wallet_source) as w:
            prop=w.read('module.prop').replace(b'version=1.0',b'version=1.1-integrated').replace(b'2026101101',WALLET_CODE.encode())
            archive(w,wallet,{'module.prop':prop,'customize.sh':(HERE/'customize-wallet.sh').read_bytes(),'service.sh':(HERE/'service-wallet.sh').read_bytes(),'README.txt':b'Exact-ROM wallet1.1; explicit first TSM migration consent; existing CN state is never cleared; no payment/card tests.\n'},{'wallet.sh':(HERE/'wallet.sh').read_bytes()})
        with zipfile.ZipFile(BASE/'releases/xuanyuan-os4-suite-1.4.zip') as original:
            wallet_row=next(r for r in original.read('catalog.sh').decode().splitlines() if r.startswith('wallet)'))
            wallet_owned=''.join(r+'\n' for r in original.read('owned-packages.txt').decode().splitlines() if r.startswith('wallet|'))
        data={n:z.read(n) for n in z.namelist() if not n.startswith('payload/') and n not in ['control.sha256','checksums.sha256']}
        data=parent_changes(data,apk,child,wallet,wallet_row,wallet_owned,digest(old),digest(new))
        data['control.sha256']=''.join(digest(raw)+'  '+n+'\n' for n,raw in sorted(data.items()) if n!='customize.sh').encode()
        additions={'wallet.sh':data.pop('wallet.sh'),'payload/wallet.zip':wallet}
        archive(z,pending,{**data,'payload/unified.apk':apk,'payload/xiaoai.zip':child},additions)
        report={'version':'1.7-wallet-selectable','version_code':PARENT_CODE,'sha256':sha(pending),'bytes':pending.stat().st_size,'source_sha256':SOURCE_SHA,'unified_apk_sha256':expected,'xiaoai_sha256':sha(child),'wallet_sha256':sha(wallet),'components':IDS,'wallet_included':True,'wallet_reset_policy':'explicit-first-eea-tsm-only; existing-cn-preserved','global_xmsf_modified':False,'device_tested':False}
        for p,dest in [(pending,output),(child,targets[2]),(wallet,targets[3])]:os.rename(p,dest)
        targets[1].write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('apk');p.add_argument('output');p.add_argument('--apk-sha',required=True);a=p.parse_args();print(json.dumps(build(a.apk,a.apk_sha,a.output),ensure_ascii=False,indent=2))
