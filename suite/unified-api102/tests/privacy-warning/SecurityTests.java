import android.app.ActivityThread;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Binder;
import android.os.Build;
import com.miui.server.SecurityManagerService;
import com.miui.server.security.AgentPrivacyService;
import dalvik.system.InMemoryDexClassLoader;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModuleInterface.PackageLoadedParam;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import local.xuanyuan.unified.PrivacyHooks;
import local.xuanyuan.unified.WarningHooks;

/** Executes the actual registered API102 hookers, with no native ART interception. */
public final class SecurityTests {
    private static final int AI = 10123, OTHER = 10456;
    private static final ClassLoader LOADER = SecurityTests.class.getClassLoader();
    private static int checks;
    private static Path mounts;
    private static final Map<Executable, XposedInterface.Hooker> hooks = new LinkedHashMap<>();
    private static final Map<Executable, XposedInterface.Hooker> registered = new LinkedHashMap<>();
    private static final List<Executable> unhooked = new ArrayList<>();
    private static int position, failAt;
    private static String failureStage;
    private static Error installFailure;
    private static Error cleanupFailure;
    private static boolean inspectInstalling;
    private static final List<String> logs = new ArrayList<>();
    private static final XposedInterface api = (XposedInterface) Proxy.newProxyInstance(LOADER,
            new Class<?>[]{XposedInterface.class}, (proxy, method, args) -> {
        if (method.getName().equals("log")) {
            if ("log".equals(failureStage)) throw installFailure;
            logs.add(Arrays.toString(args)); return null;
        }
        if (!method.getName().equals("hook")) throw new AssertionError(method);
        Executable executable = (Executable) args[0];
        position++;
        inject("hook");
        return Proxy.newProxyInstance(LOADER, new Class<?>[]{XposedInterface.HookBuilder.class}, (builder, operation, values) -> {
            if (operation.getName().equals("setExceptionMode")) {
                inject("mode");
                check(values[0] == XposedInterface.ExceptionMode.PASSTHROUGH, "explicit exception propagation");
                return builder;
            }
            if (operation.getName().equals("intercept")) {
                inject("intercept");
                check(!hooks.containsKey(executable), "one registration per executable");
                XposedInterface.Hooker hooker = (XposedInterface.Hooker) values[0];
                hooks.put(executable, hooker);
                registered.put(executable, hooker);
                if (inspectInstalling) inactive(Collections.singletonMap(executable, hooker));
                return Proxy.newProxyInstance(LOADER, new Class<?>[]{XposedInterface.HookHandle.class}, (handle, action, ignored) -> {
                    if (action.getName().equals("unhook")) {
                        unhooked.add(executable); hooks.remove(executable);
                        if (cleanupFailure != null && unhooked.size() == 7) throw cleanupFailure;
                        return null;
                    }
                    if (action.getName().equals("getExecutable")) return executable;
                    throw new AssertionError(action);
                });
            }
            throw new AssertionError(operation);
        });
    });

    interface Body { Object run() throws Throwable; }

    static void inject(String stage) {
        if (position == failAt && stage.equals(failureStage)) throw installFailure;
    }

    static void check(boolean value, String label) {
        checks++;
        if (!value) throw new AssertionError(label);
    }

    static void sameException(Throwable expected, Body body) throws Throwable {
        try { body.run(); } catch (Throwable actual) {
            check(actual == expected, "original exception identity: " + actual);
            return;
        }
        throw new AssertionError("original exception swallowed");
    }

    static Object invoke(Executable executable, Object target, Object[] args, Body original) throws Throwable {
        XposedInterface.Hooker hooker = hooks.get(executable);
        check(hooker != null, "registered: " + executable);
        return invokeHook(hooker, executable, target, args, original);
    }

    static Object invokeHook(XposedInterface.Hooker hooker, Executable executable, Object target,
            Object[] args, Body original) throws Throwable {
        return hooker.intercept(new XposedInterface.Chain() {
            public Executable getExecutable() { return executable; }
            public Object getThisObject() { return target; }
            public List<Object> getArgs() { return Collections.unmodifiableList(Arrays.asList(args)); }
            public Object getArg(int index) { return args[index]; }
            public Object proceed() throws Throwable { return original.run(); }
            public Object proceed(Object[] changed) { throw new AssertionError("arguments changed"); }
            public Object proceedWith(Object changed) { throw new AssertionError("receiver changed"); }
            public Object proceedWith(Object changed, Object[] arguments) { throw new AssertionError("call changed"); }
        });
    }

