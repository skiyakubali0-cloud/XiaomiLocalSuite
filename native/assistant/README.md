# Assistant native references

These independently authored sources explain the exact-ROM launcher route hook.
They are reference implementations, not a generic launcher patch. They retain
byte/symbol/ROM checks and change only the selected launcher route.

No compiled native library, NDK, third-party Zygisk header or OEM library is
included. The legacy scripts expect a locally prepared `ndk/`, a lawful Zygisk
header in `native-include/`, and the exact checked OEM input below `live/`.
Do not execute these reference scripts until those inputs are deliberately
prepared. The supported public suite builder reuses only hash-locked local
materials; it does not promise to rebuild every OEM-derived native artifact
from these sources or from an arbitrary firmware.
