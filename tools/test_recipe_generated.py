"""Offline synthetic recipe regressions; no OEM binaries or private material needed."""
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import struct
import subprocess
import unittest
from unittest.mock import Mock, patch
import warnings
import zipfile

import recipe_generated as recipes


def sha(data):
    return hashlib.sha256(data).hexdigest()


def generated_items():
    return [recipes.RECIPES["assistant"]["output"], recipes.RECIPES["warning"]["output"],
            *(r["output"] for r in recipes.RECIPES["weather"]), *recipes.RECIPES["markers"]]


def synthetic_elf():
    data = bytearray(318656)
    data[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", data, 18, 183)
    struct.pack_into("<Q", data, 32, 64)
    struct.pack_into("<HH", data, 54, 56, 1)
    struct.pack_into("<IIQ", data, 64, 1, 5, 0)
    struct.pack_into("<QQ", data, 96, 0x44498, 0x44498)
    struct.pack_into("<I", data, 0x38ed4, 0x900000a8)
    return data


def zipped(entries):
    stream = BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(stream, "w") as archive:
            for name, data in entries:
                archive.writestr(name, data)
    return stream.getvalue()


class GeneratedRecipes(unittest.TestCase):
    def test_recipe_outputs_match_locked_materials(self):
        lock = json.loads((recipes.ROOT / "materials.lock.json").read_text())["artifacts"]
        indexed = {(x["component"], x["path"]): x for x in lock}
        self.assertEqual(len(generated_items()), 11)
        for item in generated_items():
            with self.subTest(path=item["path"]):
                actual = {k: item[k] for k in ("component", "path", "sha256", "bytes")}
                self.assertEqual(actual, indexed[(item["component"], item["path"])])

    def test_input_contract_separates_stock_and_public_build_tools(self):
        self.assertEqual(len(recipes.STOCK_INPUTS), 4)
        self.assertEqual(len(recipes.TOOL_INPUTS), 4)
        self.assertEqual(recipes.INPUTS, {**recipes.STOCK_INPUTS, **recipes.TOOL_INPUTS})
        self.assertEqual(set(recipes.INPUT_PROVENANCE), set(recipes.INPUTS))
        for tool in recipes.RECIPES["tools"]:
            self.assertTrue(tool["url"].startswith("https://"))
            self.assertEqual(recipes.TOOL_INPUTS[tool["sha256"]], tool["bytes"])

    def test_exact_markers_without_input_lookup(self):
        lookup = Mock(side_effect=AssertionError("marker must not read caller inputs"))
        expected = {
            "xiaoai": b"xuanyuan EEA OS4.0.0.6 AI privacy compatibility 1\n",
            "phone": b"unified-api102\n", "disaster": b"13.6.5-261003.0.1\n", "gallery": b"",
        }
        for marker in recipes.RECIPES["markers"]:
            with self.subTest(path=marker["path"]):
                result = recipes.generate(marker, lookup)
                self.assertEqual(result, expected[marker["component"]])
                self.assertEqual(len(result), marker["bytes"])
                self.assertEqual(sha(result), marker["sha256"])
        lookup.assert_not_called()

    def test_unrelated_paths_are_not_generated_even_with_known_hash(self):
        lookup = Mock(side_effect=AssertionError("unrelated item must not read inputs"))
        for component, path in (("gallery", "system/product/other/.replace"),
                                ("assistant", "../lib.so"), ("wallet", "payload/Mipay.apk")):
            item = dict(generated_items()[0], component=component, path=path)
            self.assertIsNone(recipes.generate(item, lookup))
        lookup.assert_not_called()

    def test_rejects_changed_requested_hash_size_and_boolean_size_before_lookup(self):
        lookup = Mock(side_effect=AssertionError("forged identity must fail before lookup"))
        for item in generated_items():
            for changes in ({"sha256": "0" * 64}, {"bytes": item["bytes"] + 1}, {"bytes": False}):
                with self.subTest(path=item["path"], changes=changes):
                    with self.assertRaisesRegex(ValueError, "Requested generated material identity mismatch"):
                        recipes.generate({**item, **changes}, lookup)
        lookup.assert_not_called()

    def test_missing_stock_inputs_report_exact_hash_and_length(self):
        for recipe in [recipes.RECIPES["assistant"], recipes.RECIPES["warning"], *recipes.RECIPES["weather"]]:
            lookup = Mock(return_value=None)
            digest = recipe["input_sha256"]
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, digest) as caught:
                recipes.generate(recipe["output"], lookup)
            self.assertIn(str(recipes.INPUTS[digest]), str(caught.exception))
            lookup.assert_called_once_with(digest)

    def test_foreign_stock_is_rejected_before_transformation_or_java(self):
        with patch.object(recipes, "_assistant") as native, patch.object(recipes, "_warning") as warning, patch.object(recipes, "_weather") as weather:
            for item in generated_items()[:4]:
                with self.subTest(path=item["path"]), self.assertRaisesRegex(ValueError, "Recipe input identity mismatch"):
                    recipes.generate(item, lambda digest: b"foreign untrusted OEM bytes")
            native.assert_not_called()
            warning.assert_not_called()
            weather.assert_not_called()

    def test_missing_or_changed_tool_jar_fails_before_running_java(self):
        digest = recipes.RECIPES["tools"][0]["sha256"]
        with patch.object(recipes, "_run") as run:
            with self.assertRaisesRegex(ValueError, digest):
                recipes._warning(b"synthetic APK", lambda key: None)
            with self.assertRaisesRegex(ValueError, "Recipe input identity mismatch"):
                recipes._warning(b"synthetic APK", lambda key: b"foreign tool")
            run.assert_not_called()

    def test_transformation_output_is_independently_hash_checked(self):
        with patch.object(recipes, "_input", return_value=b"synthetic stock"), patch.object(recipes, "_assistant", return_value=b"wrong output"):
            with self.assertRaisesRegex(ValueError, "Generated material identity mismatch"):
                recipes.generate(recipes.RECIPES["assistant"]["output"], lambda key: None)

    def test_assistant_changes_only_branch_own_route_and_segment_lengths(self):
        stock = bytes(synthetic_elf())
        result = recipes._assistant(stock)
        expected = bytearray(stock)
        route = bytes.fromhex(recipes.RECIPES["assistant"]["route_text_hex"])
        end = 0x44500 + len(route)
        struct.pack_into("<I", expected, 0x38ed4, 0x14000000 + (0x44500 - 0x38ed4) // 4)
        expected[0x44500:end] = route
        struct.pack_into("<QQ", expected, 96, end, end)
        self.assertEqual(result, bytes(expected))
        self.assertEqual(len(result), len(stock))
        self.assertEqual(stock, bytes(synthetic_elf()))

    def test_assistant_refuses_unexpected_instruction_padding_or_elf_segment(self):
        for offset, value in ((0x38ed4, 0xff), (0x44500, 1), (18, 0), (54, 0), (96, 0), (68, 0)):
            data = synthetic_elf()
            data[offset] = value
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                recipes._assistant(bytes(data))

    def test_weather_changes_exactly_one_sixteen_byte_slot_from_apk_member(self):
        recipe = deepcopy(recipes.RECIPES["weather"][0])
        before = bytes.fromhex(recipe["before_hex"])
        stock = b"unchanged prefix" + before + b"unchanged suffix"
        recipe.update(original_library_sha256=sha(stock), original_library_bytes=len(stock), offset=len(b"unchanged prefix"))
        result = recipes._weather(zipped([(recipe["member"], stock)]), recipe)
        self.assertEqual(result, b"unchanged prefix" + struct.pack("<IIII", 0x52800000, 0xd65f03c0, 0xd503201f, 0xd503201f) + b"unchanged suffix")
        self.assertEqual(len(result), len(stock))
        wrong_site = dict(recipe, offset=recipe["offset"] + 1)
        with self.assertRaisesRegex(ValueError, "patch site is not stock"):
            recipes._weather(zipped([(recipe["member"], stock)]), wrong_site)
        with self.assertRaisesRegex(ValueError, "Weather library identity mismatch"):
            recipes._weather(zipped([(recipe["member"], b"changed stock")]), recipe)

    def test_weather_missing_or_duplicate_member_is_rejected(self):
        recipe = recipes.RECIPES["weather"][0]
        for entries in ([], [(recipe["member"], b"a"), (recipe["member"], b"b")]):
            with self.subTest(entries=len(entries)), self.assertRaisesRegex(ValueError, "exactly one original library"):
                recipes._weather(zipped(entries), recipe)

    def test_external_tool_failure_does_not_echo_private_inputs(self):
        failed = subprocess.CompletedProcess([], 1, "private stdout sentinel", "private stderr sentinel")
        with patch.object(recipes.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(ValueError, "javac recipe tool failed") as caught:
                recipes._run(["javac", "synthetic-path"])
            self.assertNotIn("sentinel", str(caught.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
