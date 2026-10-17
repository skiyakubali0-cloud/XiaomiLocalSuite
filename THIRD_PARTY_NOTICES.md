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

## Warning DEX recipe build dependencies

The offline warning DEX generator uses the following four pinned JARs on the
build host only. They are not checked in or bundled into the generated APK,
warning DEX or suite. Exact download URLs, byte lengths and SHA-256 values are
recorded in `recipes/generated.json`; the generator verifies each supplied JAR.

| Coordinate | Upstream license declaration | Official POM | Upstream source |
| --- | --- | --- | --- |
| `com.android.tools.smali:smali-dexlib2:3.0.9` | The BSD 3-Clause License (`BSD-3-Clause`) | [Google Maven POM](https://dl.google.com/dl/android/maven2/com/android/tools/smali/smali-dexlib2/3.0.9/smali-dexlib2-3.0.9.pom) | [Google smali / dexlib2](https://github.com/google/smali/tree/master/dexlib2) |
| `com.google.guava:guava:31.1-android` | Apache License, Version 2.0 (`Apache-2.0`), inherited from `guava-parent:31.1-android` | [Artifact POM](https://repo.maven.apache.org/maven2/com/google/guava/guava/31.1-android/guava-31.1-android.pom), [parent POM](https://repo.maven.apache.org/maven2/com/google/guava/guava-parent/31.1-android/guava-parent-31.1-android.pom) | [Guava v31.1 source](https://github.com/google/guava/tree/v31.1) |
| `com.google.guava:failureaccess:1.0.1` | The Apache Software License, Version 2.0 (`Apache-2.0`), inherited from `guava-parent:26.0-android` | [Artifact POM](https://repo.maven.apache.org/maven2/com/google/guava/failureaccess/1.0.1/failureaccess-1.0.1.pom), [parent POM](https://repo.maven.apache.org/maven2/com/google/guava/guava-parent/26.0-android/guava-parent-26.0-android.pom) | [Guava / failureaccess source](https://github.com/google/guava/tree/master/failureaccess) |
| `com.google.code.findbugs:jsr305:3.0.2` | The Apache Software License, Version 2.0 (`Apache-2.0`) in the POM; additional source-file notices described below | [Artifact POM](https://repo.maven.apache.org/maven2/com/google/code/findbugs/jsr305/3.0.2/jsr305-3.0.2.pom) | [Exact published source archive](https://repo.maven.apache.org/maven2/com/google/code/findbugs/jsr305/3.0.2/jsr305-3.0.2-sources.jar) |

The dexlib2 POM names the [BSD 3-Clause license](https://opensource.org/licenses/BSD-3-Clause).
The Guava, failureaccess and jsr305 POM declarations name
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.txt).
These are upstream declarations, separate from this project's own Apache-2.0
license; they do not replace notices attached to individual upstream files.

In the exact `jsr305:3.0.2` source archive linked above,
`javax/annotation/concurrent/GuardedBy.java`, `Immutable.java`,
`NotThreadSafe.java` and `ThreadSafe.java` each retain a source header crediting
Brian Goetz, copyright 2005, and declaring the Creative Commons Attribution
License with the URL `http://creativecommons.org/licenses/by/2.5` and official
home `http://www.jcip.net`. This is
[CC BY 2.5](https://creativecommons.org/licenses/by/2.5/), in addition to the
artifact-level Apache-2.0 declaration in its POM. The recipe uses the unmodified
published JAR; these four source files are not copied or modified here.

Android SDK tools and Java are separately installed development dependencies,
not bundled in this source distribution. Xiaomi, HyperOS, Android, LSPosed and
libxposed names identify compatibility or dependencies, not endorsement.

Older hook implementations included as reference sources are this project's
compatibility logic, not an OEM decompiled application tree. Host tests contain
synthetic Android/OEM class fixtures, which establish test contracts only and
are not shipped as a replacement phone framework.
