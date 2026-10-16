package local.xuanyuan.unified;

import android.app.Activity;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModuleInterface;

public final class SuggestionHooks {
    public static void install(final XposedInterface api,
            final XposedModuleInterface.PackageReadyParam p) throws Throwable {
        boolean assistant = "com.miui.personalassistant".equals(p.getPackageName());
        if ((!assistant && !"com.xiaomi.aicr".equals(p.getPackageName())) || Build.VERSION.SDK_INT != 37
                || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)) return;
        String expected = assistant ? "6ecb326cd18351e032f5fe493c1bc1bb28e417bd03954e5133c237bcffc43562"
                : "f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520";
        if (!expected.equals(Reflect.hashFile(p.getApplicationInfo().sourceDir))) {
            log(api, "Unsupported AI engine APK; no changes");
            return;
        }
        if (assistant) {
            api.hook(Reflect.method(Activity.class, "startActivityForResult", Intent.class, int.class, Bundle.class))
                    .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                Object[] replacementArgs = null;
                try {
                    Intent original = (Intent) chain.getArgs().get(0);
                    if (original != null && original.getComponent() == null
                            && Intent.ACTION_SEARCH.equals(original.getAction())
                            && "com.android.calendar".equals(original.getPackage())) {
                        Activity activity = (Activity) chain.getThisObject();
                        if (original.resolveActivity(activity.getPackageManager()) == null) {
                            Intent replacement = new Intent(original).setPackage("com.xiaomi.calendar");
                            if (replacement.resolveActivity(activity.getPackageManager()) != null) {
                                replacementArgs = chain.getArgs().toArray();
                                replacementArgs[0] = replacement;
                                log(api, "Calendar SEARCH routed to installed Xiaomi Calendar");
                            }
                        }
                    }
                } catch (Throwable ignored) { }
                // Never mutate the caller's Intent or the chain's immutable argument list.
                return replacementArgs == null ? chain.proceed() : chain.proceed(replacementArgs);
            });
            log(api, "Exact assistant verified; calendar SEARCH fallback installed");
            return;
        }
        ClassLoader loader = p.getClassLoader();
        api.hook(Reflect.method(Reflect.type("ws1", loader), "b"))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            try {
                Class<?> level = Reflect.type("fs1", loader);
                boolean lite = (Boolean) Reflect.call(Reflect.type("zs1", loader), "m")
                        || (Boolean) Reflect.get(level, "f")
                        || ((Integer) Reflect.call(level, "b")).intValue() == (Integer) Reflect.get(level, "e");
                int ram = (Integer) Reflect.get(level, "g");
                lite |= ram >= 1 && ram < 5;
                if (!lite) return true;
            } catch (Throwable ignored) { }
            return original;
        });
        log(api, "Exact EEA engine verified; intention capability enabled; consent unchanged");
    }

    private static void log(XposedInterface api, String message) {
        try {
            api.log(Log.INFO, "XuanyuanSuggestion", message);
        } catch (Throwable ignored) { }
    }
}
