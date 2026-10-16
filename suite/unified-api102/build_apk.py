"""Build the 1.6/code17 API102 candidate with a caller-owned signing key; never install."""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent
DEFAULT_APK = "XuanyuanUnifiedCompat-1.6-wallet-selectable-api102.apk"


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--ui-candidate", action="store_true", help="Retired frozen 1.4 candidate")
    mode.add_argument("--full-nonwallet", action="store_true", help="Retired frozen 1.5 candidate")
    mode.add_argument("--wallet-selectable", action="store_true", help="Build 1.6/code17")
    parser.add_argument("--sdk", type=Path, help="SDK root; defaults to ANDROID_SDK_ROOT or ANDROID_HOME")
    parser.add_argument("--deps-dir", type=Path, default=ROOT / "build/deps", help="Directory containing pinned AARs; offline")
    parser.add_argument("--keystore", type=Path, help="Caller-provided signing keystore (never created or modified)")
    parser.add_argument("--key-alias", help="Alias in the supplied keystore")
    parser.add_argument("--output", type=Path, default=Path("build") / DEFAULT_APK,
                        help="New .apk path under this script's build/; relative paths use the script directory")
    args = parser.parse_args()
    if args.ui_candidate:
        parser.error("1.4/code15 is frozen; use --wallet-selectable for 1.6/code17")
    if args.full_nonwallet:
        parser.error("1.5/code16 is frozen; use --wallet-selectable for 1.6/code17")
    output = (ROOT / args.output).resolve()
    build = ROOT / "build"
    if build.is_symlink() or build not in output.parents or output.suffix != ".apk":
        parser.error("--output must be a new .apk inside local build/")
    evidence = output.with_suffix(".build-evidence.json")
    if output.exists() or evidence.exists():
        parser.error("Refusing to overwrite existing output or evidence; choose a new --output under build/")
    if not args.keystore or not args.keystore.is_file() or not args.key_alias:
        parser.error("Provide --keystore and --key-alias; no signing key is generated")
    for secret in ("SUITE_STORE_PASSWORD", "SUITE_KEY_PASSWORD"):
        if not os.environ.get(secret):
            parser.error("Set the " + secret + " environment secret")
    sdk = args.sdk or os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not sdk:
        parser.error("Provide --sdk or set ANDROID_SDK_ROOT/ANDROID_HOME (Android 36, build-tools 36.0.0)")
    args.sdk = Path(sdk).resolve()
    return args, output, evidence


def run(*command):
    # Signing tools may echo secrets or private paths on failure. Do not relay their output.
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True)
    if result.returncode:
        raise ValueError(Path(command[0]).name + " failed (exit " + str(result.returncode) + ")")
    return result.stdout + result.stderr


def build_apk(args, output, evidence):
    from fetch_dependencies import ignored_build, load_lock, verify

    android = args.sdk / "platforms/android-36/android.jar"
    tools = args.sdk / "build-tools/36.0.0"
    java_home = os.environ.get("JAVA_HOME")
    javac = str(Path(java_home) / "bin/javac") if java_home else shutil.which("javac")
    if not javac:
        raise ValueError("JDK 17+ required; set JAVA_HOME or put javac/java on PATH")
    version = re.search(r"javac (\d+)", run(javac, "-version"))
    if not version or int(version[1]) < 17:
        raise ValueError("JDK 17+ required")
    for path in [android, *[tools / name for name in ("d8", "aapt2", "zipalign", "apksigner")]]:
        if not path.is_file():
            raise ValueError("SDK requires platforms;android-36 and build-tools;36.0.0")
    dependencies = load_lock()
    jars = {}
    for dependency in dependencies:
        data = (args.deps_dir / dependency["file"]).read_bytes()
        verify(data, dependency)
        with zipfile.ZipFile(BytesIO(data)) as archive:
            jars[dependency["coordinate"].split(":")[1]] = archive.read("classes.jar")
    build = ignored_build(ROOT)
    with tempfile.TemporaryDirectory(prefix="wallet-selectable-", dir=build) as temp:
        work = Path(temp)
        for name, data in jars.items():
            (work / (name + ".jar")).write_bytes(data)
        classes, dex = work / "classes", work / "dex"
        classes.mkdir()
        dex.mkdir()
        sources = sorted(p for p in (ROOT / "src").rglob("*.java") if not p.name.startswith("._"))
        classpath = os.pathsep.join(map(str, [android, *[work / (name + ".jar") for name in jars]]))
        run(javac, "-encoding", "UTF-8", "-source", "8", "-target", "8", "-classpath", classpath,
            "-d", classes, *sources)
        program = work / "program.jar"
        with zipfile.ZipFile(program, "w") as archive:
            for path in classes.rglob("*.class"):
                if not path.name.startswith("._"):
                    archive.write(path, str(path.relative_to(classes)))
        run(tools / "d8", "--min-api", "34", "--lib", android, "--classpath", work / "api.jar",
            "--output", dex, program, work / "service.jar", work / "interface.jar")
        unsigned, aligned, signed = [work / name for name in ("unsigned.apk", "aligned.apk", "signed.apk")]
        run(tools / "aapt2", "link", "-o", unsigned, "-I", android,
            "--manifest", ROOT / "AndroidManifest.xml", "--version-code", "17",
            "--version-name", "1.6-wallet-selectable-api102")
        metadata = sorted(p for p in (ROOT / "META-INF/xposed").iterdir() if not p.name.startswith("._"))
        with zipfile.ZipFile(unsigned, "a") as archive:
            for path in dex.glob("classes*.dex"):
                archive.write(path, path.name)
            for path in metadata:
                archive.write(path, str(path.relative_to(ROOT)))
        run(tools / "zipalign", "-p", "4", unsigned, aligned)
        run(tools / "apksigner", "sign", "--ks", args.keystore, "--ks-key-alias", args.key_alias,
            "--ks-pass", "env:SUITE_STORE_PASSWORD", "--key-pass", "env:SUITE_KEY_PASSWORD",
            "--out", signed, aligned)
        run(tools / "apksigner", "verify", "--verbose", signed)
        with zipfile.ZipFile(signed) as archive:
            if any(n.endswith((".jks", ".keystore", ".pem", ".p12")) or n.startswith("private/")
                   for n in archive.namelist()) or archive.read("META-INF/xposed/scope.list") != b"":
                raise ValueError("APK private-material/default-scope check failed")
        inputs = [ROOT / name for name in ("AndroidManifest.xml", "build_apk.py", "fetch_dependencies.py", "deps.lock.json")]
        report = {
            "apk": str(output.relative_to(ROOT)), "apk_sha256": hashlib.sha256(signed.read_bytes()).hexdigest(),
            "dependencies": {d["file"]: d["sha256"] for d in dependencies},
            "sources": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in [*inputs, *sources, *metadata]},
            "default_scope": [], "default_enabled": False, "priority_supported": False,
            "device_verified": False, "private_signing_key_excluded": True,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects an output created by another concurrent build.
        with output.open("xb") as stream:
            stream.write(signed.read_bytes())
        with evidence.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, indent=2) + "\n")
    print(str(output.relative_to(ROOT)))


def main():
    args, output, evidence = arguments()
    try:
        build_apk(args, output, evidence)
    except ValueError as error:
        print("Build failed: " + str(error), file=sys.stderr)
        return 1
    except (OSError, KeyError, zipfile.BadZipFile):
        print("Build failed; check local inputs and tool availability. No tool output was logged.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
