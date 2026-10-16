package local.xuanyuan.unified;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.*;
import io.github.libxposed.service.*;
import java.io.*;
import java.lang.ref.WeakReference;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import org.json.*;

/** Manual preset entry. Manifest registration and its Settings link belong to the host. */
public final class PresetActivity extends Activity {
    private static volatile XposedService service;
    private static boolean registered;
    private static WeakReference<PresetActivity> current=new WeakReference<>(null);
    private static final String HELPER="sh /data/adb/modules/xuanyuan-os4-suite/preset.sh ";
    private static final String[] TITLES={"小米应用商店","智能助理负一屏","超级小爱","电话、短信与录音","相册与 AI 编辑",
        "天气与街道定位","自然灾害预警与报警定位","小米钱包与 NFC","时钟法定节假日","国行日历","MiPush 推送配置"};
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable poll=()->check();
    private volatile boolean active;
    private boolean busy;
    private PresetConfig.ApprovalSession approval,approved;
    private XposedService approvedService;
    private PresetConfig.ApprovalSession walletConfirmation;
    private AlertDialog walletDialog;
    private String scopeFailure;
    private volatile int generation;
    private String diagnostics="";
    private SharedPreferences compat,metadata;
    private PresetConfig config,approvalConfig;
    private final Map<String,CheckBox> componentChoices=new LinkedHashMap<>(),featureChoices=new LinkedHashMap<>();
    private boolean updatingChoices;
    private TextView status,scopeReview;
    private Button apply,recheck,reboot,lsp,defaults;

