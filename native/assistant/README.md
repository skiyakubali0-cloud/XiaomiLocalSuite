# Assistant native references

These independently authored sources explain the exact-ROM launcher route hook.
They are reference implementations, not a generic launcher patch. They retain
byte/symbol/ROM checks and change only the selected launcher route.

No compiled native library, NDK, third-party Zygisk header or OEM library is
included. The legacy scripts expect a locally prepared `ndk/`, a lawful Zygisk
header in `native-include/`, and the exact checked OEM input below `live/`.
Do not execute these reference scripts until those inputs are deliberately
prepared. The supported public suite builder reuses only hash-locked local
materials. The public [full 1.7 recipe](../../docs/FULL_RECIPE.md) rebuilds the
locked assistant route library from the exact stock EEA library using
`tools/recipe_generated.py` and `recipes/generated.json`. It verifies the assembly
source, patch sites and resulting SHA256 without an NDK or private reference ZIP.
This does not enable rebuilding from an arbitrary firmware.
