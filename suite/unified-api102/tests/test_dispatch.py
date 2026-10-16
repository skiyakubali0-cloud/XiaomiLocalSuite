"""Attach real API102 wrapper to a host proxy; verify unified lifecycle dispatch."""
from pathlib import Path
import subprocess,tempfile,struct
P=Path(__file__).resolve().parents[1];API=P/'deps/api.jar'
FIX={
'android/os/Process.java':'package android.os;public class Process{public static int uid=10001;public static int myUid(){return uid;}}',
'android/os/Build.java':'package android.os; public class Build {public static String DEVICE="xuanyuan";public static class VERSION{public static int SDK_INT=37;public static String INCREMENTAL="OS4.0.0.6.XOAEUXM";}}',
'android/util/Log.java':'package android.util;public class Log {public static final int INFO=4,WARN=5,ERROR=6;}',
'android/content/SharedPreferences.java':'package android.content;public interface SharedPreferences {boolean getBoolean(String k,boolean d);}',
'android/content/pm/ApplicationInfo.java':'package android.content.pm;public class ApplicationInfo {}',
'android/os/ParcelFileDescriptor.java':'package android.os;public class ParcelFileDescriptor {}',
'android/app/AppComponentFactory.java':'package android.app;public class AppComponentFactory {}',
'android/app/AppGlobals.java':'''package android.app;public class AppGlobals {public static java.util.Set<String> features=new java.util.HashSet<>();public static boolean fail;public static int queries;public static Object getPackageManager(){if(fail)throw new SecurityException();return new PM();}public static class PM {public boolean hasSystemFeature(String name,int version){queries++;if(version!=1)throw new AssertionError();return features.contains(name);}}}''',
'local/xuanyuan/mipushcompat/MiPushModule.java':'package local.xuanyuan.mipushcompat;public class MiPushModule extends io.github.libxposed.api.XposedModule {public int pushCalls;@Override public void onPackageReady(PackageReadyParam p){if(p.isFirstPackage())pushCalls++;}}',
}
for n in ['Phone','Clock','Suggestion']:
 FIX['local/xuanyuan/unified/'+n+'Hooks.java']='package local.xuanyuan.unified;public class '+n+'Hooks {public static int calls;public static void install(io.github.libxposed.api.XposedInterface a,io.github.libxposed.api.XposedModuleInterface.PackageReadyParam p){calls++;}}'
