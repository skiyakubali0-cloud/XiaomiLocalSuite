package local.xuanyuan.smscompat;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.os.Build;
import android.os.Bundle;
import java.io.FileInputStream;
import java.security.MessageDigest;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public final class SmsHook implements IXposedHookLoadPackage {
    public void handleLoadPackage(final XC_LoadPackage.LoadPackageParam p) throws Throwable {
        if (Build.VERSION.SDK_INT != 37
                || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)) return;
        String expected;
        switch (p.packageName) {
            case "com.android.providers.telephony": expected = "c5aaafabb1679f7c2a7edd23c69366548bb5bf0591bd2293c15623522db4f9b5"; break;
            case "com.android.mms": expected = "0a59d7338d31c70a0fb8f5477f264033d77abf4101f2897a60ffbabacbb1da14"; break;
            case "com.miui.audiomonitor": expected = "83133a62f37cefe873075064d39c5e176e768af251d678438a242116be8178b1"; break;
            case "com.android.soundrecorder": expected = "26cc4ef1ba6dc07013837a0b12fb91a31eff340f0b4496a91cc48387ebb72dcc"; break;
            case "com.android.incallui": expected = "590f2ed0e5e0923e79a452d72cd9c6e9783e1dde4cb8c987355ebcfce7b8c3bd"; break;
            case "com.miui.yellowpage": expected = "e07e59b9d9a99b0cce4bf06b9734002016b1c3bebe701c6ee368cdc8161cb733"; break;
            default: return;
        }
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream in = new FileInputStream(p.appInfo.sourceDir)) {
            byte[] buffer = new byte[65536];
            int n;
            while ((n = in.read(buffer)) != -1) digest.update(buffer, 0, n);
        }
        StringBuilder hash = new StringBuilder();
        for (byte b : digest.digest()) hash.append(String.format("%02x", b & 255));
        if (!expected.equals(hash.toString())) {
            XposedBridge.log("XuanyuanPhoneCompat: unsupported APK " + p.packageName);
            return;
        }
        if ("com.android.providers.telephony".equals(p.packageName)) {
            // The verified EEA provider already contains the OTP schema and handlers.
            XposedHelpers.setStaticBooleanField(XposedHelpers.findClass(
                    "com.android.providers.telephony.MmsSmsUtils", p.classLoader),
                    "HAS_VERIFICATION_CODE_CATEGORY", true);
            XposedBridge.log("XuanyuanSmsCompat: exact EEA provider verified; native OTP grouping available");
            return;
        }
        if ("com.android.incallui".equals(p.packageName)) { hookQuickAntispam(p); return; }
        if ("com.miui.yellowpage".equals(p.packageName)) {
            hookQuickAntispam(p);
            // This field is changed only in the verified YellowPage process.
            // Keep actual system properties and number-normalization region intact.
            XposedHelpers.setStaticBooleanField(
                    XposedHelpers.findClass("miui.os.Build", p.classLoader),
                    "IS_INTERNATIONAL_BUILD", false);
            final ThreadLocal<Boolean> cnRequest = new ThreadLocal<>();
            XposedHelpers.findAndHookMethod("miui.os.Build", p.classLoader, "getRegion", new XC_MethodHook() {
                protected void afterHookedMethod(MethodHookParam param) {
                    if (Boolean.TRUE.equals(cnRequest.get())) param.setResult("CN");
                }
            });
            // Select the CN number database only while OEM request parameters are assembled.
            XposedHelpers.findAndHookMethod("com.miui.yellowpage.utils.l1", p.classLoader,
                    "e", java.util.Map.class, new XC_MethodHook() {
                protected void beforeHookedMethod(MethodHookParam param) {
                    param.setObjectExtra("previous", cnRequest.get());
                    cnRequest.set(true);
                }
                protected void afterHookedMethod(MethodHookParam param) {
                    if (param.getObjectExtra("previous") == null) cnRequest.remove();
                    else cnRequest.set((Boolean) param.getObjectExtra("previous"));
                }
            });
            XposedHelpers.findAndHookMethod("n1.b", p.classLoader, "e", Context.class,
                    XposedHelpers.findClass("n1.a", p.classLoader), new XC_MethodHook() {
                protected void afterHookedMethod(MethodHookParam param) {
                    String feature = ((Enum<?>) param.args[1]).name();
                    if ("ANTISPAM".equals(feature) || "ANTISPAM_SYNC".equals(feature))
                        param.setResult(true);
                }
            });
            // Existing EEA databases do not run the CN creation/upgrade import.
            // Seed only an empty category table through the original importer.
            XposedHelpers.findAndHookMethod(
                    "com.miui.yellowpage.providers.yellowpage.YellowPageDatabaseHelper",
                    p.classLoader, "getReadableDatabase", new XC_MethodHook() {
                private final ThreadLocal<Boolean> importing = new ThreadLocal<>();
                protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                    if (Boolean.TRUE.equals(importing.get()) || param.hasThrowable()
                            || !(param.getResult() instanceof android.database.sqlite.SQLiteDatabase)) return;
                    android.database.sqlite.SQLiteDatabase db = (android.database.sqlite.SQLiteDatabase) param.getResult();
                    if (android.database.DatabaseUtils.longForQuery(db,
                            "SELECT count(*) FROM antispam_category", null) == 0) {
                        importing.set(true);
                        try { XposedHelpers.callMethod(param.thisObject, "o", db); }
                        finally { importing.remove(); }
                    }
                }
            });
            XposedHelpers.findAndHookMethod("com.miui.yellowpage.utils.j0", p.classLoader,
                    "w", new XC_MethodHook() {
                protected void afterHookedMethod(MethodHookParam param) {
                    if (!Integer.valueOf(0).equals(param.getResult()))
                        XposedBridge.log("XuanyuanPhoneCompat: YellowPage request status="
                                + param.getResult() + "; description=" + XposedHelpers.callMethod(param.thisObject, "s"));
                }
            });
            XposedBridge.log("XuanyuanPhoneCompat: exact CN YellowPage verified; local database and native settings enabled, consent unchanged");
            return;
        }
        if ("com.miui.audiomonitor".equals(p.packageName)) { hookMonitor(p); return; }
        if ("com.android.soundrecorder".equals(p.packageName)) { hookRecorder(p); return; }

        // Restore the bundled CN smart-SMS engine only in this exact MMS APK.
        // Framework properties, stored preferences and OEM consent remain intact.
        XposedHelpers.setStaticBooleanField(
                XposedHelpers.findClass("miui.os.Build", p.classLoader),
                "IS_INTERNATIONAL_BUILD", false);
        // Only the app's device helper; do not change global properties or consent defaults.
        XposedHelpers.setStaticBooleanField(XposedHelpers.findClass("gn.b", p.classLoader),
                "a", false);
        XposedHelpers.findAndHookMethod(android.app.Application.class, "attach", Context.class,
                new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) {
                XposedHelpers.setStaticBooleanField(XposedHelpers.findClass("g5.f3", p.classLoader),
                        "a", true);
            }
        });
        XposedHelpers.findAndHookMethod("com.miui.smsextra.util.UpdateVerificationCodeUtils",
                p.classLoader, "isVerificationCodeCategoryEnabled", Context.class, new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) {
                // Reuse the OEM switch and template-consent checks after restoring capability.
                param.setResult(XposedHelpers.callStaticMethod(
                        XposedHelpers.findClass("g5.f3", p.classLoader), "b", param.args[0]));
            }
        });
        XposedHelpers.findAndHookMethod("com.miui.smsextra.understand.UnderstandFactory",
                p.classLoader, "getMmsConfigWithKey", String.class, new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                if (param.hasThrowable() || param.getResult() != null
                        || !"recognition_partner_url".equals(param.args[0])) return;
                // Settings can open before the async parser has read the OEM config.
                XposedHelpers.callStaticMethod((Class<?>) param.method.getDeclaringClass(), "initMmsConfigJson");
                param.setResult(XposedBridge.invokeOriginalMethod(param.method, null, param.args));
            }
        });
        XposedHelpers.findAndHookMethod("com.miui.smsextra.sdk.SDKManager", p.classLoader,
                "init", new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) {
                if (!param.hasThrowable())
                    XposedBridge.log("XuanyuanSmsCompat: Xiaomi smart SMS SDK="
                            + XposedHelpers.callMethod(param.thisObject, "isXiaomiSdk")
                            + "; classifier=" + XposedHelpers.callMethod(param.thisObject, "canClassify"));
            }
        });
        XposedHelpers.findAndHookMethod("ef.d", p.classLoader, "b", String.class, new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) {
                XposedBridge.log("XuanyuanSmsCompat: local classification model loaded=" + !param.hasThrowable());
            }
        });

        // Native CN metadata now matches the app-local CN device helper.
        XposedBridge.log("XuanyuanSmsCompat: exact APK verified; CN smart SMS and OTP settings active");
    }

    private static void hookQuickAntispam(final XC_LoadPackage.LoadPackageParam p) {
        XposedHelpers.findAndHookMethod("android.app.ApplicationPackageManager", p.classLoader,
                "getApplicationInfo", String.class, int.class, new XC_MethodHook() {
            private String checkedPath;
            private boolean supported;
            protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                if (!"com.miui.securitycenter".equals(param.args[0]) || ((Integer) param.args[1] & 128) == 0
                        || !(param.getResult() instanceof ApplicationInfo)) return;
                ApplicationInfo original = (ApplicationInfo) param.getResult();
                if (!original.sourceDir.equals(checkedPath)) {
                    MessageDigest digest = MessageDigest.getInstance("SHA-256");
                    try (FileInputStream in = new FileInputStream(original.sourceDir)) {
                        byte[] buffer = new byte[65536]; int n;
                        while ((n = in.read(buffer)) != -1) digest.update(buffer, 0, n);
                    }
                    StringBuilder hash = new StringBuilder();
                    for (byte value : digest.digest()) hash.append(String.format("%02x", value & 255));
                    supported = "da9c99b77d29f8052bd71ec98fa8736ba7b04ed13881ffb09575db1d592af793".equals(hash.toString());
                    checkedPath = original.sourceDir;
                }
                if (!supported) return;
                // This EEA build retains the original ADD_FIREWALL handler.
                // Only the caller's metadata copy gets the missing capability bit.
                ApplicationInfo copy = new ApplicationInfo(original);
                copy.metaData = original.metaData == null ? new Bundle() : new Bundle(original.metaData);
                copy.metaData.putBoolean("miui.supportQuickAntispam", true);
                param.setResult(copy);
            }
        });
    }

    private static void hookRecorder(final XC_LoadPackage.LoadPackageParam p) {
        XposedHelpers.findAndHookMethod("com.android.soundrecorder.SoundRecorderSettings$a",
                p.classLoader, "K0", String.class, new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) throws Throwable {
                if (param.hasThrowable()) return;
                Context context = (Context) XposedHelpers.callMethod(param.thisObject, "getContext");
                Intent intent = new Intent("miui.intent.action.VOIPRECORD_SETTINGS")
                        .setClassName("com.miui.audiomonitor", "com.miui.audiomonitor.VoipRecordSettingsActivity");
                if (context == null || context.getPackageManager().resolveActivity(intent, 0) == null) return;
                Object category = XposedHelpers.callMethod(param.thisObject, "I0", "pref_category_key_other_caller");
                Object entry = XposedHelpers.callMethod(param.thisObject, "I0", "pref_key_app_records");
                if (category == null || entry == null) return;
                XposedHelpers.callMethod(category, "H", true);
                XposedHelpers.callMethod(entry, "H", true);
                XposedHelpers.setObjectField(entry, "f", param.thisObject);
                XposedHelpers.setObjectField(entry, "m", intent);
                XposedBridge.log("XuanyuanPhoneCompat: original app-recording preference enabled");
            }
        });
        XposedBridge.log("XuanyuanPhoneCompat: exact EEA recorder verified");
    }

    private static void hookMonitor(final XC_LoadPackage.LoadPackageParam p) {
        final ThreadLocal<Boolean> localRegion = new ThreadLocal<>();
        XposedHelpers.findAndHookMethod("miuix.core.util.SystemProperties", p.classLoader,
                "get", String.class, String.class, new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) {
                if (Boolean.TRUE.equals(localRegion.get()) && "ro.miui.region".equals(param.args[0]))
                    param.setResult("CN");
            }
        });
        XC_MethodHook region = new XC_MethodHook() {
            protected void beforeHookedMethod(MethodHookParam param) throws Throwable {
                param.setObjectExtra("previousRegion", localRegion.get());
                boolean normalSettings = true;
                if (param.thisObject instanceof Activity) {
                    normalSettings = (Integer) param.args[0] == -1 && !Boolean.TRUE.equals(param.args[1])
                            && XposedHelpers.getObjectField(param.thisObject, "mRequestPackage") == null;
                }
                localRegion.set(normalSettings);
            }
            protected void afterHookedMethod(MethodHookParam param) {
                Boolean previous = (Boolean) param.getObjectExtra("previousRegion");
                if (previous == null) localRegion.remove(); else localRegion.set(previous);
            }
        };
        // Use original CN app list and consent flow only at these two call sites.
        // This neither accepts consent nor enables a recording switch.
        XposedHelpers.findAndHookMethod("com.miui.audiomonitor.voiprecord.utils.CloudControlUtil",
                p.classLoader, "useLocalConfig", region);
        XposedHelpers.findAndHookMethod("com.miui.audiomonitor.VoipRecordSettingsActivity",
                p.classLoader, "checkPrivacy", int.class, Boolean.class, region);
        XposedBridge.log("XuanyuanPhoneCompat: exact CN monitor verified; settings and local app list adapted");
    }
}
