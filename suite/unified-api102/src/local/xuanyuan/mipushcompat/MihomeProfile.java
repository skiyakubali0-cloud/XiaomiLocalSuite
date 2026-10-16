package local.xuanyuan.mipushcompat;

import java.io.FileInputStream;
import java.io.IOException;
import java.lang.reflect.Method;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.List;

/** One exact MiHome release; hashes are checked only by the Manager's worker. */
public final class MihomeProfile {
    public static final String PACKAGE = "com.xiaomi.smarthome";
    public static final String VERSION_NAME = "11.7.704";
    public static final long VERSION_CODE = 11070704;
    public static final String BASE_SHA256 = "6d2849c40fe3e931b97d9124e1077e2dd2d262c54b07a81bfa5c34c81f1d6c92";
    public static final String SPLIT_SHA256 = "b6d817797f494a0f8933aeda1715455f415da1caaca45190a0cec19624537b9d";
    public static final List<String> EVENTS = Arrays.asList("decision", "route", "dispatch", "registration", "arrival", "pass_through", "click");

    public static boolean verify(String pkg, String versionName, long versionCode, List<String> paths) {
        if (!PACKAGE.equals(pkg) || !VERSION_NAME.equals(versionName) || versionCode != VERSION_CODE || paths.size() != 2) return false;
        try { return BASE_SHA256.equals(hash(paths.get(0))) && SPLIT_SHA256.equals(hash(paths.get(1))); }
        catch (IOException | NoSuchAlgorithmException error) { return false; }
    }

    static String hash(String path) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (FileInputStream input = new FileInputStream(path)) {
            byte[] bytes = new byte[65536];
            int count;
            while ((count = input.read(bytes)) != -1) digest.update(bytes, 0, count);
        }
        StringBuilder hex = new StringBuilder();
        for (byte b : digest.digest()) hex.append(String.format(java.util.Locale.ROOT, "%02x", b & 255));
        return hex.toString();
    }

    public static Method exactMethod(Class<?> owner, String name, Class<?> result, Class<?>... params) throws NoSuchMethodException {
        for (Method method : owner.getDeclaredMethods()) {
            if (method.getName().equals(name) && method.getReturnType() == result
                    && Arrays.equals(method.getParameterTypes(), params)) return method;
        }
        throw new NoSuchMethodException(name);
    }

    public static boolean validEvent(String event, String route, long code) {
        if (!EVENTS.contains(event)) return false;
        if (event.equals("route") || event.equals("dispatch")) {
            return code == 0 && (route.equals("xmsf") || route.equals("app_local") || route.equals("other"));
        }
        if (!route.isEmpty()) return false;
        return event.equals("registration") || (event.equals("decision") ? code == 0 || code == 1 : code == 0);
    }
}
