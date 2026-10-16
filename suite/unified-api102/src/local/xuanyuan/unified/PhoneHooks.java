package local.xuanyuan.unified;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.database.DatabaseUtils;
import android.database.sqlite.SQLiteDatabase;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModuleInterface;
import java.util.Map;

public final class PhoneHooks {
    public static void install(final XposedInterface api,
            final XposedModuleInterface.PackageReadyParam p) throws Throwable {
        if (Build.VERSION.SDK_INT != 37 || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)) return;
        String name = p.getPackageName();
        String expected;
        switch (name) {
            case "com.android.providers.telephony": expected = "c5aaafabb1679f7c2a7edd23c69366548bb5bf0591bd2293c15623522db4f9b5"; break;
            case "com.android.mms": expected = "0a59d7338d31c70a0fb8f5477f264033d77abf4101f2897a60ffbabacbb1da14"; break;
            case "com.miui.audiomonitor": expected = "83133a62f37cefe873075064d39c5e176e768af251d678438a242116be8178b1"; break;
            case "com.android.soundrecorder": expected = "26cc4ef1ba6dc07013837a0b12fb91a31eff340f0b4496a91cc48387ebb72dcc"; break;
            case "com.android.incallui": expected = "590f2ed0e5e0923e79a452d72cd9c6e9783e1dde4cb8c987355ebcfce7b8c3bd"; break;
            case "com.miui.yellowpage": expected = "e07e59b9d9a99b0cce4bf06b9734002016b1c3bebe701c6ee368cdc8161cb733"; break;
            default: return;
        }
        if (!expected.equals(Reflect.hashFile(p.getApplicationInfo().sourceDir))) {
            log(api, "Unsupported Phone APK; no changes");
            return;
        }
        ClassLoader loader = p.getClassLoader();
        if ("com.android.providers.telephony".equals(name)) {
            Reflect.setStaticBoolean(Reflect.type("com.android.providers.telephony.MmsSmsUtils", loader),
                    "HAS_VERIFICATION_CODE_CATEGORY", true);
            log(api, "Exact EEA provider verified; native OTP grouping available");
            return;
        }
        if ("com.android.incallui".equals(name)) {
            hookQuickAntispam(api, loader);
            return;
        }
        if ("com.miui.yellowpage".equals(name)) {
            hookYellowPage(api, loader);
            return;
        }
        if ("com.miui.audiomonitor".equals(name)) {
            hookMonitor(api, loader);
            return;
        }
        if ("com.android.soundrecorder".equals(name)) {
            hookRecorder(api, loader);
            return;
        }

