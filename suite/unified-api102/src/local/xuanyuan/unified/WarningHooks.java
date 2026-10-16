package local.xuanyuan.unified;

import android.os.Build;
import android.util.Log;
import dalvik.system.InMemoryDexClassLoader;
import java.io.*;
import java.lang.reflect.Array;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModuleInterface;

public final class WarningHooks {
    private static boolean loaded;

    private static String sha(byte[] bytes) throws Exception {
        StringBuilder out = new StringBuilder();
        for (byte b : MessageDigest.getInstance("SHA-256").digest(bytes)) out.append(String.format("%02x", b & 255));
        return out.toString();
    }

    private static byte[] read(String path) throws Exception {
        try (InputStream in = new FileInputStream(path); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[65536]; int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }

    /** Prepend before AppComponentFactory/application classes resolve, from onPackageLoaded. */
    public static synchronized void install(XposedInterface api,
            XposedModuleInterface.PackageLoadedParam p) throws Throwable {
        if (loaded || !"com.miui.securitycenter".equals(p.getPackageName())
                || Build.VERSION.SDK_INT != 37 || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)
                || !new File("/product/etc/xuanyuan-warning.enabled").isFile()) return;
        try {
            Object process = Reflect.call(Reflect.type("android.app.ActivityThread", null), "currentProcessName");
            if (!(process instanceof String) || !((String) process).startsWith("com.miui.securitycenter")) return;
            if (!"f3d338484cc5fd3f3fec9e8d9d0b4c6370923fba0f5e0d81975a45e914cbc776".equals(
                    Reflect.hashFile(p.getApplicationInfo().sourceDir))) {
                api.log(Log.WARN, "XuanyuanWarning", "unsupported APK; inactive"); return;
            }
            byte[] dex = read("/product/framework/xuanyuan-warning.dex");
            // The original Payload and its SHA256 field are package-private module classes.
            Object expected = Reflect.get(Reflect.type("local.xuanyuan.disastercompat.Payload",
                    WarningHooks.class.getClassLoader()), "SHA256");
            if (!sha(dex).equals(expected)) throw new SecurityException("Warning DEX mismatch");
            ClassLoader loader = p.getDefaultClassLoader();
            ClassLoader donor = new InMemoryDexClassLoader(ByteBuffer.wrap(dex), loader);
            Object targetPath = Reflect.get(loader, "pathList");
            Object donorPath = Reflect.get(donor, "pathList");
            Object[] before = (Object[]) Reflect.get(targetPath, "dexElements");
            Object[] extra = (Object[]) Reflect.get(donorPath, "dexElements");
            Object[] combined = (Object[]) Array.newInstance(before.getClass().getComponentType(), extra.length + before.length);
            System.arraycopy(extra, 0, combined, 0, extra.length);
            System.arraycopy(before, 0, combined, extra.length, before.length);
            Reflect.set(targetPath, "dexElements", combined);
            loaded = true;
            boolean international = (Boolean) Reflect.get(Reflect.type("miui.os.Build", loader), "IS_INTERNATIONAL_BUILD");
            api.log(Log.INFO, "XuanyuanWarning", "1.1 active; 18 classes/21 gates including policeassist; international="
                    + international + "; process=" + process);
        } catch (Throwable e) { api.log(Log.WARN, "XuanyuanWarning", "inactive", e); }
    }
}
