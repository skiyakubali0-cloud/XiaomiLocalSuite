package local.xuanyuan.clockcompat;

import android.os.Build;
import android.os.Bundle;
import java.io.FileInputStream;
import java.security.MessageDigest;
import de.robv.android.xposed.IXposedHookLoadPackage;
import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;
import de.robv.android.xposed.XposedHelpers;
import de.robv.android.xposed.callbacks.XC_LoadPackage;

public final class ClockHook implements IXposedHookLoadPackage {
    private static final String PREFIX = "com.android.deskclock.";
    public void handleLoadPackage(final XC_LoadPackage.LoadPackageParam p) throws Throwable {
        if (!"com.android.deskclock".equals(p.packageName) || Build.VERSION.SDK_INT != 37
                || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)) return;
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream in = new FileInputStream(p.appInfo.sourceDir)) {
            byte[] buffer = new byte[65536]; int n;
            while ((n = in.read(buffer)) != -1) digest.update(buffer, 0, n);
        }
        StringBuilder hash = new StringBuilder();
        for (byte b : digest.digest()) hash.append(String.format("%02x", b & 255));
        if (!"41defcfd640a3ba5d359c20004d9dced5f6c0810204c41c94530af2a2bc1e9f6".equals(hash.toString())) {
            XposedBridge.log("XuanyuanClock: unsupported Clock APK; no changes"); return;
        }
        XposedHelpers.findAndHookMethod(PREFIX + "util.Util", p.classLoader, "isInternational", new XC_MethodHook() {
            protected void beforeHookedMethod(MethodHookParam param) {
                // Only the nearest Clock caller matters, never an outer UI/startup frame.
                for (StackTraceElement frame : Thread.currentThread().getStackTrace()) {
                    String c = frame.getClassName(), m = frame.getMethodName();
                    if (!c.startsWith(PREFIX) || (c.equals(PREFIX + "util.Util") && m.equals("isInternational"))) continue;
                    if ((c.equals(PREFIX + "alarm.AlarmRepeatAdapter")
                                && (m.equals("setData") || m.equals("setRepeatItemChecked")))
                            || (c.equals(PREFIX + "alarm.RepeatAlarmController") && m.equals("initRepeatAlarmAdapterData"))
                            || (c.equals(PREFIX + "alarm.bedtime.BedtimeGuideActivity") && m.equals("initData"))
                            || (c.equals(PREFIX + "addition.holiday.HolidayUpdateScheduler") && m.equals("checkAndUpdate"))
                            || (c.equals(PREFIX + "DeskClockApp") && m.equals("onCreate"))) param.setResult(false);
                    return;
                }
            }
        });
        XposedHelpers.findAndHookMethod(PREFIX + "settings.SettingsFragment", p.classLoader,
                "onCreatePreferences", Bundle.class, String.class, new XC_MethodHook() {
            protected void afterHookedMethod(MethodHookParam param) {
                if (param.hasThrowable()) return;
                Object group = XposedHelpers.getObjectField(param.thisObject, "mOtherPreferenceCategory");
                Object holiday = XposedHelpers.getObjectField(param.thisObject, "mValueHolidayPreference");
                // Restore only the holiday row; do not expose hidden CN privacy controls.
                boolean hidden = !(Boolean) XposedHelpers.callMethod(group, "isVisible");
                if (hidden) {
                    int count = (Integer) XposedHelpers.callMethod(group, "getPreferenceCount");
                    for (int i = 0; i < count; i++) {
                        Object row = XposedHelpers.callMethod(group, "getPreference", i);
                        if (row != holiday) XposedHelpers.callMethod(row, "setVisible", false);
                    }
                }
                XposedHelpers.callMethod(group, "addPreference", holiday);
                XposedHelpers.callMethod(holiday, "setVisible", true);
                XposedHelpers.callMethod(group, "setVisible", true);
            }
        });
        XposedBridge.log("XuanyuanClock: exact EEA APK verified; holiday repeat/update enabled; consent unchanged");
    }
}
