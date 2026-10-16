package local.xuanyuan.mipushcompat;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkInfo;
import android.util.Log;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModule;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Permit a native push connection attempt when public validation alone is unavailable. */
final class WalletNetwork {
    static void install(XposedModule module, ClassLoader loader, AtomicBoolean ready, int uid)
            throws ReflectiveOperationException {
        Class<?> service = Class.forName("com.xiaomi.push.service.XMPushService", false, loader);
        Method validation = MihomeProfile.exactMethod(service, "a", boolean.class, Context.class);
        if (Modifier.isStatic(validation.getModifiers())) throw new NoSuchMethodException("static validation");
        AtomicInteger reports = new AtomicInteger();
        module.hook(validation).setId("wallet-native-connection-attempt")
            .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                if (!ready.get()) return chain.proceed();
                boolean permit = false;
                try {
                    Context context = (Context) chain.getArg(0);
                    permit = canAttempt(context, uid);
                    // No network flag or credential is changed; the SDK still performs its real handshake.
                    if (permit && reports.getAndIncrement() < 4) {
                        try { module.log(Log.INFO, "MiPushWalletNetwork", "native attempt allowed on connected unvalidated network"); }
                        catch (RuntimeException | LinkageError ignored) { }
                    }
                } catch (RuntimeException | LinkageError ignored) { }
                return permit ? true : chain.proceed();
            });
    }
    private static boolean canAttempt(Context context, int uid) {
        if (context == null || uid < 0 || uid / 100000 != 0
                || !WalletChinaRoute.PACKAGE.equals(context.getPackageName())
                || context.getApplicationInfo().uid != uid) return false;
        ConnectivityManager manager = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        if (manager == null) return false;
        Network network = manager.getActiveNetwork();
        if (network == null) return false;
        NetworkCapabilities caps = manager.getNetworkCapabilities(network);
        NetworkInfo info = manager.getActiveNetworkInfo();
        return caps != null && info != null && info.isConnected()
                && !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
                && !caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_CAPTIVE_PORTAL)
                && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_SUSPENDED)
                && network.equals(manager.getActiveNetwork());
    }

}
