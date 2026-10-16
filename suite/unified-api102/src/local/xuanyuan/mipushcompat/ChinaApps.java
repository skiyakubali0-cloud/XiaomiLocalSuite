package local.xuanyuan.mipushcompat;

import android.content.SharedPreferences;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

/** Explicit per-app requests; an SDK scan alone never enables an adapter. */
public final class ChinaApps {
    public static final String KEY = "china_apps";

    public static Set<String> requested(SharedPreferences prefs) {
        Set<String> apps = new HashSet<>(prefs.getStringSet(KEY, Collections.emptySet()));
        apps.removeIf(pkg -> !CoolapkProfile.PACKAGE.equals(pkg) && ExactChinaProfile.find(pkg) == null);
        return apps;
    }

    public static boolean requested(SharedPreferences prefs, String pkg) {
        return requested(prefs).contains(pkg);
    }

    public static void migrate(SharedPreferences prefs) {
        if (prefs.getStringSet(KEY, null) != null) {
            prefs.edit().remove("coolapk_china").apply();
            return;
        }
        Set<String> apps = new HashSet<>();
        // Preserve only the effective 0.5 choice, not a dormant legacy flag.
        if (prefs.getBoolean("coolapk_china", false) && prefs.getBoolean("enabled", false)
                && prefs.getStringSet("selected", Collections.emptySet()).contains(CoolapkProfile.PACKAGE)) {
            apps.add(CoolapkProfile.PACKAGE);
        }
        prefs.edit().putStringSet(KEY, apps).remove("coolapk_china").apply();
    }
}
