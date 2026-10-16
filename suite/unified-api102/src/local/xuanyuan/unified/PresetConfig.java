package local.xuanyuan.unified;

import java.util.*;

/** Preset policy, independent of Android and of scope-approval callbacks. */
public final class PresetConfig {
    public static final String XMSF="com.xiaomi.xmsf";
    public static final List<String> COMPONENTS=PresetSelection.COMPONENTS;
    public static final List<String> OPTIONAL_PUSH=Collections.unmodifiableList(Arrays.asList(
        "com.coolapk.market","com.mipay.wallet","com.miui.mediaeditor","com.miui.virtualsim","com.xiaomi.smarthome"));

    public static final class ApprovalSession {
        private volatile boolean active=true;
        private boolean waiting,walletWaiting;
        public void expire(){active=false;}
        public void requireActive(){if(!active)throw new IllegalStateException("本次应用会话已结束；请手动应用预设。");}
        private synchronized void await(){requireActive();waiting=true;}
        private synchronized void awaitWallet(){requireActive();walletWaiting=true;}
        private synchronized boolean claimWallet(){if(!active||!walletWaiting)return false;walletWaiting=false;return true;}
        private synchronized boolean claim(){if(!active||!waiting)return false;waiting=false;return true;}
    }

    public static final class Plan {
        public final String state,boot,message;
        public final Set<String> ids;
        public final boolean walletPending;
        public Plan(Object state,Object ids,Object walletPending,Object message,Object boot){
            if(!(state instanceof String)||!Arrays.asList("install","running","reboot","migrate","ready","blocked").contains(state)
                ||!(ids instanceof String)||!(walletPending instanceof Boolean)||!(message instanceof String)
                ||((String)message).length()>8192||!(boot instanceof String)
                ||!((String)boot).matches("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"))
                throw new IllegalArgumentException("Root plan 字段无效");
            Set<String> parsed=new LinkedHashSet<>();
            if(!((String)ids).isEmpty())for(String id:((String)ids).split(",",-1))
                if(!COMPONENTS.contains(id)||!parsed.add(id))throw new IllegalArgumentException("Root plan 组件无效");
            this.state=(String)state;this.ids=Collections.unmodifiableSet(parsed);this.walletPending=(Boolean)walletPending;
            this.message=(String)message;this.boot=(String)boot;
        }
    }

    public interface Adapter {
        void requireConnected();
        Plan plan() throws Exception;
        Set<String> scope();
        boolean installed(String pkg);
        boolean legacyInstalled();
        Set<String> selectedPush();
        Map<String,Boolean> localFlags();
        Map<String,Boolean> remoteFlags();
        void backup(Map<String,Boolean> local,Map<String,Boolean> remote,Set<String> scope) throws Exception;
        boolean writeLocal(Map<String,Boolean> flags);
        boolean writeRemote(Map<String,Boolean> flags);
        void markReboot(String boot) throws Exception;
        void rememberScopeRequest(String boot,Set<String> scope) throws Exception;
        boolean rebootPending(String boot);
        void requestScope(Set<String> missing,ApprovalSession session);
        void requestWalletMigration(ApprovalSession session);
        Plan command(String action) throws Exception;
    }

