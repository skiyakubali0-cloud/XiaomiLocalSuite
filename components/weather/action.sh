#!/system/bin/sh
MODDIR=${0%/*}
sh "$MODDIR/core.sh" || exit 1
sh "$MODDIR/apply.sh" || exit 1
am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -n com.miui.weather2/.ActivityWeatherMain