        // Only the exact MMS process; preserve global properties and OEM consent.
        Reflect.setStaticBoolean(Reflect.type("miui.os.Build", loader), "IS_INTERNATIONAL_BUILD", false);
        Reflect.setStaticBoolean(Reflect.type("gn.b", loader), "a", false);
        api.hook(Reflect.method(Application.class, "attach", Context.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            try {
                Reflect.setStaticBoolean(Reflect.type("g5.f3", loader), "a", true);
            } catch (Throwable ignored) { }
            return original;
        });
        api.hook(Reflect.method(Reflect.type("com.miui.smsextra.util.UpdateVerificationCodeUtils", loader),
                "isVerificationCodeCategoryEnabled", Context.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            try {
                // Retain the OEM switch and template-consent checks.
                return Reflect.call(Reflect.type("g5.f3", loader), "b", chain.getArgs().get(0));
            } catch (Throwable ignored) {
                return original;
            }
        });
        Class<?> factory = Reflect.type("com.miui.smsextra.understand.UnderstandFactory", loader);
        api.hook(Reflect.method(factory, "getMmsConfigWithKey", String.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            if (original != null || !"recognition_partner_url".equals(chain.getArgs().get(0))) return original;
            try {
                Reflect.call(factory, "initMmsConfigJson");
                // The exact APK's getter reads JSONObject field e. Read it after OEM init
                // instead of invoking the original getter a second time.
                Object config = Reflect.get(factory, "e");
                if (config != null && Boolean.TRUE.equals(Reflect.call(config, "has", "recognition_partner_url")))
                    return Reflect.call(config, "get", "recognition_partner_url");
            } catch (Throwable ignored) { }
            return original;
        });
        api.hook(Reflect.method(Reflect.type("com.miui.smsextra.sdk.SDKManager", loader), "init"))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            try {
                boolean xiaomi = Boolean.TRUE.equals(Reflect.call(chain.getThisObject(), "isXiaomiSdk"));
                boolean classifier = Boolean.TRUE.equals(Reflect.call(chain.getThisObject(), "canClassify"));
                log(api, "Smart SMS Xiaomi SDK=" + xiaomi + "; classifier=" + classifier);
            } catch (Throwable ignored) { }
            return original;
        });
        api.hook(Reflect.method(Reflect.type("ef.d", loader), "b", String.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            boolean loaded = false;
            try {
                Object original = chain.proceed();
                loaded = true;
                return original;
            } finally {
                log(api, "Local classification model loaded=" + loaded);
            }
        });
        log(api, "Exact MMS APK verified; CN smart SMS and OTP settings active");
    }

    private static void hookYellowPage(XposedInterface api, ClassLoader loader) throws Throwable {
        hookQuickAntispam(api, loader);
        Class<?> build = Reflect.type("miui.os.Build", loader);
        Reflect.setStaticBoolean(build, "IS_INTERNATIONAL_BUILD", false);
        final ThreadLocal<Boolean> cnRequest = new ThreadLocal<>();
        api.hook(Reflect.method(build, "getRegion"))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            return Boolean.TRUE.equals(cnRequest.get()) ? "CN" : original;
        });
        api.hook(Reflect.method(Reflect.type("com.miui.yellowpage.utils.l1", loader), "e", Map.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Boolean previous = cnRequest.get();
            cnRequest.set(true);
            try {
                return chain.proceed();
            } finally {
                if (previous == null) cnRequest.remove(); else cnRequest.set(previous);
            }
        });
        api.hook(Reflect.method(Reflect.type("n1.b", loader), "e", Context.class, Reflect.type("n1.a", loader)))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            try {
                String feature = ((Enum<?>) chain.getArgs().get(1)).name();
                if ("ANTISPAM".equals(feature) || "ANTISPAM_SYNC".equals(feature)) return true;
            } catch (Throwable ignored) { }
            return original;
        });
        final ThreadLocal<Boolean> importing = new ThreadLocal<>();
        api.hook(Reflect.method(Reflect.type(
                "com.miui.yellowpage.providers.yellowpage.YellowPageDatabaseHelper", loader), "getReadableDatabase"))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            if (Boolean.TRUE.equals(importing.get()) || !(original instanceof SQLiteDatabase)) return original;
            try {
                SQLiteDatabase db = (SQLiteDatabase) original;
                if (DatabaseUtils.longForQuery(db, "SELECT count(*) FROM antispam_category", null) == 0) {
                    importing.set(true);
                    try {
                        Reflect.call(chain.getThisObject(), "o", db);
                    } finally {
                        importing.remove();
                    }
                }
            } catch (Throwable ignored) { }
            return original;
        });
        api.hook(Reflect.method(Reflect.type("com.miui.yellowpage.utils.j0", loader), "w"))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            if (!Integer.valueOf(0).equals(original))
                log(api, "YellowPage request returned nonzero status");
            return original;
        });
        log(api, "Exact CN YellowPage verified; local database and native settings enabled; consent unchanged");
    }

    private static void hookQuickAntispam(XposedInterface api, ClassLoader loader) throws Throwable {
        api.hook(Reflect.method(Reflect.type("android.app.ApplicationPackageManager", loader),
                "getApplicationInfo", String.class, int.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(new XposedInterface.Hooker() {
            private String checkedPath;
            private boolean supported;

            public Object intercept(XposedInterface.Chain chain) throws Throwable {
                Object original = chain.proceed();
                if (!"com.miui.securitycenter".equals(chain.getArgs().get(0))
                        || ((Integer) chain.getArgs().get(1) & 128) == 0
                        || !(original instanceof ApplicationInfo)) return original;
                try {
                    ApplicationInfo info = (ApplicationInfo) original;
                    // Keep path and digest paired even when package queries run concurrently.
                    synchronized (this) {
                        if (!info.sourceDir.equals(checkedPath)) {
                            boolean matches = "da9c99b77d29f8052bd71ec98fa8736ba7b04ed13881ffb09575db1d592af793"
                                    .equals(Reflect.hashFile(info.sourceDir));
                            supported = matches;
                            checkedPath = info.sourceDir;
                        }
                        if (!supported) return original;
                    }
                    ApplicationInfo copy = new ApplicationInfo(info);
                    copy.metaData = info.metaData == null ? new Bundle() : new Bundle(info.metaData);
                    copy.metaData.putBoolean("miui.supportQuickAntispam", true);
                    return copy;
                } catch (Throwable ignored) {
                    return original;
                }
            }
        });
    }

    private static void hookRecorder(XposedInterface api, ClassLoader loader) throws Throwable {
        api.hook(Reflect.method(Reflect.type("com.android.soundrecorder.SoundRecorderSettings$a", loader),
                "K0", String.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            try {
                Object receiver = chain.getThisObject();
                Context context = (Context) Reflect.call(receiver, "getContext");
                Intent intent = new Intent("miui.intent.action.VOIPRECORD_SETTINGS").setClassName(
                        "com.miui.audiomonitor", "com.miui.audiomonitor.VoipRecordSettingsActivity");
                if (context == null || context.getPackageManager().resolveActivity(intent, 0) == null) return original;
                Object category = Reflect.call(receiver, "I0", "pref_category_key_other_caller");
                Object entry = Reflect.call(receiver, "I0", "pref_key_app_records");
                if (category == null || entry == null) return original;
                Reflect.call(category, "H", true);
                Reflect.call(entry, "H", true);
                Reflect.set(entry, "f", receiver);
                Reflect.set(entry, "m", intent);
                log(api, "Original app-recording preference enabled");
            } catch (Throwable ignored) { }
            return original;
        });
        log(api, "Exact EEA recorder verified");
    }

    private static void hookMonitor(XposedInterface api, ClassLoader loader) throws Throwable {
        final ThreadLocal<Boolean> localRegion = new ThreadLocal<>();
        api.hook(Reflect.method(Reflect.type("miuix.core.util.SystemProperties", loader),
                "get", String.class, String.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            return Boolean.TRUE.equals(localRegion.get()) && "ro.miui.region".equals(chain.getArgs().get(0))
                    ? "CN" : original;
        });
        XposedInterface.Hooker region = chain -> {
            boolean normalSettings = true;
            if (chain.getThisObject() instanceof Activity) {
                try {
                    normalSettings = Integer.valueOf(-1).equals(chain.getArgs().get(0))
                            && !Boolean.TRUE.equals(chain.getArgs().get(1))
                            && Reflect.get(chain.getThisObject(), "mRequestPackage") == null;
                } catch (Throwable ignored) {
                    normalSettings = false;
                }
            }
            Boolean previous = localRegion.get();
            localRegion.set(normalSettings);
            try {
                return chain.proceed();
            } finally {
                if (previous == null) localRegion.remove(); else localRegion.set(previous);
            }
        };
        api.hook(Reflect.method(Reflect.type("com.miui.audiomonitor.voiprecord.utils.CloudControlUtil", loader),
                "useLocalConfig")).setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(region);
        api.hook(Reflect.method(Reflect.type("com.miui.audiomonitor.VoipRecordSettingsActivity", loader),
                "checkPrivacy", int.class, Boolean.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(region);
        log(api, "Exact CN monitor verified; settings and local app list adapted; consent unchanged");
    }

    private static void log(XposedInterface api, String message) {
        try {
            api.log(Log.INFO, "XuanyuanPhoneCompat", message);
        } catch (Throwable ignored) { }
    }
}
