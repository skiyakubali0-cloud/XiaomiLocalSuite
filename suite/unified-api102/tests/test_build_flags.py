"""Portable, offline build preflight and pinned dependency regressions."""
from pathlib import Path
import hashlib
import importlib.util
import io
import os
from unittest import mock
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildFlags(unittest.TestCase):
    def test_ui_candidate_rejected_without_touching_frozen_artifact(self):
        with tempfile.TemporaryDirectory(prefix="frozen-ui-build-") as temp:
            root = Path(temp)
            script = root / "build_apk.py"
            script.write_bytes((ROOT / "build_apk.py").read_bytes())
            old = root / "build/XuanyuanUnifiedCompat-1.4-ui-api102.apk"
            old.parent.mkdir()
            old.write_bytes(b"frozen 1.4 sentinel")
            result = subprocess.run([sys.executable, str(script), "--ui-candidate"],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("1.4/code15 is frozen", result.stderr)
            self.assertIn("--wallet-selectable", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(old.read_bytes(), b"frozen 1.4 sentinel")
            self.assertEqual({p for p in root.rglob("*") if not p.name.startswith("._")}, {script, old.parent, old})

    def test_full_nonwallet_rejected_without_writes(self):
        with tempfile.TemporaryDirectory(prefix="frozen-nonwallet-build-") as temp:
            root = Path(temp)
            script = root / "build_apk.py"
            script.write_bytes((ROOT / "build_apk.py").read_bytes())
            old = root / "build/XuanyuanUnifiedCompat-1.5-full-nonwallet-api102.apk"
            old.parent.mkdir()
            old.write_bytes(b"frozen 1.5 sentinel")
            result = subprocess.run([sys.executable, str(script), "--full-nonwallet"],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("1.5/code16 is frozen", result.stderr)
            self.assertIn("--wallet-selectable", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(old.read_bytes(), b"frozen 1.5 sentinel")
            self.assertEqual({p for p in root.rglob("*") if not p.name.startswith("._")}, {script, old.parent, old})

def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableBuild(unittest.TestCase):
    def invoke(self, root, *flags, **environment):
        script = root / "build_apk.py"
        script.write_bytes((ROOT / script.name).read_bytes())
        env = {k: v for k, v in os.environ.items()
               if k not in ("SUITE_STORE_PASSWORD", "SUITE_KEY_PASSWORD", "ANDROID_HOME", "ANDROID_SDK_ROOT")}
        env.update(environment)
        return subprocess.run([sys.executable, str(script), "--wallet-selectable", *flags],
                              capture_output=True, text=True, env=env, timeout=10)

    def test_existing_output_and_evidence_preserved_before_key_or_dependency_reads(self):
        for suffix in (".apk", ".build-evidence.json"):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                old = root / ("build/frozen" + suffix)
                old.parent.mkdir()
                old.write_bytes(b"sentinel")
                result = self.invoke(root, "--output", "build/frozen.apk")
                self.assertEqual(result.returncode, 2)
                self.assertIn("Refusing to overwrite", result.stderr)
                self.assertEqual(old.read_bytes(), b"sentinel")
                self.assertEqual(len(list(root.rglob("*"))), 3)

    def test_output_cannot_escape_build(self):
        for output in ("../outside.apk", "outside.apk", "build/../outside.apk", "build/not-apk.zip"):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                result = self.invoke(root, "--output", output)
                self.assertEqual(result.returncode, 2)
                self.assertIn("inside local build/", result.stderr)
                self.assertFalse((root / "build").exists())

    def test_symlink_build_refused_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "outside"
            target.mkdir()
            (root / "build").symlink_to(target, target_is_directory=True)
            result = self.invoke(root)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(list(target.iterdir()), [])

    def test_requires_caller_key_secrets_and_sdk_without_creating_build(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = self.invoke(root)
            self.assertIn("Provide --keystore", result.stderr)
            key = root / "caller.jks"
            key.write_bytes(b"caller sentinel")
            flags = ("--keystore", str(key), "--key-alias", "caller")
            result = self.invoke(root, *flags)
            self.assertIn("SUITE_STORE_PASSWORD environment secret", result.stderr)
            result = self.invoke(root, *flags, SUITE_STORE_PASSWORD="secret sentinel")
            self.assertIn("SUITE_KEY_PASSWORD environment secret", result.stderr)
            result = self.invoke(root, *flags, SUITE_STORE_PASSWORD="secret sentinel", SUITE_KEY_PASSWORD="secret sentinel")
            self.assertEqual(result.returncode, 2)
            self.assertIn("Provide --sdk", result.stderr)
            self.assertNotIn("secret sentinel", result.stdout + result.stderr)
            self.assertEqual(key.read_bytes(), b"caller sentinel")
            self.assertFalse((root / "build").exists())

    def test_tool_failure_does_not_echo_password_or_private_paths(self):
        builder = load_module("build_apk")
        failed = subprocess.CompletedProcess([], 1, "secret sentinel", "private path sentinel")
        with mock.patch.object(builder.subprocess, "run", return_value=failed) as child:
            with self.assertRaisesRegex(ValueError, r"apksigner failed \(exit 1\)") as error:
                builder.run(Path("apksigner"), "--ks-pass", "env:SUITE_STORE_PASSWORD")
        self.assertNotIn("sentinel", str(error.exception))
        self.assertEqual(child.call_args.args[0][-1], "env:SUITE_STORE_PASSWORD")
        self.assertTrue(child.call_args.kwargs["capture_output"])


class Dependencies(unittest.TestCase):
    def test_original_hashes_coordinates_and_scopes(self):
        helper = load_module("fetch_dependencies")
        deps = helper.load_lock()
        expected = {
            "api": "423484a6e1807e7a423c4b88fcd8176d104318259d91791877fed88fe91479d0",
            "service": "a665e4af4638924047f5d5cb610553e15bc2c0ea2ce64a27afb6dee257ff014c",
            "interface": "4e0b76d6050be1d3dc0d35525180ad7d9b60a47fd8d8fe1d18c2bdc840be9ddb",
        }
        self.assertEqual(len(deps), 3)
        for dependency, name in zip(deps, expected):
            self.assertEqual(dependency["sha256"], expected[name])
            self.assertEqual(dependency["coordinate"], f"io.github.libxposed:{name}:102.0.0@aar")
            self.assertEqual(dependency["url"], f"https://repo.maven.apache.org/maven2/io/github/libxposed/{name}/102.0.0/{name}-102.0.0.aar")
            self.assertEqual(dependency["scope"], "compileOnly" if name == "api" else "implementation")

    def test_local_input_and_download_are_verified_and_never_replace_cache(self):
        helper = load_module("fetch_dependencies")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            local = root / "local"
            local.mkdir()
            data = b"fixture dependency"
            dependency = {"file": "fixture.aar", "url": "https://example.invalid/fixture.aar",
                          "sha256": hashlib.sha256(data).hexdigest()}
            (local / dependency["file"]).write_bytes(b"tampered")
            with mock.patch.object(helper, "ROOT", root), mock.patch.object(helper, "load_lock", return_value=[dependency]), mock.patch.object(helper.urllib.request, "urlopen") as network:
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    helper.fetch(local)
                self.assertFalse((root / "build").exists())
                (local / dependency["file"]).write_bytes(data)
                helper.fetch(local)
                network.assert_not_called()
                cache = root / "build/deps/fixture.aar"
                self.assertEqual(cache.read_bytes(), data)
                self.assertIn("*", (root / "build/.gitignore").read_text())
                network.return_value.__enter__.return_value = io.BytesIO(b"tampered download")
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    helper.fetch()
                self.assertEqual(cache.read_bytes(), data)
                network.return_value.__enter__.return_value = io.BytesIO(data)
                helper.fetch()
                network.assert_called_with(dependency["url"], timeout=60)
                cache.write_bytes(b"existing sentinel")
                with self.assertRaisesRegex(ValueError, "Refusing to replace"):
                    helper.fetch(local)
                self.assertEqual(cache.read_bytes(), b"existing sentinel")


if __name__ == "__main__":
    unittest.main(verbosity=2)
