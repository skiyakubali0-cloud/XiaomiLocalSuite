package local.xuanyuan.unified;

import android.content.*;
import android.util.Log;
import local.xuanyuan.mipushcompat.WalletRecovery;

/** Existing wallet recovery, restricted to this bundle's verified ROM/user. */
public final class BootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        if(!Platform.exactRom()||intent==null||!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())||!WalletRecovery.configured(context))return;
        PendingResult pending=goAsync();
        new Thread(()->{try{Log.i("MiPushWalletRecovery","boot_start="+WalletRecovery.start(context));}
            catch(Exception e){Log.w("MiPushWalletRecovery","boot_failed="+e.getClass().getSimpleName());}
            finally{pending.finish();}},"wallet-boot").start();
    }
}
