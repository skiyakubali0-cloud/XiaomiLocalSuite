package local.xuanyuan.unified;

import android.content.Context;
import android.os.Binder;
import android.os.Build;
import android.util.Log;
import java.io.File;
import java.lang.reflect.Constructor;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import io.github.libxposed.api.XposedInterface;

/** Enable the existing OEM AI permission service only for XiaoAI on the verified EEA build. */
public final class PrivacyHooks {
    private static volatile Context context;
    private static volatile int assistantUid = -1;
    private static final ThreadLocal<Boolean> aiCall = new ThreadLocal<>();
    private static Installation installed;

    private static final class Installation {
        // Each attempt owns its gate: a failed attempt must stay inert even after a retry.
        volatile boolean active;
        final List<XposedInterface.HookHandle> handles = new ArrayList<>();

        void hook(XposedInterface api, Executable executable, XposedInterface.Hooker hooker) {
            handles.add(api.hook(executable).setExceptionMode(XposedInterface.ExceptionMode.PASSTHROUGH)
                    .intercept(chain -> active ? hooker.intercept(chain) : chain.proceed()));
        }

        void rollback(Throwable failure) {
            active = false;
            for (int i = handles.size() - 1; i >= 0; i--) {
                try { handles.get(i).unhook(); }
                catch (Throwable cleanup) { if (cleanup != failure) failure.addSuppressed(cleanup); }
            }
        }
    }

    private static boolean assistant(int uid) {
        if (context == null || uid < 10000) return false;
        if (assistantUid < 0) {
            try { assistantUid = context.getPackageManager().getApplicationInfo("com.miui.voiceassist", 0).uid; }
            catch (Exception e) { return false; }
        }
        return uid == assistantUid;
    }

    private static void hookMethods(Installation installation, XposedInterface api, Class<?> owner,
            String name, XposedInterface.Hooker hooker) throws NoSuchMethodException {
        boolean found = false;
        for (Method method : owner.getDeclaredMethods()) {
            if (method.getName().equals(name)) {
                found = true;
                installation.hook(api, method, hooker);
            }
        }
        if (!found) throw new NoSuchMethodException(owner.getName() + "." + name);
    }

    /** Called only from onSystemServerStarting, before SecurityManagerService is constructed. */
    public static synchronized void install(XposedInterface api, ClassLoader systemServerLoader) throws Throwable {
        if (installed != null) return;
        if (Build.VERSION.SDK_INT != 37 || !"xuanyuan".equals(Build.DEVICE)
                || !"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)) return;
        if (!new File("/product/etc/xuanyuan-ai-privacy.enabled").isFile()) return;
        if (!"cef17afe99cfa6396922e2fe1dce6642ec86ddcf141589b8ef4d007d6920ecdb".equals(
                    Reflect.hashFile("/system_ext/framework/miui-services.jar"))
                || !"55f69e60be40e1daf88fed21d4bb21cc82410497af329c61ea65df469dbaca30".equals(
                    Reflect.hashFile("/system_ext/framework/miui-framework.jar"))) {
            api.log(Log.WARN, "XuanyuanAiPrivacy", "framework mismatch; inactive"); return;
        }
        Class<?> service = Reflect.type("com.miui.server.SecurityManagerService", systemServerLoader);
        Class<?> privacy = Reflect.type("com.miui.server.security.AgentPrivacyService", systemServerLoader);
        Installation installation = new Installation();
        try {
            // Do not flip IS_INTERNATIONAL_BUILD in system_server.
            for (Constructor<?> constructor : service.getDeclaredConstructors()) {
                installation.hook(api, constructor, chain -> {
                    Object result = chain.proceed(); // Constructor failure must escape unchanged.
                    try {
                        context = (Context) Reflect.get(chain.getThisObject(), "mContext");
                        if (Reflect.get(chain.getThisObject(), "mAiPrivacy") == null) {
                            Object handler = Reflect.get(chain.getThisObject(), "mSecurityWriteHandler");
                            Reflect.set(chain.getThisObject(), "mAiPrivacy", Reflect.construct(privacy, context, handler));
                        }
                        api.log(Log.INFO, "XuanyuanAiPrivacy", "OEM permission service initialized");
                    } catch (Throwable e) { api.log(Log.WARN, "XuanyuanAiPrivacy", "init failed", e); }
                    return result;
                });
            }
            for (String name : new String[]{"accessAppsContentEnable", "accessAppsControlEnable",
                    "updateAppContentEnable", "updateAppControlEnable", "shouldDisplayInAISetting"}) {
                final int uidIndex = name.startsWith("update") ? 0 : 1;
                hookMethods(installation, api, service, name, chain -> {
                    Boolean previous = aiCall.get();
                    try {
                        aiCall.set(assistant((Integer) chain.getArg(uidIndex))
                                && Reflect.get(chain.getThisObject(), "mAiPrivacy") != null);
                        return chain.proceed();
                    } finally {
                        if (previous == null) aiCall.remove(); else aiCall.set(previous);
                    }
                });
            }
            hookMethods(installation, api, service, "enforceNotInternationalBuild", chain ->
                    Boolean.TRUE.equals(aiCall.get()) ? null : chain.proceed());
            // Root helpers may manage only XiaoAI AI endpoints; app callers retain OEM checks.
            for (String name : new String[]{"checkGrantPermissionPkg", "enforcePackage"}) {
                hookMethods(installation, api, service, name, chain ->
                        Boolean.TRUE.equals(aiCall.get()) && Binder.getCallingUid() == 0 ? null : chain.proceed());
            }
            installation.hook(api, Reflect.method(Reflect.type("com.miui.server.security.AgentPrivacyUtils", systemServerLoader),
                    "shouldSkipAIPermissionCheck", Context.class, int.class), chain ->
                            assistant((Integer) chain.getArg(1)) ? false : chain.proceed());
            // Initializing the service must not introduce policy changes for other EEA apps.
            Class<?> local = Reflect.type("com.miui.server.SecurityManagerService$LocalService", systemServerLoader);
            for (String name : new String[]{"accessAppContentEnable", "accessAppControlEnable"}) {
                hookMethods(installation, api, local, name, chain ->
                        !assistant((Integer) chain.getArg(0)) ? true : chain.proceed());
            }
            installation.hook(api, Reflect.method(Reflect.type("com.android.server.input.InputManagerServiceStubImpl", systemServerLoader),
                    "shouldCheckPermission", int.class), chain ->
                            assistant((Integer) chain.getArg(0)) ? true : chain.proceed());
            api.log(Log.INFO, "XuanyuanAiPrivacy", "exact framework verified; XiaoAI-only hooks installed");
        } catch (Throwable failure) {
            installation.rollback(failure);
            throw failure;
        }
        installed = installation;
        installation.active = true;
    }
}
