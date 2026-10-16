package local.xuanyuan.mipushcompat;

import io.github.libxposed.api.XposedInterface;
import java.util.function.Consumer;

/** Original execution is never inside the diagnostic error handler. */
public final class OriginalGuard {
    public static Object intercept(XposedInterface.Chain chain, Consumer<Object> diagnostic) throws Throwable {
        Object result = chain.proceed();
        try { diagnostic.accept(result); }
        catch (RuntimeException | LinkageError ignored) { /* Reporting must not change the app's result. */ }
        return result;
    }
}
