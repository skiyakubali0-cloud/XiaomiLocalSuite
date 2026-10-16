package local.xuanyuan.mipushcompat;

import java.util.List;

/** Reviewed CN SDK builds only; detection alone never authorizes routing. */
public final class ExactChinaProfile {
    public final String pkg, sha256, owner, decision, route, receiver;
    public final long version;

    private ExactChinaProfile(String pkg, long version, String sha256, String owner,
            String decision, String route, String receiver) {
        this.pkg = pkg; this.version = version; this.sha256 = sha256; this.owner = owner;
        this.decision = decision; this.route = route; this.receiver = receiver;
    }

    public static ExactChinaProfile find(String pkg) {
        if ("com.miui.mediaeditor".equals(pkg)) return new ExactChinaProfile(pkg, 210994048,
                "e7c37c8ee2e10e8e45b60ad3ff293ad8a0b1c702f9e79aaa8df97ecfbcf4f699",
                "an0.a0", "m", "c", "com.miui.camerainfra.cloudconfig.push.cn.MiPushMessageReceiver");
        if ("com.miui.virtualsim".equals(pkg)) return new ExactChinaProfile(pkg, 9190,
                "281b31cc1421c4880121baad94ab65f363ed3e60c1bdc179e7df63d890c56eb2",
                "com.xiaomi.mipush.sdk.ak", "a", "a", "com.miui.virtualsim.push.MiPushMessageReceiver");
        if ("com.mipay.wallet".equals(pkg)) return new ExactChinaProfile(pkg, 20577699,
                "c5fa1012886f21d9be2453d66e741d6821e9b94d39a6881318c3d1d196ddb058",
                "com.xiaomi.mipush.sdk.g0", "K", "d", "com.xiaomi.jr.app.mipush.MiPushMessageBroadcastReceiver");
        return null;
    }

    public static boolean verify(String pkg, long version, List<String> paths) {
        ExactChinaProfile profile = find(pkg);
        if (profile == null || version != profile.version || paths.size() != 1) return false;
        try { return profile.sha256.equals(MihomeProfile.hash(paths.get(0))); }
        catch (java.io.IOException | java.security.NoSuchAlgorithmException error) { return false; }
    }
}
