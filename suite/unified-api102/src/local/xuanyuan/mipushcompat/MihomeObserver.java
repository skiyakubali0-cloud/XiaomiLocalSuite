package local.xuanyuan.mipushcompat;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.os.Bundle;
import android.util.Log;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModule;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/** Observes native calls only; no initialization, registration, synthetic receipt or routing mutation. */
public final class MihomeObserver {
    private final XposedModule module;
    private final SharedPreferences prefs;
    private final long updated;
    private final String identity;
    private final ClassLoader loader;

    private MihomeObserver(XposedModule module, SharedPreferences prefs, ClassLoader loader) {
        this.module = module; this.prefs = prefs; this.loader = loader;
        updated = prefs.getLong(MihomeProfile.PACKAGE + ".updated", -1);
        identity = prefs.getString(MihomeProfile.PACKAGE + ".sourceIdentity", "");
    }

    public static void install(XposedModule module, SharedPreferences prefs, ClassLoader loader) {
        new MihomeObserver(module, prefs, loader).install();
    }

    private void install() {
        observe("com.xiaomi.mipush.sdk.s", "a", boolean.class, "decision");
        observe("com.xiaomi.mipush.sdk.s", "a", Intent.class, "route");
        observe("com.xiaomi.mipush.sdk.s", "b", void.class, "dispatch", Intent.class);
        try {
            Class<?> command = Class.forName("com.xiaomi.mipush.sdk.MiPushCommandMessage", false, loader);
            Class<?> message = Class.forName("com.xiaomi.mipush.sdk.MiPushMessage", false, loader);
            observe("com.xiaomi.smarthome.framework.push.PushReceiver", "onCommandResult", void.class, "registration", Context.class, command);
            observe("com.xiaomi.mipush.sdk.PushMessageReceiver", "onNotificationMessageArrived", void.class, "arrival", Context.class, message);
            observe("com.xiaomi.smarthome.framework.push.PushReceiver", "onReceivePassThroughMessage", void.class, "pass_through", Context.class, message);
            observe("com.xiaomi.smarthome.framework.push.PushReceiver", "onNotificationMessageClicked", void.class, "click", Context.class, message);
        } catch (ReflectiveOperationException | LinkageError error) {
            module.log(Log.WARN, "MiHomeObserve", "Callback hooks unavailable; receipt unverified");
        }
    }

    private void observe(String owner, String name, Class<?> result, String event, Class<?>... params) {
        try {
            Method method = MihomeProfile.exactMethod(Class.forName(owner, false, loader), name, result, params);
            module.hook(method).setId("mihome-observe:" + event)
                    .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                    .intercept(chain -> OriginalGuard.intercept(chain, value -> record(chain, event, value)));
            module.log(Log.INFO, "MiHomeObserve", "Installed observation: " + event);
        } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
            module.log(Log.WARN, "MiHomeObserve", "Observation unavailable: " + event);
        }
    }

    private void record(XposedInterface.Chain chain, String event, Object value) {
        try {
            Context context = null;
            long code = 0;
            String route = "";
            if (event.equals("decision") || event.equals("route") || event.equals("dispatch")) {
                for (Field field : chain.getThisObject().getClass().getDeclaredFields()) {
                    if (field.getType() == Context.class) {
                        field.setAccessible(true); context = (Context) field.get(chain.getThisObject()); break;
                    }
                }
                if (event.equals("decision")) code = Boolean.TRUE.equals(value) ? 1 : 0;
                else {
                    Intent intent = event.equals("route") ? (Intent) value : (Intent) chain.getArg(0);
                    if (intent == null) return;
                    ComponentName component = intent.getComponent();
                    String pkg = component == null ? intent.getPackage() : component.getPackageName();
                    String type = component == null ? "" : component.getClassName();
                    boolean pushService = type.equals("com.xiaomi.push.service.XMPushService")
                            || type.equals("com.xiaomi.xmsf.push.service.XMPushService");
                    route = pushService && "com.xiaomi.xmsf".equals(pkg) ? "xmsf"
                            : pushService && MihomeProfile.PACKAGE.equals(pkg) ? "app_local" : "other";
                }
            } else {
                if (!chain.getThisObject().getClass().getName().equals("com.xiaomi.smarthome.framework.push.PushReceiver")) return;
                context = (Context) chain.getArg(0);
                Object message = chain.getArg(1);
                if (message == null) return;
                if (event.equals("registration")) {
                    if (!"register".equals(message.getClass().getMethod("getCommand").invoke(message))) return;
                    code = ((Number) message.getClass().getMethod("getResultCode").invoke(message)).longValue();
                }
            }
            if (context == null || !prefs.getBoolean("enabled", false)
                    || !prefs.getBoolean(MihomeProfile.PACKAGE + ".mh_verified", false)
                    || !prefs.getStringSet("selected", Collections.emptySet()).contains(MihomeProfile.PACKAGE)
                    || prefs.getLong(MihomeProfile.PACKAGE + ".updated", -1) != updated
                    || !identity.equals(prefs.getString(MihomeProfile.PACKAGE + ".sourceIdentity", ""))) return;
            PackageInfo info = context.getPackageManager().getPackageInfo(MihomeProfile.PACKAGE, 0);
            List<String> paths = new ArrayList<>(); paths.add(info.applicationInfo.sourceDir);
            if (info.applicationInfo.splitSourceDirs != null) paths.addAll(Arrays.asList(info.applicationInfo.splitSourceDirs));
            if (info.lastUpdateTime != updated || info.getLongVersionCode() != MihomeProfile.VERSION_CODE
                    || !MihomeProfile.VERSION_NAME.equals(info.versionName) || !identity.equals(SdkScanner.sourceIdentity(paths))) return;
            Bundle report = new Bundle();
            report.putString("event", event); report.putString("route", route); report.putLong("code", code);
            report.putLong("updated", updated);
            context.getContentResolver().call(DiagnosticProvider.URI, "mihome", MihomeProfile.PACKAGE, report);
            module.log(Log.INFO, "MiHomeObserve", "Original event=" + event + " route=" + route + " code=" + code);
        } catch (ReflectiveOperationException | android.content.pm.PackageManager.NameNotFoundException | RuntimeException | LinkageError ignored) { }
    }
}
