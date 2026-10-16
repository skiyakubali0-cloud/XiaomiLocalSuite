package local.xuanyuan.unified;

import io.github.libxposed.service.XposedService;
import io.github.libxposed.service.XposedServiceHelper;
import java.util.ArrayList;
import java.util.List;

/** libxposed accepts one process listener; settings pages share its live service. */
public final class FrameworkService {
    private static final List<XposedServiceHelper.OnServiceListener> listeners=new ArrayList<>();
    private static boolean registered;
    private static XposedService current;
    private FrameworkService() { }
    public static synchronized void addListener(XposedServiceHelper.OnServiceListener listener){
        listeners.add(listener);
        if(!registered){
            registered=true;
            XposedServiceHelper.registerListener(new XposedServiceHelper.OnServiceListener(){
                public void onServiceBind(XposedService s){
                    synchronized(FrameworkService.class){current=s;for(XposedServiceHelper.OnServiceListener l:listeners)l.onServiceBind(s);}
                }
                public void onServiceDied(XposedService s){
                    synchronized(FrameworkService.class){if(current==s)current=null;for(XposedServiceHelper.OnServiceListener l:listeners)l.onServiceDied(s);}
                }
            });
        }else if(current!=null)listener.onServiceBind(current);
    }
}