    static Object call(Object target, String name, Class<?>[] types, Object[] args, Body original) throws Throwable {
        Class<?> owner = target instanceof Class ? (Class<?>) target : target.getClass();
        return invoke(owner.getDeclaredMethod(name, types), target instanceof Class ? null : target, args, original);
    }

    static Object gate(SecurityManagerService service, String name, Body original) throws Throwable {
        boolean region = name.equals("enforceNotInternationalBuild");
        return call(service, name, region ? new Class<?>[0] : new Class<?>[]{String.class},
                region ? new Object[0] : new Object[]{"com.miui.voiceassist"}, original);
    }

    static Object endpoint(SecurityManagerService service, String name, int uid, Body original) throws Throwable {
        boolean update = name.startsWith("update");
        return call(service, name, update ? new Class<?>[]{int.class, boolean.class} : new Class<?>[]{String.class, int.class},
                update ? new Object[]{uid, false} : new Object[]{"com.miui.voiceassist", uid}, original);
    }

    @SuppressWarnings("unchecked")
    static ThreadLocal<Boolean> state() throws Exception {
        Field field = PrivacyHooks.class.getDeclaredField("aiCall"); field.setAccessible(true);
        return (ThreadLocal<Boolean>) field.get(null);
    }

    static void field(Class<?> owner, String name, Object value) throws Exception {
        Field field = owner.getDeclaredField(name); field.setAccessible(true); field.set(null, value);
    }

    static void privacyGuards() throws Throwable {
        PrivacyHooks.install(api, LOADER);
        check(hooks.isEmpty(), "missing privacy marker");
        Files.createFile(mounts.resolve("privacy.enabled"));
        Build.VERSION.SDK_INT=36; PrivacyHooks.install(api, LOADER); check(hooks.isEmpty(), "SDK guard");
        Build.VERSION.SDK_INT=37; Build.DEVICE="other";
        PrivacyHooks.install(api, LOADER); check(hooks.isEmpty(), "device guard");
        Build.DEVICE="xuanyuan"; Build.VERSION.INCREMENTAL="OS4.0.0.6.XOACNXM";
        PrivacyHooks.install(api, LOADER); check(hooks.isEmpty(), "EEA ROM guard");
        Build.VERSION.INCREMENTAL="OS4.0.0.6.XOAEUXM";
        for (String file : new String[]{"services", "framework"}) {
            Path path = mounts.resolve(file); byte[] before = Files.readAllBytes(path);
            Files.write(path, new byte[]{1}); PrivacyHooks.install(api, LOADER);
            check(hooks.isEmpty(), "framework mismatch: " + file); Files.write(path, before);
        }
    }

    static void inactive(Map<Executable, XposedInterface.Hooker> snapshot) throws Throwable {
        // Seed the exact conditions that would otherwise bypass gates or initialize the OEM service.
        Context context = new Context();
        field(PrivacyHooks.class, "context", context);
        field(PrivacyHooks.class, "assistantUid", AI);
        Binder.uid=0;
        for (Map.Entry<Executable, XposedInterface.Hooker> entry : snapshot.entrySet()) {
            for (int uid : new int[]{AI, OTHER}) {
                for (Boolean previous : new Boolean[]{null, false, true}) {
                    if (previous == null) state().remove(); else state().set(previous);
                    Executable executable=entry.getKey();
                    Object[] args=new Object[executable.getParameterCount()];
                    Class<?>[] types=executable.getParameterTypes();
                    for (int i=0;i<args.length;i++) {
                        args[i]=types[i]==int.class ? uid : types[i]==boolean.class ? false
                                : types[i]==Context.class ? context : "com.miui.voiceassist";
                    }
                    SecurityManagerService target=new SecurityManagerService();
                    int before=AgentPrivacyService.calls;
                    int[] calls={0}; Object result=new Object();
                    Body original=() -> {
                        calls[0]++;
                        check(state().get() == previous, "inactive endpoint does not change nested state");
                        return result;
                    };
                    check(invokeHook(entry.getValue(), executable, target, args, original) == result, "inactive returns original result");
                    check(calls[0] == 1, "inactive original executes once: " + executable);
                    Error failure=new AssertionError("inactive original"); calls[0]=0;
                    sameException(failure, () -> invokeHook(entry.getValue(), executable, target, args, () -> {
                        calls[0]++; throw failure;
                    }));
                    check(calls[0] == 1, "inactive failing original executes once");
                    check(target.mAiPrivacy == null && AgentPrivacyService.calls == before, "inactive constructor has no OEM effects");
                    check(state().get() == previous, "inactive restores no state because it never changes it");
                    Field captured=PrivacyHooks.class.getDeclaredField("context"); captured.setAccessible(true);
                    check(captured.get(null) == context, "inactive constructor never captures context");
                }
            }
        }
        state().remove();
    }

