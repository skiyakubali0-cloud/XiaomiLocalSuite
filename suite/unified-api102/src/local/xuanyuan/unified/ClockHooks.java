package local.xuanyuan.unified;

import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModuleInterface;

public final class ClockHooks {
    private static final String PREFIX = "com.android.deskclock.";

    public static void install(final XposedInterface api,
            final XposedModuleInterface.PackageReadyParam p) throws Throwable {
        if (!"com.android.deskclock".equals(p.getPackageName()) || Build.VERSION.SDK_INT != 37
                || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)) return;
        if (!"41defcfd640a3ba5d359c20004d9dced5f6c0810204c41c94530af2a2bc1e9f6"
                .equals(Reflect.hashFile(p.getApplicationInfo().sourceDir))) {
            log(api, "Unsupported Clock APK; no changes");
            return;
        }
        ClassLoader loader = p.getClassLoader();
        api.hook(Reflect.method(Reflect.type(PREFIX + "util.Util", loader), "isInternational"))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            // Only the nearest Clock caller matters, never an outer UI/startup frame.
            for (StackTraceElement frame : Thread.currentThread().getStackTrace()) {
                String c = frame.getClassName(), m = frame.getMethodName();
                if (!c.startsWith(PREFIX) || (c.equals(PREFIX + "util.Util") && m.equals("isInternational"))) continue;
                if ((c.equals(PREFIX + "alarm.AlarmRepeatAdapter")
                            && (m.equals("setData") || m.equals("setRepeatItemChecked")))
                        || (c.equals(PREFIX + "alarm.RepeatAlarmController") && m.equals("initRepeatAlarmAdapterData"))
                        || (c.equals(PREFIX + "alarm.bedtime.BedtimeGuideActivity") && m.equals("initData"))
                        || (c.equals(PREFIX + "addition.holiday.HolidayUpdateScheduler") && m.equals("checkAndUpdate"))
                        || (c.equals(PREFIX + "DeskClockApp") && m.equals("onCreate"))) return false;
                break;
            }
            return chain.proceed();
        });
        api.hook(Reflect.method(Reflect.type(PREFIX + "settings.SettingsFragment", loader),
                "onCreatePreferences", Bundle.class, String.class))
                .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
            Object original = chain.proceed();
            try {
                Object group = Reflect.get(chain.getThisObject(), "mOtherPreferenceCategory");
                Object holiday = Reflect.get(chain.getThisObject(), "mValueHolidayPreference");
                // Restore only the holiday row; do not expose hidden CN privacy controls.
                boolean hidden = !(Boolean) Reflect.call(group, "isVisible");
                if (hidden) {
                    int count = (Integer) Reflect.call(group, "getPreferenceCount");
                    for (int i = 0; i < count; i++) {
                        Object row = Reflect.call(group, "getPreference", i);
                        if (row != holiday) Reflect.call(row, "setVisible", false);
                    }
                }
                Reflect.call(group, "addPreference", holiday);
                Reflect.call(holiday, "setVisible", true);
                Reflect.call(group, "setVisible", true);
            } catch (Throwable ignored) { }
            return original;
        });
        log(api, "Exact EEA APK verified; holiday repeat/update enabled; consent unchanged");
    }

    private static void log(XposedInterface api, String message) {
        try {
            api.log(Log.INFO, "XuanyuanClock", message);
        } catch (Throwable ignored) { }
    }
}
