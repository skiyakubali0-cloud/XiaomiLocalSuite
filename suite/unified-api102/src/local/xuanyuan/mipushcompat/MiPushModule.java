package local.xuanyuan.mipushcompat;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.util.Log;
import io.github.libxposed.api.XposedModule;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Set;

/** API102: exact app-specific China adapter plus optional native diagnostics. */
public class MiPushModule extends XposedModule {
    public static final String PRIORITY_STATUS = "priority_unsupported";

    @Override public void onPackageReady(PackageReadyParam param) {
        if (getApiVersion() < 102 || !param.isFirstPackage()) return;
        final String pkg = param.getPackageName();
        if (pkg.equals("local.xuanyuan.mipushcompat") || pkg.equals("com.xiaomi.xmsf")) return;
        final SharedPreferences prefs;
        try {
            prefs = getRemotePreferences("selection");
            if (!selected(prefs, pkg) && !ChinaApps.requested(prefs, pkg)) return;
        } catch (RuntimeException error) {
            log(Log.WARN, "MiPushDetect", "Selection unavailable; diagnostics off: " + pkg); return;
        }
        List<String> paths = new ArrayList<>();
        paths.add(param.getApplicationInfo().sourceDir);
        if (param.getApplicationInfo().splitSourceDirs != null) paths.addAll(Arrays.asList(param.getApplicationInfo().splitSourceDirs));
        String expected = prefs.getString(pkg + ".sourceIdentity", "");
        if (expected.isEmpty() || !expected.equals(SdkScanner.sourceIdentity(paths))) {
            log(Log.WARN, "MiPushDetect", "APK metadata changed or evidence absent; observation off: " + pkg);
            return;
        }
        if (CoolapkProfile.PACKAGE.equals(pkg) && prefs.getBoolean(pkg + ".cp_verified", false)) CoolapkObserver.install(this, prefs);
        if (prefs.getBoolean(pkg + ".cn_verified", false)) {
            if (WalletChinaRoute.PACKAGE.equals(pkg)) {
                WalletChinaRoute.install(this, prefs, pkg, param.getClassLoader(), param.getApplicationInfo());
            } else {
                ExactChinaRoute.install(this, prefs, pkg, param.getClassLoader());
            }
        }
        if (!selected(prefs, pkg)) return;
        Set<String> guards = prefs.getStringSet(pkg + ".guards", Collections.emptySet());
        log(Log.INFO, "MiPushDetect", "API=" + getApiVersion() + " package=" + pkg
                + " scanner_guards=" + guards.size() + " priority=" + PRIORITY_STATUS);
        if (MihomeProfile.PACKAGE.equals(pkg) && prefs.getBoolean(pkg + ".mh_verified", false)) {
            MihomeObserver.install(this, prefs, param.getClassLoader());
        }
        for (String name : guards) {
            if (!name.startsWith("com.xiaomi.mipush.sdk.")) continue;
            try {
                Class<?> type = Class.forName(name, false, param.getClassLoader());
                Method method = type.getDeclaredMethod("shouldUseMIUIPush", Context.class);
                if (method.getReturnType() != boolean.class || !Modifier.isStatic(method.getModifiers())
                        || !Modifier.isPublic(method.getModifiers())) continue;
                hook(method).setId("mipush-observe:" + name).setExceptionMode(ExceptionMode.PASSTHROUGH)
                        .intercept(chain -> OriginalGuard.intercept(chain, result -> {
                            try {
                                Context context = (Context) chain.getArgs().get(0);
                                if (!selected(prefs, pkg) || context == null
                                        || context.getPackageManager().getPackageInfo(pkg, 0).lastUpdateTime
                                        != prefs.getLong(pkg + ".updated", -1)) return;
                                log(Log.INFO, "MiPushDetect", pkg + " " + name + ".shouldUseMIUIPush original=" + result
                                        + " status=" + (Boolean.TRUE.equals(result) ? "native_supported" : "sdk_native_false")
                                        + " priority=" + PRIORITY_STATUS + " delivery=unverified");
                                Bundle report = new Bundle();
                                report.putBoolean("original", Boolean.TRUE.equals(result));
                                context.getContentResolver().call(DiagnosticProvider.URI, "observe", pkg, report);
                            } catch (android.content.pm.PackageManager.NameNotFoundException ignored) { }
                        }));
            } catch (ReflectiveOperationException | RuntimeException | LinkageError error) {
                log(Log.WARN, "MiPushDetect", "Guard observation unavailable: " + pkg + " " + name);
            }
        }
    }

    private static boolean selected(SharedPreferences prefs, String pkg) {
        return prefs.getBoolean("enabled", false) && prefs.getStringSet("selected", Collections.emptySet()).contains(pkg);
    }
}