    static void resetRegistration() {
        check(hooks.isEmpty(), "no live partial hooks before retry");
        registered.clear(); unhooked.clear(); position=0;
    }

    static void rolledBack() throws Throwable {
        List<Executable> expected=new ArrayList<>(registered.keySet()); Collections.reverse(expected);
        check(unhooked.equals(expected), "every returned handle rolled back in reverse order");
        check(hooks.isEmpty(), "failed group has no remaining registrations");
        inactive(registered);
    }

    static final class MissingMethodLoader extends ClassLoader {
        private final String owner, method;
        MissingMethodLoader(String owner, String method) { super(LOADER); this.owner=owner; this.method=method; }
        protected Class<?> loadClass(String name, boolean resolve) throws ClassNotFoundException {
            if (!name.equals(owner)) return super.loadClass(name, resolve);
            Class<?> type=findLoadedClass(name);
            if (type == null) {
                try {
                    byte[] bytes=Files.readAllBytes(mounts.getParent().resolve("missing/" + method + ".class"));
                    type=defineClass(name, bytes, 0, bytes.length);
                } catch (java.io.IOException e) { throw new ClassNotFoundException(name, e); }
            }
            if (resolve) resolveClass(type);
            return type;
        }
    }

    static void privacyTransaction() throws Throwable {
        List<Map<Executable, XposedInterface.Hooker>> failedSnapshots=new ArrayList<>();
        inspectInstalling=true;
        for (String stage : new String[]{"hook", "mode", "intercept"}) {
            for (int index=1;index<=15;index++) {
                resetRegistration(); failAt=index; failureStage=stage;
                installFailure=new AssertionError("install " + stage + " at " + index);
                sameException(installFailure, () -> { PrivacyHooks.install(api, LOADER); return null; });
                check(position == index, "injected every registration position");
                rolledBack(); failedSnapshots.add(new LinkedHashMap<>(registered));
            }
        }
        resetRegistration(); failAt=0; failureStage="log";
        installFailure=new AssertionError("final install log");
        sameException(installFailure, () -> { PrivacyHooks.install(api, LOADER); return null; });
        check(registered.size() == 15, "failure after entire group still rolls back");
        rolledBack(); failedSnapshots.add(new LinkedHashMap<>(registered));
        resetRegistration();
        installFailure=new AssertionError("install with rollback error");
        cleanupFailure=new AssertionError("one unhook error");
        sameException(installFailure, () -> { PrivacyHooks.install(api, LOADER); return null; });
        check(installFailure.getSuppressed().length == 1 && installFailure.getSuppressed()[0] == cleanupFailure,
                "rollback error is suppressed on original install exception");
        rolledBack(); failedSnapshots.add(new LinkedHashMap<>(registered));
        cleanupFailure=null;
        failureStage=null;
        String[][] missing={
            {"com.miui.server.SecurityManagerService", "accessAppsContentEnable", "accessAppsControlEnable",
                "updateAppContentEnable", "updateAppControlEnable", "shouldDisplayInAISetting",
                "enforceNotInternationalBuild", "checkGrantPermissionPkg", "enforcePackage"},
            {"com.miui.server.SecurityManagerService$LocalService", "accessAppContentEnable", "accessAppControlEnable"},
            {"com.miui.server.security.AgentPrivacyUtils", "shouldSkipAIPermissionCheck"},
            {"com.android.server.input.InputManagerServiceStubImpl", "shouldCheckPermission"}
        };
        for (String[] group : missing) {
            for (int i=1;i<group.length;i++) {
                resetRegistration();
                try {
                    PrivacyHooks.install(api, new MissingMethodLoader(group[0], group[i]));
                    throw new AssertionError("missing required method accepted: " + group[i]);
                } catch (NoSuchMethodException expected) {
                    check(expected.getMessage().contains(group[i]), "missing exact expected method rejected");
                }
                rolledBack(); failedSnapshots.add(new LinkedHashMap<>(registered));
            }
        }
        resetRegistration();
        PrivacyHooks.install(api, LOADER);
        check(hooks.keySet().stream().filter(e -> e instanceof Constructor).count() == 2, "direct constructor support");
        check(hooks.size() == 15, "all overloads and gates registered");
        int before=position;
        PrivacyHooks.install(api, LOADER); check(position == before, "committed group is not installed twice");
        // Old chain snapshots remain inactive even when a later attempt has committed.
        for (Map<Executable, XposedInterface.Hooker> snapshot : failedSnapshots) inactive(snapshot);
        inspectInstalling=false;
        field(PrivacyHooks.class, "context", null);
        field(PrivacyHooks.class, "assistantUid", -1);
        System.out.println("PASS: failure at 15 positions x 3 API stages, final log, rollback error, and 12 missing methods; inactive stale snapshots after retry");
    }

