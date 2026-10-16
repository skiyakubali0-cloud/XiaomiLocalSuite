"""Host policy and pipe tests; no APK build, root, device, or signing commands."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/local/xuanyuan/unified"
ANDROID = Path(os.environ.get("ANDROID_SDK_ROOT", "/opt/homebrew/share/android-commandlinetools")) / "platforms/android-36/android.jar"

HARNESS = r'''
package local.xuanyuan.unified;
import java.util.*;

public final class PresetPolicyTest {
    static final String BOOT="11111111-1111-4111-8111-111111111111",NEXT="22222222-2222-4222-8222-222222222222";
    static final String[] IDS={"phone","privacy","suggestions","warning","clock"};
    static final Set<String> REQUIRED=new LinkedHashSet<>(Arrays.asList("system","com.android.mms","com.android.soundrecorder",
        "com.miui.audiomonitor","com.miui.yellowpage","com.android.incallui","com.android.providers.telephony","com.android.phone",
        "com.xiaomi.aicr","com.miui.personalassistant","com.miui.securitycenter","com.android.deskclock"));
    static final PresetConfig POLICY=new PresetConfig(PresetSelection.all(),REQUIRED,"local.xuanyuan.mipushcompat");
    static void check(boolean value){if(!value)throw new AssertionError();}
    interface Checked {void run() throws Exception;}
    static void fails(Checked action)throws Exception{boolean failed=false;try{action.run();}catch(IllegalStateException|IllegalArgumentException e){failed=true;}check(failed);}
    static Map<String,Boolean> flags(boolean value){Map<String,Boolean> result=new LinkedHashMap<>();for(String id:IDS)result.put(id,value);return result;}
    static PresetConfig.Plan plan(String state){return plan(state,false,BOOT);}
    static PresetConfig.Plan plan(String state,boolean wallet,String boot){return new PresetConfig.Plan(state,POLICY.selection.componentCsv(),wallet,"fixture diagnostic",boot);}

    static final class Fake implements PresetConfig.Adapter {
        PresetConfig policy=POLICY;
        PresetConfig.Plan plan=PresetPolicyTest.plan("ready"),second;
        boolean connected=true,legacy,remoteFail,readbackFail,localFail,markerFail,backupFail,expireOnFresh,scopeRevoked;
        int walletRequests;
        int planReads,scopeReads,localWrites,remoteWrites,requests,backups,markers,legacyReads,pushReads;
        Set<String> inspected=new LinkedHashSet<>();
        Set<String> installed=new LinkedHashSet<>(REQUIRED),scope=new LinkedHashSet<>(),selected=new LinkedHashSet<>(),requested;
        Map<String,Boolean> local=new LinkedHashMap<>(),remote=new LinkedHashMap<>(),savedLocal,savedRemote;
        Set<String> savedScope,requestBefore;
        String pendingBoot="",requestBoot="";
        List<String> commands=new ArrayList<>(),events=new ArrayList<>(),arguments=new ArrayList<>();
        PresetConfig.ApprovalSession session=new PresetConfig.ApprovalSession();
        Map<String,Object> selection=new LinkedHashMap<>(),compatExtras=new LinkedHashMap<>();
        Fake(){selection.put("enabled",true);selection.put("china_apps",new LinkedHashSet<>(Arrays.asList("user.china")));selection.put("wallet_boot_synced",BOOT);compatExtras.put("unrelated",42);}
        public void requireConnected(){if(!connected)throw new IllegalStateException("disconnected");}
        public PresetConfig.Plan plan(){planReads++;if(expireOnFresh&&planReads>1)session.expire();if(second!=null&&planReads>1)return second;return plan;}
        public Set<String> scope(){if(scopeRevoked&&++scopeReads>1)scope.remove("system");return new LinkedHashSet<>(scope);}
        public boolean installed(String pkg){inspected.add(pkg);return installed.contains(pkg);}
        public boolean legacyInstalled(){legacyReads++;return legacy;}
        public Set<String> selectedPush(){pushReads++;return new LinkedHashSet<>(selected);}
        public Map<String,Boolean> localFlags(){return new LinkedHashMap<>(local);}
        public Map<String,Boolean> remoteFlags(){return new LinkedHashMap<>(remote);}
        public void backup(Map<String,Boolean> l,Map<String,Boolean> r,Set<String> s){
            if(backupFail)throw new IllegalStateException("backup failed");
            if(savedScope==null){backups++;savedLocal=new LinkedHashMap<>(l);savedRemote=new LinkedHashMap<>(r);savedScope=new LinkedHashSet<>(s);events.add("backup");}
        }
        public boolean writeLocal(Map<String,Boolean> f){check(savedScope!=null);localWrites++;events.add("local:"+f);local=new LinkedHashMap<>(f);if(localFail){localFail=false;return false;}return true;}
        public boolean writeRemote(Map<String,Boolean> f){check(savedScope!=null);remoteWrites++;events.add("remote:"+f);remote=new LinkedHashMap<>(f);
            if(remoteFail){remoteFail=false;return false;}if(readbackFail){readbackFail=false;remote.put("phone",!f.getOrDefault("phone",false));}return true;}
        public void markReboot(String boot){markers++;if(markerFail)throw new IllegalStateException("marker failure");pendingBoot=boot;events.add("marker");}
        public void rememberScopeRequest(String boot,Set<String> before){if(!boot.equals(requestBoot)){requestBoot=boot;requestBefore=new LinkedHashSet<>(before);}}
        public boolean rebootPending(String boot){return boot.equals(pendingBoot)||(boot.equals(requestBoot)&&!scope.equals(requestBefore));}
        public void requestScope(Set<String> missing,PresetConfig.ApprovalSession token){check(savedScope!=null&&token==session);requests++;requested=new LinkedHashSet<>(missing);}
        public void requestWalletMigration(PresetConfig.ApprovalSession token){check(token==session);walletRequests++;}
        public PresetConfig.Plan command(String command){
            arguments.add(policy.selection.arguments(command));
            commands.add(command);events.add(command);
            if(command.equals("migrate")){check(remote.equals(flags(false)));check(remoteWrites>0);check(local.equals(flags(false)));return selectedPlan("reboot");}
            if(command.equals("apply")||command.equals("apply-wallet"))return selectedPlan("running");
            throw new AssertionError("unexpected command "+command);
        }
        PresetConfig.Plan selectedPlan(String state){return new PresetConfig.Plan(state,String.join(",",policy.selection.components),false,"",BOOT);}
        void choose(String components,String features){policy=new PresetConfig(PresetSelection.parse(components,features),REQUIRED,"local.xuanyuan.mipushcompat");plan=selectedPlan("ready");}
        String apply()throws Exception{return policy.apply(this,session);}
        String approved()throws Exception{return policy.completeApproved(this,session);}
        void completeScope(){scope.addAll(policy.targets(this));}
        void noFlags(){check(localWrites==0&&remoteWrites==0);}
    }

    public static void main(String[] args)throws Exception{
        Fake a=new Fake();
        switch(args[0]){
            case "required-contract":
                check(new LinkedHashSet<>(Arrays.asList(Features.IDS)).equals(new LinkedHashSet<>(Arrays.asList(IDS))));
                check(Features.scope((key,def)->true).equals(REQUIRED));check(REQUIRED.size()==12);break;
            case "missing":
                a.scope.add("extra.scope");a.apply();a.noFlags();check(a.requests==1&&a.requested.containsAll(REQUIRED));
                check(a.savedScope.equals(a.scope)&&a.savedLocal.isEmpty()&&a.savedRemote.isEmpty());check(!a.rebootPending(BOOT)&&a.markers==0);break;
            case "false-approved":
                a.apply();a.approved();a.noFlags();check(a.requests==1&&a.commands.isEmpty());check(!a.rebootPending(BOOT));break;
            case "partial":
                a.apply();a.scope.add("system");a.approved();a.noFlags();check(a.requests==1&&a.markers==0);check(a.rebootPending(BOOT));break;
            case "rejected":
                a.apply();a.session.expire();a.approved();a.noFlags();check(a.requests==1&&!a.rebootPending(BOOT));break;
            case "expired":
                a.apply();a.completeScope();a.session.expire();a.approved();a.noFlags();check(a.planReads==1&&a.requests==1);break;
            case "unrelated-callback":
                POLICY.completeApproved(a,new PresetConfig.ApprovalSession());a.noFlags();check(a.requests==0&&a.planReads==0);break;
            case "approved":
                a.apply();a.completeScope();a.scope.add("user.extra");String done=a.approved();
                check(a.local.equals(flags(true))&&a.remote.equals(flags(true)));check(a.rebootPending(BOOT)&&!a.rebootPending(NEXT));
                check(a.requests==1&&a.markers==1&&a.scope.contains("user.extra")&&a.backups==1);check(done.contains("重启"));
                int writes=a.remoteWrites;a.approved();check(a.remoteWrites==writes);break;
            case "callback-root-barrier":
                a.apply();a.completeScope();a.plan=plan("reboot");a.approved();a.noFlags();check(a.commands.isEmpty()&&a.requests==1);break;
            case "callback-install-barrier":
                a.apply();a.completeScope();a.plan=plan("install");a.approved();a.noFlags();check(a.commands.isEmpty()&&a.requests==1);break;
            case "noop":
                a.completeScope();a.local=flags(true);a.remote=flags(true);a.apply();a.noFlags();check(a.requests==0&&a.commands.isEmpty()&&a.markers==0&&a.backups==0);break;
            case "wallet-manual":
                a.plan=plan("ready",true,BOOT);a.completeScope();String doneWallet=a.apply();
                check(a.local.equals(flags(true))&&a.remote.equals(flags(true)));check(doneWallet.contains("钱包仍需用户手动"));break;
            case "preserve-push":
                a.selected.add("user.push");a.installed.add("user.push");a.installed.addAll(PresetConfig.OPTIONAL_PUSH);
                a.scope.add("scope.extra");Map<String,Object> original=new LinkedHashMap<>(a.selection);a.apply();a.completeScope();a.approved();
                check(a.selection.equals(original));check(a.scope.contains("scope.extra")&&a.scope.contains("user.push"));check(a.compatExtras.get("unrelated").equals(42));break;
            case "optional-absent":
                a.selected.add("missing.push");Set<String> targets=POLICY.targets(a);check(targets.equals(REQUIRED));
                a.installed.add("com.mipay.wallet");check(POLICY.targets(a).contains("com.mipay.wallet"));
                a.installed.remove("com.android.mms");check(POLICY.targets(a).contains("com.android.mms"));break;
            case "required-absent":
                a.installed.remove("com.android.mms");a.completeScope();fails(a::apply);a.noFlags();check(a.requests==0&&a.markers==0);break;
            case "xmsf-existing":
                a.scope.add(PresetConfig.XMSF);fails(a::apply);a.noFlags();check(a.requests==0&&a.commands.isEmpty());break;
            case "xmsf-selected":
                a.selected.add(PresetConfig.XMSF);a.installed.add(PresetConfig.XMSF);a.selected.add("local.xuanyuan.mipushcompat");a.installed.add("local.xuanyuan.mipushcompat");
                a.apply();check(!a.requested.contains(PresetConfig.XMSF)&&!a.requested.contains("local.xuanyuan.mipushcompat"));break;
            case "remote-failure":case "remote-readback":case "local-failure":case "marker-failure":
                a.completeScope();Map<String,Boolean> before=new LinkedHashMap<>();before.put("clock",false);a.local=new LinkedHashMap<>(before);a.remote=new LinkedHashMap<>(before);
                a.remoteFail=args[0].equals("remote-failure");a.readbackFail=args[0].equals("remote-readback");a.localFail=args[0].equals("local-failure");a.markerFail=args[0].equals("marker-failure");
                fails(a::apply);check(a.local.equals(before)&&a.remote.equals(before)&&!a.rebootPending(BOOT));check(a.savedLocal.equals(before)&&a.savedRemote.equals(before));break;
            case "backup-failure":
                a.completeScope();a.backupFail=true;fails(a::apply);a.noFlags();check(a.requests==0&&a.markers==0);break;
            case "root-barriers":
                for(String state:Arrays.asList("blocked","running","reboot")){Fake f=new Fake();f.plan=plan(state);f.apply();f.noFlags();check(f.requests==0&&f.commands.isEmpty()&&f.markers==0);}break;
            case "root-install":
                a.plan=plan("install");a.installed.clear();a.apply();a.noFlags();check(a.commands.equals(Arrays.asList("apply"))&&a.requests==0);break;
            case "root-migrate":case "root-migrate-already-off":
                a.plan=plan("migrate");a.local=flags(!args[0].endsWith("already-off"));a.remote=new LinkedHashMap<>(a.local);a.legacy=true;
                a.apply();check(a.commands.equals(Arrays.asList("migrate"))&&a.requests==0&&a.remote.equals(flags(false)));
                check(a.events.get(0).equals("backup")&&a.events.indexOf("migrate")>a.events.indexOf("marker"));break;
            case "migration-commit-failure":
                a.plan=plan("migrate");a.local=flags(true);a.remote=flags(true);a.remoteFail=true;fails(a::apply);
                check(a.commands.isEmpty()&&a.local.equals(flags(true))&&a.remote.equals(flags(true)));break;
            case "root-changed":
                a.completeScope();a.second=plan("reboot");fails(a::apply);a.noFlags();break;
            case "scope-revoked":
                a.completeScope();a.scopeRevoked=true;fails(a::apply);a.noFlags();break;
            case "session-expires-during-root":
                a.apply();a.completeScope();a.expireOnFresh=true;fails(a::approved);a.noFlags();break;
            case "wallet-pending-noop":
                a.plan=plan("ready",true,BOOT);a.completeScope();a.local=flags(true);a.remote=flags(true);
                check(a.apply().contains("钱包仍需用户手动"));a.noFlags();check(a.markers==0&&a.commands.isEmpty());break;
            case "legacy-remains":
                a.completeScope();a.legacy=true;fails(a::apply);a.noFlags();break;
            case "disconnected":
                a.connected=false;fails(a::apply);a.noFlags();check(a.planReads==0&&a.requests==0&&a.commands.isEmpty());break;
            case "ids-incomplete":
                a.plan=new PresetConfig.Plan("ready","phone",false,"",BOOT);a.completeScope();fails(a::apply);a.noFlags();break;
            case "boot-marker":
                a.completeScope();a.apply();int bootWrites=a.remoteWrites,markers=a.markers;
                a.apply();check(a.remoteWrites==bootWrites&&a.markers==markers&&a.rebootPending(BOOT));
                a.plan=plan("ready",false,NEXT);a.apply();check(a.remoteWrites==bootWrites&&!a.rebootPending(NEXT));break;
            case "untrusted-fields":
                Object[][] invalid={{"ready;reboot","phone",false,"",BOOT},{"ready","phone,phone",false,"",BOOT},
                    {"ready","phone,$(reboot)",false,"",BOOT},{"ready","phone",1,"",BOOT},{"ready","phone",false,42,BOOT},
                    {"ready","phone",false,"","not-a-boot-id"},{null,"phone",false,"",BOOT}};
                for(Object[] fields:invalid)fails(()->new PresetConfig.Plan(fields[0],fields[1],fields[2],fields[3],fields[4]));break;
            case "selection-closure":
                PresetSelection p=PresetSelection.parse("calendar,phone,xiaoai","clock,privacy,warning");
                check(p.componentCsv().equals("market,assistant,xiaoai,phone,disaster,clock,calendar"));
                check(p.featureCsv().equals("privacy,warning,clock"));
                check(p.requiredComponents().equals(new LinkedHashSet<>(Arrays.asList("market","assistant","xiaoai","disaster","clock"))));
                check(PresetSelection.parse("-","phone,suggestions").componentCsv().equals("market,assistant,xiaoai,phone"));
                check(PresetSelection.parse("-","-").components.isEmpty());
                for(String action:Arrays.asList("plan","apply","migrate","reboot","lsp"))check(p.arguments(action).equals(action+" "+p.componentCsv()+" "+p.featureCsv()));
                check(PresetSelection.parse("-","-").arguments("plan").equals("plan - -"));
                Set<String> selectable=new LinkedHashSet<>(PresetConfig.COMPONENTS);
                check(PresetSelection.all().components.equals(selectable));
                check(PresetSelection.all().featureCsv().equals(String.join(",",IDS)));break;
            case "wallet-selectable":
                check(PresetSelection.COMPONENTS.size()==11&&PresetSelection.all().components.size()==11);
                check(PresetSelection.defaults().components.size()==10&&!PresetSelection.defaults().components.contains("wallet"));
                check(PresetSelection.parse("wallet","-").arguments("apply").equals("apply wallet -"));
                check(!PresetSelection.parse("wallet","-").requiredComponents().contains("wallet"));
                for(String action:Arrays.asList("plan","apply","apply-wallet","migrate","reboot","lsp"))
                    check(PresetSelection.parse("wallet","-").arguments(action).equals(action+" wallet -"));
                check(PresetSelection.parse("wallet,phone,xiaoai","clock,privacy,warning").componentCsv().equals("market,assistant,xiaoai,phone,disaster,wallet,clock"));
                fails(()->PresetSelection.parse("wallet,wallet","-"));break;
            case "wallet-confirmation":
                a.choose("wallet","-");a.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);
                a.apply();a.noFlags();check(a.walletRequests==1&&a.commands.isEmpty()&&a.requests==0);
                a.policy.completeWalletMigration(a,a.session);a.noFlags();
                check(a.commands.equals(Arrays.asList("apply-wallet"))&&a.arguments.equals(Arrays.asList("apply-wallet wallet -")));
                a.policy.completeWalletMigration(a,a.session);check(a.commands.size()==1);break;
            case "wallet-confirmation-required-every-job":
                a.choose("wallet","-");a.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);
                a.apply();a.policy.completeWalletMigration(a,a.session);
                a.session=new PresetConfig.ApprovalSession();a.apply();
                check(a.walletRequests==2&&a.commands.size()==1);a.noFlags();break;
            case "wallet-no-confirmation":
                a.choose("wallet","-");a.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);
                a.policy.completeWalletMigration(a,a.session);a.noFlags();check(a.commands.isEmpty()&&a.planReads==0);break;
            case "wallet-confirmation-expired":
                a.choose("wallet","-");a.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);
                a.apply();a.session.expire();a.policy.completeWalletMigration(a,a.session);
                a.noFlags();check(a.commands.isEmpty());break;
            case "wallet-confirmation-root-changed":
                for(String state:Arrays.asList("blocked","running","reboot","ready")){
                    Fake f=new Fake();f.choose("wallet","-");f.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);
                    f.apply();f.plan=f.selectedPlan(state);f.policy.completeWalletMigration(f,f.session);
                    f.noFlags();check(f.commands.isEmpty());
                }break;
            case "wallet-confirmation-cn-context":
                a.choose("wallet","-");a.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);a.apply();
                a.plan=a.selectedPlan("install");a.policy.completeWalletMigration(a,a.session);
                a.noFlags();check(a.commands.isEmpty());
                a.apply();check(a.commands.equals(Arrays.asList("apply"))&&a.arguments.equals(Arrays.asList("apply wallet -"))&&a.walletRequests==1);break;
            case "wallet-confirmation-disconnected":
                a.choose("wallet","-");a.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);a.apply();
                a.connected=false;fails(()->a.policy.completeWalletMigration(a,a.session));a.noFlags();check(a.commands.isEmpty());break;
            case "wallet-confirmation-plan-mismatch":
                a.choose("wallet","-");a.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);a.apply();
                a.plan=plan("install",true,BOOT);fails(()->a.policy.completeWalletMigration(a,a.session));a.noFlags();check(a.commands.isEmpty());break;
            case "wallet-confirmation-xmsf":
                a.choose("wallet","-");a.plan=new PresetConfig.Plan("install","wallet",true,"",BOOT);a.apply();
                a.scope.add(PresetConfig.XMSF);fails(()->a.policy.completeWalletMigration(a,a.session));a.noFlags();check(a.commands.isEmpty());break;
            case "wallet-unselected-pending":
                a.choose("phone","-");a.plan=new PresetConfig.Plan("install","market,phone",true,"",BOOT);
                fails(a::apply);a.noFlags();check(a.walletRequests==0&&a.commands.isEmpty());break;
            case "selection-whitelist":
                for(String invalidCsv:Arrays.asList("", "phone,phone", "phone,", " phone", "PHONE", "-,-", "phone;reboot", "$(reboot)", "phone clock"))fails(()->PresetSelection.parse(invalidCsv,"-"));
                for(String invalidCsv:Arrays.asList("", "privacy,privacy", "privacy,", "warning ", "wallet", "-,-", "$(reboot)"))fails(()->PresetSelection.parse("-",invalidCsv));
                fails(()->PresetSelection.parse(null,"-"));fails(()->PresetSelection.parse("-",null));
                fails(()->PresetSelection.all().arguments("plan;reboot"));break;
            case "selection-immutable":
                List<String> components=new ArrayList<>(Arrays.asList("phone")),features=new ArrayList<>(Arrays.asList("privacy"));
                PresetSelection frozen=new PresetSelection(components,features);components.clear();features.add("clock");
                check(frozen.componentCsv().equals("market,assistant,xiaoai,phone")&&frozen.featureCsv().equals("privacy"));
                try{frozen.components.clear();throw new AssertionError();}catch(UnsupportedOperationException expected){}
                try{frozen.features.add("clock");throw new AssertionError();}catch(UnsupportedOperationException expected){}break;
            case "selected-scopes-and-flags":
                a.choose("-","clock,privacy");a.installed.clear();a.installed.add("com.android.deskclock");a.scope.add("preserved.extra");
                a.local=flags(true);a.remote=flags(true);a.apply();a.noFlags();
                check(a.requested.equals(new LinkedHashSet<>(Arrays.asList("system","com.android.deskclock")))&&a.pushReads==0);
                check(!a.inspected.contains("com.android.mms")&&!a.inspected.contains("com.xiaomi.aicr"));
                a.completeScope();a.approved();Map<String,Boolean> selectedFlags=flags(false);selectedFlags.put("privacy",true);selectedFlags.put("clock",true);
                check(a.local.equals(selectedFlags)&&a.remote.equals(selectedFlags)&&a.scope.contains("preserved.extra"));
                a.apply();check(a.requests==1&&a.remoteWrites==1);break;
            case "empty-selection-off":
                a.choose("-","-");a.installed.clear();a.legacy=true;a.local=flags(true);a.remote=flags(true);a.scope.add("preserved.extra");
                a.apply();check(a.local.equals(flags(false))&&a.remote.equals(flags(false)));
                check(a.requests==0&&a.commands.isEmpty()&&a.inspected.isEmpty()&&a.legacyReads==0&&a.pushReads==0&&a.markers==1);
                check(a.scope.equals(new LinkedHashSet<>(Arrays.asList("preserved.extra"))));a.apply();check(a.remoteWrites==1);break;
            case "empty-selection-root-barriers":
                for(String state:Arrays.asList("blocked","running","reboot")){Fake f=new Fake();f.choose("-","-");f.plan=f.selectedPlan(state);f.local=flags(true);f.remote=flags(true);f.apply();f.noFlags();check(f.commands.isEmpty()&&f.requests==0);}break;
            case "components-without-features":
                a.choose("phone,wallet","-");a.installed.clear();a.legacy=true;a.plan=a.selectedPlan("install");a.apply();a.noFlags();
                check(a.policy.selection.componentCsv().equals("market,phone,wallet"));
                check(a.commands.equals(Arrays.asList("apply"))&&a.requests==0&&a.legacyReads==0);
                a.plan=a.selectedPlan("ready");a.apply();check(a.local.equals(flags(false))&&a.remote.equals(flags(false))&&a.requests==0);break;
            case "mipush-component-gate":
                a.choose("wallet","-");a.selected.add("user.push");a.installed.add("user.push");a.installed.addAll(PresetConfig.OPTIONAL_PUSH);
                check(a.policy.selection.componentCsv().equals("wallet"));
                check(a.policy.targets(a).isEmpty()&&a.pushReads==0);a.apply();check(a.requests==0);
                a.choose("mipush","-");check(a.policy.targets(a).containsAll(PresetConfig.OPTIONAL_PUSH)&&a.policy.targets(a).contains("user.push"));
                a.apply();check(a.requests==1);a.completeScope();a.approved();check(a.remote.equals(flags(false)));break;
            case "subset-migration-blocked":
                a.choose("-","phone");a.plan=a.selectedPlan("migrate");a.local=flags(true);a.remote=flags(true);a.legacy=true;
                check(a.policy.describe(a,a.plan).contains("固定五项迁移范围"));fails(a::apply);a.noFlags();check(a.commands.isEmpty()&&a.requests==0&&a.backups==0);break;
            case "all-features-minimal-components-migrate":
                a.choose("-",String.join(",",IDS));check(a.policy.selection.components.size()==6);a.plan=a.selectedPlan("migrate");a.legacy=true;
                a.apply();check(a.commands.equals(Arrays.asList("migrate"))&&a.remote.equals(flags(false))&&a.local.equals(flags(false)));break;
            case "selected-ids-exact":
                a.choose("-","clock");a.plan=plan("ready");fails(a::apply);a.noFlags();check(a.requests==0);
                a.plan=new PresetConfig.Plan("ready","",false,"",BOOT);fails(a::apply);a.noFlags();
                a.plan=a.selectedPlan("ready");a.completeScope();a.second=plan("ready");fails(a::apply);a.noFlags();break;
            case "selected-callback-root-changed":
                a.choose("-","privacy");a.apply();a.completeScope();a.plan=plan("ready");fails(a::approved);a.noFlags();check(a.requests==1);break;
            case "selected-approval-expires-on-change":
                a.choose("-","privacy");a.apply();a.completeScope();PresetConfig frozenPolicy=a.policy;a.session.expire();a.choose("-","clock");
                frozenPolicy.completeApproved(a,a.session);a.approved();a.noFlags();check(a.requests==1);break;
            default:throw new AssertionError(args[0]);
        }
        System.out.println("PASS "+args[0]);
    }
}
'''

PIPE_HARNESS = r'''
package local.xuanyuan.unified;
import java.util.*;
import java.io.IOException;
public final class PresetPipeTest {
    public static void main(String[] args)throws Exception {
        List<String> command=Arrays.asList(System.getProperty("java.home")+"/bin/java","-cp",System.getProperty("java.class.path"),"local.xuanyuan.unified.PresetPipeTest$Child",args[0]);
        if(args[0].equals("both")){
            PresetActivity.Capture result=PresetActivity.Capture.run(command,5);
            if(result.exit!=0||result.out.length()!=60000||result.err.length()!=60000)throw new AssertionError();
        }else{
            boolean rejected=false;
            try{PresetActivity.Capture.run(command,args[0].equals("timeout")?1:5);}catch(IOException e){rejected=true;}
            if(!rejected)throw new AssertionError();
        }
    }
    public static final class Child {
        public static void main(String[] args)throws Exception {
            if(args[0].equals("timeout")){System.err.print("fixture-timeout");System.err.flush();Thread.sleep(30000);return;}
            byte[] block=new byte[1000];Arrays.fill(block,(byte)'x');
            for(int i=0;i<(args[0].equals("both")?60:100);i++){System.out.write(block);System.err.write(block);}
        }
    }
}
'''


class PresetPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="preset-policy-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        stub = cls.work / "android/content/SharedPreferences.java"
        stub.parent.mkdir(parents=True)
        stub.write_text("package android.content; public interface SharedPreferences {boolean getBoolean(String k,boolean d);}")
        harness = cls.work / "PresetPolicyTest.java"
        harness.write_text(HARNESS)
        subprocess.run(["javac", "-encoding", "UTF-8", "-d", str(cls.work), str(stub), str(SOURCE / "Features.java"),
                        str(SOURCE / "PresetSelection.java"), str(SOURCE / "PresetConfig.java"), str(harness)], check=True, capture_output=True, text=True)

    def run_case(self, name):
        subprocess.run(["java", "-cp", str(self.work), "local.xuanyuan.unified.PresetPolicyTest", name],
                       check=True, capture_output=True, text=True, timeout=10)


CASES = ["required-contract", "missing", "false-approved", "partial", "rejected", "expired", "unrelated-callback",
         "approved", "callback-root-barrier", "callback-install-barrier", "noop", "wallet-manual", "preserve-push",
         "optional-absent", "required-absent", "xmsf-existing", "xmsf-selected", "remote-failure", "remote-readback",
         "local-failure", "marker-failure", "backup-failure", "root-barriers", "root-install", "root-migrate",
         "root-migrate-already-off", "migration-commit-failure", "root-changed", "legacy-remains", "disconnected",
         "ids-incomplete", "boot-marker", "untrusted-fields", "scope-revoked", "session-expires-during-root", "wallet-pending-noop", "selection-closure", "wallet-selectable", "wallet-confirmation", "wallet-confirmation-required-every-job", "wallet-no-confirmation", "wallet-confirmation-expired", "wallet-confirmation-root-changed", "wallet-confirmation-cn-context", "wallet-confirmation-disconnected", "wallet-confirmation-plan-mismatch", "wallet-confirmation-xmsf", "wallet-unselected-pending", "selection-whitelist", "selection-immutable",
         "selected-scopes-and-flags", "empty-selection-off", "empty-selection-root-barriers", "components-without-features",
         "mipush-component-gate", "subset-migration-blocked", "all-features-minimal-components-migrate", "selected-ids-exact",
         "selected-callback-root-changed", "selected-approval-expires-on-change"]
for _case in CASES:
    setattr(PresetPolicy, "test_" + _case.replace("-", "_"), lambda self, name=_case: self.run_case(name))


@unittest.skipUnless(ANDROID.is_file(), "Android SDK android-36/android.jar unavailable for source type check")
class PresetActivityHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="preset-activity-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        harness = cls.work / "PresetPipeTest.java"
        harness.write_text(PIPE_HARNESS)
        cls.cp = os.pathsep.join(map(str, [cls.work, ANDROID, ROOT / "deps/service.jar", ROOT / "deps/interface.jar"]))
        subprocess.run(["javac", "-encoding", "UTF-8", "-source", "8", "-target", "8", "-cp", cls.cp, "-d", str(cls.work),
                        *[str(SOURCE / name) for name in ("Platform.java", "Features.java", "FrameworkService.java", "PresetSelection.java", "PresetConfig.java", "UiIcon.java", "AppUi.java", "PresetActivity.java")],
                        str(harness)], check=True, capture_output=True, text=True)

    def run_pipe(self, case):
        subprocess.run(["java", "-cp", self.cp, "local.xuanyuan.unified.PresetPipeTest", case],
                       check=True, capture_output=True, text=True, timeout=12)

    def test_both_pipes_drained_before_wait(self):
        self.run_pipe("both")

    def test_excess_output_rejected(self):
        self.run_pipe("overflow")

    def test_timeout_bounded(self):
        self.run_pipe("timeout")


if __name__ == "__main__":
    unittest.main(verbosity=2)
