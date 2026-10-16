package local.xuanyuan.mipushcompat;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModule;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicBoolean;

/** Exact Coolapk 16.6.4 SDK 6_0_1-C only. Let the SDK manage its own service. */
public final class CoolapkChinaRoute {
    private static boolean installed;
    public static synchronized void install(XposedModule module, SharedPreferences prefs, Context context) {
        if (installed || !CoolapkProfile.PACKAGE.equals(context.getPackageName())) return;
        try {
            Class<?> type = Class.forName("com.xiaomi.mipush.sdk.u", false, context.getClassLoader());
            Method decision = MihomeProfile.exactMethod(type, "a", boolean.class);
            Method route = MihomeProfile.exactMethod(type, "c", Intent.class);
            long updated = prefs.getLong(CoolapkProfile.PACKAGE + ".updated", -1);
            String identity = prefs.getString(CoolapkProfile.PACKAGE + ".sourceIdentity", "");
            AtomicInteger reports = new AtomicInteger();
            AtomicBoolean ready = new AtomicBoolean();
            module.hook(decision).setId("coolapk-own-channel")
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                    Object original = chain.proceed();
                    try { if (ready.get() && active(prefs, updated, identity) && ChinaApps.requested(prefs, CoolapkProfile.PACKAGE)) {
                        if (diagnostics(prefs) && reports.getAndIncrement() < 20) module.log(Log.INFO, "CoolapkChina", "Own channel selected; original=" + original);
                        return false;
                    } } catch (RuntimeException | LinkageError ignored) { }
                    return original;
                });
            installed = true;
            module.hook(route).setId("coolapk-route-observe")
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                .intercept(chain -> OriginalGuard.intercept(chain, value -> {
                    try {
                    if (!diagnostics(prefs) || !ready.get() || !active(prefs, updated, identity) || !(value instanceof Intent)) return;
                    ComponentName component = ((Intent) value).getComponent();
                    if (component == null) return;
                    String pkg = component.getPackageName();
                    module.log(Log.INFO, "CoolapkChina", "Actual route=" + (CoolapkProfile.PACKAGE.equals(pkg) ? "app_local" : "com.xiaomi.xmsf".equals(pkg) ? "xmsf" : "other"));
                    } catch (LinkageError ignored) { }
                }));
            ready.set(true);
            module.log(Log.INFO, "CoolapkChina", "Exact route hooks installed");
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
            module.log(Log.WARN, "CoolapkChina", "Route unavailable: " + error.getClass().getSimpleName());
        }
    }

    private static boolean diagnostics(SharedPreferences prefs) {
        return prefs.getBoolean("enabled", false)
                && prefs.getStringSet("selected", Collections.emptySet()).contains(CoolapkProfile.PACKAGE);
    }

    private static boolean active(SharedPreferences prefs, long updated, String identity) {
        try {
            return updated > 0 && !identity.isEmpty()
                && prefs.getBoolean(CoolapkProfile.PACKAGE + ".cp_verified", false)
                && (ChinaApps.requested(prefs, CoolapkProfile.PACKAGE) || diagnostics(prefs))
                && updated == prefs.getLong(CoolapkProfile.PACKAGE + ".updated", -1)
                && identity.equals(prefs.getString(CoolapkProfile.PACKAGE + ".sourceIdentity", ""));
        } catch (RuntimeException error) { return false; }
    }
}
