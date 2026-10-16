package local.xuanyuan.unified;

import android.os.Build;

/** The unified bundle is pinned to the reviewed owner-user ROM. */
public final class Platform {
    private Platform() { }
    public static boolean exactRom(){return Build.VERSION.SDK_INT==37&&"xuanyuan".equals(Build.DEVICE)
        &&"OS4.0.0.6.XOAEUXM".equals(Build.VERSION.INCREMENTAL)&&android.os.Process.myUid()/100000==0;}
}
