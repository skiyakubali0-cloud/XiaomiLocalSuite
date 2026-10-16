package local.xuanyuan.mipushcompat;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.util.Log;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModule;
import java.io.File;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Frozen wallet-only CN storage and SDK decision; native SDK owns registration. */
public final class WalletChinaRoute {
    public static final String PACKAGE = "com.mipay.wallet";
    private static final String PREFIX = "mipushcn_";

    public static void install(XposedModule module, SharedPreferences prefs, String pkg,
            ClassLoader loader, ApplicationInfo app) {
        if (!PACKAGE.equals(pkg)) return;
        AtomicBoolean ready = new AtomicBoolean();
        AtomicInteger reports = new AtomicInteger();
        try {
            // One startup snapshot. Namespace and routing must never split on live updates.
            Map<String, ?> config = prefs.getAll();
            if (!contains(config.get(ChinaApps.KEY), pkg)
                    || !Boolean.TRUE.equals(config.get(pkg + ".cn_verified"))
                    || !Boolean.TRUE.equals(config.get("wallet_background_ready"))) return;
            Object stamp = config.get(pkg + ".updated");
            Object evidence = config.get(pkg + ".sourceIdentity");
            if (!(stamp instanceof Long) || (Long) stamp <= 0
                    || !(evidence instanceof String) || ((String) evidence).isEmpty()) return;
            long updated = (Long) stamp;
            String identity = (String) evidence;
            boolean diagnostics = Boolean.TRUE.equals(config.get("enabled"))
                    && contains(config.get("selected"), pkg);
            ExactChinaProfile profile = ExactChinaProfile.find(pkg);
            Class<?> owner = Class.forName(profile.owner, false, loader);
            Method decision = sdkMethod(owner, profile.decision, boolean.class);
            Method route = sdkMethod(owner, profile.route, Intent.class);
            Method preferences = MihomeProfile.exactMethod(Class.forName("android.app.ContextImpl"),
                    "getSharedPreferences", SharedPreferences.class, String.class, int.class);
            Constructor<File> files = File.class.getConstructor(File.class, String.class);
            Context runtime = runtimeContext();

            // Resolve every target first; partially registered groups stay inert forever.
            module.hook(preferences).setId("wallet-china-preferences")
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                    Object[] replacement = null;
                    try {
                        if (ready.get() && chain.getThisObject() instanceof Context) {
                            String name = preferenceName(((Context) chain.getThisObject()).getPackageName(),
                                    (String) chain.getArg(0));
                            if (name != null && !name.equals(chain.getArg(0))) {
                                replacement = new Object[] { name, chain.getArg(1) };
                            }
                        }
                    } catch (RuntimeException | LinkageError ignored) { }
                    return replacement == null ? chain.proceed() : chain.proceed(replacement);
                });
            module.hook(files).setId("wallet-china-files")
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                    Object[] replacement = null;
                    try {
                        if (ready.get()) {
                            String name = fileName((File) chain.getArg(0), (String) chain.getArg(1));
                            if (name != null && !name.equals(chain.getArg(1))) {
                                replacement = new Object[] { chain.getArg(0), name };
                            }
                        }
                    } catch (RuntimeException | LinkageError ignored) { }
                    return replacement == null ? chain.proceed() : chain.proceed(replacement);
                });
            module.hook(decision).setId("wallet-china-decision")
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                .intercept(chain -> ready.get() ? false : chain.proceed());
            module.hook(route).setId("wallet-china-route")
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                .intercept(chain -> OriginalGuard.intercept(chain, value -> {
                    if (!ready.get() || !diagnostics || !(value instanceof Intent)) return;
                    ComponentName component = ((Intent) value).getComponent();
                    if (component == null || reports.getAndIncrement() >= 20) return;
                    String target = component.getPackageName();
                    report(module, Log.INFO, "route=" + (pkg.equals(target) ? "app_local"
                            : "com.xiaomi.xmsf".equals(target) ? "xmsf" : "other"));
                }));
            WalletHeartbeat.install(module, loader, ready, app.uid);
            WalletNetwork.install(module, loader, ready, app.uid);
            // Manager metadata is insufficient: re-read installed version/source and APK bytes.
            if (!verifyRuntime(runtime, app, updated, identity)) {
                report(module, Log.WARN, "runtime APK verification failed; hooks inactive");
                return;
            }
            ready.set(true);
            report(module, Log.INFO, "exact route installed; process configuration frozen");
        } catch (ReflectiveOperationException | android.content.pm.PackageManager.NameNotFoundException
                | RuntimeException | LinkageError error) {
            ready.set(false);
            report(module, Log.WARN, "route unavailable: " + error.getClass().getSimpleName());
        }
    }

    private static boolean contains(Object value, String pkg) {
        return value instanceof Set && ((Set<?>) value).contains(pkg);
    }

    static Method sdkMethod(Class<?> owner, String name, Class<?> result) throws NoSuchMethodException {
        Method method = MihomeProfile.exactMethod(owner, name, result);
        if (Modifier.isStatic(method.getModifiers())) throw new NoSuchMethodException(name);
        return method;
    }

    private static Context runtimeContext() throws ReflectiveOperationException {
        Class<?> thread = Class.forName("android.app.ActivityThread");
        Method current = thread.getDeclaredMethod("currentActivityThread");
        Method context = thread.getDeclaredMethod("getSystemContext");
        current.setAccessible(true);
        context.setAccessible(true);
        return (Context) context.invoke(current.invoke(null));
    }

    static boolean verifyRuntime(Context context, ApplicationInfo app, long updated, String identity)
            throws android.content.pm.PackageManager.NameNotFoundException {
        if (context == null || app == null || !PACKAGE.equals(app.packageName)
                || app.sourceDir == null || (app.splitSourceDirs != null && app.splitSourceDirs.length != 0)) return false;
        PackageInfo info = context.getPackageManager().getPackageInfo(PACKAGE, 0);
        ApplicationInfo installed = info.applicationInfo;
        List<String> paths = Collections.singletonList(app.sourceDir);
        if (!PACKAGE.equals(info.packageName) || installed == null || !PACKAGE.equals(installed.packageName)
                || installed.uid != app.uid || !app.sourceDir.equals(installed.sourceDir)
                || (installed.splitSourceDirs != null && installed.splitSourceDirs.length != 0)
                || info.lastUpdateTime != updated || !identity.equals(SdkScanner.sourceIdentity(paths))
                || !ExactChinaProfile.verify(PACKAGE, info.getLongVersionCode(), paths)) return false;
        return context.getPackageManager().getPackageInfo(PACKAGE, 0).lastUpdateTime == updated
                && identity.equals(SdkScanner.sourceIdentity(paths));
    }

    static String preferenceName(String pkg, String name) {
        return PACKAGE.equals(pkg) && targetName(name) && name.startsWith("mipush") ? PREFIX + name : name;
    }

    static String fileName(File parent, String name) {
        if (parent == null || !targetName(name) || !(name.startsWith("mipush") || PACKAGE.equals(name))) return name;
        String path = parent.getAbsolutePath();
        return (path.equals("/data/user/0/" + PACKAGE + "/files")
                || path.equals("/data/data/" + PACKAGE + "/files")) ? PREFIX + name : name;
    }

    private static boolean targetName(String name) {
        return name != null && !name.startsWith(PREFIX) && name.indexOf('/') < 0 && name.indexOf('\\') < 0;
    }

    private static void report(XposedModule module, int level, String message) {
        try { module.log(level, "MiPushWalletChina", PACKAGE + " " + message); }
        catch (RuntimeException | LinkageError ignored) { }
    }
}