    public final PresetSelection selection;
    private final Set<String> featureScopes;
    private final String ownPackage;
    public PresetConfig(PresetSelection selection,Set<String> scopes,String ownPackage){
        this.selection=Objects.requireNonNull(selection);featureScopes=new LinkedHashSet<>();this.ownPackage=ownPackage;
        for(String pkg:scopes)if(selection.features.contains(Features.featureFor(pkg)))featureScopes.add(pkg);
    }
    public void requirePlan(Plan plan){
        if(!plan.ids.equals(selection.components))throw new IllegalStateException("Root plan 与所选组件及依赖不一致，已停止。");
    }
    private boolean selectedLegacy(Adapter a){return !selection.features.isEmpty()&&a.legacyInstalled();}
    public Set<String> targets(Adapter a){
        Set<String> targets=new LinkedHashSet<>(featureScopes);
        if(selection.components.contains("mipush")){
            Set<String> extras=new LinkedHashSet<>(OPTIONAL_PUSH);extras.addAll(a.selectedPush());
            extras.removeIf(pkg->!a.installed(pkg));targets.addAll(extras);
        }
        targets.remove(XMSF);targets.remove(ownPackage);
        return targets;
    }
    private void requireInstalled(Adapter a){
        Set<String> absent=new LinkedHashSet<>();
        for(String pkg:featureScopes)if(!"system".equals(pkg)&&!a.installed(pkg))absent.add(pkg);
        if(!absent.isEmpty())throw new IllegalStateException("必需组件尚未安装，禁止开启所选兼容：\n"+String.join("\n",absent));
    }
    public Set<String> missing(Adapter a){Set<String> missing=targets(a);missing.removeAll(checkedScope(a));return missing;}
    private Set<String> checkedScope(Adapter a){
        Set<String> scope=new LinkedHashSet<>(a.scope());
        if(scope.contains(XMSF))throw new IllegalStateException("本插件作用域包含 XMSF；请在 LSPosed 中人工核对并移除本插件的 XMSF 作用域后重查。");
        return scope;
    }
    private Map<String,Boolean> flags(boolean value){Map<String,Boolean> flags=new LinkedHashMap<>();for(String id:PresetSelection.FEATURES)flags.put(id,value&&selection.features.contains(id));return flags;}
    public String describe(Adapter a,Plan p){
        requirePlan(p);
        String wallet=p.walletPending?"\n钱包仍需用户手动完成；不会重置钱包/TSM 或代签协议。":"";
        switch(p.state){
            case "install":return "组件需要安装/升级。点击应用预设后才开始。"+(p.walletPending?"首次钱包 TSM 迁移需单独确认：将清除旧小米 TSM 本地数据及绑定密钥，现有卡可能失效。":"");
            case "running":return "组件安装任务运行中；页面打开时每 3 秒重查。";
            case "migrate":return selection.features.containsAll(PresetSelection.FEATURES)
                ?"检测到所选旧兼容插件。点击应用预设：先提交并核实五个兼容开关关闭，再迁移；随后重启。"
                :"部分兼容选择不能执行固定五项迁移；请先人工核对现有固定五项迁移范围，或选择全部五项兼容后重新检查。未移除任何旧插件。";
            case "reboot":return "Root 步骤要求重启。请点击重启，返回后重新检查。";
            case "blocked":return "Root 检查阻止操作。";
            default:
                a.requireConnected();requireInstalled(a);
                Set<String> missing=missing(a);
                if(!missing.isEmpty())return "等待作用域授权/应用预设：\n"+String.join("\n",missing)+"\n仅当前应用会话可在授权后核实并继续；返回页面请重新检查并手动应用。"+wallet;
                if(selectedLegacy(a))return "旧兼容 APK 仍存在，禁止开启统一兼容；请重新检查 Root 迁移状态。";
                if(!flags(true).equals(a.localFlags())||!flags(true).equals(a.remoteFlags()))return "作用域已核实；点击应用预设以保存所选兼容开关（未选项关闭）。"+wallet;
                return (a.rebootPending(p.boot)?"配置已保存，仍需重启（本次启动尚未改变）。":"配置与作用域已核实，无需重复安装或重启。功能业务效果尚未验收。")+wallet;
        }
    }