    static SecurityManagerService constructors() throws Throwable {
        SecurityManagerService service = new SecurityManagerService();
        Throwable failure = new AssertionError("original constructor");
        int before = AgentPrivacyService.calls;
        int[] originalCalls={0};
        sameException(failure, () -> invoke(SecurityManagerService.class.getConstructor(), service, new Object[0], () -> {
            originalCalls[0]++; throw failure;
        }));
        check(originalCalls[0] == 1, "active failing constructor original executes once");
        check(service.mAiPrivacy == null && AgentPrivacyService.calls == before, "failed original skips optional init");
        for (Constructor<?> constructor : SecurityManagerService.class.getConstructors()) {
            originalCalls[0]=0;
            invoke(constructor, service, constructor.getParameterCount()==0 ? new Object[0] : new Object[]{1}, () -> {
                originalCalls[0]++; return null;
            });
            check(originalCalls[0] == 1, "active constructor original executes once");
        }
        check(AgentPrivacyService.calls == before + 1, "existing OEM service reused");
        Object existing = service.mAiPrivacy;
        AgentPrivacyService.fail=true;
        SecurityManagerService optionalFailure = new SecurityManagerService();
        originalCalls[0]=0;
        check(invoke(SecurityManagerService.class.getConstructor(), optionalFailure, new Object[0], () -> {
            originalCalls[0]++; return null;
        }) == null,
                "optional init exception does not replace original success");
        check(originalCalls[0] == 1, "optional init failure does not replay original constructor");
        check(logs.stream().anyMatch(log -> log.contains("init failed")), "optional init error logged");
        AgentPrivacyService.fail=false;
        check(service.mAiPrivacy == existing, "other instance service preserved");
        return service;
    }

