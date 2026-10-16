package local.xuanyuan.mipushcompat;

import android.app.Application;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Log;
import io.github.libxposed.api.XposedModule;
import io.github.libxposed.api.XposedInterface;
import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

/** Observe only the real SDK registration callback, after the wrapper attaches. */
public final class CoolapkObserver {
    private static final Set<Method> installed = new HashSet<>();
    private static final ThreadLocal<Integer> attachDepth = ThreadLocal.withInitial(() -> 0);
    public static void install(XposedModule module, SharedPreferences prefs) {
        try {
            module.hook(Application.class.getDeclaredMethod("attach", Context.class))
                .setId("coolapk-attach-observe").setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                .intercept(chain -> {
                    int depth = attachDepth.get(); attachDepth.set(depth + 1);
                    try { return OriginalGuard.intercept(chain, ignored -> {
                    if (depth != 0) return;
                    try {
                        Context context = (Context) chain.getArg(0);
                        ClassLoader loader = context.getClassLoader();
                        CoolapkChinaRoute.install(module, prefs, context);
                        Class<?> receiver = Class.forName("com.tencent.android.mipush.XMPushMessageReceiver", false, loader);
                        Class<?> message = Class.forName("com.xiaomi.mipush.sdk.MiPushCommandMessage", false, loader);
                        observeMessages(module, prefs, receiver, loader);
                        for (String name : new String[]{"onReceiveRegisterResult", "onCommandResult"}) {
                            try {
                                Method method = receiver.getMethod(name, Context.class, message);
                                synchronized (installed) { if (!installed.add(method)) continue; }
                                module.hook(method).setId("coolapk-register:" + name)
                                    .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                                    .intercept(callback -> OriginalGuard.intercept(callback, result -> {
                                        try {
                                            if (!prefs.getBoolean("enabled", false) || !prefs.getBoolean(CoolapkProfile.PACKAGE + ".cp_verified", false)
                                                || !prefs.getStringSet("selected", Collections.emptySet()).contains(CoolapkProfile.PACKAGE)) return;
                                            Object value = callback.getArg(1);
                                            if (value == null || !"register".equals(message.getMethod("getCommand").invoke(value))) return;
                                            long code = ((Number) message.getMethod("getResultCode").invoke(value)).longValue();
                                            Context ctx = (Context) callback.getArg(0);
                                            long updated = ctx.getPackageManager().getPackageInfo(CoolapkProfile.PACKAGE, 0).lastUpdateTime;
                                            if (updated != prefs.getLong(CoolapkProfile.PACKAGE + ".updated", -1)) return;
                                            Bundle report = new Bundle(); report.putLong("code", code); report.putLong("updated", updated);
                                            Bundle accepted = ctx.getContentResolver().call(DiagnosticProvider.URI, "coolapk", CoolapkProfile.PACKAGE, report);
                                            module.log(Log.INFO, "CoolapkObserve", "Report accepted=" + (accepted != null));
                                            module.log(Log.INFO, "CoolapkObserve", "Original registration code=" + code);
                                        } catch (ReflectiveOperationException | android.content.pm.PackageManager.NameNotFoundException | RuntimeException | LinkageError error) { module.log(Log.WARN, "CoolapkObserve", "Report unavailable: " + error.getClass().getSimpleName()); }
                                    }));
                                module.log(Log.INFO, "CoolapkObserve", "Installed " + name);
                            } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
                                module.log(Log.WARN, "CoolapkObserve", "Callback unavailable: " + name);
                            }
                        }
                    } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
                        module.log(Log.WARN, "CoolapkObserve", "Wrapper callback classes unavailable: " + error.getClass().getSimpleName());
                    }
                }); } finally { attachDepth.set(depth); }
                });
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
            module.log(Log.WARN, "CoolapkObserve", "Attach observation unavailable");
        }
    }
    private static void observeMessages(XposedModule module, SharedPreferences prefs, Class<?> receiver, ClassLoader loader)
            throws ReflectiveOperationException {
        Class<?> message = Class.forName("com.xiaomi.mipush.sdk.MiPushMessage", false, loader);
        for (String name : new String[]{"onNotificationMessageArrived", "onReceivePassThroughMessage", "onNotificationMessageClicked"}) {
            Method method = receiver.getMethod(name, Context.class, message);
            synchronized (installed) { if (!installed.add(method)) continue; }
            module.hook(method).setId("coolapk-message:" + name)
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                .intercept(chain -> OriginalGuard.intercept(chain, result -> {
                    if (!prefs.getBoolean("enabled", false) || !prefs.getBoolean(CoolapkProfile.PACKAGE + ".cp_verified", false)
                        || !prefs.getStringSet("selected", Collections.emptySet()).contains(CoolapkProfile.PACKAGE)) return;
                    // Count only native callbacks; never read the message body, token or sender.
                    module.log(Log.INFO, "CoolapkReceipt", "Native callback=" + name);
                }));
        }
    }

}