    @Override public void onCreate(Bundle state){
        AppUi.theme(this);super.onCreate(state);current=new WeakReference<>(this);
        compat=getSharedPreferences("compat",0);metadata=getSharedPreferences("preset",0);
        Set<String> components=new LinkedHashSet<>(),features=new LinkedHashSet<>();
        for(String id:PresetSelection.COMPONENTS)if(metadata.getBoolean("selected_component_"+id,!"wallet".equals(id)))components.add(id);
        for(String id:PresetSelection.FEATURES)if(metadata.getBoolean("selected_feature_"+id,true))features.add(id);
        config=configuration(new PresetSelection(components,features));
        LinearLayout box=AppUi.page(this,"组件配置","按需选择，再检查并应用");
        AppUi.space(box,AppUi.text(this,"组件按需安装，依赖自动补齐。\n保留现有数据，不自动重置钱包凭据。",12,AppUi.muted(this)),0,14);
        LinearLayout help=AppUi.details(box,"安装与数据说明");
        TextView note=new TextView(this);note.setText("可选择 11 个组件与 5 个兼容功能。新配置默认选择钱包以外的 10 个组件与全部兼容；已有选择沿用。钱包可按需勾选，首次 TSM 迁移须单独确认。取消组件仅跳过安装，不卸载；取消兼容会保存为关闭。首次操作必须点击应用预设。\n依赖组件会自动勾选并锁定；先取消依赖它的兼容或组件，才能取消该组件。\n"
            +"MiPush 的 selection 配置原样保留；新安装不会自动开启中国区路由或加入应用。系统升级后，推送可能需要单独重新扫描并核对每个 APK 的精确证据。\n"
            +"首次迁移若需清除旧小米 TSM 本地数据及绑定密钥，会单独提示确认，现有卡可能失效。不代签隐私协议，不修改 LSPosed 数据库。作用域通过框架正常授权；所有目标确认后才保存兼容开关。配置完成不代表功能业务效果已验收。");note.setTextSize(13);note.setTextColor(AppUi.muted(this));AppUi.space(help,note,8,0);
        AppUi.section(box,"安装组件");LinearLayout componentCard=AppUi.card(box);
        for(int i=0;i<PresetConfig.COMPONENTS.size();i++){
            String id=PresetConfig.COMPONENTS.get(i);CheckBox c=new CheckBox(this);
            componentChoices.put(id,c);AppUi.choice(componentCard,c);c.setOnCheckedChangeListener((button,checked)->selectionChanged());
        }
        AppUi.section(box,"兼容功能");LinearLayout featureCard=AppUi.card(box);
        for(int i=0;i<Features.IDS.length;i++){
            String id=Features.IDS[i];CheckBox c=new CheckBox(this);c.setText(Features.TITLES[i]);
            featureChoices.put(id,c);AppUi.choice(featureCard,c);c.setOnCheckedChangeListener((button,checked)->selectionChanged());
        }
        updateChoices();
        defaults=button(box,"恢复当前默认选择（10 组件 / 5 兼容；钱包按需勾选；仍需点击应用）",()->chooseSelection(PresetSelection.defaults()));
        LinearLayout review=AppUi.details(box,"作用域明细");scopeReview=AppUi.text(this,"检查后显示所需作用域",12,AppUi.muted(this));AppUi.space(review,scopeReview,8,0);
        apply=button(box,"应用预设",()->{
            if(approval!=null)approval.expire();approved=null;scopeFailure=null;approval=new PresetConfig.ApprovalSession();
            approvalConfig=config;PresetConfig.ApprovalSession session=approval;submit((snapshot,a)->snapshot.apply(a,session));
        });
        recheck=button(box,"重新检查（不写配置）",this::check);
        lsp=button(box,"打开 LSPosed 核对/授权作用域",()->submit((snapshot,a)->{
            a.requireConnected();a.plan();a.command("lsp");return "请在 LSPosed 核对本插件的作用域；返回后重新检查。";
        }));
        reboot=button(box,"重启（明确执行）",()->submit((snapshot,a)->{
            a.requireConnected();PresetConfig.Plan p=a.plan();
            if("blocked".equals(p.state)||"running".equals(p.state)||(!"reboot".equals(p.state)&&!a.rebootPending(p.boot)))
                throw new IllegalStateException("当前检查未允许重启；请先处理 Root 状态。");
            a.command("reboot");return "已请求重启；返回后会重新读取实时计划。";
        }));
        LinearLayout result=AppUi.card(box);result.addView(AppUi.text(this,"检查结果",12,AppUi.muted(this)));status=AppUi.text(this,"等待检查…",13,AppUi.ink(this));status.setTextIsSelectable(true);AppUi.space(result,status,7,0);
        if(!registered){registered=true;local.xuanyuan.unified.FrameworkService.addListener(new ServiceListener());}
    }
    private static final class ServiceListener implements XposedServiceHelper.OnServiceListener {
        public void onServiceBind(XposedService s){service=s;refreshCurrent();}
        public void onServiceDied(XposedService s){if(service==s)service=null;refreshCurrent();}
    }
    private static final class ScopeListener implements XposedService.OnScopeEventListener {
        private final WeakReference<PresetActivity> owner;
        private final PresetConfig.ApprovalSession session;
        private final XposedService bound;
        ScopeListener(PresetActivity a,PresetConfig.ApprovalSession session,XposedService bound){owner=new WeakReference<>(a);this.session=session;this.bound=bound;}
        public void onScopeRequestApproved(List<String> ignored){
            PresetActivity a=owner.get();if(a!=null)a.handler.post(()->{
                if(a.active&&a.approval==session&&service==bound){a.approved=session;a.approvedService=bound;a.completeApproval();}
            });
        }
        public void onScopeRequestFailed(String message){
            session.expire();PresetActivity a=owner.get();if(a!=null)a.handler.post(()->{
                if(a.active&&a.approval==session){
                    a.approved=null;a.scopeFailure="作用域授权失败/拒绝："+clean(message)+"。未写兼容开关；可核对后重新检查。";
                    a.status.setText(a.scopeFailure+a.diagnostics());
                }
            });
        }
    }
    private void completeApproval(){
        if(busy||approved==null||approved!=approval||approvalConfig!=config||!active)return;
        PresetConfig.ApprovalSession session=approved;XposedService bound=approvedService;approved=null;
        submit((snapshot,a)->{
            if(service!=bound)throw new IllegalStateException("框架连接已改变；请手动重新检查并应用。");
            return snapshot.completeApproved(a,session);
        });
    }
    private void showWalletConfirmation(){
        final PresetConfig.ApprovalSession session=walletConfirmation;walletConfirmation=null;
        final PresetConfig snapshot=config;final XposedService bound=service;
        if(session==null||session!=approval||approvalConfig!=snapshot||!active||busy)return;
        walletDialog=new AlertDialog.Builder(this)
            .setTitle("确认首次钱包 TSM 迁移")
            .setMessage("首次迁移将清除旧小米 TSM 本地数据及 UID 绑定的 Keystore 密钥，现有卡可能失效。仅在 Root 检查要求首次迁移时执行；以后国行 TSM 已就绪时不重置。\n确认后仅授权本次所选钱包安装任务。是否继续？")
            .setNegativeButton("取消",(dialog,which)->session.expire())
            .setPositiveButton("确认迁移并安装",(dialog,which)->{
                if(!active||busy||approval!=session||config!=snapshot||service!=bound){session.expire();return;}
                submit((selected,a)->selected.completeWalletMigration(a,session));
            })
            .setOnCancelListener(dialog->session.expire()).create();
        walletDialog.setOnDismissListener(dialog->walletDialog=null);walletDialog.show();
    }
    private static void refreshCurrent(){PresetActivity a=current.get();if(a!=null)a.handler.post(()->{if(a.active)a.check();});}
    private Button button(LinearLayout box,String title,Runnable action){return AppUi.button(box,title,"应用预设".equals(title),action);}
    private PresetConfig configuration(PresetSelection selection){return new PresetConfig(selection,Features.scope(ALL_FEATURES),getPackageName());}
    private void updateChoices(){
        updatingChoices=true;
        Set<String> required=config.selection.requiredComponents();int i=0;
        for(Map.Entry<String,CheckBox> entry:componentChoices.entrySet()){
            String id=entry.getKey();CheckBox c=entry.getValue();c.setChecked(config.selection.components.contains(id));
            c.setText(TITLES[i++]+("wallet".equals(id)?"\n可选安装；首次 TSM 迁移须单独确认，现有卡可能失效":required.contains(id)?"\n相关功能需要此组件":""));
            c.setEnabled(!busy&&!required.contains(id));
        }
        for(Map.Entry<String,CheckBox> entry:featureChoices.entrySet()){
            entry.getValue().setChecked(config.selection.features.contains(entry.getKey()));entry.getValue().setEnabled(!busy);
        }
        updatingChoices=false;
    }
    private void selectionChanged(){
        if(updatingChoices)return;
        if(busy){updateChoices();return;}
        Set<String> components=new LinkedHashSet<>(),features=new LinkedHashSet<>();
        for(Map.Entry<String,CheckBox> e:componentChoices.entrySet())if(e.getValue().isChecked())components.add(e.getKey());
        for(Map.Entry<String,CheckBox> e:featureChoices.entrySet())if(e.getValue().isChecked())features.add(e.getKey());
        chooseSelection(new PresetSelection(components,features));
    }
    private void chooseSelection(PresetSelection selection){
        if(busy)return;
        if(selection.equals(config.selection)){updateChoices();return;}
        if(approval!=null)approval.expire();walletConfirmation=null;if(walletDialog!=null)walletDialog.dismiss();approval=null;approved=null;approvalConfig=null;approvedService=null;scopeFailure=null;
        generation++;lastPlan=null;handler.removeCallbacks(poll);config=configuration(selection);updateChoices();
        SharedPreferences.Editor editor=metadata.edit();
        for(String id:PresetSelection.COMPONENTS)editor.putBoolean("selected_component_"+id,selection.components.contains(id));
        for(String id:PresetSelection.FEATURES)editor.putBoolean("selected_feature_"+id,selection.features.contains(id));
        boolean saved=editor.commit();if(!saved)Toast.makeText(this,"选择未能记住；本页选择仍有效。",Toast.LENGTH_LONG).show();
        scopeReview.setText("");status.setText((saved?"选择已记住":"选择未能保存；本页选择仍有效")+"；尚未安装组件或写入兼容开关。请重新检查或点击应用预设。");
    }
    private interface Work {String run(PresetConfig snapshot,AndroidAdapter adapter) throws Exception;}
    private void check(){submit((snapshot,a)->{PresetConfig.Plan p=a.plan();return snapshot.describe(a,p);});}
    private void submit(Work work){
        if(busy||!active)return;
        handler.removeCallbacks(poll);busy=true;setButtons(false);status.setText("正在检查/执行所选步骤…");
        final int epoch=generation;final PresetConfig snapshot=config;
        worker.execute(()->{
            String text;boolean running=false;String review="";
            try{
                ensureActive();if(!Platform.exactRom())throw new IllegalStateException("仅支持机主用户的 xuanyuan / OS4.0.0.6.XOAEUXM / Android 17；未执行 Root 或配置操作。");
                AndroidAdapter a=new AndroidAdapter(snapshot,epoch);a.requireCurrent();text=work.run(snapshot,a);a.requireCurrent();
                review="所选兼容目标作用域（仅检查所选功能；保留已有额外作用域，不加入 XMSF）：\n"+String.join("\n",snapshot.targets(a))
                    +(snapshot.selection.components.contains("mipush")?"\n可选 MiPush 范围仅含已安装应用；加入作用域不会开启中国区推送。":"");
                running=lastPlan!=null&&"running".equals(lastPlan.state);
            }catch(Exception error){text="未完成："+clean(error.getMessage());}
            final String result=text,scopes=review;final boolean repeat=running;
            handler.post(()->{
                busy=false;if(!active||epoch!=generation||isFinishing()||isDestroyed()){if(active)check();return;}
                setButtons(true);scopeReview.setText(scopes);status.setText((scopeFailure==null?result:scopeFailure+"\n"+result)+diagnostics());
                if(walletConfirmation!=null){showWalletConfirmation();return;}
                if(approved!=null){completeApproval();return;}
                if(repeat)handler.postDelayed(poll,3000);
            });
        });
    }
    private void setButtons(boolean enabled){apply.setEnabled(enabled);recheck.setEnabled(enabled);reboot.setEnabled(enabled);lsp.setEnabled(enabled);defaults.setEnabled(enabled);updateChoices();}
    private void ensureActive(){if(!active||Thread.currentThread().isInterrupted())throw new IllegalStateException("页面已离开；请返回后重新检查并手动应用。");}
    @Override protected void onResume(){super.onResume();active=true;generation++;check();}
    @Override protected void onStop(){active=false;walletConfirmation=null;if(walletDialog!=null)walletDialog.dismiss();generation++;if(approval!=null)approval.expire();approved=null;handler.removeCallbacks(poll);super.onStop();}
    @Override protected void onDestroy(){active=false;if(approval!=null)approval.expire();if(current.get()==this)current.clear();handler.removeCallbacksAndMessages(null);worker.shutdown();super.onDestroy();}

