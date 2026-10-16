package local.xuanyuan.suggestioncompat;

import android.app.Activity;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import java.io.FileInputStream;
import java.security.MessageDigest;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public final class SuggestionHook implements IXposedHookLoadPackage {
    private static final String PREFIX = "com.xiaomi.aicr.";
    public void handleLoadPackage(final XC_LoadPackage.LoadPackageParam p) throws Throwable {
        boolean assistant = "com.miui.personalassistant".equals(p.packageName);
        if ((!assistant && !"com.xiaomi.aicr".equals(p.packageName)) || Build.VERSION.SDK_INT != 37
                || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)) return;
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream in = new FileInputStream(p.appInfo.sourceDir)) {
            byte[] buffer = new byte[65536]; int n;
            while ((n = in.read(buffer)) != -1) digest.update(buffer, 0, n);
        }
        StringBuilder hash = new StringBuilder();
        for (byte b : digest.digest()) hash.append(String.format("%02x", b & 255));
        String expected = assistant ? "6ecb326cd18351e032f5fe493c1bc1bb28e417bd03954e5133c237bcffc43562"
            : "f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520";
        if (!expected.equals(hash.toString())) {
            XposedBridge.log("XuanyuanSuggestion: unsupported AI engine APK; no changes"); return;
        }
        if (assistant) {
            XposedHelpers.findAndHookMethod(Activity.class, "startActivityForResult",
                Intent.class, int.class, Bundle.class, new XC_MethodHook() {
                    protected void beforeHookedMethod(MethodHookParam param) {
                        Intent original = (Intent) param.args[0];
                        if (original == null || original.getComponent() != null
                            || !Intent.ACTION_SEARCH.equals(original.getAction())
                            || !"com.android.calendar".equals(original.getPackage())) return;
                        Activity activity = (Activity) param.thisObject;
                        if (original.resolveActivity(activity.getPackageManager()) != null) return;
                        Intent replacement = new Intent(original).setPackage("com.xiaomi.calendar");
                        if (replacement.resolveActivity(activity.getPackageManager()) == null) return;
                        param.args[0] = replacement;
                        XposedBridge.log("XuanyuanSuggestion: calendar SEARCH routed to installed Xiaomi Calendar");
                    }
                });
            XposedBridge.log("XuanyuanSuggestion: exact assistant verified; calendar SEARCH fallback installed");
            return;
        }
        XposedHelpers.findAndHookMethod("ws1", p.classLoader, "b", new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) {
                if (param.hasThrowable()) return;
                Class<?> level = XposedHelpers.findClass("fs1", p.classLoader);
                boolean lite = (Boolean) XposedHelpers.callStaticMethod(XposedHelpers.findClass("zs1", p.classLoader), "m")
                    || XposedHelpers.getStaticBooleanField(level, "f")
                    || ((Integer) XposedHelpers.callStaticMethod(level, "b")) == XposedHelpers.getStaticIntField(level, "e");
                int ram = XposedHelpers.getStaticIntField(level, "g");
                lite |= ram >= 1 && ram < 5;
                if (!lite) param.setResult(true);
            }
        });
        XposedBridge.log("XuanyuanSuggestion: exact EEA engine verified; intention capability enabled, consent unchanged");
    }
}
