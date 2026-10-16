# API102 APK build

This directory builds the original **1.6-wallet-selectable-api102 / code 17** candidate. Package names such as `local.xuanyuan` are software identities and remain unchanged. Building never installs or enables the module. The retired `--ui-candidate` and `--full-nonwallet` modes fail before reading dependencies or writing artifacts.

## Requirements

- Python 3.9+; Python code uses only the standard library.
- JDK 17+ with `java` and `javac`; set `JAVA_HOME` or place both on `PATH`.
- Android SDK with `platforms;android-36` and `build-tools;36.0.0`. Set `ANDROID_SDK_ROOT` (or `ANDROID_HOME`), or pass `--sdk`. There is no machine-specific SDK default. SDK command-line tools can install the packages with `sdkmanager 'platforms;android-36' 'build-tools;36.0.0'`.
- Your own keystore and alias. The script never generates, copies, modifies or recovers a signing key.

Run commands from this directory. Set `PYTHONDONTWRITEBYTECODE=1` for tests to avoid Python caches outside `build/`.

## Pinned dependencies

`deps.lock.json` records official Maven Central coordinates, exact URLs and the original SHA-256 values for libxposed API, service and interface 102.0.0. API is **compileOnly**: it is a D8 classpath dependency and is not bundled. Service and interface are program inputs bundled into the APK. Only `classes.jar` extracted from the hash-verified AAR is used; separate caller-supplied JARs are ignored.

Maven POM license metadata (a declaration, not a copy of upstream license text):

| Coordinate | POM | Declared license | License URL from POM |
| --- | --- | --- | --- |
| `io.github.libxposed:api:102.0.0@aar` | [api POM](https://repo.maven.apache.org/maven2/io/github/libxposed/api/102.0.0/api-102.0.0.pom) | Apache License 2.0 | https://github.com/libxposed/api/blob/master/LICENSE |
| `io.github.libxposed:service:102.0.0@aar` | [service POM](https://repo.maven.apache.org/maven2/io/github/libxposed/service/102.0.0/service-102.0.0.pom) | Apache License 2.0 | https://github.com/libxposed/service/blob/master/LICENSE |
| `io.github.libxposed:interface:102.0.0@aar` | [interface POM](https://repo.maven.apache.org/maven2/io/github/libxposed/interface/102.0.0/interface-102.0.0.pom) | Apache License 2.0 | https://github.com/libxposed/service/blob/master/LICENSE |

The referenced upstream GitHub repositories/license pages currently return 404. No upstream LICENSE or NOTICE text was retrieved or reconstructed. Preserve the POM declarations and URLs as evidence for third-party notices; they do not prove that a separate upstream NOTICE is absent.

Choose one explicit dependency preparation step:

```sh
python3 fetch_dependencies.py --download
# Or offline: directory containing api-102.0.0.aar,
# service-102.0.0.aar and interface-102.0.0.aar
python3 fetch_dependencies.py --local-dir /path/to/local/aars
```

Both write verified AARs to `build/deps/`. The builder never downloads dependencies. You can alternatively pass `--deps-dir /path/to/local/aars` directly when building; it verifies the same hashes without changing that directory. Do not commit AARs or JARs.

## Signing and building

Provide `SUITE_STORE_PASSWORD` and `SUITE_KEY_PASSWORD` through your secret manager or a shell prompt with echo disabled; do not put passwords in command arguments, files, shell history or logs. Both variables are required, even when the passwords match. Android's signer receives `env:` references only. Captured tool output is not printed on failure because external tools may echo private inputs; errors name the failed tool and exit status.

```sh
# Export the SDK root and supply the two password environment secrets first.
python3 build_apk.py --wallet-selectable \
  --keystore /path/to/your-signing.jks --key-alias your-alias
```

The default APK is `build/XuanyuanUnifiedCompat-1.6-wallet-selectable-api102.apk`, accompanied by `.build-evidence.json` with source/dependency/APK hashes and `device_verified: false`. No absolute local path, keystore path, alias or password is written into the evidence. Certificates are necessarily public parts of a signed APK: use a certificate subject appropriate for public distribution.

Every build uses fresh temporary intermediates under `build/`, then removes them. Existing APKs and evidence files are never overwritten, including concurrent output creation. For another build, supply a fresh path:

```sh
python3 build_apk.py --wallet-selectable \
  --keystore /path/to/your-signing.jks --key-alias your-alias \
  --output build/another-candidate.apk
```

Relative output paths are relative to this script's directory. Outputs outside `build/` are rejected. Generated `build/.gitignore` excludes all directory contents, including dependencies, APKs, evidence and any temporary private material, once this clean source directory is placed in Git. Never force-add that directory. Do not delete existing APKs just to bypass the overwrite guard. To discard stale files, remove only the specific unwanted intermediates or use a fresh output name.

**A newly signed APK cannot directly update the existing phone installation signed with a different key.** Same package/version does not confer the old signing identity. This build does not prove device compatibility or authorize uninstalling, replacing or installing anything on the original phone. Keep the original private key outside this repository.

## Host regressions

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_build_flags.py -v
```

The other original host tests still expect `deps/*.jar`. To run them without writing binaries outside ignored `build/` or modifying those tests, prepare the dependencies above, then run their unchanged copies in an isolated layout:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PYTHON'
import os, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
root = Path.cwd()
with tempfile.TemporaryDirectory(prefix="host-regression-", dir=root / "build") as temp:
    project = Path(temp) / "unified-api102"
    shutil.copytree(root, project,
                    ignore=shutil.ignore_patterns("build", "deps", "__pycache__"))
    (project / "deps").mkdir()
    for name in ("api", "service", "interface"):
        with zipfile.ZipFile(root / f"build/deps/{name}-102.0.0.aar") as archive:
            (project / f"deps/{name}.jar").write_bytes(archive.read("classes.jar"))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s",
                    str(project / "tests"), "-p", "test_*.py", "-v"],
                   env=env, check=True)
PYTHON
```

Set `ANDROID_SDK_ROOT` for these original tests. These host checks and signature verification do not establish real phone behavior.
