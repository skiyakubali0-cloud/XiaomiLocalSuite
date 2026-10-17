"""Pure-standard-library tests using public templates and synthetic locked materials."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import build_suite as b
import recipe_assemble as a


def sha(data):
    return hashlib.sha256(data).hexdigest()


def apk_bytes():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, raw in {
            "AndroidManifest.xml": b"synthetic manifest; checked by injected checker",
            "classes.dex": b"synthetic code17",
            "META-INF/xposed/java_init.list": b"local.xuanyuan.unified.UnifiedModule\n",
            "META-INF/xposed/scope.list": b"",
            "META-INF/xposed/module.prop": b"minApiVersion=102\ntargetApiVersion=102\nstaticScope=false\n",
        }.items():
            archive.writestr(name, raw)
    return stream.getvalue()


class SelectionTests(unittest.TestCase):
    def test_canonical_dependency_closure(self):
        self.assertEqual(a.selection(["phone", "xiaoai"]), ("market", "assistant", "xiaoai", "phone"))
        self.assertEqual(a.selection(reversed(a.IDS)), a.IDS)
        self.assertEqual(a.selection(["clock"]), ("clock",))

    def test_invalid_selection_is_rejected_before_filesystem_access(self):
        for ids in (None, "phone", [], ["wallet", "wallet"], ["unknown"], ["../x"], [None], [{}]):
            with self.subTest(ids=ids), patch.object(Path, "stat", side_effect=AssertionError("filesystem touched")):
                with self.assertRaises(ValueError):
                    a.assemble("missing", "missing", "missing", ids, "missing.zip")


class AssembleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="recipe-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "public source"
        self.source.mkdir()
        for relative in ("suite/module", "components"):
            shutil.copytree(b.ROOT / relative, self.source / relative)
        self.lock = json.loads((b.ROOT / "materials.lock.json").read_text())
        self.original = self.lock["original_unified_sha256"]
        self.materials = {}
        for item in self.lock["artifacts"]:
            if (item["component"], item["path"]) == ("parent", "payload/unified.apk"):
                continue  # Caller builds this APK; no old/private reference APK exists.
            key = item["component"] + "/" + item["path"]
            data = b"" if item["bytes"] == 0 else b"\x00synthetic locked material: " + key.encode()
            item.update(sha256=sha(data), bytes=len(data))
            self.materials[key] = data
        self.save_lock()
        self.resolved = self.root / "resolved local"
        self.resolved.mkdir()
        self.apk = self.root / "caller code17.apk"
        self.apk.write_bytes(apk_bytes())
        self.output = self.root / "private outputs" / "selected.zip"
        self.checked = []

    def save_lock(self):
        (self.source / "materials.lock.json").write_text(json.dumps(self.lock), encoding="utf-8")

    def resolve(self, ids):
        chosen = a.selection(ids)
        for key, data in self.materials.items():
            component, name = key.split("/", 1)
            if component in chosen or component == "parent" and "calendar" in chosen:
                path = self.resolved / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

    def checker(self, path):
        self.assertEqual(path.read_bytes(), self.apk.read_bytes())
        self.checked.append(path)

    def build(self, ids, checker=None):
        return a.assemble(self.source, self.resolved, self.apk, ids, self.output,
                          apk_checker=self.checker if checker is None else checker)

    def sums(self, archive, name, expected):
        rows = archive.read(name).decode().splitlines()
        self.assertEqual({row.split("  ", 1)[1] for row in rows}, set(expected))
        for row in rows:
            digest, path = row.split("  ", 1)
            self.assertEqual(digest, sha(archive.read(path)), path)

    def verify(self, archive, ids):
        chosen = a.selection(ids)
        catalog = json.loads(archive.read("webroot/catalog.json"))
        self.assertEqual([row["id"] for row in catalog], list(chosen))
        expected_payloads = {"payload/unified.apk"}
        expected_payloads.update("payload/" + key + ".zip" for key in chosen if key in b.COMPONENTS)
        if "calendar" in chosen:
            expected_payloads.update(("payload/calendar.apk", "payload/calendar-global.apk"))
        self.assertEqual({n for n in archive.namelist() if n.startswith("payload/")}, expected_payloads)
        self.assertEqual(archive.read("payload/unified.apk"), self.apk.read_bytes())
        self.assertNotIn("parent/payload/unified.apk", self.materials)
        self.assertFalse((self.resolved / "parent/payload/unified.apk").exists())
        shell_catalog = archive.read("catalog.sh").decode()
        self.assertEqual(re.findall(r"^([a-z]+)\)", shell_catalog, re.M), list(chosen))
        self.assertIn("MID='' PKG='' CODE='' FILE='' SHA='' TITLE='' KIND=''", shell_catalog)
        for row in catalog:
            self.assertEqual(row["sha256"], sha(archive.read(row["file"])))
            self.assertEqual(row["bytes"], len(archive.read(row["file"])))
            self.assertRegex(shell_catalog, row["id"] + r"\).*SHA='" + row["sha256"] + "'")
            self.assertTrue(set(row["dependencies"]).issubset(chosen))
        self.sums(archive, "checksums.sha256", set(archive.namelist()) - {"checksums.sha256"})
        self.sums(archive, "control.sha256", {n for n in archive.namelist() if not n.startswith("payload/")
                  and n not in {"control.sha256", "checksums.sha256", "customize.sh"}})
        control = archive.read("control.sh").decode()
        preset = archive.read("preset.sh").decode()
        self.assertIn("ORDER='" + " ".join(chosen) + "'", control)
        self.assertIn("P_ORDER='" + " ".join(a.IDS) + "'", preset)
        self.assertIn("P_AVAILABLE='" + " ".join(chosen) + "'", preset)
        self.assertIn("ORDER=$P_AVAILABLE", preset)
        self.assertIn("for P_ID in $P_AVAILABLE; do", preset)
        self.assertNotIn("for P_ID in $P_ORDER; do", preset)
        self.assertLess(preset.index("Component not included in this package"), preset.index("check platform"))
        self.assertLess(preset.index("Component not included in this package"), preset.index("check start"))
        # Requiring unavailable components/features cannot silently truncate a requested plan.
        self.assertIn('normalize "$P_COMPONENTS" "$P_ORDER"; P_PROFILE=$P_NORMAL', preset)
        self.assertIn('normalize "${P_PROFILE:--}" "$P_ORDER"; P_PROFILE=$P_NORMAL', preset)
        self.assertIn('case " $P_AVAILABLE " in *" $P_ID "*) ;; *) blocked', preset)
        cap_line = next(line for line in control.splitlines() if line.startswith(" capabilities)"))
        self.assertIn('[ "$#" = 1 ] || fail', cap_line)
        self.assertIn("platform; integrity; printf '%s\\n' '" + ",".join(chosen) + "';;", cap_line)
        cap_start = preset.index('if [ "$ACTION" = capabilities ]; then')
        cap_branch = preset[cap_start:preset.index("\nfi", cap_start) + 3]
        template = (self.source / "suite/module/preset.sh").read_text()
        template_start = template.index('if [ "$ACTION" = capabilities ]; then')
        self.assertEqual(cap_branch, template[template_start:template.index("\nfi", template_start) + 3])
        self.assertEqual(preset.count('if [ "$ACTION" = capabilities ]; then'), 1)
        self.assertIn('[ "$P_ARGC" = 1 ] || fail', cap_branch)
        self.assertIn('platform; integrity', cap_branch)
        self.assertIn('"$(prop "$M" id)" = xuanyuan-os4-suite', cap_branch)
        self.assertIn('"$(prop "$M" versionCode)" = 2026101604', cap_branch)
        self.assertIn('printf \'%s\\n\' "$ORDER" | tr \' \' \',\'', cap_branch)
        self.assertLess(preset.index('if [ "$ACTION" = capabilities ]'), preset.index("trap emit EXIT"))
        # Existing generic WebUI renders only filtered catalog rows, including restore actions.
        self.assertEqual(archive.read("webroot/index.html"), (self.source / "suite/module/webroot/index.html").read_bytes())
        for info in archive.infolist():
            self.assertLess(info.extract_version, 45)
            self.assertEqual(info.extra, b"")
        for key in chosen:
            if key not in b.COMPONENTS:
                continue
            with zipfile.ZipFile(io.BytesIO(archive.read("payload/" + key + ".zip"))) as child:
                self.sums(child, "checksums.sha256", set(child.namelist()) - {"checksums.sha256"})
                for material, data in self.materials.items():
                    if material.startswith(key + "/"):
                        self.assertEqual(child.read(material[len(key) + 1:]), data)
                for path in b.files(self.source / "components" / key):
                    name = path.relative_to(self.source / "components" / key).as_posix()
                    if key == "xiaoai" and name == "privacy.sh":
                        continue
                    self.assertEqual(child.read(name), path.read_bytes(), key + "/" + name)
                for info in child.infolist():
                    self.assertLess(info.extract_version, 45)
                    self.assertEqual(info.extra, b"")

    def test_phone_partial_has_closure_and_only_exact_selected_materials(self):
        self.resolve(["phone"])
        report = self.build(["phone"])
        self.assertEqual(report["selected"], ["market", "phone"])
        self.assertFalse(report["wallet_reset"])
        self.assertEqual(report["available_ids"], ["market", "phone"])
        self.assertEqual(report["available_features"], ["phone"])
        self.assertEqual(report["sha256"], b.digest(self.output))
        self.assertEqual(report["bytes"], self.output.stat().st_size)
        self.assertTrue(report["auto_install_components"])
        self.assertEqual(report["wallet_first_migration"], "phone-confirmation-only")
        self.assertFalse(report["device_tested"])
        self.assertTrue(report["clean_install_only"])
        with zipfile.ZipFile(self.output) as archive:
            self.verify(archive, ["phone"])

    def test_staging_uses_existing_output_parent_and_preserves_checksums(self):
        self.resolve(["phone"])
        self.assertFalse(self.output.parent.exists())
        temporary_directory = a.tempfile.TemporaryDirectory
        stages = []
        def capture_stage(*args, **kwargs):
            self.assertEqual(kwargs["dir"], self.output.parent)
            self.assertTrue(self.output.parent.is_dir())
            directory = temporary_directory(*args, **kwargs)
            stages.append(Path(directory.name))
            self.assertEqual(stages[-1].parent.resolve(), self.output.parent.resolve())
            return directory
        with patch.object(a.tempfile, "TemporaryDirectory", side_effect=capture_stage) as create:
            self.build(["phone"])
        self.assertEqual(create.call_count, 1)
        self.assertFalse(stages[0].exists())
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])
        with zipfile.ZipFile(self.output) as archive:
            self.verify(archive, ["phone"])

    def test_staging_location_does_not_change_full_zip_bytes(self):
        self.resolve(a.IDS)
        temporary_directory = a.tempfile.TemporaryDirectory
        def old_system_temp(*args, **kwargs):
            kwargs.pop("dir")  # Reproduce the previous default-system-temp placement.
            return temporary_directory(*args, **kwargs)
        with patch.object(a.tempfile, "TemporaryDirectory", side_effect=old_system_temp):
            previous = self.build(a.IDS)
        previous_bytes = self.output.read_bytes()
        self.output = self.root / "new output directory" / "suite.zip"
        current = self.build(a.IDS)
        self.assertEqual(self.output.read_bytes(), previous_bytes)
        self.assertEqual((current["sha256"], current["bytes"]), (previous["sha256"], previous["bytes"]))
        with zipfile.ZipFile(self.output) as archive:
            self.verify(archive, a.IDS)

    def test_unified_only_capability_needs_no_stock_unified_or_other_materials(self):
        report = self.build(["mipush"])
        self.assertEqual(report["available_features"], [])
        self.assertEqual(list(self.resolved.iterdir()), [])
        with zipfile.ZipFile(self.output) as archive:
            self.verify(archive, ["mipush"])
            customize = archive.read("customize.sh").decode()
            self.assertNotIn('module install "$MODPATH/payload/xiaoai.zip"', customize)
            self.assertIn("本包未选择小爱", customize)
            self.assertIn('if [ -f "$X/module.prop" ]; then', customize)
            self.assertLess(customize.index("本包未选择小爱"), customize.index("shared_install ||"))
            self.assertIn("2026101602:428c72628cfcf14f9d17b229690c3cb4b93ef48c089dd58a6a505b87ed95b7f2) PAIR_XIAOAI=true", customize)
            self.assertIn("2026101603:7f508bd4fe60bb2cc1585295ea03a717846b5918cdafcbeb91333785e67e2dde) PAIR_XIAOAI=true", customize)

    def test_xiaoai_paired_hashes_and_independent_restore_scripts(self):
        self.resolve(["xiaoai"])
        report = self.build(["xiaoai"])
        self.assertEqual(report["available_features"], ["privacy", "suggestions"])
        with zipfile.ZipFile(self.output) as archive:
            self.verify(archive, ["xiaoai"])
            with zipfile.ZipFile(io.BytesIO(archive.read("payload/xiaoai.zip"))) as child:
                privacy = child.read("privacy.sh")
                self.assertIn(self.original.encode(), privacy)
                self.assertIn(b.digest(self.apk).encode(), privacy)
                self.assertIn("2026101603:" + sha(privacy) + ") ;;", archive.read("customize.sh").decode())
            self.assertIn('module install "$MODPATH/payload/xiaoai.zip"', archive.read("customize.sh").decode())
            shared = archive.read("shared.sh").decode()
            self.assertIn("UNIFIED_SHA=" + b.digest(self.apk), shared)
            for old_hash in re.findall(r"[0-9a-f]{64}", (self.source / "suite/module/shared.sh").read_text()):
                self.assertIn(old_hash, shared)
            self.assertIn("SELF_SHA=" + b.digest(self.apk), archive.read("migrate-legacy.sh").decode())

    def test_calendar_includes_cn_and_global_restore_materials_only(self):
        self.resolve(["calendar"])
        self.build(["calendar"])
        with zipfile.ZipFile(self.output) as archive:
            self.verify(archive, ["calendar"])
            for name in ("payload/calendar.apk", "payload/calendar-global.apk"):
                self.assertEqual(archive.read(name), self.materials["parent/" + name])

    def test_full_suite_wallet_logic_guards_and_all_binaries_unchanged(self):
        self.resolve(a.IDS)
        self.build(a.IDS)
        with zipfile.ZipFile(self.output) as archive:
            self.verify(archive, a.IDS)
            self.assertEqual(archive.read("wallet.sh"), (self.source / "suite/module/wallet.sh").read_bytes())
            helper = archive.read("install-selected.sh").decode()
            self.assertIn("AUTO_IDS='" + ",".join(a.IDS) + "'", helper)
            self.assertNotIn('@SELECTED_IDS@', helper)
            self.assertIn('sh "$M/install-selected.sh" resume', archive.read("service.sh").decode())
            self.assertIn('sh "$MODPATH/install-selected.sh" flash', archive.read("customize.sh").decode())
            self.assertEqual(archive.read("owned-packages.txt"), (self.source / "suite/module/owned-packages.txt").read_bytes())
            control = archive.read("control.sh").decode()
            before = (self.source / "suite/module/control.sh").read_text()
            self.assertEqual(control[control.index("wallet_install() ("):control.index("install_one() {")],
                             before[before.index("wallet_install() ("):before.index("install_one() {")])
            self.assertEqual(control[control.index("platform() {"):control.index("integrity() {")],
                             before[before.index("platform() {"):before.index("integrity() {")])
            self.assertFalse(any("authorized" in name or "reset-marker" in name for name in archive.namelist()))
            with zipfile.ZipFile(io.BytesIO(archive.read("payload/wallet.zip"))) as wallet:
                self.assertFalse(any("authorized" in name for name in wallet.namelist()))
                script = wallet.read("wallet.sh").decode()
                self.assertIn("Existing CN TSM; no reset", script)
                self.assertIn("RESET_XIAOMI_TSM_ONLY:$W_BOOT:$W_EEA", script)

    def test_missing_or_tampered_selected_material_rejected(self):
        for mode in ("missing", "size", "sha"):
            with self.subTest(mode=mode):
                self.resolve(["assistant"])
                name = next(name for name in self.materials if name.startswith("assistant/"))
                path = self.resolved / name
                if mode == "missing":
                    path.unlink()
                elif mode == "size":
                    path.write_bytes(path.read_bytes() + b"x")
                else:
                    data = path.read_bytes()
                    path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
                with self.assertRaisesRegex(ValueError, "Missing resolved material|Material bytes mismatch|Material SHA256 mismatch"):
                    self.build(["assistant"])
                self.assertFalse(self.output.exists())

    def test_missing_calendar_restore_material_rejected(self):
        self.resolve(["calendar"])
        (self.resolved / "parent/payload/calendar-global.apk").unlink()
        with self.assertRaisesRegex(ValueError, "Missing resolved material"):
            self.build(["calendar"])

    def test_apk_metadata_and_signature_checker_fail_closed(self):
        self.apk.write_bytes(b"not an APK")
        with self.assertRaises(zipfile.BadZipFile):
            self.build(["clock"])
        self.assertFalse(self.checked)
        self.apk.write_bytes(apk_bytes())
        def reject(path):
            raise ValueError("signature rejected")
        with self.assertRaisesRegex(ValueError, "signature rejected"):
            self.build(["clock"], checker=reject)
        self.assertFalse(self.output.exists())

    def test_source_evidence_follows_apk_snapshot_without_reference_builder(self):
        proof = json.dumps({"apk_sha256": b.digest(self.apk), "sources": {"synthetic-source": "verified-by-caller"}}).encode()
        self.apk.with_suffix(".build-evidence.json").write_bytes(proof)
        def source_checker(path):
            self.assertNotEqual(path, self.apk)
            self.assertEqual(path.with_suffix(".build-evidence.json").read_bytes(), proof)
            self.assertEqual(json.loads(proof)["apk_sha256"], b.digest(path))
        with patch.object(b, "build_suite", side_effect=AssertionError("private reference builder called")):
            report = self.build(["clock"], checker=source_checker)
        self.assertEqual(report["selected"], ["clock"])
        with zipfile.ZipFile(self.output) as archive:
            self.assertFalse(any("build-evidence" in name for name in archive.namelist()))

    @unittest.skipUnless(shutil.which("sh"), "POSIX shell unavailable; remaining tests require only Python")
    def test_template_capabilities_reject_wrong_identity_version_and_failed_gates(self):
        self.resolve(["phone"])
        self.build(["phone"])
        with zipfile.ZipFile(self.output) as archive:
            preset = archive.read("preset.sh").decode()
            order = re.search(r"^ORDER='([^']+)'$", archive.read("control.sh").decode(), re.M)[1]
        # Execute only the capability branch with local shell functions replacing the
        # controller. No Android command, phone path or installed package is accessed.
        stub = self.root / "synthetic control.sh"
        stub.write_text("ORDER='" + order + "'\n" + '''
fail() { printf '%s\\n' "$*" >&2; exit 77; }
platform() { [ "$TEST_PLATFORM" = yes ] || fail platform; }
integrity() { [ "$TEST_INTEGRITY" = yes ] || fail integrity; }
prop() { case "$2" in id) printf '%s' "$TEST_ID";; versionCode) printf '%s' "$TEST_VERSION";; esac; }
''')
        script = self.root / "synthetic preset.sh"
        script.write_text(preset.replace('. "$M/control.sh"', ". " + shlex.quote(str(stub)), 1))
        environment = dict(os.environ, TEST_PLATFORM="yes", TEST_INTEGRITY="yes",
                           TEST_ID="xuanyuan-os4-suite", TEST_VERSION="2026101604")
        def run(env, *args):
            return subprocess.run([shutil.which("sh"), str(script), *args], env=env,
                                  capture_output=True, text=True, timeout=5)
        result = run(environment, "capabilities")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "market,phone\n", ""))
        for change in ({"TEST_ID": "other-suite"}, {"TEST_VERSION": "2026101603"},
                       {"TEST_PLATFORM": "no"}, {"TEST_INTEGRITY": "no"}):
            with self.subTest(change=change):
                result = run(dict(environment, **change), "capabilities")
                self.assertEqual((result.returncode, result.stdout), (77, ""))
        result = run(environment, "capabilities", "extra")
        self.assertEqual((result.returncode, result.stdout), (77, ""))

    def test_resolved_material_symlink_is_not_followed(self):
        self.resolve(["assistant"])
        path = self.resolved / next(name for name in self.materials if name.startswith("assistant/"))
        data = path.read_bytes()
        path.unlink()
        real = self.root / "outside material"
        real.write_bytes(data)
        try:
            path.symlink_to(real)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        with self.assertRaisesRegex(ValueError, "Resolved material symlink"):
            self.build(["assistant"])

    def test_invalid_catalog_rejected_instead_of_accessing_invented_payload(self):
        catalog = self.source / "suite/module/webroot/catalog.json"
        rows = json.loads(catalog.read_text())
        rows[0]["id"] = "unknown"
        catalog.write_text(json.dumps(rows))
        with self.assertRaisesRegex(ValueError, "catalog IDs"):
            self.build(["clock"])
        self.assertFalse(self.output.exists())

    def test_output_is_private_exclusive_and_race_safe(self):
        with self.assertRaisesRegex(ValueError, "outside public source"):
            a.assemble(self.source, self.resolved, self.apk, ["clock"], self.source / "release.zip",
                       apk_checker=self.checker)
        self.output.parent.mkdir()
        self.output.write_bytes(b"keep old output")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.build(["clock"])
        self.assertEqual(self.output.read_bytes(), b"keep old output")
        self.output.unlink()
        def concurrent_writer(path):
            self.output.write_bytes(b"concurrent output")
        with self.assertRaises(FileExistsError):
            self.build(["clock"], checker=concurrent_writer)
        self.assertEqual(self.output.read_bytes(), b"concurrent output")


if __name__ == "__main__":
    unittest.main()
