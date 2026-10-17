package local.xuanyuan.unified;

import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.*;
import android.widget.*;
import io.github.libxposed.service.*;
import java.lang.ref.WeakReference;
import java.util.*;
import java.util.concurrent.*;

/** One entry for API102 feature switches; original MiPush settings stay separate. */
public final class SettingsActivity extends Activity {
    private static volatile XposedService service;
    private static boolean registered;
    private static WeakReference<SettingsActivity> current=new WeakReference<>(null);
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final List<CompoundButton> choices=new ArrayList<>();
    private SharedPreferences prefs;
    private TextView status;
    private Button save,migrate,restore;
    private boolean busy;
    @Override public void onCreate(Bundle state){
        AppUi.theme(this);super.onCreate(state);current=new WeakReference<>(this);prefs=getSharedPreferences("compat",0);
        LinearLayout box=AppUi.page(this,"小米本地化","熟悉的功能，按你的方式组合");
        LinearLayout connection=AppUi.hero(box);
        status=AppUi.text(this,"正在读取框架状态…",14,0xfff3f6fa);AppUi.space(connection,status,10,0);
        AppUi.section(box,"兼容开关");
        LinearLayout features=AppUi.card(box);
        String[] titles={"电话与短信","AI识屏和智控","小爱建议","自然灾害预警","法定节假日"};
        String[] details={"录音与短信智能识别兼容","超级小爱 · 权限管理","日程、出行与生活提醒","预警与报警定位支持","时钟与作息重复规则"};
        for(int i=0;i<Features.IDS.length;i++){
            if(i>0)AppUi.divider(features);
            Switch c=AppUi.toggle(features,titles[i],details[i],i+1);
            c.setChecked(Features.enabled(prefs,Features.IDS[i]));choices.add(c);
        }
        save=AppUi.button(box,"保存兼容设置",true,()->saveChoices());
        TextView note=AppUi.text(this,"保存后核对作用域，再重启生效",11,AppUi.muted(this));AppUi.space(box,note,0,10);
        AppUi.section(box,"快捷入口");
        LinearLayout shortcuts=new LinearLayout(this);box.addView(shortcuts);
        Button preset=AppUi.shortcut(shortcuts,"组件配置","按需勾选组件",0,()->startActivity(new Intent(this,PresetActivity.class)));preset.setEnabled(Platform.exactRom());
        Button push=AppUi.shortcut(shortcuts,"推送管理","MiPush 与钱包",6,()->startActivity(new Intent().setClassName(getPackageName(),"local.xuanyuan.mipushcompat.Manager")));push.setEnabled(Platform.exactRom());
        Button warning=AppUi.button(box,"预警与报警定位设置  ›",false,()->startActivity(new Intent().setClassName(getPackageName(),"local.xuanyuan.disastercompat.EntryActivity")));warning.setEnabled(Platform.exactRom());
        Button stock=AppUi.button(box,"原电话与短信 · 禁用 / 恢复  ›",false,()->startActivity(new Intent(this,StockAppsActivity.class)));stock.setEnabled(Platform.exactRom());
        LinearLayout advanced=AppUi.details(box,"迁移与恢复");
        AppUi.space(advanced,AppUi.text(this,"已有旧兼容插件时，先迁移并重启，避免重复加载。只处理兼容插件，保留应用数据。",13,AppUi.muted(this)),8,14);
        migrate=AppUi.button(advanced,"迁移旧兼容插件（保留数据）",false,()->confirmMigration(false));
        restore=AppUi.button(advanced,"恢复旧兼容 APK",false,()->confirmMigration(true));
        AppUi.space(box,AppUi.text(this,"LOCAL SUITE  ·  按需启用",11,AppUi.muted(this)),8,0);
        if(!registered){registered=true;local.xuanyuan.unified.FrameworkService.addListener(new XposedServiceHelper.OnServiceListener(){
            public void onServiceBind(XposedService s){service=s;SettingsActivity a=current.get();if(a!=null)a.runOnUiThread(a::showStatus);}
            public void onServiceDied(XposedService s){if(service==s)service=null;SettingsActivity a=current.get();if(a!=null)a.runOnUiThread(a::showStatus);}
        });}
        showStatus();
    }
    private void showStatus(){
        if(!Platform.exactRom()){save.setEnabled(false);migrate.setEnabled(false);restore.setEnabled(false);status.setText("当前设备未适配，兼容与 Root 操作暂不可用。");return;}
        String old=legacyInstalled();status.setText(service==null?"等待框架连接 · 请先在 LSPosed 启用统一插件":
            "框架 API "+service.getApiVersion()+" · "+(old.isEmpty()?"已连接，当前选择以开关为准":"检测到旧兼容 APK：\n"+old+"\n迁移前保留其原配置；不会操作小米应用的数据。"));
    }
    private String legacyInstalled(){StringBuilder out=new StringBuilder();for(String p:Features.LEGACY)try{getPackageManager().getPackageInfo(p,0);out.append(p).append('\n');}catch(PackageManager.NameNotFoundException ignored){}return out.toString().trim();}
    private boolean publish(){
        try{
            if(service==null||service.getApiVersion()<102){status.setText("需要已连接的 API102 框架。");return false;}
            SharedPreferences.Editor e=service.getRemotePreferences("compat").edit();
            for(String id:Features.IDS)e.putBoolean(id,Features.enabled(prefs,id));
            if(!e.commit()){status.setText("配置未同步成功，不能据本地开关判断生效。");return false;}
            return true;
        }catch(RuntimeException e){status.setText("配置同步失败："+e.getClass().getSimpleName());return false;}
    }
    private void saveChoices(){
        if(busy)return;
        for(int i=0;i<Features.IDS.length;i++)if(choices.get(i).isChecked())try{
            getPackageManager().getPackageInfo(Features.LEGACY[i],0);status.setText("请先迁移旧兼容插件并重启；旧 APK 仍在："+Features.LEGACY[i]);return;
        }catch(PackageManager.NameNotFoundException ignored){}
        boolean any=false;for(CompoundButton c:choices)any|=c.isChecked();
        if(any){root("status",result->{if(result.contains("MIGRATION_READY"))persistChoices();else status.setText("迁移后需要先重启，避免旧钩子仍在内存中。");});return;}
        persistChoices();
    }
    private void persistChoices(){
        SharedPreferences.Editor e=prefs.edit();for(int i=0;i<Features.IDS.length;i++)e.putBoolean(Features.IDS[i],choices.get(i).isChecked());if(!e.commit()){status.setText("本地配置保存失败。");return;}
        if(!publish())return;
        Set<String> scope=Features.scope(prefs);
        SharedPreferences push=getSharedPreferences("selection",0);
        scope.addAll(push.getStringSet("selected",Collections.emptySet()));
        scope.addAll(push.getStringSet("china_apps",Collections.emptySet()));
        scope.remove("com.xiaomi.xmsf");scope.remove(getPackageName());
        if(scope.isEmpty()){status.setText("兼容功能已全部关闭；重启后生效。MiPush开关未修改。");return;}
        try{service.requestScope(new ArrayList<>(scope),new XposedService.OnScopeEventListener(){
            public void onScopeRequestApproved(List<String> approved){runOnUiThread(()->status.setText("作用域请求已处理。请在 LSPosed 核对统一插件的实际作用域，再重启；此结果不代表全部业务已验收。"));}
            public void onScopeRequestFailed(String message){runOnUiThread(()->status.setText("作用域未确认："+message+"。请到LSPosed手动勾选并重启。"));}
        });}catch(RuntimeException error){status.setText("请在LSPosed管理器核对作用域并重启。");}
    }
    private void confirmMigration(boolean reverse){
        if(busy)return;
        new AlertDialog.Builder(this).setTitle(reverse?"恢复旧兼容 APK":"迁移旧兼容插件")
            .setMessage(reverse?"先关闭统一兼容功能，再恢复本次备份的旧兼容APK。数据保留；随后需要在LSPosed重新启用旧插件、核对作用域并重启。MiPush设置保留。":"请先在套件中安装/升级电话、小爱、预警组件，再迁移。仅处理本套件已核对的五个旧兼容APK：电话短信、AI权限、小爱建议、预警、时钟。先备份APK，保留数据卸载；不操作小米应用、账号或卡片。完成后先重启，再开启统一兼容功能。")
            .setNegativeButton("取消",null).setPositiveButton("继续",(d,w)->{
                // Deactivate new compatibility before either direction; MiPush prefs are untouched.
                SharedPreferences.Editor e=prefs.edit();for(String id:Features.IDS)e.putBoolean(id,false);e.commit();for(CompoundButton c:choices)c.setChecked(false);
                if(!publish())return;
                root(reverse?"restore":"remove",result->{prefs.edit().putBoolean("migration_pending",true).apply();status.setText(result+"\n请先重启。旧插件恢复后需到LSPosed核对启用与作用域。");});
            }).show();
    }
    private interface Result {void done(String text);}
    private void root(String action,Result result){
        if(busy)return;busy=true;save.setEnabled(false);migrate.setEnabled(false);restore.setEnabled(false);status.setText("正在执行固定迁移步骤…");
        worker.execute(()->{
            String text;boolean ok=false;
            try{
                if(!Arrays.asList("status","remove","restore").contains(action))throw new IllegalArgumentException();
                java.lang.Process p=new ProcessBuilder("su","-c","sh /data/adb/modules/xuanyuan-os4-suite/migrate-legacy.sh "+action).redirectErrorStream(true).start();
                if(!p.waitFor(120,TimeUnit.SECONDS)){p.destroy();throw new IllegalStateException("迁移响应超时，请检查日志，不要重复操作");}
                text=new String(p.getInputStream().readNBytes(65536),"UTF-8");ok=p.exitValue()==0;
            }catch(Exception error){text="迁移未确认："+error.getMessage();}
            final String report=text;final boolean success=ok;
            runOnUiThread(()->{busy=false;if(isFinishing()||isDestroyed())return;save.setEnabled(true);migrate.setEnabled(true);restore.setEnabled(true);if(success)result.done(report);else status.setText(report);});
        });
    }
    @Override protected void onDestroy(){if(current.get()==this)current.clear();worker.shutdown();super.onDestroy();}
}