    private volatile PresetConfig.Plan lastPlan;
    private final class AndroidAdapter implements PresetConfig.Adapter {
        private final XposedService connected=service;
        private final PresetConfig snapshot;
        private final int epoch;
        AndroidAdapter(PresetConfig snapshot,int epoch){this.snapshot=snapshot;this.epoch=epoch;}
        private void requireCurrent(){ensureActive();if(epoch!=generation)throw new IllegalStateException("选择或页面会话已改变；请重新检查并手动应用。");}
        public void requireConnected(){
            requireCurrent();if(connected==null||connected!=service||connected.getApiVersion()<102)throw new IllegalStateException("需要已连接的 API102 框架服务；请启用本插件后返回重查。");
        }
        public PresetConfig.Plan plan() throws Exception {return command("plan");}
        public Set<String> scope(){requireConnected();return new LinkedHashSet<>(connected.getScope());}
        public boolean installed(String pkg){try{getPackageManager().getPackageInfo(pkg,0);return true;}catch(PackageManager.NameNotFoundException ignored){return false;}}
        public boolean legacyInstalled(){
            for(int i=0;i<Features.IDS.length;i++)if(snapshot.selection.features.contains(Features.IDS[i])&&installed(Features.LEGACY[i]))return true;
            return false;
        }
        public Set<String> selectedPush(){
            SharedPreferences selection=getSharedPreferences("selection",0);
            Set<String> selected=new LinkedHashSet<>(selection.getStringSet("selected",Collections.emptySet()));
            selected.addAll(selection.getStringSet("china_apps",Collections.emptySet()));return selected;
        }
        private Map<String,Boolean> readFlags(SharedPreferences prefs){
            Map<String,?> values=prefs.getAll();Map<String,Boolean> flags=new LinkedHashMap<>();
            for(String id:Features.IDS){Object value=values.get(id);if(value!=null&&!(value instanceof Boolean))throw new IllegalStateException("兼容配置类型异常："+id);if(value!=null)flags.put(id,(Boolean)value);}
            return flags;
        }
        public Map<String,Boolean> localFlags(){return readFlags(compat);}
        public Map<String,Boolean> remoteFlags(){requireConnected();return readFlags(connected.getRemotePreferences("compat"));}
        public void backup(Map<String,Boolean> local,Map<String,Boolean> remote,Set<String> scope){
            requireCurrent();if(metadata.getBoolean("backup_done",false))return;
            SharedPreferences.Editor e=metadata.edit().putStringSet("backup_scope",new LinkedHashSet<>(scope));
            for(String id:Features.IDS){if(local.containsKey(id))e.putBoolean("backup_local_"+id,local.get(id));if(remote.containsKey(id))e.putBoolean("backup_remote_"+id,remote.get(id));}
            if(!e.putBoolean("backup_done",true).commit())throw new IllegalStateException("本地首次备份失败，未写兼容配置。");
        }
        private boolean writeFlags(SharedPreferences prefs,Map<String,Boolean> flags){
            SharedPreferences.Editor e=prefs.edit();for(String id:Features.IDS){if(flags.containsKey(id))e.putBoolean(id,flags.get(id));else e.remove(id);}return e.commit();
        }
        public boolean writeLocal(Map<String,Boolean> flags){return writeFlags(compat,flags);}
        public boolean writeRemote(Map<String,Boolean> flags){requireConnected();return writeFlags(connected.getRemotePreferences("compat"),flags);}
        public void markReboot(String boot){requireCurrent();if(!boot.equals(metadata.getString("pending_boot",""))&&!metadata.edit().putString("pending_boot",boot).commit())throw new IllegalStateException("重启标记保存失败。");}
        public void rememberScopeRequest(String boot,Set<String> scope){
            requireCurrent();if(boot.equals(metadata.getString("scope_request_boot","")))return;
            if(!metadata.edit().putString("scope_request_boot",boot).putStringSet("scope_request_before",new LinkedHashSet<>(scope)).commit())
                throw new IllegalStateException("待授权记录保存失败；没有请求作用域。");
        }
        public boolean rebootPending(String boot){
            if(boot.equals(metadata.getString("pending_boot","")))return true;
            return boot.equals(metadata.getString("scope_request_boot",""))
                &&!scope().equals(metadata.getStringSet("scope_request_before",Collections.emptySet()));
        }
        public void requestScope(Set<String> missing,PresetConfig.ApprovalSession session){
            requireConnected();connected.requestScope(new ArrayList<>(missing),new ScopeListener(PresetActivity.this,session,connected));
        }
        public void requestWalletMigration(PresetConfig.ApprovalSession session){requireCurrent();walletConfirmation=session;}
        public PresetConfig.Plan command(String action) throws Exception {
            requireCurrent();if(!Platform.exactRom())throw new IllegalStateException("系统不受支持。");
            // Only immutable, validated whitelist values can contribute command arguments.
            String command=HELPER+snapshot.selection.arguments(action);
            if(!"plan".equals(action))requireConnected();
            Capture result;
            try{result=Capture.run(Arrays.asList("su","-c",command),"migrate".equals(action)?120:30);}
            catch(Exception error){appendDiagnostics(action+" 捕获失败："+error.getMessage());throw error;}
            appendDiagnostics(action+" exit="+result.exit+"\nstderr:\n"+result.err);
            if(result.exit!=0){appendDiagnostics("stdout:\n"+result.out);throw new IOException("Root 步骤失败；见下方诊断。");}
            // The helper's final nonempty stdout line is its only JSON result.
            String out=result.out.trim();int newline=out.lastIndexOf('\n');
            if(newline>=0)appendDiagnostics("stdout:\n"+out.substring(0,newline));
            String json=out.substring(newline+1);
            try{
                JSONTokener tokener=new JSONTokener(json);Object value=tokener.nextValue();
                if(!(value instanceof JSONObject)||tokener.nextClean()!=0)throw new JSONException("需要单个 JSON 对象");
                JSONObject o=(JSONObject)value;
                if(o.has("job")&&!(o.get("job") instanceof JSONObject))throw new JSONException("job 类型无效");
                PresetConfig.Plan plan=new PresetConfig.Plan(o.get("state"),o.get("ids"),o.get("wallet_pending"),o.get("message"),o.get("boot"));
                requireCurrent();snapshot.requirePlan(plan);
                appendDiagnostics("Root plan: "+plan.state+"\n"+plan.message+(plan.walletPending?"\nwallet_pending=true":""));lastPlan=plan;return plan;
            }catch(JSONException|IllegalArgumentException error){appendDiagnostics("无效 Root stdout:\n"+json);throw new IOException("Root JSON 无效；已停止。",error);}
        }
    }
    private static String clean(String text){return text==null?"":text.replaceAll("[\\p{Cntrl}&&[^\\n\\t]]","?");}
    private synchronized void appendDiagnostics(String text){diagnostics+="\n"+clean(text);if(diagnostics.length()>16000)diagnostics=diagnostics.substring(diagnostics.length()-16000);}
    private synchronized String diagnostics(){return "\n\nRoot 诊断（原文，仅供排查）："+diagnostics;}

