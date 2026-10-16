package local.xuanyuan.aiprivacy;

import android.app.AppOpsManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.os.Bundle;
import android.os.Build;
import android.os.IBinder;
import android.os.Looper;
import java.lang.reflect.InvocationTargetException;
import java.util.*;
import org.json.*;

/** Fixed XiaoAI-only root CLI for KernelSU WebUI; the OEM service owns the policy database. */
public final class Manager {
    static final String XIAOAI = "com.miui.voiceassist";
    static Context context;
    static Object security;
    static Class<?> api;
    static int uid;

    static Object call(String method, Class<?>[] types, Object... args) throws Exception {
        return api.getMethod(method, types).invoke(security, args);
    }
    static Map<?, ?> states(int type, List<String> pairs) throws Exception {
        Object result = call(type == 0 ? "accessAppsContentEnable" : "accessAppsControlEnable",
                new Class<?>[]{String.class, int.class, List.class}, XIAOAI, uid, pairs);
        if (!(result instanceof Map)) throw new IllegalStateException("AI 权限服务没有返回有效状态");
        return (Map<?, ?>) result;
    }
    static int mode(int type) throws Exception {
        return (Integer) AppOpsManager.class.getMethod("checkOpNoThrow", int.class, int.class, String.class)
                .invoke(context.getSystemService("appops"), 10054 + type, uid, XIAOAI);
    }
    static Bundle visible(int type, List<String> pairs) throws Exception {
        return (Bundle) call("shouldDisplayInAISetting", new Class<?>[]{int.class, int.class, List.class}, type, uid, pairs);
    }
    static JSONObject status() throws Exception {
        JSONObject result = new JSONObject().put("ready", true);
        for (int type = 0; type < 2; type++) {
            Map<?, ?> map = states(type, Collections.emptyList());
            String state = String.valueOf(map.get(XIAOAI + "~" + uid));
            int mode = mode(type);
            if (!state.equals(mode == 0 ? "1" : "-2"))
                throw new IllegalStateException("系统开关与权限服务不一致，暂不允许修改");
            result.put(type == 0 ? "screen" : "control", mode == 0);
        }
        return result;
    }
    static JSONArray apps(int type) throws Exception {
        List<ApplicationInfo> apps = context.getPackageManager().getInstalledApplications(0);
        apps.sort(Comparator.comparing(a -> a.loadLabel(context.getPackageManager()).toString()));
        List<String> pairs = new ArrayList<>();
        for (ApplicationInfo app : apps) pairs.add(app.packageName + "~" + app.uid);
        Bundle display = visible(type, pairs);
        if (display == null) throw new IllegalStateException("无法读取原厂可管理应用范围");
        Map<?, ?> states = states(type, pairs);
        JSONArray list = new JSONArray();
        for (ApplicationInfo app : apps) {
            String key = app.packageName + "~" + app.uid;
            if (!display.getBoolean(key, false)) continue;
            String state = String.valueOf(states.get(key));
            if (!Arrays.asList("1", "0", "-1", "-2", "-3").contains(state))
                throw new IllegalStateException("未识别的原厂权限状态: " + state);
            list.put(new JSONObject().put("package", app.packageName)
                    .put("label", app.loadLabel(context.getPackageManager()).toString())
                    .put("allowed", state.equals("1") || state.equals("-2"))
                    .put("blocked", state.equals("-1")));
        }
        return list;
    }
    static JSONObject run(String action) throws Exception {
        if ("status".equals(action)) return status();
        String[] parts = action.split(":");
        if (parts.length < 2 || parts.length > 3) throw new IllegalArgumentException("未知操作");
        int type = "screen".equals(parts[0]) ? 0 : "control".equals(parts[0]) ? 1 : -1;
        if (type < 0) throw new IllegalArgumentException("未知功能");
        status(); // Fail closed if backend is missing; never present cosmetic switches.
        if (parts.length == 2 && "list".equals(parts[1])) return new JSONObject().put("apps", apps(type));
        String value = parts[parts.length - 1];
        if (!"on".equals(value) && !"off".equals(value)) throw new IllegalArgumentException("无效开关值");
        boolean enable = "on".equals(value);
        if (parts.length == 2) {
            AppOpsManager.class.getMethod("setMode", int.class, int.class, String.class, int.class)
                    .invoke(context.getSystemService("appops"), 10054 + type, uid, XIAOAI, enable ? 0 : 1);
            if ((mode(type) == 0) != enable) throw new IllegalStateException("系统开关写入后校验失败");
        } else {
            String pkg = parts[1];
            if (!pkg.matches("[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)+")) throw new IllegalArgumentException("无效包名");
            ApplicationInfo target = context.getPackageManager().getApplicationInfo(pkg, 0);
            String key = pkg + "~" + target.uid;
            List<String> pairs = Collections.singletonList(key);
            if (!visible(type, pairs).getBoolean(key, false)) throw new IllegalArgumentException("该应用不在原厂可管理范围");
            if ("-1".equals(String.valueOf(states(type, pairs).get(key))))
                throw new IllegalStateException("该应用受系统策略限制");
            call(type == 0 ? "updateAppContentEnable" : "updateAppControlEnable",
                    new Class<?>[]{int.class, String.class, int.class, boolean.class}, uid, pkg, target.uid, enable);
            String readback = String.valueOf(states(type, pairs).get(key));
            boolean actual = readback.equals("1") || readback.equals("-2");
            if (actual != enable) throw new IllegalStateException("逐应用权限写入后校验失败");
        }
        return status();
    }
    public static void main(String[] args) {
        try {
            if (android.os.Process.myUid() != 0 || args.length != 1 || Build.VERSION.SDK_INT != 37
                    || !"xuanyuan".equals(Build.DEVICE) || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL))
                throw new SecurityException("仅支持指定系统的 KernelSU 模块页面");
            Looper.prepareMainLooper();
            Class<?> thread = Class.forName("android.app.ActivityThread");
            Object current = thread.getMethod("systemMain").invoke(null);
            context = (Context) thread.getMethod("getSystemContext").invoke(current);
            uid = context.getPackageManager().getApplicationInfo(XIAOAI, 0).uid;
            IBinder binder = (IBinder) Class.forName("android.os.ServiceManager").getMethod("getService", String.class).invoke(null, "security");
            security = Class.forName("miui.security.ISecurityManager$Stub").getMethod("asInterface", IBinder.class).invoke(null, binder);
            api = Class.forName("miui.security.ISecurityManager");
            System.out.println(run(args[0]));
            System.exit(0);
        } catch (Throwable e) {
            while (e instanceof InvocationTargetException && e.getCause() != null) e = e.getCause();
            System.err.println("AI 权限服务尚未就绪或操作失败：" + e.getMessage());
            System.exit(1);
        }
    }
}
