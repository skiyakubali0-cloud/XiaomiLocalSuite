#!/system/bin/sh
M=${0%/*}
# Only reconcile task bookkeeping; never install components automatically at boot.
sh "$M/control.sh" reconcile
