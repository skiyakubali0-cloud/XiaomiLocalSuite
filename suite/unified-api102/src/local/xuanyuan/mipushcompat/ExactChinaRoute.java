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
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Per-process SDK decision only; SDK owns registration, regions and components. */
public final class ExactChinaRoute {
    public static void install(XposedModule module, SharedPreferences prefs, String pkg, ClassLoader loader) {
        ExactChinaProfile profile = ExactChinaProfile.find(pkg);
        if (profile == null || !ChinaApps.requested(prefs, pkg)) return;
        long updated = prefs.getLong(pkg + ".updated", -1);
        String identity = prefs.getString(pkg + ".sourceIdentity", "");
        AtomicBoolean ready = new AtomicBoolean();
        AtomicInteger reports = new AtomicInteger();
        try {
            Class<?> owner = Class.forName(profile.owner, false, loader);
            Method decision = MihomeProfile.exactMethod(owner, profile.decision, boolean.class);
            Method route = MihomeProfile.exactMethod(owner, profile.route, Intent.class);
            module.hook(decision).setId("china-decision:" + pkg)
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                    Object original = chain.proceed();
                    try {
                        if (ready.get() && active(prefs, pkg, updated, identity)) return false;
                    } catch (RuntimeException | LinkageError ignored) { }
                    return original;
                });
            module.hook(route).setId("china-route:" + pkg)
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                .intercept(chain -> OriginalGuard.intercept(chain, value -> {
                    try {
                        if (!ready.get() || !active(prefs, pkg, updated, identity)
                                || !diagnostics(prefs, pkg) || !(value instanceof Intent)) return;
                        ComponentName component = ((Intent) value).getComponent();
                        if (component == null || reports.getAndIncrement() >= 20) return;
                        String target = component.getPackageName();
                        module.log(Log.INFO, "MiPushChina", pkg + " route="
                                + (pkg.equals(target) ? "app_local" : "com.xiaomi.xmsf".equals(target) ? "xmsf" : "other"));
                    } catch (RuntimeException | LinkageError ignored) { }
                }));
            if ("com.miui.mediaeditor".equals(pkg)) {
                Method support = MihomeProfile.exactMethod(Class.forName(
                        "com.miui.camerainfra.cloudconfig.push.cn.MiPushInitializer", false, loader),
                        "isSupport", boolean.class);
                module.hook(support).setId("china-provider:" + pkg)
                    .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                        Object original = chain.proceed();
                        try {
                            if (ready.get() && active(prefs, pkg, updated, identity)) return true;
                        } catch (RuntimeException | LinkageError ignored) { }
                        return original;
                    });
                // SDK 7.7's XMSF-only app-info recovery also runs in the own service.
                // Its second-process writes to mipush.xml overwrite SDK credentials.
                Class<?> pushService = Class.forName("com.xiaomi.push.service.XMPushService", false, loader);
                Method restore = MihomeProfile.exactMethod(Class.forName(
                        "com.xiaomi.push.service.c", false, loader), "c", void.class, pushService);
                module.hook(restore).setId("china-own-service-recovery:" + pkg)
                    .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                        try {
                            Object context = chain.getArg(0);
                            if (ready.get() && active(prefs, pkg, updated, identity)
                                    && context instanceof Context && pkg.equals(((Context) context).getPackageName())) return null;
                        } catch (RuntimeException | LinkageError ignored) { }
                        return chain.proceed();
                    });
            }
            ready.set(true);
            module.log(Log.INFO, "MiPushChina", pkg + " exact route installed");
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
            module.log(Log.WARN, "MiPushChina", pkg + " route unavailable: " + error.getClass().getSimpleName());
        }
    }

    private static boolean diagnostics(SharedPreferences prefs, String pkg) {
        return prefs.getBoolean("enabled", false)
                && prefs.getStringSet("selected", Collections.emptySet()).contains(pkg);
    }

    private static boolean active(SharedPreferences prefs, String pkg, long updated, String identity) {
        return updated > 0 && !identity.isEmpty() && prefs.getBoolean(pkg + ".cn_verified", false)
                && ChinaApps.requested(prefs, pkg) && updated == prefs.getLong(pkg + ".updated", -1)
                && identity.equals(prefs.getString(pkg + ".sourceIdentity", ""));
    }
}