FIX['local/xuanyuan/unified/WarningHooks.java']='package local.xuanyuan.unified;public class WarningHooks{public static int calls;public static void install(io.github.libxposed.api.XposedInterface a,io.github.libxposed.api.XposedModuleInterface.PackageLoadedParam p){calls++;}}'
FIX['local/xuanyuan/unified/PrivacyHooks.java']='package local.xuanyuan.unified;public class PrivacyHooks{public static int calls;public static void install(io.github.libxposed.api.XposedInterface a,ClassLoader p){calls++;}}'
HARNESS='''import java.lang.reflect.*;import java.util.*;import io.github.libxposed.api.*;import local.xuanyuan.unified.*;
public class DispatchTest {
 static int n,version=102;static boolean prefsFail;static Map<String,Boolean> flags=new HashMap<>();
 static void ok(boolean b){n++;if(!b)throw new AssertionError(n);}
 static Object zero(Class<?> c){if(c==boolean.class)return false;if(c==int.class)return 0;if(c==long.class)return 0L;return null;}
 static XposedModuleInterface.PackageReadyParam ready(String name,boolean first){return (XposedModuleInterface.PackageReadyParam)Proxy.newProxyInstance(DispatchTest.class.getClassLoader(),new Class[]{XposedModuleInterface.PackageReadyParam.class},(o,m,a)->{if(m.getName().equals("getPackageName"))return name;if(m.getName().equals("isFirstPackage"))return first;if(m.getName().endsWith("ClassLoader"))return DispatchTest.class.getClassLoader();return null;});}
 static UnifiedModule module(String proc){UnifiedModule u=new UnifiedModule();XposedInterface a=(XposedInterface)Proxy.newProxyInstance(DispatchTest.class.getClassLoader(),new Class[]{XposedInterface.class},(o,m,args)->{switch(m.getName()){case "getApiVersion":return version;case "getRemotePreferences":if(prefsFail)throw new IllegalStateException();return (android.content.SharedPreferences)(k,d)->flags.getOrDefault(k,d);default:return zero(m.getReturnType());}});u.attachFramework(a,()->{});u.onModuleLoaded(new XposedModuleInterface.ModuleLoadedParam(){public boolean isSystemServer(){return proc.equals("system_server");}public String getProcessName(){return proc;}});return u;}
 public static void main(String[] a)throws Exception {
  UnifiedModule u=module("com.android.mms");u.onPackageReady(ready("com.android.mms",true));ok(u.pushCalls==1&&PhoneHooks.calls==0);
  flags.put("phone",true);u.onPackageReady(ready("com.android.mms",true));ok(PhoneHooks.calls==1);
  u.onPackageReady(ready("com.android.mms",false));ok(PhoneHooks.calls==1&&u.pushCalls==2);
  u.onPackageReady(ready("com.xiaomi.xmsf",true));ok(PhoneHooks.calls==1);
  flags.put("clock",true);u.onPackageReady(ready("com.android.deskclock",true));ok(ClockHooks.calls==1);
  flags.put("suggestions",true);u.onPackageReady(ready("com.xiaomi.aicr",true));ok(SuggestionHooks.calls==1);
  flags.put("warning",true);UnifiedModule w=module("com.miui.securitycenter");w.onPackageLoaded(ready("com.miui.securitycenter",true));ok(WarningHooks.calls==1);w.onPackageReady(ready("com.miui.securitycenter",true));ok(WarningHooks.calls==1);
  flags.put("privacy",true);UnifiedModule sys=module("system_server");sys.onSystemServerStarting(()->DispatchTest.class.getClassLoader());ok(PrivacyHooks.calls==1);
  ok(u.getApiVersion()==102); // Real API102 wrapper reports its library contract; minApi metadata gates old frameworks.
  android.os.Build.DEVICE="wrong";int count=u.pushCalls;u.onPackageReady(ready("com.android.mms",true));ok(u.pushCalls==count&&PhoneHooks.calls==1);android.os.Build.DEVICE="xuanyuan";
  prefsFail=true;u.onPackageReady(ready("com.android.mms",true));ok(PhoneHooks.calls==1);prefsFail=false;
  android.os.Process.uid=110001;int ownerBefore=PhoneHooks.calls;u.onPackageReady(ready("com.android.mms",true));ok(PhoneHooks.calls==ownerBefore);android.os.Process.uid=10001;
  UnifiedModule radio=module("com.android.phone");int prior=PhoneHooks.calls;
  radio.onPackageReady(ready("com.android.phone",true));radio.onPackageReady(ready("com.android.providers.telephony",false));ok(PhoneHooks.calls==prior+2);
  radio.onPackageReady(ready("com.android.incallui",false));ok(PhoneHooks.calls==prior+2);
  java.nio.file.Files.delete(java.nio.file.Path.of(a[0]));java.nio.file.Files.delete(java.nio.file.Path.of(a[1]));
  int phoneBefore=PhoneHooks.calls,suggestionBefore=SuggestionHooks.calls;
  radio.onPackageReady(ready("com.android.providers.telephony",false));u.onPackageReady(ready("com.xiaomi.aicr",true));
  ok(PhoneHooks.calls==phoneBefore&&SuggestionHooks.calls==suggestionBefore);
  android.app.AppGlobals.features.add("local.xuanyuan.compat.phone");
  radio.onPackageReady(ready("com.android.providers.telephony",false));u.onPackageReady(ready("com.android.mms",true));
  ok(PhoneHooks.calls==phoneBefore+2);ok(SuggestionHooks.calls==suggestionBefore);
  android.app.AppGlobals.features.clear();android.app.AppGlobals.features.add("local.xuanyuan.compat.xiaoai");
  u.onPackageReady(ready("com.xiaomi.aicr",true));u.onPackageReady(ready("com.android.mms",true));
  ok(SuggestionHooks.calls==suggestionBefore+1&&PhoneHooks.calls==phoneBefore+2);
  android.app.AppGlobals.features.add("local.xuanyuan.compat.phone");android.app.AppGlobals.fail=true;
  u.onPackageReady(ready("com.android.mms",true));ok(PhoneHooks.calls==phoneBefore+2);android.app.AppGlobals.fail=false;
  flags.put("phone",false);int q=android.app.AppGlobals.queries;u.onPackageReady(ready("com.android.mms",true));
  ok(PhoneHooks.calls==phoneBefore+2&&android.app.AppGlobals.queries==q);flags.put("phone",true);
  android.os.Build.DEVICE="wrong";u.onPackageReady(ready("com.android.mms",true));
  ok(PhoneHooks.calls==phoneBefore+2&&android.app.AppGlobals.queries==q);android.os.Build.DEVICE="xuanyuan";
  android.app.AppGlobals.features.clear();u.onPackageReady(ready("com.android.mms",true));
  ok(PhoneHooks.calls==phoneBefore+2);
  System.out.println("PASS "+n+" real API102 lifecycle dispatch assertions");
 }
}'''
with tempfile.TemporaryDirectory(prefix='dispatch-') as d:
 t=Path(d);files=[]
 for n,s in FIX.items():q=t/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(s);files.append(q)
 h=t/'DispatchTest.java';h.write_text(HARNESS);files += [h,P/'src/local/xuanyuan/unified/Platform.java',P/'src/local/xuanyuan/unified/Features.java',P/'src/local/xuanyuan/unified/UnifiedModule.java',P/'src/local/xuanyuan/unified/Reflect.java']
 subprocess.run(['javac','-cp',str(API),'-d',str(t),*map(str,files)],check=True)
 # Rewrite only compiled host mount paths, preserving production guards/source.
 f=t/'local/xuanyuan/unified/UnifiedModule.class';data=f.read_bytes()
 for old in [b'/product/etc/xuanyuan-suite-phone.enabled',b'/product/etc/xuanyuan-ai-privacy.enabled']:
  marker=t/old.decode().split('/')[-1];marker.touch();new=str(marker).encode();needle=struct.pack('>H',len(old))+old;assert needle in data;data=data.replace(needle,struct.pack('>H',len(new))+new)
 f.write_bytes(data)
 subprocess.run(['java','-cp',str(t)+':'+str(API),'DispatchTest',str(t/'xuanyuan-suite-phone.enabled'),str(t/'xuanyuan-ai-privacy.enabled')],check=True)