    /** Start both drains before waiting. Limits apply even if a child holds pipes open. */
    static final class Capture {
        final String out,err;final int exit;
        Capture(String out,String err,int exit){this.out=out;this.err=err;this.exit=exit;}
        static Capture run(List<String> command,int seconds) throws Exception {
            Process p=new ProcessBuilder(command).start();
            Drain stdout=new Drain(p.getInputStream()),stderr=new Drain(p.getErrorStream());
            Thread out=new Thread(stdout,"preset-stdout"),err=new Thread(stderr,"preset-stderr");
            out.setDaemon(true);err.setDaemon(true);out.start();err.start();
            boolean done=false;
            try{
                done=p.waitFor(seconds,TimeUnit.SECONDS);
                if(!done){p.destroyForcibly();throw new IOException("Root 响应超时；请重查实时计划。stderr: "+stderr.text());}
                out.join(1000);err.join(1000);
                if(out.isAlive()||err.isAlive()||stdout.overflow||stderr.overflow||stdout.error!=null||stderr.error!=null)
                    throw new IOException("Root 输出不完整或超过 64 KiB；已停止。stderr: "+stderr.text());
                return new Capture(stdout.text(),stderr.text(),p.exitValue());
            }finally{
                if(!done)p.destroyForcibly();p.getOutputStream().close();p.getInputStream().close();p.getErrorStream().close();
            }
        }
    }
    private static final class Drain implements Runnable {
        private final InputStream stream;
        private final ByteArrayOutputStream bytes=new ByteArrayOutputStream();
        volatile boolean overflow;volatile IOException error;
        Drain(InputStream stream){this.stream=stream;}
        public void run(){try{byte[] buffer=new byte[4096];int n;while((n=stream.read(buffer))!=-1){synchronized(this){int left=65536-bytes.size();if(n>left)overflow=true;bytes.write(buffer,0,Math.min(n,left));}}}catch(IOException e){error=e;}}
        synchronized String text(){return new String(bytes.toByteArray(),StandardCharsets.UTF_8);}
    }

    // Features.scope reads only getBoolean; no temporary write to compat is needed.
    private static final SharedPreferences ALL_FEATURES=new SharedPreferences(){
        public boolean getBoolean(String k,boolean d){return true;}
        public Map<String,?> getAll(){throw new UnsupportedOperationException();}
        public String getString(String k,String d){throw new UnsupportedOperationException();}
        public Set<String> getStringSet(String k,Set<String> d){throw new UnsupportedOperationException();}
        public int getInt(String k,int d){throw new UnsupportedOperationException();}
        public long getLong(String k,long d){throw new UnsupportedOperationException();}
        public float getFloat(String k,float d){throw new UnsupportedOperationException();}
        public boolean contains(String k){throw new UnsupportedOperationException();}
        public Editor edit(){throw new UnsupportedOperationException();}
        public void registerOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener l){throw new UnsupportedOperationException();}
        public void unregisterOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener l){throw new UnsupportedOperationException();}
    };
}
