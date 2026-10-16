package local.xuanyuan.mipushcompat;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.os.PowerManager;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;

/** Explicit wallet-only background/boot setup. No credentials or XMSF settings. */
public final class WalletRecovery {
    public static final String PACKAGE="com.mipay.wallet";
    private static final String CONFIGURED="wallet_background_configured", OWNED="wallet_battery_owned";
    private static final String CLI="/data/adb/modules/zygisk_vector/cli --json ";
    private static SharedPreferences prefs(Context c){return c.getSharedPreferences("selection",0);}
    public static boolean configured(Context c){return prefs(c).getBoolean(CONFIGURED,false);}
    public static boolean exact(Context c){
        try{
            if(android.os.Process.myUid()/100000!=0)return false;
            PackageInfo p=c.getPackageManager().getPackageInfo(PACKAGE,0);
            return p.applicationInfo.enabled&&(p.applicationInfo.splitSourceDirs==null||p.applicationInfo.splitSourceDirs.length==0)&&ExactChinaProfile.verify(PACKAGE,p.getLongVersionCode(),Arrays.asList(p.applicationInfo.sourceDir));
        }catch(Exception e){return false;}
    }
    public static boolean ready(Context c){
        PowerManager power=(PowerManager)c.getSystemService(Context.POWER_SERVICE);
        return configured(c)&&exact(c)&&power!=null&&power.isIgnoringBatteryOptimizations(PACKAGE);
    }
    private static String root(String command)throws Exception{
        Process p=new ProcessBuilder("su","-c",command).redirectErrorStream(true).start();
        ByteArrayOutputStream data=new ByteArrayOutputStream();
        Thread read=new Thread(()->{try(InputStream in=p.getInputStream()){byte[] b=new byte[4096];int n;while((n=in.read(b))>0){if(data.size()+n>262144)break;data.write(b,0,n);}}catch(Exception ignored){}});
        read.start();
        if(!p.waitFor(35,TimeUnit.SECONDS)){p.destroy();throw new IllegalStateException("Root request timed out");}
        read.join(2000);
        if(read.isAlive())throw new IllegalStateException("Root output incomplete");
        if(p.exitValue()!=0)throw new IllegalStateException("Root command failed");
        return data.toString("UTF-8");
    }
    public static void prepare(Context c)throws Exception{
        if(!exact(c))throw new IllegalStateException("Wallet APK mismatch");
        SharedPreferences p=prefs(c);
        boolean already=((PowerManager)c.getSystemService(Context.POWER_SERVICE)).isIgnoringBatteryOptimizations(PACKAGE);
        // Persist ownership before mutation, so a failure can still be restored.
        if(!p.edit().putBoolean(OWNED,p.getBoolean(OWNED,false)||!already).commit())throw new IllegalStateException("Save failed");
        root("cmd deviceidle whitelist +com.mipay.wallet");
        if(!((PowerManager)c.getSystemService(Context.POWER_SERVICE)).isIgnoringBatteryOptimizations(PACKAGE))throw new IllegalStateException("Battery exemption not applied");
        if(!p.edit().putBoolean(CONFIGURED,true).commit())throw new IllegalStateException("Save failed");
    }
    public static void restore(Context c)throws Exception{
        SharedPreferences p=prefs(c);
        if(!configured(c)&&!p.getBoolean(OWNED,false))return;
        root("am force-stop --user 0 com.mipay.wallet");
        if(p.getBoolean(OWNED,false))root("cmd deviceidle whitelist -com.mipay.wallet");
        if(!p.edit().remove(CONFIGURED).remove(OWNED).remove("wallet_boot_synced").commit())throw new IllegalStateException("Save failed");
    }
    public static void stop(Context c)throws Exception{
        if(!exact(c))throw new IllegalStateException("Wallet APK mismatch");
        root("am force-stop --user 0 com.mipay.wallet");
    }
    public static boolean frameworkReady(Context c)throws Exception{
        if(!"yes".equals(root("if [ -f /data/adb/modules/zygisk_vector/cli ]; then echo yes; else echo no; fi").trim())){
            String path=c.getApplicationInfo().sourceDir;
            String quoted="'"+path.replace("'","'\"'\"'")+"'";
            String out=root("CLASSPATH="+quoted+" /system/bin/app_process /system/bin local.xuanyuan.mipushcompat.LegacyFrameworkGate");
            return "MIPUSH_GATE_READY".equals(out.trim());
        }
        JSONObject modules=new JSONObject(root(CLI+"modules ls"));
        if(!modules.optBoolean("success"))return false;
        JSONArray rows=modules.getJSONArray("data");boolean enabled=false;
        for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);if("local.xuanyuan.mipushcompat".equals(row.optString("PACKAGE"))&&"enabled".equals(row.optString("STATUS")))enabled=true;}
        if(!enabled)return false;
        JSONObject scopes=new JSONObject(root(CLI+"scope ls local.xuanyuan.mipushcompat"));
        if(!scopes.optBoolean("success"))return false;
        rows=scopes.getJSONArray("data");
        for(int i=0;i<rows.length();i++){JSONObject row=rows.getJSONObject(i);if(PACKAGE.equals(row.optString("APP_PACKAGE"))&&row.optInt("USER_ID",-1)==0)return true;}
        return false;
    }
    private static boolean bootEvidenceCurrent(Context c){
        try {
            PackageInfo p=c.getPackageManager().getPackageInfo(PACKAGE,0);
            return p.lastUpdateTime==prefs(c).getLong("wallet_boot_updated",-1)
                && SdkScanner.sourceIdentity(Arrays.asList(p.applicationInfo.sourceDir)).equals(prefs(c).getString("wallet_boot_identity",""));
        } catch(Exception e){return false;}
    }
    public static boolean start(Context c)throws Exception{
        if(!prefs(c).getBoolean("wallet_boot_synced",false)||!ready(c)||!bootEvidenceCurrent(c)||!ChinaApps.requested(prefs(c),PACKAGE)||!frameworkReady(c))return false;
        String result=root("am startservice --user 0 -n com.mipay.wallet/com.xiaomi.push.service.XMPushService");
        if(result.contains("Error")||result.contains("Exception"))throw new IllegalStateException("Wallet service start rejected");
        return true;
    }
}
