# Third-party notices

XiaomiLocalSuite's independently authored tooling is Apache-2.0. This license
does not grant rights to Xiaomi firmware, applications, libraries or DEX files.
None of those binaries or decompiled OEM source trees are distributed here.

The Android build uses three external pinned artifacts:

| Coordinate | Use |
| --- | --- |
| io.github.libxposed:api:102.0.0 | Compile only; framework supplies API at runtime |
| io.github.libxposed:service:102.0.0 | Included in the locally built APK |
| io.github.libxposed:interface:102.0.0 | Included in the locally built APK |

Maven Central POM metadata for all three 102.0.0 coordinates declares Apache
License 2.0. The upstream GitHub license URLs named by those POMs currently
return 404; no separate upstream LICENSE/NOTICE text was retrieved. This is an
upstream declaration, not proof that no additional NOTICE exists. See the
[exact POM links](suite/unified-api102/README.md#pinned-dependencies).

Their archives/JARs are not checked in. Exact SHA256 values are recorded in
`suite/unified-api102/deps.lock.json`. Fetch from the pinned source, verify hashes
and review the upstream POM/license before redistributing any built APK. If the
pinned artifacts are unavailable, obtain the exact local reviewed copies; do not
substitute an unreviewed version or relax the checksum check.

Android SDK tools and Java are separately installed development dependencies,
not bundled in this source distribution. Xiaomi, HyperOS, Android, LSPosed and
libxposed names identify compatibility or dependencies, not endorsement.

Older hook implementations included as reference sources are this project's
compatibility logic, not an OEM decompiled application tree. Host tests contain
synthetic Android/OEM class fixtures, which establish test contracts only and
are not shipped as a replacement phone framework.
