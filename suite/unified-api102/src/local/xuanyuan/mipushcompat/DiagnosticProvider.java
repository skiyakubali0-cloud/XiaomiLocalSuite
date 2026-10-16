package local.xuanyuan.mipushcompat;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.database.Cursor;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;
import java.util.Arrays;
import java.util.Collections;
import java.util.ArrayList;
import java.util.List;

/** Authenticated, whitelisted observations only; never tokens, payloads or credentials. */
public final class DiagnosticProvider extends ContentProvider {
    public static final Uri URI = Uri.parse("content://local.xuanyuan.mipushcompat.diagnostics");
    @Override public boolean onCreate() { return true; }
    @Override public synchronized Bundle call(String method, String pkg, Bundle extras) {
        if (pkg == null || extras == null || (!"observe".equals(method) && !"mihome".equals(method) && !"coolapk".equals(method))) return null;
        String[] callers = getContext().getPackageManager().getPackagesForUid(Binder.getCallingUid());
        SharedPreferences prefs = getContext().getSharedPreferences("selection", 0);
        if (callers == null || !Arrays.asList(callers).contains(pkg)
                || !prefs.getBoolean("enabled", false)
                || !prefs.getStringSet("selected", Collections.emptySet()).contains(pkg)) return null;
        try {
            PackageInfo info = getContext().getPackageManager().getPackageInfo(pkg, 0);
            if ("coolapk".equals(method)) {
                if (!CoolapkProfile.PACKAGE.equals(pkg) || !prefs.getBoolean(pkg + ".cp_verified", false)
                    || info.getLongVersionCode() != CoolapkProfile.VERSION_CODE
                    || info.lastUpdateTime != prefs.getLong(pkg + ".cp_updated", -1)
                    || info.lastUpdateTime != extras.getLong("updated", -1)
                    || !(extras.get("code") instanceof Long) || !(extras.get("updated") instanceof Long)
                    || !extras.keySet().equals(new java.util.HashSet<>(Arrays.asList("code", "updated")))) return null;
                List<String> paths = new ArrayList<>(); paths.add(info.applicationInfo.sourceDir);
                if (info.applicationInfo.splitSourceDirs != null) paths.addAll(Arrays.asList(info.applicationInfo.splitSourceDirs));
                if (!SdkScanner.sourceIdentity(paths).equals(prefs.getString(pkg + ".cp_identity", ""))) return null;
                prefs.edit().putLong(pkg + ".cp_code", extras.getLong("code"))
                    .putLong(pkg + ".cp_result_updated", info.lastUpdateTime)
                    .putLong(pkg + ".cp_at", System.currentTimeMillis()).apply();
                return new Bundle();
            }
            if ("mihome".equals(method)) {
                if (!MihomeProfile.PACKAGE.equals(pkg) || !prefs.getBoolean(pkg + ".mh_verified", false)
                        || info.getLongVersionCode() != MihomeProfile.VERSION_CODE
                        || !MihomeProfile.VERSION_NAME.equals(info.versionName)
                        || info.lastUpdateTime != prefs.getLong(pkg + ".mh_updated", -1)
                        || info.lastUpdateTime != extras.getLong("updated", -1)) return null;
                List<String> paths = new ArrayList<>(); paths.add(info.applicationInfo.sourceDir);
                if (info.applicationInfo.splitSourceDirs != null) paths.addAll(Arrays.asList(info.applicationInfo.splitSourceDirs));
                if (!SdkScanner.sourceIdentity(paths).equals(prefs.getString(pkg + ".mh_identity", ""))
                        || !extras.keySet().equals(new java.util.HashSet<>(Arrays.asList("event", "route", "code", "updated")))) return null;
                if (!(extras.get("event") instanceof String) || !(extras.get("route") instanceof String)
                        || !(extras.get("code") instanceof Long) || !(extras.get("updated") instanceof Long)) return null;
                String event = extras.getString("event", ""), route = extras.getString("route", "");
                long code = extras.getLong("code", 0);
                if (!MihomeProfile.validEvent(event, route, code)) return null;
                SharedPreferences.Editor editor = prefs.edit();
                if (prefs.getLong(pkg + ".mh_history_updated", -1) != info.lastUpdateTime) {
                    for (String old : MihomeProfile.EVENTS) {
                        String key = pkg + ".mh." + old;
                        editor.remove(key + ".at").remove(key + ".route").remove(key + ".code");
                    }
                }
                String key = pkg + ".mh." + event;
                editor.putLong(pkg + ".mh_history_updated", info.lastUpdateTime)
                        .putLong(key + ".at", System.currentTimeMillis());
                if (event.equals("route") || event.equals("dispatch")) editor.putString(key + ".route", route);
                if (event.equals("decision") || event.equals("registration")) editor.putLong(key + ".code", code);
                editor.apply();
                return new Bundle();
            }
            if (!extras.containsKey("original")) return null;
            prefs.edit().putBoolean(pkg + ".original", extras.getBoolean("original"))
                    .putLong(pkg + ".updated", info.lastUpdateTime)
                    .putLong(pkg + ".observed", System.currentTimeMillis()).apply();
        } catch (android.content.pm.PackageManager.NameNotFoundException | RuntimeException ignored) { return null; }
        return new Bundle();
    }
    @Override public Cursor query(Uri uri, String[] p, String s, String[] a, String sort) { return null; }
    @Override public String getType(Uri uri) { return null; }
    @Override public Uri insert(Uri uri, ContentValues v) { return null; }
    @Override public int delete(Uri uri, String s, String[] a) { return 0; }
    @Override public int update(Uri uri, ContentValues v, String s, String[] a) { return 0; }
}
