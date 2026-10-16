package local.xuanyuan.unified;

import android.util.Log;
import local.xuanyuan.mipushcompat.MiPushModule;

/** One modern API102 entry for OEM compatibility and unchanged MiPush routes. */
public final class UnifiedModule extends MiPushModule {
    private String processName="";
    private boolean componentActive(String marker,String feature){
        if(new java.io.File(marker).isFile())return true;
        // SUSFS hides new overlay files from app UIDs. SystemConfig's boot-time
        // feature declaration follows the same component's mounted permission XML.
        try{
            Object pm=Reflect.call(Reflect.type("android.app.AppGlobals",UnifiedModule.class.getClassLoader()),"getPackageManager");
            return Boolean.TRUE.equals(Reflect.call(pm,"hasSystemFeature",feature,1));
        }catch(ReflectiveOperationException|RuntimeException e){
            log(Log.WARN,"XuanyuanUnified","Component presence unavailable: "+feature+" "+e.getClass().getSimpleName());return false;
        }
    }
    private boolean exact(){return getApiVersion()>=102&&Platform.exactRom();}
    private boolean enabled(String id){try{return Features.enabled(getRemotePreferences("compat"),id);}catch(RuntimeException e){return false;}}
    @Override public void onModuleLoaded(ModuleLoadedParam p){processName=p.getProcessName();log(Log.INFO,"XuanyuanUnified","API102 entry attached; exact ROM="+exact());}
    @Override public void onPackageLoaded(PackageLoadedParam p){
        if(!exact()||!p.isFirstPackage()||!processName.startsWith("com.miui.securitycenter")||!enabled("warning"))return;
        try{WarningHooks.install(this,p);}catch(Throwable e){log(Log.ERROR,"XuanyuanUnified","Warning hooks inactive: "+e.getClass().getSimpleName());}
    }
    @Override public void onSystemServerStarting(SystemServerStartingParam p){
        if(!exact()||!enabled("privacy"))return;
        try{PrivacyHooks.install(this,p.getClassLoader());}catch(Throwable e){log(Log.ERROR,"XuanyuanUnified","AI privacy hooks inactive: "+e.getClass().getSimpleName());}
    }
    @Override public void onPackageReady(PackageReadyParam p){
        // Original MiPush0.8.2 package, storage, opt-ins and fail-closed group remain intact.
        if(!exact())return;
        super.onPackageReady(p);
        // TelephonyProvider shares com.android.phone and can arrive after the host package.
        if(!p.isFirstPackage()&&!"com.android.providers.telephony".equals(p.getPackageName()))return;
        String feature=Features.featureFor(p.getPackageName());
        if(feature==null||!enabled(feature))return;
        if("phone".equals(feature)&&!componentActive("/product/etc/xuanyuan-suite-phone.enabled","local.xuanyuan.compat.phone"))return;
        if("suggestions".equals(feature)&&!componentActive("/product/etc/xuanyuan-ai-privacy.enabled","local.xuanyuan.compat.xiaoai"))return;
        try{
            switch(feature){
                case "phone":PhoneHooks.install(this,p);break;
                case "suggestions":SuggestionHooks.install(this,p);break;
                case "clock":ClockHooks.install(this,p);break;
                default:break;
            }
        }catch(Throwable e){log(Log.ERROR,"XuanyuanUnified",feature+" hooks inactive: "+e);}
    }
}
