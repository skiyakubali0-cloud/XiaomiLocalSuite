package local.xuanyuan.unified;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.database.sqlite.SQLiteDatabase;
import android.os.Build;
import android.os.Bundle;
import com.android.deskclock.settings.SettingsFragment;
import com.miui.audiomonitor.VoipRecordSettingsActivity;
import com.miui.smsextra.understand.UnderstandFactory;
import com.miui.yellowpage.providers.yellowpage.YellowPageDatabaseHelper;
import io.github.libxposed.api.XposedInterface;
import io.github.libxposed.api.XposedModuleInterface;
import java.lang.reflect.Executable;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public final class Harness {
    public interface Work { Object run(Object[] args) throws Throwable; }
    private static int assertions;
    private static final Map<String, String> HASHES = new LinkedHashMap<>();
    private static final ClassLoader LOADER = Harness.class.getClassLoader();
    static {
        HASHES.put("com.android.providers.telephony", "c5aaafabb1679f7c2a7edd23c69366548bb5bf0591bd2293c15623522db4f9b5");
        HASHES.put("com.android.mms", "0a59d7338d31c70a0fb8f5477f264033d77abf4101f2897a60ffbabacbb1da14");
        HASHES.put("com.miui.audiomonitor", "83133a62f37cefe873075064d39c5e176e768af251d678438a242116be8178b1");
        HASHES.put("com.android.soundrecorder", "26cc4ef1ba6dc07013837a0b12fb91a31eff340f0b4496a91cc48387ebb72dcc");
        HASHES.put("com.android.incallui", "590f2ed0e5e0923e79a452d72cd9c6e9783e1dde4cb8c987355ebcfce7b8c3bd");
        HASHES.put("com.miui.yellowpage", "e07e59b9d9a99b0cce4bf06b9734002016b1c3bebe701c6ee368cdc8161cb733");
        HASHES.put("com.android.deskclock", "41defcfd640a3ba5d359c20004d9dced5f6c0810204c41c94530af2a2bc1e9f6");
        HASHES.put("com.miui.personalassistant", "6ecb326cd18351e032f5fe493c1bc1bb28e417bd03954e5133c237bcffc43562");
        HASHES.put("com.xiaomi.aicr", "f081299f3e638d188a2d3d2ace6aeef4ab9d0226f775fc7474495812f67b8520");
    }

    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) throw new AssertionError(message);
    }

    private static final class Api {
        final Map<Method, XposedInterface.Hooker> hooks = new LinkedHashMap<>();
        final List<String> logs = new ArrayList<>();
        boolean failLog;
        final XposedInterface api = (XposedInterface) Proxy.newProxyInstance(LOADER,
                new Class<?>[]{XposedInterface.class}, (proxy, method, args) -> {
            if (method.getName().equals("hook")) {
                Method target = (Method) args[0];
                return Proxy.newProxyInstance(LOADER, new Class<?>[]{XposedInterface.HookBuilder.class},
                        new java.lang.reflect.InvocationHandler() {
                    XposedInterface.ExceptionMode mode;
                    public Object invoke(Object builder, Method m, Object[] a) {
                        if (m.getName().equals("setExceptionMode")) {mode = (XposedInterface.ExceptionMode) a[0]; return builder;}
                        if (m.getName().equals("intercept")) {
                            check(mode == XposedInterface.ExceptionMode.PASSTHROUGH, "explicit exception semantics");
                            check(hooks.put(target, (XposedInterface.Hooker) a[0]) == null, "exact unique hook");
                            return null;
                        }
                        throw new AssertionError(m);
                    }
                });
            }
            if (method.getName().equals("log")) {
                check(args.length == 3 && args[0].equals(4), "safe INFO log overload");
                check(((String) args[1]).length() < 32 && ((String) args[2]).length() < 160, "bounded logs");
                if (failLog) throw new IllegalStateException("logger");
                logs.add((String) args[2]);
                return null;
            }
            throw new AssertionError("Unexpected API operation: " + method);
        });

        TestChain call(String owner, String method, Object receiver, Object[] args, Work work) throws Throwable {
            Method target = null;
            for (Method m : hooks.keySet()) if (m.getDeclaringClass().getName().equals(owner)
                    && m.getName().equals(method)) target = m;
            check(target != null, "registered " + owner + "." + method);
            TestChain chain = new TestChain(target, receiver, args, work);
            chain.result = hooks.get(target).intercept(chain);
            check(chain.calls <= 1, "no double invocation: " + target);
            return chain;
        }
    }

    private static final class TestChain implements XposedInterface.Chain {
        final Method method;
        final Object receiver;
        final Object[] args;
        final Work work;
        int calls;
        Object[] actualArgs;
        Object result;
        TestChain(Method m, Object r, Object[] a, Work w) {method=m;receiver=r;args=a;work=w;}
        public Executable getExecutable() {return method;}
        public Object getThisObject() {return receiver;}
        public List<Object> getArgs() {return Collections.unmodifiableList(Arrays.asList(args));}
        public Object getArg(int i) {return args[i];}
        public Object proceed() throws Throwable {return proceed(args);}
        public Object proceed(Object[] a) throws Throwable {
            check(++calls == 1, "original invoked once");actualArgs=a;return work.run(a);
        }
        public Object proceedWith(Object r) {throw new AssertionError("receiver swap");}
        public Object proceedWith(Object r, Object[] a) {throw new AssertionError("receiver swap");}
    }

    private static XposedModuleInterface.PackageReadyParam param(String name) {
        ApplicationInfo info = new ApplicationInfo();info.sourceDir=name;
        return (XposedModuleInterface.PackageReadyParam) Proxy.newProxyInstance(LOADER,
                new Class<?>[]{XposedModuleInterface.PackageReadyParam.class}, (proxy, method, args) -> {
            switch (method.getName()) {
                case "getPackageName": return name;
                case "getApplicationInfo": return info;
                case "getClassLoader": case "getDefaultClassLoader": return LOADER;
                case "isFirstPackage": return true;
                case "getAppComponentFactory": return null;
                default: throw new AssertionError(method);
            }
        });
    }

    private static void install(Api api, String name) throws Throwable {
        XposedModuleInterface.PackageReadyParam p = param(name);
        PhoneHooks.install(api.api, p);ClockHooks.install(api.api, p);SuggestionHooks.install(api.api, p);
    }

    private static Api installed(String name) throws Throwable {
        Reflect.fail=null;Reflect.hashes.put(name,HASHES.get(name));
        Api api=new Api();install(api,name);return api;
    }

    private static void sameFailure(Api api, String owner, String name, Object receiver, Object... args) throws Throwable {
        Throwable marker = new Throwable("original identity");
        int[] calls = {0};
        try {
            api.call(owner, name, receiver, args, a -> {calls[0]++;throw marker;});
            throw new AssertionError("swallowed original exception");
        } catch (Throwable thrown) {
            check(thrown == marker, "unchanged exception identity: " + name);
            check(calls[0] == 1, "failing original invoked exactly once");
        }
    }

    private static void guards() throws Throwable {
        // Every package gets positive controls, then independent ROM and APK negatives.
        int[] counts={0,5,3,1,1,6,2,1,1};int index=0;
        for(String name:HASHES.keySet()) {
            Api positive=installed(name);
            check(positive.hooks.size()==counts[index++],"package-specific hook count: "+name);
            for(Method m:positive.hooks.keySet()) {
                Object[] args=new Object[m.getParameterCount()];
                for(int i=0;i<args.length;i++) if(m.getParameterTypes()[i]==int.class)args[i]=0;
                sameFailure(positive,m.getDeclaringClass().getName(),m.getName(),null,args);
            }
            for(int gate=0;gate<4;gate++) {
                Build.VERSION.SDK_INT=gate==0?36:37;Build.DEVICE=gate==1?"nezha":"xuanyuan";
                Build.VERSION.INCREMENTAL=gate==2?"OS4.0.0.6.XOACNXM":"OS4.0.0.6.XOAEUXM";
                Reflect.hashes.put(name,gate==3?"wrong":HASHES.get(name));
                miui.os.Build.IS_INTERNATIONAL_BUILD=true;gn.b.a=true;
                com.android.providers.telephony.MmsSmsUtils.HAS_VERIFICATION_CODE_CATEGORY=false;
                Api negative=new Api();install(negative,name);
                check(negative.hooks.isEmpty(),"guard rejects package "+name+" gate "+gate);
                check(miui.os.Build.IS_INTERNATIONAL_BUILD && gn.b.a
                        && !com.android.providers.telephony.MmsSmsUtils.HAS_VERIFICATION_CODE_CATEGORY,"guard blocks field writes");
            }
            Build.VERSION.SDK_INT=37;Build.DEVICE="xuanyuan";Build.VERSION.INCREMENTAL="OS4.0.0.6.XOAEUXM";
        }
        Reflect.hashReads.clear();Api unrelated=new Api();install(unrelated,"android");
        check(unrelated.hooks.isEmpty() && Reflect.hashReads.isEmpty(),"no framework or unrelated package scope");
        installed("com.android.providers.telephony");
        check(com.android.providers.telephony.MmsSmsUtils.HAS_VERIFICATION_CODE_CATEGORY,"exact provider capability");
        check(miui.os.Build.IS_GLOBAL_BUILD,"global build untouched");
    }

    private static void antispam() throws Throwable {
        Api api=installed("com.android.incallui");String owner="android.app.ApplicationPackageManager";
        ApplicationInfo original=new ApplicationInfo();original.sourceDir="security-good";
        original.metaData=new Bundle();original.metaData.put("keep","original");
        Reflect.hashes.put(original.sourceDir,"da9c99b77d29f8052bd71ec98fa8736ba7b04ed13881ffb09575db1d592af793");
        Reflect.hashReads.clear();
        for(Object[] args:new Object[][]{{"other",128},{"com.miui.securitycenter",0},{"com.miui.securitycenter",64}})
            check(api.call(owner,"getApplicationInfo",null,args,a->original).result==original,"metadata argument gate");
        check(Reflect.hashReads.isEmpty(),"no hash read outside exact metadata request");
        Object[] request={"com.miui.securitycenter",128|64};
        ApplicationInfo copy=(ApplicationInfo)api.call(owner,"getApplicationInfo",null,request,a->original).result;
        check(copy!=original && copy.metaData!=original.metaData,"metadata defensive copies");
        check(copy.metaData.getBoolean("miui.supportQuickAntispam") && "original".equals(copy.metaData.get("keep")),"only capability added");
        check(!original.metaData.containsKey("miui.supportQuickAntispam"),"caller metadata unchanged");
        api.call(owner,"getApplicationInfo",null,request,a->original);
        check(Reflect.hashReads.get("security-good")==1,"exact path hash cache");
        ApplicationInfo changed=new ApplicationInfo();changed.sourceDir="security-new";
        Reflect.hashes.put(changed.sourceDir,"wrong");
        check(api.call(owner,"getApplicationInfo",null,request,a->changed).result==changed,"changed APK rejects cached support");
        check(api.call(owner,"getApplicationInfo",null,request,a->original).result!=original,"returning to known APK rechecks");
        check(Reflect.hashReads.get("security-good")==2,"cache changes with source path");
        changed.sourceDir="unreadable";Reflect.fail="hash:unreadable";
        check(api.call(owner,"getApplicationInfo",null,request,a->changed).result==changed,"hash failure preserves result");
        Reflect.fail=null;original.metaData=null;
        check(((ApplicationInfo)api.call(owner,"getApplicationInfo",null,request,a->original).result).metaData
                .getBoolean("miui.supportQuickAntispam"),"null metadata copied safely");
        check(api.call(owner,"getApplicationInfo",null,request,a->null).result==null,"null package result");
    }

    private static String region(Api api) throws Throwable {
        return (String)api.call("miuix.core.util.SystemProperties","get",null,
                new Object[]{"ro.miui.region","SG"},a->"SG").result;
    }

    private static void otherThread(Work work) throws Throwable {
        AtomicReference<Throwable> failure=new AtomicReference<>();
        Thread thread=new Thread(()->{try{work.run(new Object[0]);}catch(Throwable t){failure.set(t);}});
        thread.start();thread.join();if(failure.get()!=null)throw failure.get();
    }

    private static void monitor() throws Throwable {
        Api api=installed("com.miui.audiomonitor");
        String owner="com.miui.audiomonitor.VoipRecordSettingsActivity";
        VoipRecordSettingsActivity activity=new VoipRecordSettingsActivity();
        check(region(api).equals("SG"),"monitor outside scope");
        for(Object[] args:new Object[][]{{-1,false},{-1,null},{0,false},{-1,true}}) {
            boolean normal=args[0].equals(-1) && !Boolean.TRUE.equals(args[1]);
            api.call(owner,"checkPrivacy",activity,args,a->{check(region(api).equals(normal?"CN":"SG"),"privacy arguments gate");return null;});
            check(region(api).equals("SG"),"privacy scope restored");
        }
        activity.mRequestPackage="caller";
        api.call(owner,"checkPrivacy",activity,new Object[]{-1,false},a->{check(region(api).equals("SG"),"external package privacy unchanged");return null;});
        activity.mRequestPackage=null;
        api.call("com.miui.audiomonitor.voiprecord.utils.CloudControlUtil","useLocalConfig",null,new Object[0],a->{
            check(region(api).equals("CN"),"local cloud list scope");
            otherThread(b->{check(region(api).equals("SG"),"monitor thread isolation");return null;});
            api.call(owner,"checkPrivacy",activity,new Object[]{-1,true},b->{check(region(api).equals("SG"),"nested false scope");return null;});
            check(region(api).equals("CN"),"nested previous scope restored");
            sameFailure(api,"miuix.core.util.SystemProperties","get",null,"ro.miui.region","SG");
            return false;
        });
        check(region(api).equals("SG"),"cloud scope restored");
        sameFailure(api,owner,"checkPrivacy",activity,-1,false);
        check(region(api).equals("SG"),"throwing privacy call clears scope");
        Reflect.fail="get:mRequestPackage";
        api.call(owner,"checkPrivacy",activity,new Object[]{-1,false},a->{check(region(api).equals("SG"),"optional field failure stays narrow");return null;});
        Reflect.fail=null;
        api.call("com.miui.audiomonitor.voiprecord.utils.CloudControlUtil","useLocalConfig",null,new Object[0],a->{
            check(api.call("miuix.core.util.SystemProperties","get",null,new Object[]{"other.property","SG"},b->"SG").result.equals("SG"),"other properties unchanged");return false;});
    }

    private static String yellowRegion(Api api) throws Throwable {
        return (String)api.call("miui.os.Build","getRegion",null,new Object[0],a->"SG").result;
    }

    private static void yellowpage() throws Throwable {
        Api api=installed("com.miui.yellowpage");String request="com.miui.yellowpage.utils.l1";
        check(!miui.os.Build.IS_INTERNATIONAL_BUILD && miui.os.Build.IS_GLOBAL_BUILD,"YellowPage process-local build flag");
        check(yellowRegion(api).equals("SG"),"YellowPage normal region unchanged");
        api.call(request,"e",null,new Object[]{new HashMap<>()},a->{
            check(yellowRegion(api).equals("CN"),"YellowPage request region");
            api.call(request,"e",null,new Object[]{new HashMap<>()},b->{check(yellowRegion(api).equals("CN"),"nested CN request");return null;});
            sameFailure(api,request,"e",null,new HashMap<>());
            check(yellowRegion(api).equals("CN"),"nested failure restores outer request");
            otherThread(b->{check(yellowRegion(api).equals("SG"),"YellowPage thread isolation");return null;});
            sameFailure(api,"miui.os.Build","getRegion",null);return null;
        });
        check(yellowRegion(api).equals("SG"),"request region removed");
        sameFailure(api,request,"e",null,new HashMap<>());
        check(yellowRegion(api).equals("SG"),"throwing request region removed");
        for(n1.a feature:n1.a.values())check(api.call("n1.b","e",null,new Object[]{new Context(),feature},a->false).result
                .equals(feature!=n1.a.OTHER),"only antispam feature gates");
        YellowPageDatabaseHelper helper=new YellowPageDatabaseHelper();SQLiteDatabase db=new SQLiteDatabase();
        String database=helper.getClass().getName();
        helper.callback=a->{api.call(database,"getReadableDatabase",helper,new Object[0],b->db);return null;};
        check(api.call(database,"getReadableDatabase",helper,new Object[0],a->db).result==db && helper.imports==1,"empty-table import avoids recursion");
        db.count=5;api.call(database,"getReadableDatabase",helper,new Object[0],a->db);
        check(helper.imports==1,"populated categories preserved");
        db.count=0;helper.fail=true;
        check(api.call(database,"getReadableDatabase",helper,new Object[0],a->db).result==db,"optional import failure preserves database");
        helper.fail=false;api.call(database,"getReadableDatabase",helper,new Object[0],a->db);
        check(helper.imports==3,"import guard cleared after failure");
        db.fail=true;check(api.call(database,"getReadableDatabase",helper,new Object[0],a->db).result==db,"query failure preserves database");
        api.failLog=true;
        check(api.call("com.miui.yellowpage.utils.j0","w",new Object(),new Object[0],a->7).result.equals(7),"log failure preserves request status");
    }

    private static void mms() throws Throwable {
        Api api=installed("com.android.mms");
        check(!miui.os.Build.IS_INTERNATIONAL_BUILD && !gn.b.a && miui.os.Build.IS_GLOBAL_BUILD,"MMS local fields only");
        g5.f3.a=false;
        api.call("android.app.Application","attach",null,new Object[]{new Context()},a->null);
        check(g5.f3.a,"attach restores capability");
        String otp="com.miui.smsextra.util.UpdateVerificationCodeUtils";
        for(boolean allowed:new boolean[]{false,true}) {
            g5.f3.allowed=allowed;
            check(api.call(otp,"isVerificationCodeCategoryEnabled",null,new Object[]{new Context()},a->!allowed).result.equals(allowed),"OEM consent decides OTP");
        }
        Reflect.fail="call:b";
        check(api.call(otp,"isVerificationCodeCategoryEnabled",null,new Object[]{new Context()},a->false).result.equals(false),"OEM switch lookup failure preserves result");
        Reflect.fail=null;
        String factory=UnderstandFactory.class.getName();UnderstandFactory.inits=0;UnderstandFactory.e=null;
        check(api.call(factory,"getMmsConfigWithKey",null,new Object[]{"other"},a->null).result==null && UnderstandFactory.inits==0,"other null keys untouched");
        Object known=new Object();
        check(api.call(factory,"getMmsConfigWithKey",null,new Object[]{"recognition_partner_url"},a->known).result==known && UnderstandFactory.inits==0,"existing OEM value preserved");
        TestChain cold=api.call(factory,"getMmsConfigWithKey",null,new Object[]{"recognition_partner_url"},a->null);
        check(cold.calls==1 && cold.result.equals("https://oem.invalid/partner") && UnderstandFactory.inits==1,"cold partner lookup repaired without second original call");
        UnderstandFactory.fail=true;
        check(api.call(factory,"getMmsConfigWithKey",null,new Object[]{"recognition_partner_url"},a->null).result==null,"OEM initializer failure preserves null");
        UnderstandFactory.fail=false;UnderstandFactory.missing=true;
        check(api.call(factory,"getMmsConfigWithKey",null,new Object[]{"recognition_partner_url"},a->null).result==null,"missing OEM partner key stays null");
        UnderstandFactory.missing=false;Reflect.fail="get:e";
        check(api.call(factory,"getMmsConfigWithKey",null,new Object[]{"recognition_partner_url"},a->null).result==null,"JSON reflection failure preserves null");
        Reflect.fail=null;int before=UnderstandFactory.inits;
        sameFailure(api,factory,"getMmsConfigWithKey",null,"recognition_partner_url");
        check(UnderstandFactory.inits==before,"failed original does not initialize config");
        api.failLog=true;sameFailure(api,"ef.d","b",null,"model");
        check(api.call("ef.d","b",null,new Object[]{"model"},a->known).result==known,"model result survives logger failure");
        check(api.call("com.miui.smsextra.sdk.SDKManager","init",new com.miui.smsextra.sdk.SDKManager(),new Object[0],a->known).result==known,"SDK result preserved");
    }

    private static void recorder() throws Throwable {
        Api api=installed("com.android.soundrecorder");
        com.android.soundrecorder.SoundRecorderSettings.a settings=new com.android.soundrecorder.SoundRecorderSettings.a();
        String owner=settings.getClass().getName();Object original=new Object();
        check(api.call(owner,"K0",settings,new Object[]{"key"},a->original).result==original && !settings.entry.visible,"unresolved recording settings untouched");
        settings.context.pm.installed.add("com.miui.audiomonitor");
        check(api.call(owner,"K0",settings,new Object[]{"key"},a->original).result==original,"recorder original result");
        check(settings.entry.visible && settings.category.visible && settings.entry.f==settings,"existing recording preference restored");
        Intent intent=(Intent)settings.entry.m;
        check(intent.getAction().equals("miui.intent.action.VOIPRECORD_SETTINGS")
                && intent.getComponent().name.equals("com.miui.audiomonitor.VoipRecordSettingsActivity"),"exact recording destination");
        Reflect.fail="call:I0";
        check(api.call(owner,"K0",settings,new Object[]{"key"},a->original).result==original,"recorder optional reflection failure");
        Reflect.fail=null;
    }

    private static Api clockApi;
    private static int clockCalls;
    public static Object clock() throws Throwable {
        return clockApi.call("com.android.deskclock.util.Util","isInternational",null,new Object[0],a->{clockCalls++;return true;}).result;
    }

    private static void clockTests() throws Throwable {
        clockApi=installed("com.android.deskclock");clockCalls=0;
        check(clock().equals(true),"non-Clock caller unchanged");
        check(com.android.deskclock.alarm.AlarmRepeatAdapter.setData().equals(false),"repeat setData gate");
        check(com.android.deskclock.alarm.AlarmRepeatAdapter.setRepeatItemChecked().equals(false),"repeat checked gate");
        check(com.android.deskclock.alarm.RepeatAlarmController.initRepeatAlarmAdapterData().equals(false),"repeat controller gate");
        check(com.android.deskclock.alarm.bedtime.BedtimeGuideActivity.initData().equals(false),"bedtime guide gate");
        check(com.android.deskclock.addition.holiday.HolidayUpdateScheduler.checkAndUpdate().equals(false),"holiday update gate");
        com.android.deskclock.DeskClockApp.nested=false;
        check(com.android.deskclock.DeskClockApp.onCreate().equals(false),"app startup direct gate");
        check(clockCalls==1,"allowed before override skips original");
        check(com.android.deskclock.alarm.AlarmRepeatAdapter.unrelated().equals(true),"unlisted Clock method unchanged");
        com.android.deskclock.DeskClockApp.nested=true;
        check(com.android.deskclock.DeskClockApp.onCreate().equals(true),"nearest unlisted caller blocks outer startup frame");
        check(clockCalls==3,"only allowed callsites skip original");
        SettingsFragment settings=new SettingsFragment();SettingsFragment.Row privacy=new SettingsFragment.Row();
        settings.mOtherPreferenceCategory.visible=false;settings.mOtherPreferenceCategory.rows.add(privacy);
        Object result=new Object();String owner=settings.getClass().getName();
        check(clockApi.call(owner,"onCreatePreferences",settings,new Object[]{new Bundle(),"root"},a->result).result==result,"Clock preferences result preserved");
        check(!privacy.visible && settings.mValueHolidayPreference.visible && settings.mOtherPreferenceCategory.visible
                && settings.mOtherPreferenceCategory.rows.contains(settings.mValueHolidayPreference),"only holiday row exposed from hidden category");
        privacy.visible=true;
        clockApi.call(owner,"onCreatePreferences",settings,new Object[]{new Bundle(),"root"},a->result);
        check(privacy.visible,"already visible category keeps other rows");
        Reflect.fail="get:mOtherPreferenceCategory";
        check(clockApi.call(owner,"onCreatePreferences",settings,new Object[]{new Bundle(),"root"},a->result).result==result,"Clock reflection failure preserves result");
        Reflect.fail=null;
    }

    private static void calendar() throws Throwable {
        Api api=installed("com.miui.personalassistant");Activity activity=new Activity();
        activity.pm.installed.add("com.xiaomi.calendar");Bundle options=new Bundle();Object token=new Object();
        Intent intent=new Intent(Intent.ACTION_SEARCH).setPackage("com.android.calendar");
        intent.flags=123;intent.data="calendar://search";intent.extras.put("query","meeting");
        Object[] args={intent,42,options};String owner="android.app.Activity";
        TestChain routed=api.call(owner,"startActivityForResult",activity,args,a->token);
        Intent replacement=(Intent)routed.actualArgs[0];
        check(routed.result==token && routed.calls==1 && routed.actualArgs!=args,"calendar copied args and one original call");
        check(replacement!=intent && replacement.getPackage().equals("com.xiaomi.calendar")
                && intent.getPackage().equals("com.android.calendar") && args[0]==intent,"caller Intent unchanged");
        check(replacement.flags==123 && replacement.data.equals(intent.data) && replacement.extras.equals(intent.extras)
                && routed.actualArgs[1].equals(42) && routed.actualArgs[2]==options,"calendar payload preserved");
        activity.pm.installed.add("com.android.calendar");
        check(api.call(owner,"startActivityForResult",activity,args,a->token).actualArgs==args,"existing calendar wins");
        activity.pm.installed.clear();
        check(api.call(owner,"startActivityForResult",activity,args,a->token).actualArgs==args,"no fallback if Xiaomi calendar missing");
        activity.pm.installed.add("com.xiaomi.calendar");
        for(Intent excluded:new Intent[]{null,new Intent("other").setPackage("com.android.calendar"),
                new Intent(Intent.ACTION_SEARCH).setPackage("other"),
                new Intent(Intent.ACTION_SEARCH).setClassName("com.android.calendar","Explicit")}) {
            Object[] unchanged={excluded,42,options};
            check(api.call(owner,"startActivityForResult",activity,unchanged,a->token).actualArgs==unchanged,"calendar exact action/package/component gate");
        }
        activity.pm.fail=true;
        check(api.call(owner,"startActivityForResult",activity,args,a->token).actualArgs==args,"resolver failure preserves original arguments");
        activity.pm.fail=false;api.failLog=true;
        sameFailure(api,owner,"startActivityForResult",activity,intent,42,options);
    }

    private static void engine() throws Throwable {
        Api api=installed("com.xiaomi.aicr");Class<?> fs=Class.forName("fs1"),zs=Class.forName("zs1");
        for(int ram:new int[]{-1,0,1,4,5,8}) {
            Reflect.set(fs,"g",ram);Reflect.set(fs,"f",false);Reflect.set(fs,"tier",3);Reflect.set(zs,"lite",false);
            check(api.call("ws1","b",null,new Object[0],a->false).result.equals(!(ram>=1 && ram<5)),"engine exact RAM gate "+ram);
        }
        Reflect.set(fs,"g",8);
        for(int gate=0;gate<3;gate++) {
            Reflect.set(zs,"lite",gate==0);Reflect.set(fs,"f",gate==1);Reflect.set(fs,"tier",gate==2?2:3);
            check(api.call("ws1","b",null,new Object[0],a->false).result.equals(false),"engine lite gate "+gate);
            check(api.call("ws1","b",null,new Object[0],a->true).result.equals(true),"lite gate retains original true");
        }
        for(String fail:new String[]{"type:fs1","type:zs1","call:m","get:f","call:b","get:e","get:g"}) {
            Reflect.set(zs,"lite",false);Reflect.set(fs,"f",false);Reflect.set(fs,"tier",3);Reflect.fail=fail;
            check(api.call("ws1","b",null,new Object[0],a->false).result.equals(false),"engine optional reflection failure "+fail);
        }
        Reflect.fail=null;
    }

    public static void main(String[] args) throws Throwable {
        guards();antispam();monitor();yellowpage();mms();recorder();clockTests();calendar();engine();
        System.out.println("PASS: "+assertions+" host assertions; all package branches, narrow gates, exception identity, single invocation");
    }
}
