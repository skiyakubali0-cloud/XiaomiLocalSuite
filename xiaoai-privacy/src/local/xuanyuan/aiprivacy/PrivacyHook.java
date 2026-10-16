package local.xuanyuan.aiprivacy;

import android.content.Context;
import android.os.Binder;
import android.os.Build;
import java.io.FileInputStream;
import java.security.MessageDigest;
import de.robv.android.xposed.*;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

/** Enable the existing OEM AI permission service only for XiaoAI on the verified EEA build. */
public final class PrivacyHook implements IXposedHookLoadPackage {
    private static volatile Context context;
    private static volatile int assistantUid = -1;
    private static final ThreadLocal<Boolean> aiCall = new ThreadLocal<>();

    private static boolean assistant(int uid) {
        if (context == null || uid < 10000) return false;
        if (assistantUid < 0) {
            try { assistantUid = context.getPackageManager().getApplicationInfo("com.miui.voiceassist", 0).uid; }
            catch (Exception e) { return false; }
        }
        return uid == assistantUid;
    }

    private static boolean hash(String file, String expected) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream in = new FileInputStream(file)) {
            byte[] buffer = new byte[65536]; int n;
            while ((n = in.read(buffer)) > 0) digest.update(buffer, 0, n);
        }
        StringBuilder out = new StringBuilder();
        for (byte b : digest.digest()) out.append(String.format("%02x", b & 255));
        return expected.equals(out.toString());
    }

    public void handleLoadPackage(XC_LoadPackage.LoadPackageParam p) throws Throwable {
        if (!"android".equals(p.packageName) || Build.VERSION.SDK_INT != 37
                || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)) return;
        if (!new java.io.File("/product/etc/xuanyuan-ai-privacy.enabled").isFile()) return;
        if (!hash("/system_ext/framework/miui-services.jar", "cef17afe99cfa6396922e2fe1dce6642ec86ddcf141589b8ef4d007d6920ecdb")
                || !hash("/system_ext/framework/miui-framework.jar", "55f69e60be40e1daf88fed21d4bb21cc82410497af329c61ea65df469dbaca30")) {
            XposedBridge.log("XuanyuanAiPrivacy: framework mismatch; inactive"); return;
        }
        Class<?> service = XposedHelpers.findClass("com.miui.server.SecurityManagerService", p.classLoader);
        Class<?> privacy = XposedHelpers.findClass("com.miui.server.security.AgentPrivacyService", p.classLoader);
        // Do not flip IS_INTERNATIONAL_BUILD in system_server: unrelated EEA behavior stays intact.
        XposedBridge.hookAllConstructors(service, new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) {
                if (param.hasThrowable()) return;
                try {
                    context = (Context) XposedHelpers.getObjectField(param.thisObject, "mContext");
                    if (XposedHelpers.getObjectField(param.thisObject, "mAiPrivacy") == null) {
                        Object handler = XposedHelpers.getObjectField(param.thisObject, "mSecurityWriteHandler");
                        XposedHelpers.setObjectField(param.thisObject, "mAiPrivacy",
                                XposedHelpers.newInstance(privacy, context, handler));
                    }
                    XposedBridge.log("XuanyuanAiPrivacy: OEM permission service initialized");
                } catch (Throwable e) { XposedBridge.log("XuanyuanAiPrivacy: init failed " + e); }
            }
        });
        for (String name : new String[]{"accessAppsContentEnable", "accessAppsControlEnable",
                "updateAppContentEnable", "updateAppControlEnable", "shouldDisplayInAISetting"}) {
            final int uidIndex = name.startsWith("update") ? 0 : 1;
            XposedBridge.hookAllMethods(service, name, new XC_MethodHook() {
                protected void beforeHookedMethod(MethodHookParam param) {
                    param.setObjectExtra("previous", aiCall.get());
                    aiCall.set(assistant((Integer) param.args[uidIndex])
                            && XposedHelpers.getObjectField(param.thisObject, "mAiPrivacy") != null);
                }
                protected void afterHookedMethod(MethodHookParam param) {
                    Boolean previous = (Boolean) param.getObjectExtra("previous");
                    if (previous == null) aiCall.remove(); else aiCall.set(previous);
                }
            });
        }
        XposedBridge.hookAllMethods(service, "enforceNotInternationalBuild", new XC_MethodHook() {
            protected void beforeHookedMethod(MethodHookParam param) {
                if (Boolean.TRUE.equals(aiCall.get())) param.setResult(null);
            }
        });
        // KernelSU WebUI's root helper may manage only the above XiaoAI AI endpoints.
        // Ordinary app callers still pass every original package/permission check.
        for (String name : new String[]{"checkGrantPermissionPkg", "enforcePackage"}) {
            XposedBridge.hookAllMethods(service, name, new XC_MethodHook() {
                protected void beforeHookedMethod(MethodHookParam param) {
                    if (Boolean.TRUE.equals(aiCall.get()) && Binder.getCallingUid() == 0) param.setResult(null);
                }
            });
        }
        XposedHelpers.findAndHookMethod("com.miui.server.security.AgentPrivacyUtils", p.classLoader,
                "shouldSkipAIPermissionCheck", Context.class, int.class, new XC_MethodHook() {
            protected void beforeHookedMethod(MethodHookParam param) {
                if (assistant((Integer) param.args[1])) param.setResult(false);
            }
        });
        // Initializing the service must not introduce policy changes for other EEA apps.
        Class<?> local = XposedHelpers.findClass("com.miui.server.SecurityManagerService$LocalService", p.classLoader);
        for (String name : new String[]{"accessAppContentEnable", "accessAppControlEnable"}) {
            XposedBridge.hookAllMethods(local, name, new XC_MethodHook() {
                protected void beforeHookedMethod(MethodHookParam param) {
                    if (!assistant((Integer) param.args[0])) param.setResult(true);
                }
            });
        }
        XposedHelpers.findAndHookMethod("com.android.server.input.InputManagerServiceStubImpl", p.classLoader,
                "shouldCheckPermission", int.class, new XC_MethodHook() {
            protected void beforeHookedMethod(MethodHookParam param) {
                if (assistant((Integer) param.args[0])) param.setResult(true);
            }
        });
        XposedBridge.log("XuanyuanAiPrivacy: exact framework verified; XiaoAI-only hooks installed");
    }
}
