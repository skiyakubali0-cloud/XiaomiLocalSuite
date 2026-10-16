package local.xuanyuan.unified;

import android.content.SharedPreferences;
import java.util.*;

/** Independent feature switches; MiPush selection stays in its original namespace. */
public final class Features {
    public static final String[] IDS={"phone","privacy","suggestions","warning","clock"};
    public static final String[] TITLES={"电话、短信与录音兼容","小爱 AI识屏和智控权限","小爱建议兼容","自然灾害预警与报警定位兼容","时钟法定节假日兼容"};
    public static final String[] LEGACY={"local.xuanyuan.smscompat","local.xuanyuan.aiprivacy","local.xuanyuan.suggestioncompat","local.xuanyuan.disastercompat","local.xuanyuan.clockcompat"};
    private static final String[][] SCOPES={
        {"com.android.mms","com.android.soundrecorder","com.miui.audiomonitor","com.miui.yellowpage","com.android.incallui","com.android.providers.telephony","com.android.phone"},
        {"system"},{"com.xiaomi.aicr","com.miui.personalassistant"},{"com.miui.securitycenter"},{"com.android.deskclock"}};
    private Features() { }
    public static boolean enabled(SharedPreferences p,String id){return p.getBoolean(id,false);}
    public static Set<String> scope(SharedPreferences p){
        Set<String> result=new LinkedHashSet<>();
        for(int i=0;i<IDS.length;i++)if(enabled(p,IDS[i]))result.addAll(Arrays.asList(SCOPES[i]));
        return result;
    }
    public static String featureFor(String pkg){
        for(int i=0;i<IDS.length;i++)if(Arrays.asList(SCOPES[i]).contains(pkg))return IDS[i];
        return null;
    }
}
