package local.xuanyuan.mipushcompat;

import java.util.List;

/** Exact official wrapped APK; matching it does not claim a successful SDK scan. */
public final class CoolapkProfile {
    public static final String PACKAGE = "com.coolapk.market";
    public static final long VERSION_CODE = 2609291;
    public static boolean verify(String pkg, long version, List<String> paths) {
        if (!PACKAGE.equals(pkg) || version != VERSION_CODE || paths.size() != 1) return false;
        try { return "9a2be68a5dbb500f40fdd5e183ef36388dec676caaaa23a5a872429ddbba9eff".equals(MihomeProfile.hash(paths.get(0))); }
        catch (java.io.IOException | java.security.NoSuchAlgorithmException error) { return false; }
    }
}
