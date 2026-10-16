#!/bin/sh
set -eu
TASK_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
"$TASK_DIR/ndk/bin/clang++" --target=aarch64-linux-android35 --sysroot="$TASK_DIR/ndk/sysroot" \
 -std=c++17 -O2 -shared -fPIC -fno-exceptions -fno-rtti -fvisibility=hidden \
 -static-libstdc++ -Wl,-z,max-page-size=16384 -Wl,--no-undefined \
 -I"$TASK_DIR/native-include" "$TASK_DIR/assistant-native.cpp" -llog -ldl \
 -o "$TASK_DIR/assistant-native.so"
