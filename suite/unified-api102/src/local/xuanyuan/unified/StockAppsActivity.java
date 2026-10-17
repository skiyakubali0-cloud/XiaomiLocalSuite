package local.xuanyuan.unified;

import android.app.*;
import android.content.*;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.*;
import org.json.JSONObject;
import java.util.*;
import java.util.concurrent.*;

/** Explicit user-0 enablement controls; defaults are chosen in system settings. */
public final class StockAppsActivity extends Activity {
    private static final String HELPER="sh /data/adb/modules/xuanyuan-os4-suite/stock-apps.sh ";
    private static final String[] IDS={"phone","sms"};
    private static final String[] TITLES={"原 Google 电话","原 Google 短信"};
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final TextView[] summaries=new TextView[2];
    private final Button[] disable=new Button[2],enable=new Button[2];
    private Button refresh;
    private TextView status;
    private boolean busy,active;

    @Override public void onCreate(Bundle state){
        AppUi.theme(this);super.onCreate(state);
        LinearLayout box=AppUi.page(this,"原电话与短信","切换完成后，按需停用原应用");
        AppUi.space(box,AppUi.text(this,"先安装电话、短信组件并按提示重启，再把小米电话和小米短信设为默认应用。\n禁用仅针对机主用户的原 Google 应用，保留数据；恢复只重新启用，不自动更改默认应用。",13,AppUi.muted(this)),0,14);
        AppUi.button(box,"打开系统默认应用设置",false,()->{
            try{startActivity(new Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS));}
            catch(ActivityNotFoundException error){status.setText("请手动进入系统设置中的默认应用页面。");}
        });
        for(int i=0;i<IDS.length;i++){
            final int index=i;
            AppUi.section(box,TITLES[i]);LinearLayout card=AppUi.card(box);
            summaries[i]=AppUi.text(this,"等待读取…",13,AppUi.muted(this));AppUi.space(card,summaries[i],0,8);
            disable[i]=AppUi.button(card,"禁用"+TITLES[i],false,()->confirmDisable(index));
            enable[i]=AppUi.button(card,"恢复"+TITLES[i],false,()->run("enable",IDS[index]));
        }
        refresh=AppUi.button(box,"重新检查",false,()->run(null,null));
        status=AppUi.text(this,"等待读取…",12,AppUi.muted(this));status.setTextIsSelectable(true);AppUi.space(box,status,8,0);
        setActionsDisabled();
    }
    private void confirmDisable(int index){
        if(busy)return;
        new AlertDialog.Builder(this).setTitle("禁用"+TITLES[index]+"？")
            .setMessage("将保留应用数据。执行前会再次检查小米替代应用、默认应用和模块状态。需要切回时可在本页恢复原应用。")
            .setNegativeButton("取消",null).setPositiveButton("禁用",(d,w)->run("disable",IDS[index])).show();
    }
    private void setActionsDisabled(){
        for(Button button:disable)button.setEnabled(false);
        for(Button button:enable)button.setEnabled(false);
    }
    private String defaultLabel(String holder){
        if(holder.isEmpty())return "尚未设置";
        try{return getPackageManager().getApplicationLabel(getPackageManager().getApplicationInfo(holder,0)).toString();}
        catch(android.content.pm.PackageManager.NameNotFoundException error){return holder;}
    }
    private void run(String action,String id){
        if(busy||!active)return;
        setActionsDisabled();
        if(!Platform.exactRom()){status.setText("当前机型或系统未适配，未执行更改。");return;}
        if(action!=null&&(!Arrays.asList("enable","disable").contains(action)||!Arrays.asList(IDS).contains(id)))return;
        busy=true;refresh.setEnabled(false);status.setText(action==null?"正在读取状态…":"正在执行并核对状态…");
        worker.execute(()->{
            String report="";JSONObject snapshot=null;
            try{
                if(action!=null){
                    PresetActivity.Capture result=PresetActivity.Capture.run(Arrays.asList("su","-c",HELPER+action+" "+id),30);
                    report=(result.exit==0?"操作结果：":"操作未通过：")+result.out+result.err+"\n";
                }
                PresetActivity.Capture current=PresetActivity.Capture.run(Arrays.asList("su","-c",HELPER+"status"),30);
                if(current.exit!=0)throw new IllegalStateException(current.out+current.err);
                snapshot=new JSONObject(current.out);
                // Parse both rows before enabling any action.
                for(String key:IDS){JSONObject row=snapshot.getJSONObject(key);row.getBoolean("installed");row.getBoolean("disabled");row.getBoolean("can_disable");row.getString("holder");}
                report+="禁用需满足：电话组件已生效、替代应用版本匹配且已设为默认。安装或重启后请重新检查。";
            }catch(Exception error){snapshot=null;report+="状态无法确认，操作按钮已停用："+error.getMessage();}
            final String message=report;final JSONObject result=snapshot;
            runOnUiThread(()->{
                busy=false;if(isFinishing()||isDestroyed())return;
                refresh.setEnabled(true);setActionsDisabled();status.setText(message);
                if(result==null){for(TextView summary:summaries)summary.setText("状态未确认");return;}
                try{
                    for(int i=0;i<IDS.length;i++){
                        JSONObject row=result.getJSONObject(IDS[i]);boolean installed=row.getBoolean("installed"),disabled=row.getBoolean("disabled");
                        summaries[i].setText((!installed?"原应用未安装":disabled?"原应用已禁用":"原应用已启用")+"\n当前默认："+defaultLabel(row.getString("holder")));
                        if(active){disable[i].setEnabled(installed&&!disabled&&row.getBoolean("can_disable"));enable[i].setEnabled(installed&&disabled);}
                    }
                }catch(Exception error){setActionsDisabled();status.setText("状态解析失败，请重新检查。");}
            });
        });
    }
    @Override protected void onResume(){super.onResume();active=true;run(null,null);}
    @Override protected void onPause(){active=false;setActionsDisabled();super.onPause();}
    @Override protected void onDestroy(){worker.shutdown();super.onDestroy();}
}