    static void privacySecurity(SecurityManagerService service) throws Throwable {
        Throwable denied = new SecurityException("OEM denied");
        Object result = new Object();
        for (String name : new String[]{"accessAppsContentEnable", "accessAppsControlEnable", "updateAppContentEnable",
                "updateAppControlEnable", "shouldDisplayInAISetting"}) {
            Binder.uid=0;
            check(endpoint(service, name, AI, () -> {
                check(Boolean.TRUE.equals(state().get()), "AI state active: " + name);
                for (String gate : new String[]{"enforceNotInternationalBuild", "checkGrantPermissionPkg", "enforcePackage"}) {
                    check(gate(service, gate, () -> { throw denied; }) == null, "root AI gate: " + gate);
                }
                return result;
            }) == result, "endpoint return preserved");
            check(state().get() == null, "outer state removed");
            for (int uid : new int[]{OTHER, 0, 9999, AI + 100000}) {
                endpoint(service, name, uid, () -> {
                    check(Boolean.FALSE.equals(state().get()), "nonassistant UID: " + uid);
                    for (String gate : new String[]{"enforceNotInternationalBuild", "checkGrantPermissionPkg", "enforcePackage"}) {
                        sameException(denied, () -> gate(service, gate, () -> { throw denied; }));
                    }
                    return null;
                });
            }
            for (int caller : new int[]{AI, OTHER, 1000}) {
                Binder.uid=caller;
                endpoint(service, name, AI, () -> {
                    for (String gate : new String[]{"checkGrantPermissionPkg", "enforcePackage"}) {
                        sameException(denied, () -> gate(service, gate, () -> { throw denied; }));
                    }
                    return null;
                });
            }
            sameException(denied, () -> endpoint(service, name, AI, () -> { throw denied; }));
            check(state().get() == null, "exception cleanup");
        }
        check("com.miui.voiceassist".equals(PackageManager.requested), "exact XiaoAI package lookup");
        Binder.uid=0;
        for (String gate : new String[]{"enforceNotInternationalBuild", "checkGrantPermissionPkg", "enforcePackage"}) {
            sameException(denied, () -> gate(service, gate, () -> { throw denied; }));
        }
        endpoint(service, "accessAppsContentEnable", AI, () -> {
            sameException(denied, () -> endpoint(service, "updateAppControlEnable", OTHER, () -> {
                check(Boolean.FALSE.equals(state().get()), "recursive nonassistant clears outer AI state");
                sameException(denied, () -> endpoint(service, "accessAppsControlEnable", AI, () -> { throw denied; }));
                check(Boolean.FALSE.equals(state().get()), "inner exception restores middle false");
                check(endpoint(service, "accessAppsControlEnable", AI, () -> result) == result, "recursive normal return");
                check(Boolean.FALSE.equals(state().get()), "inner success restores middle false");
                throw denied;
            }));
            check(Boolean.TRUE.equals(state().get()), "recursive exception restores outer true");
            check(endpoint(service, "updateAppControlEnable", OTHER, () -> result) == result, "middle normal return");
            check(Boolean.TRUE.equals(state().get()), "middle success restores outer true");
            final Throwable[] childFailure = new Throwable[1];
            Thread thread = new Thread(() -> {
                try { sameException(denied, () -> gate(service, "enforcePackage", () -> { throw denied; })); }
                catch (Throwable t) { childFailure[0]=t; }
            });
            thread.start(); thread.join();
            if (childFailure[0] != null) throw childFailure[0];
            return null;
        });
        check(state().get() == null, "recursive outer cleanup");
        state().set(false);
        sameException(denied, () -> endpoint(service, "accessAppsContentEnable", AI, () -> { throw denied; }));
        check(Boolean.FALSE.equals(state().get()), "restore explicit false"); state().remove();
        Object privacy = service.mAiPrivacy; service.mAiPrivacy=null;
        endpoint(service, "accessAppsContentEnable", AI, () -> {
            sameException(denied, () -> gate(service, "enforceNotInternationalBuild", () -> { throw denied; })); return null;
        });
        service.mAiPrivacy=privacy;
        field(PrivacyHooks.class, "assistantUid", -1); PackageManager.missing=true;
        endpoint(service, "accessAppsContentEnable", AI, () -> {
            check(Boolean.FALSE.equals(state().get()), "missing package fails closed"); return null;
        });
        PackageManager.missing=false;
        Class<?> utils=Class.forName("com.miui.server.security.AgentPrivacyUtils");
        Object input=Class.forName("com.android.server.input.InputManagerServiceStubImpl").getConstructor().newInstance();
        Object local=new SecurityManagerService.LocalService();
        for (int uid : new int[]{AI, OTHER, AI + 100000}) {
            check(call(utils, "shouldSkipAIPermissionCheck", new Class<?>[]{Context.class,int.class}, new Object[]{new Context(),uid}, () -> true)
                    .equals(uid != AI), "only AI loses skip");
            check(call(input, "shouldCheckPermission", new Class<?>[]{int.class}, new Object[]{uid}, () -> false)
                    .equals(uid == AI), "only AI input permission check enabled");
            for (String name : new String[]{"accessAppContentEnable", "accessAppControlEnable"}) {
                check(call(local, name, new Class<?>[]{int.class}, new Object[]{uid}, () -> false)
                        .equals(uid != AI), "local policy isolation");
            }
        }
        call(service, "accessAppsContentEnable", new Class<?>[]{String.class,int.class,int.class}, new Object[]{"pkg",AI,1}, () -> {
            check(Boolean.TRUE.equals(state().get()), "overloaded endpoint intercepted"); return null;
        });
        check(miui.os.Build.IS_INTERNATIONAL_BUILD, "global region unchanged");
    }

    public static final class TargetLoader extends ClassLoader {
        public final InMemoryDexClassLoader.PathList pathList=new InMemoryDexClassLoader.PathList();
        TargetLoader() { super(LOADER); pathList.dexElements=new Object[]{"original"}; }
    }

