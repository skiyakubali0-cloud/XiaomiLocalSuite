package local.xuanyuan.mipushcompat;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.os.SystemClock;
import android.util.Log;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModule;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/** Keep the exact wallet SDK's own heartbeat and cancellation, with a bounded idle gap. */
final class WalletHeartbeat {
    static final long MAX_INTERVAL = 180000L;
    private static final String ACTION = "com.xiaomi.push.PING_TIMER";

    static void install(XposedModule module, ClassLoader loader, AtomicBoolean ready, int uid)
            throws ReflectiveOperationException {
        Class<?> policy = Class.forName("com.xiaomi.push.service.r0", false, loader);
        Class<?> timer = Class.forName("com.xiaomi.push.k3", false, loader);
        Method interval = WalletChinaRoute.sdkMethod(policy, "b", long.class);
        Method schedule = MihomeProfile.exactMethod(timer, "b", void.class, Intent.class, long.class);
        if (Modifier.isStatic(schedule.getModifiers())) throw new NoSuchMethodException("static timer");
        Field policyContext = uniqueField(policy, Context.class);
        Field timerContext = uniqueField(timer, Context.class);
        Field pending = uniqueField(timer, PendingIntent.class);
        AtomicInteger reports = new AtomicInteger();
        module.hook(interval).setId("wallet-heartbeat-interval")
            .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                Object result = chain.proceed();
                if (!ready.get()) return result;
                try {
                    Context context = (Context) policyContext.get(chain.getThisObject());
                    AlarmManager alarm = alarm(context, uid);
                    if (alarm == null || !alarm.canScheduleExactAlarms()) return result;
                    long original = (Long) result;
                    if (original > MAX_INTERVAL) {
                        report(module, reports, "native interval capped at 180000 ms");
                        return MAX_INTERVAL;
                    }
                } catch (ReflectiveOperationException | RuntimeException | LinkageError ignored) { }
                return result;
            });
        module.hook(schedule).setId("wallet-heartbeat-alarm")
            .setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH).intercept(chain -> {
                // Original creates and remembers the PendingIntent; its cancellation remains intact.
                Object result = chain.proceed();
                if (!ready.get()) return result;
                try {
                    Intent intent = (Intent) chain.getArg(0);
                    if (intent == null || intent.getComponent() != null || intent.getSelector() != null
                            || !ACTION.equals(intent.getAction())
                            || !WalletChinaRoute.PACKAGE.equals(intent.getPackage())) return result;
                    Context context = (Context) timerContext.get(chain.getThisObject());
                    AlarmManager alarm = alarm(context, uid);
                    PendingIntent operation = (PendingIntent) pending.get(chain.getThisObject());
                    long deadline = (Long) chain.getArg(1), now = SystemClock.elapsedRealtime();
                    if (alarm == null || operation == null || !alarm.canScheduleExactAlarms()
                            || !WalletChinaRoute.PACKAGE.equals(operation.getCreatorPackage())
                            || operation.getCreatorUid() != uid || deadline <= now
                            || deadline - now > MAX_INTERVAL) return result;
                    alarm.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, deadline, operation);
                    report(module, reports, "native wallet heartbeat scheduled exactly");
                } catch (ReflectiveOperationException | RuntimeException | LinkageError ignored) { }
                return result;
            });
    }

    private static AlarmManager alarm(Context context, int uid) {
        if (context == null || uid < 0 || uid / 100000 != 0
                || !WalletChinaRoute.PACKAGE.equals(context.getPackageName())
                || context.getApplicationInfo().uid != uid) return null;
        return (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
    }

    private static Field uniqueField(Class<?> owner, Class<?> type) throws NoSuchFieldException {
        Field found = null;
        for (Field field : owner.getDeclaredFields()) {
            if (field.getType() != type || Modifier.isStatic(field.getModifiers())) continue;
            if (found != null) throw new NoSuchFieldException("ambiguous " + type.getSimpleName());
            found = field;
        }
        if (found == null) throw new NoSuchFieldException(type.getSimpleName());
        found.setAccessible(true);
        return found;
    }

    private static void report(XposedModule module, AtomicInteger count, String text) {
        if (count.getAndIncrement() >= 4) return;
        try { module.log(Log.INFO, "MiPushWalletHeartbeat", text); }
        catch (RuntimeException | LinkageError ignored) { }
    }
}