    /** Called only by the explicit Apply button, never by resume, polling or callbacks. */
    public String apply(Adapter a,ApprovalSession session) throws Exception {
        session.requireActive();
        a.requireConnected();Plan p=a.plan();requirePlan(p);Set<String> scope=checkedScope(a);
        if(Arrays.asList("blocked","running","reboot").contains(p.state))return describe(a,p);
        if("install".equals(p.state)){
            if(p.walletPending){
                if(!selection.components.contains("wallet"))throw new IllegalStateException("钱包未选中但 Root 要求钱包迁移，已停止。");
                session.awaitWallet();a.requestWalletMigration(session);
                return "等待首次钱包 TSM 迁移确认；尚未安装或迁移。取消后不执行。";
            }
            a.requireConnected();session.requireActive();return describe(a,a.command("apply"));
        }
        if("migrate".equals(p.state)){
            if(!selection.features.containsAll(PresetSelection.FEATURES))
                throw new IllegalStateException("部分兼容选择不能执行固定五项迁移；请先人工核对现有固定五项迁移范围，或选择全部五项兼容后重新检查。未移除任何旧插件。");
            // Force an OFF commit/readback even when the previous values were OFF.
            saveFlags(a,p,scope,false,true,session);a.requireConnected();session.requireActive();
            return describe(a,a.command("migrate"));
        }
        if(selectedLegacy(a))throw new IllegalStateException("旧兼容 APK 尚未移除，不能开启统一兼容。");
        requireInstalled(a);
        Set<String> missing=targets(a);missing.removeAll(scope);
        if(!missing.isEmpty()){
            a.backup(a.localFlags(),a.remoteFlags(),scope);a.rememberScopeRequest(p.boot,scope);a.requireConnected();session.await();
            a.requestScope(missing,session);
            return "等待 LSPosed 作用域授权；尚未写入兼容开关。本次页面会话内授权完成后会核实并继续；拒绝或离开页面后请重新检查并手动应用。"
                +(p.walletPending?"\n钱包仍需用户手动完成；不影响所选兼容配置。":"");
        }
        return enableReady(a,p,session);
    }
    /** Only the current explicit wallet dialog may consume this one-shot session. */
    public String completeWalletMigration(Adapter a,ApprovalSession session) throws Exception {
        if(!session.claimWallet())return "钱包迁移确认已结束或已处理；未执行迁移。";
        a.requireConnected();Plan p=a.plan();requirePlan(p);checkedScope(a);
        if(!"install".equals(p.state)||!p.walletPending)return describe(a,p);
        if(!selection.components.contains("wallet"))throw new IllegalStateException("钱包未选中，已停止迁移。");
        a.requireConnected();session.requireActive();
        return describe(a,a.command("apply-wallet"));
    }
    /** Approval is a trigger only. Never requests scope, installs or migrates. */
    public String completeApproved(Adapter a,ApprovalSession session) throws Exception {
        if(!session.claim())return "授权会话已结束或已处理；未写配置。";
        a.requireConnected();Plan p=a.plan();requirePlan(p);checkedScope(a);
        if(!"ready".equals(p.state))return describe(a,p);
        if(selectedLegacy(a))throw new IllegalStateException("Root 配置不完整或旧兼容 APK 仍存在；未写配置。");
        requireInstalled(a);
        if(!missing(a).isEmpty())return "授权后实际作用域仍不完整；未写兼容开关。请核对后重新检查，手动应用。";
        return enableReady(a,p,session);
    }
    private String enableReady(Adapter a,Plan p,ApprovalSession session) throws Exception {
        // Re-read both root readiness and actual scope immediately before enabling hooks.
        Plan fresh=a.plan();requirePlan(fresh);a.requireConnected();
        if(!"ready".equals(fresh.state)||!p.boot.equals(fresh.boot)||selectedLegacy(a))
            throw new IllegalStateException("Root 就绪状态已改变，请重新检查。");
        requireInstalled(a);
        if(!missing(a).isEmpty())throw new IllegalStateException("实际作用域不完整，未写入兼容开关。");
        session.requireActive();saveFlags(a,fresh,checkedScope(a),true,false,session);
        return describe(a,fresh);
    }
    private void saveFlags(Adapter a,Plan p,Set<String> scope,boolean enabled,boolean force,ApprovalSession session) throws Exception {
        Map<String,Boolean> local=new LinkedHashMap<>(a.localFlags()),remote=new LinkedHashMap<>(a.remoteFlags()),desired=flags(enabled);
        if(!force&&desired.equals(local)&&desired.equals(remote))return;
        a.backup(local,remote,scope);a.requireConnected();session.requireActive();
        try{
            if(!a.writeRemote(desired)||!desired.equals(a.remoteFlags()))throw new IllegalStateException("远程提交/回读失败");
            session.requireActive();
            if(!a.writeLocal(desired)||!desired.equals(a.localFlags()))throw new IllegalStateException("本地提交/回读失败");
            a.markReboot(p.boot);
        }catch(Exception error){
            boolean remoteRestored=false,localRestored=false;
            try{remoteRestored=a.writeRemote(remote)&&remote.equals(a.remoteFlags());}catch(RuntimeException ignored){}
            try{localRestored=a.writeLocal(local)&&local.equals(a.localFlags());}catch(RuntimeException ignored){}
            throw new IllegalStateException("配置失败，未报告成功；本地恢复="+localRestored+"，远程恢复="+remoteRestored+"；请重查。",error);
        }
    }
}