    static void warningCase(String label, String pkg, String process, boolean enabled, boolean goodApk,
            boolean goodDex, boolean expected, boolean retry) throws Throwable {
        field(WarningHooks.class, "loaded", false);
        if (enabled) Files.write(mounts.resolve("warning.enabled"), new byte[0]);
        else Files.deleteIfExists(mounts.resolve("warning.enabled"));
        ActivityThread.process=process;
        TargetLoader target=new TargetLoader(); Object[] original=target.pathList.dexElements;
        ApplicationInfo info=new ApplicationInfo(); info.sourceDir=mounts.resolve(goodApk ? "apk" : "framework").toString();
        PackageLoadedParam param=(PackageLoadedParam) Proxy.newProxyInstance(LOADER, new Class<?>[]{PackageLoadedParam.class},
                (proxy, method, args) -> {
                    switch (method.getName()) {
                        case "getPackageName": return pkg;
                        case "getApplicationInfo": return info;
                        case "getDefaultClassLoader": return target;
                        case "isFirstPackage": return true;
                        default: throw new AssertionError("wrong lifecycle API: " + method);
                    }
                });
        Path dex=mounts.resolve("warning.dex"); byte[] bytes=Files.readAllBytes(dex);
        if (!goodDex) Files.write(dex,new byte[]{0});
        int before=InMemoryDexClassLoader.calls;
        WarningHooks.install(api,param);
        check((target.pathList.dexElements != original) == expected, label);
        check(InMemoryDexClassLoader.calls == before + (expected ? 1 : 0), label + " verifies before loader creation");
        if (expected) {
            check(Arrays.equals(target.pathList.dexElements,new Object[]{"donor-first","donor-second","original"}), "prepend order");
            Object[] installed=target.pathList.dexElements;
            WarningHooks.install(api,param); check(target.pathList.dexElements == installed, "warning install once");
        }
        Files.write(dex,bytes);
        if (retry) {
            WarningHooks.install(api,param);
            check(target.pathList.dexElements != original, "bad DEX did not latch loaded");
        }
        check(miui.os.Build.IS_INTERNATIONAL_BUILD, "warning leaves global region");
    }

    static void warningSecurity() throws Throwable {
        warningCase("missing marker", "com.miui.securitycenter", "com.miui.securitycenter", false,true,true,false,false);
        warningCase("other package", "other", "com.miui.securitycenter", true,true,true,false,false);
        warningCase("other process", "com.miui.securitycenter", "other", true,true,true,false,false);
        warningCase("missing process", "com.miui.securitycenter", null, true,true,true,false,false);
        ActivityThread.fail=true;
        warningCase("process lookup failure", "com.miui.securitycenter", "com.miui.securitycenter", true,true,true,false,false);
        ActivityThread.fail=false;
        warningCase("bad APK", "com.miui.securitycenter", "com.miui.securitycenter", true,false,true,false,false);
        warningCase("bad DEX", "com.miui.securitycenter", "com.miui.securitycenter", true,true,false,false,true);
        Build.VERSION.SDK_INT=36;
        warningCase("warning SDK guard", "com.miui.securitycenter", "com.miui.securitycenter", true,true,true,false,false);
        Build.VERSION.SDK_INT=37; Build.DEVICE="other";
        warningCase("warning device guard", "com.miui.securitycenter", "com.miui.securitycenter", true,true,true,false,false);
        Build.DEVICE="xuanyuan"; Build.VERSION.INCREMENTAL="OS4.0.0.6.XOACNXM";
        warningCase("warning ROM guard", "com.miui.securitycenter", "com.miui.securitycenter", true,true,true,false,false);
        Build.VERSION.INCREMENTAL="OS4.0.0.6.XOAEUXM";
        warningCase("main process", "com.miui.securitycenter", "com.miui.securitycenter", true,true,true,true,false);
        warningCase("original process prefix", "com.miui.securitycenter", "com.miui.securitycenter:remote", true,true,true,true,false);
    }

    public static void main(String[] args) throws Throwable {
        mounts=Paths.get(args[0]); privacyGuards(); privacyTransaction(); privacySecurity(constructors()); warningSecurity();
        System.out.println("PASS: " + checks + " host assertions (real API102, Reflect and synthetic DEX hash gate)");
    }
}
