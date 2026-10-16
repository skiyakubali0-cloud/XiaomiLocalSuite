package local.xuanyuan.mipushcompat;

import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import org.json.JSONObject;
import java.io.*;
import java.security.MessageDigest;
import java.util.concurrent.TimeUnit;

/** Read-only gate pinned to the reviewed LSPosed 7912 build. Never edits its DB. */
public final class LegacyFrameworkGate {
    private static final String BASE="/data/adb/modules/zygisk_lsposed/";
    private static boolean hash(String path,String expected)throws Exception{
        MessageDigest d=MessageDigest.getInstance("SHA-256");
        try(InputStream in=new FileInputStream(path)){byte[] b=new byte[65536];int n;while((n=in.read(b))>0)d.update(b,0,n);}
        StringBuilder s=new StringBuilder();for(byte b:d.digest())s.append(String.format("%02x",b&255));return expected.equals(s.toString());
    }
    static boolean statusReady(String raw)throws Exception{
        JSONObject top=new JSONObject(raw),s=top.getJSONObject("data");
        return top.getBoolean("ok")&&"status".equals(top.getString("command"))
            &&s.getBoolean("daemonRunning")&&!s.getBoolean("safeMode")
            &&s.getInt("apiVersion")==102&&s.getInt("versionCode")==7912;
    }
    static boolean scopeReady(SQLiteDatabase db){
        try(Cursor c=db.rawQuery("SELECT 1 FROM modules_state m JOIN scope s ON m.module_pkg_name=s.module_pkg_name AND m.user_id=s.user_id WHERE m.module_pkg_name=? AND m.user_id=0 AND m.enabled=1 AND s.app_pkg_name=? LIMIT 1",new String[]{"local.xuanyuan.mipushcompat","com.mipay.wallet"})){return c.moveToFirst();}
    }
    public static void main(String[] args){
        boolean ready=false;
        try{
            if(args.length!=0||new File(BASE+"disable").exists()||new File(BASE+"remove").exists())throw new IllegalStateException();
            if(!hash(BASE+"daemon.apk","a43bb3554721d650356fa23783a4f3757b85e7c703b836a28eeba6e3cc7c960a")
                ||!hash(BASE+"lspctl","2eaa7c77e82d3b36a6f6899b2eb0e4379a1f0321b81fdb7f9e76f23a00e437e9"))throw new IllegalStateException();
            // status is read-only; both executable objects and response version are pinned.
            Process p=new ProcessBuilder(BASE+"lspctl","--json","status").redirectErrorStream(true).start();
            if(!p.waitFor(12,TimeUnit.SECONDS)){p.destroy();throw new IllegalStateException();}
            byte[] bytes;
            try(InputStream in=p.getInputStream()){bytes=in.readNBytes(32769);}
            if(p.exitValue()!=0||bytes.length>32768||!statusReady(new String(bytes,"UTF-8")))throw new IllegalStateException();
            try(SQLiteDatabase db=SQLiteDatabase.openDatabase("/data/adb/lspd/config/modules_config.db",null,SQLiteDatabase.OPEN_READONLY|SQLiteDatabase.NO_LOCALIZED_COLLATORS)){ready=scopeReady(db);}
        }catch(Exception|LinkageError ignored){}
        System.out.println(ready?"MIPUSH_GATE_READY":"MIPUSH_GATE_NOT_READY");
    }
}
