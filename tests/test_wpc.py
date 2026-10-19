"""wpc.py 的测试矩阵，对应 DESIGN.md。"""

import json
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import wpc  # noqa: E402


def cells(text, lang="mixed", **opts):
    got, _ = wpc.count_cells(text, lang, **opts)
    return got


def n(text, lang="mixed", **opts):
    return len(cells(text, lang, **opts))


# ---------------------------------------------------------------- 切格


class TestZh(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(n("春风又绿江南岸", "zh"), 7)

    def test_punct_ignored(self):
        self.assertEqual(n("春风，又绿！", "zh"), 4)
        self.assertEqual(n("春风，又绿！", "zh", punct="ignore"), 4)
        self.assertEqual(n("春风，又绿！", "zh", punct="count"), 6)

    def test_digits(self):
        self.assertEqual(n("2026", "zh", digits="each"), 4)
        self.assertEqual(n("2026", "zh", digits="word"), 1)

    def test_iteration_mark(self):
        self.assertEqual(n("々", "zh"), 1)

    def test_spaces_fold(self):
        self.assertEqual(n("中 英 混 排", "zh"), 4)
        self.assertEqual(n("中\u3000英", "zh"), 2)

    def test_fullwidth_space(self):
        self.assertEqual(n("春\u3000风", "zh"), 2)


class TestJa(unittest.TestCase):
    def test_youon_merges(self):
        self.assertEqual(n("きゃ", "ja"), 1)
        self.assertEqual(n("きよう", "ja"), 3)
        self.assertEqual(n("きゃきゃ", "ja"), 2)
        self.assertEqual(cells("きゃ", "ja"), ["きゃ"])

    def test_basic(self):
        self.assertEqual(n("さくら", "ja"), 3)

    def test_sokuon_hatsuon_chouon(self):
        self.assertEqual(n("がっこう", "ja"), 4)
        self.assertEqual(n("コーヒー", "ja"), 4)
        self.assertEqual(n("ん", "ja"), 1)
        self.assertEqual(n("ー", "ja"), 1)

    def test_halfwidth_kana(self):
        self.assertEqual(n("ｷｬ", "ja"), 1)
        self.assertEqual(n("ｺｰﾋｰ", "ja"), 4)

    def test_ivs_ignored(self):
        self.assertEqual(n("葛\U000E0100", "ja"), 1)
        self.assertEqual(n("葛\uFE00", "ja"), 1)

    def test_kanji_in_ja(self):
        self.assertEqual(n("東京", "ja"), 2)

    def test_nfc_nfd_equal(self):
        text = "がっこう"
        self.assertEqual(n(text, "ja"), n(unicodedata.normalize("NFD", text), "ja"))


class TestKo(unittest.TestCase):
    def test_syllables(self):
        self.assertEqual(n("사랑해", "ko"), 3)

    def test_nfc_nfd_equal(self):
        text = "사랑해"
        self.assertEqual(n(text, "ko"), n(unicodedata.normalize("NFD", text), "ko"))
        self.assertEqual(cells(unicodedata.normalize("NFD", text), "ko"), list(text))

    def test_isolated_jamo(self):
        got, warns = wpc.count_cells("ㄱ", "ko")
        self.assertEqual(len(got), 1)
        self.assertEqual([w["kind"] for w in warns], ["unclassified"])


class TestEn(unittest.TestCase):
    def test_letter_mode(self):
        self.assertEqual(n("don't", "en", latin="letter"), 4)
        self.assertEqual(n("well-known", "en", latin="letter"), 9)

    def test_word_mode(self):
        self.assertEqual(n("Hold me tight", "en", latin="word"), 3)
        self.assertEqual(n("well-known", "en", latin="word"), 2)

    def test_syllable_mode(self):
        cases = {
            "Hold me tight": 3,
            "Spi-der-Man": 3,
            "well-known": 2,
            "the": 1,
            "little": 2,
            "make": 1,
            "walked": 1,
            "wanted": 2,
            "boxes": 2,
            "every": 2,
            "people": 2,
            "beautiful": 3,
            "science": 2,
            "shop": 1,
            "wishes": 2,
        }
        for text, want in cases.items():
            with self.subTest(text=text):
                self.assertEqual(n(text, "en", latin="syllable"), want)

    def test_syllable_cells_align_with_count(self):
        for text in ("Spi-der-Man", "beautiful", "little", "walked"):
            with self.subTest(text=text):
                self.assertEqual(len(cells(text, "en")), n(text, "en"))

    def test_syllables_helper(self):
        self.assertEqual(wpc.syllables("beautiful"), 3)
        self.assertEqual(wpc.syllables("Spi-der-Man"), 3)


class TestMixed(unittest.TestCase):
    def test_cn_en(self):
        self.assertEqual(n("Baby 别走", "mixed"), 4)

    def test_en_cn(self):
        self.assertEqual(n("I love 東京", "mixed"), 4)

    def test_emoji_unclassified(self):
        got, warns = wpc.count_cells("春🎵", "mixed")
        self.assertEqual(len(got), 2)
        self.assertEqual(warns[0]["kind"], "unclassified")

    def test_zero_width_dropped(self):
        got, warns = wpc.count_cells("春\u200b风\ufeff", "mixed")
        self.assertEqual(len(got), 2)
        self.assertEqual(warns, [])


class TestHardAssertions(unittest.TestCase):
    """DESIGN.md 的硬断言清单。"""

    def test_1_nfc_nfd_same_count(self):
        for text, lang in (("春风又绿", "zh"), ("がっこう", "ja"), ("사랑해", "ko")):
            with self.subTest(lang=lang):
                self.assertEqual(
                    n(text, lang),
                    n(unicodedata.normalize("NFD", text), lang),
                )

    def test_2_youon(self):
        self.assertEqual(n("きゃ", "ja"), 1)
        self.assertEqual(n("きよう", "ja"), 3)

    def test_3_spiderman(self):
        self.assertEqual(n("Spi-der-Man", "en", latin="syllable"), 3)

    def test_4_punct_never_changes_count(self):
        base = n("春风又绿", "zh")
        self.assertEqual(n("春风，又绿。", "zh"), base)
        self.assertEqual(n("春\u3000风\u3001又\u3000绿", "zh"), base)


# ---------------------------------------------------------------- 结构


SPEC = """# 测试用词格
lang: mixed
latin: syllable
punct: ignore
digits: each

## s1
1 | 2/2 | zh
2 | 2/1 | en

## s2
1 | 3 | ko
"""


def make_draft(body, spec_text=SPEC, sha=None):
    sha = sha or wpc.sha256_text(spec_text)
    return f"# spec: spec.txt sha256={sha}\n\n{body}"


GOOD_BODY = """## v1 2026-10-19 10:20
[s1]
1 | 春风 | 又绿
2 | Hold me | tight
[s2]
1 | 사랑해
"""


class TestStructure(unittest.TestCase):
    def test_pass(self):
        r = wpc.check(SPEC, make_draft(GOOD_BODY))
        self.assertTrue(r.ok, r.violations)
        self.assertEqual(r.version, "v1")
        self.assertEqual(r.summary, {"lines_checked": 3, "lines_ok": 3, "violations": 0})

    def test_too_many(self):
        body = GOOD_BODY.replace("1 | 春风 | 又绿", "1 | 春风 | 又绿江南")
        r = wpc.check(SPEC, make_draft(body))
        self.assertFalse(r.ok)
        kinds = [(v["kind"], v["segment"], v["expected"], v["actual"]) for v in r.violations]
        self.assertEqual(kinds, [("too_many", 2, 2, 4)])

    def test_too_few_missing_line(self):
        body = GOOD_BODY.replace("2 | Hold me | tight\n", "")
        r = wpc.check(SPEC, make_draft(body))
        self.assertFalse(r.ok)
        self.assertEqual(r.violations[0]["kind"], "too_few")
        self.assertIsNone(r.violations[0]["segment"])

    def test_seg_count_mismatch(self):
        body = GOOD_BODY.replace("1 | 春风 | 又绿", "1 | 春风又绿")
        r = wpc.check(SPEC, make_draft(body))
        self.assertEqual(r.violations[0]["kind"], "seg_count_mismatch")
        self.assertEqual((r.violations[0]["expected"], r.violations[0]["actual"]), (2, 1))

    def test_cells_present(self):
        body = GOOD_BODY.replace("1 | 春风 | 又绿", "1 | 春风 | 又绿江南")
        r = wpc.check(SPEC, make_draft(body))
        self.assertEqual(r.violations[0]["cells"], ["又", "绿", "江", "南"])

    def test_drift(self):
        draft = make_draft(GOOD_BODY, sha="0" * 64)
        r = wpc.check(SPEC, draft)
        self.assertEqual(r.error, "spec_drift")
        self.assertFalse(r.ok)
        self.assertTrue(r.spec["drift"])

    def test_default_version_is_last(self):
        body = GOOD_BODY + """
## v2 2026-10-19 10:40
[s1]
1 | 春风 | 又绿
2 | Hold me | tight
[s2]
1 | 사랑해
"""
        self.assertEqual(wpc.check(SPEC, make_draft(body)).version, "v2")
        self.assertEqual(wpc.check(SPEC, make_draft(body), "v1").version, "v1")

    def test_unknown_version(self):
        with self.assertRaises(wpc.WpcError):
            wpc.check(SPEC, make_draft(GOOD_BODY), "v9")

    def test_line_not_in_spec(self):
        body = GOOD_BODY.replace("[s1]\n1 | 春风 | 又绿", "[s1]\n9 | 春风 | 又绿")
        with self.assertRaises(wpc.WpcError):
            wpc.check(SPEC, make_draft(body))

    def test_missing_section(self):
        body = GOOD_BODY.replace("[s2]\n1 | 사랑해\n", "")
        with self.assertRaises(wpc.WpcError):
            wpc.check(SPEC, make_draft(body))

    def test_extra_section(self):
        body = GOOD_BODY + "[s9]\n1 | x\n"
        with self.assertRaises(wpc.WpcError):
            wpc.check(SPEC, make_draft(body))

    def test_bad_draft_header(self):
        with self.assertRaises(wpc.WpcError):
            wpc.parse_draft("## v1\n[s1]\n1 | a\n")

    def test_bad_spec_line(self):
        with self.assertRaises(wpc.WpcError):
            wpc.parse_spec("## s1\n1 5/7\n")

    def test_unknown_lang(self):
        with self.assertRaises(wpc.WpcError):
            wpc.count_cells("x", "fr")

    def test_lang_default_from_global(self):
        spec = "lang: zh\n## s1\n1 | 2\n"
        self.assertEqual(wpc.parse_spec(spec).sections[0].lines[0].lang, "zh")

    def test_zero_cell_segment_passes(self):
        spec = "## s1\n1 | 2/0 | zh\n"
        body = "## v1\n[s1]\n1 | 春风 |\n"
        r = wpc.check(spec, make_draft(body, spec_text=spec))
        self.assertTrue(r.ok, r.violations)

    def test_mixed_punct_separator(self):
        body = GOOD_BODY.replace("1 | 春风 | 又绿", "1 | 春风｜又绿")
        self.assertTrue(wpc.check(SPEC, make_draft(body)).ok)


# ---------------------------------------------------------------- CLI


class TestCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.spec_path = os.path.join(self.tmp.name, "spec.txt")
        self.draft_path = os.path.join(self.tmp.name, "draft.txt")
        with open(self.spec_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(SPEC)

    def write_draft(self, body, sha=None):
        with open(self.draft_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(make_draft(body, sha=sha))

    def run_cli(self, *args):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "wpc.py")] + list(args),
            capture_output=True, text=True, encoding="utf-8",
        )
        return proc

    def test_exit_0(self):
        self.write_draft(GOOD_BODY)
        p = self.run_cli("check", "--spec", self.spec_path, "--draft", self.draft_path)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_exit_1_and_json(self):
        self.write_draft(GOOD_BODY.replace("1 | 春风 | 又绿", "1 | 春风 | 又绿江南"))
        p = self.run_cli("check", "--spec", self.spec_path, "--draft", self.draft_path, "--json")
        self.assertEqual(p.returncode, 1)
        payload = json.loads(p.stdout)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["violations"][0]["kind"], "too_many")
        self.assertEqual(payload["summary"]["violations"], 1)

    def test_exit_2_on_bad_spec(self):
        with open(self.spec_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("## s1\n坏行\n")
        self.write_draft(GOOD_BODY)
        p = self.run_cli("check", "--spec", self.spec_path, "--draft", self.draft_path)
        self.assertEqual(p.returncode, 2)
        self.assertIn("第", p.stderr)

    def test_exit_3_on_drift(self):
        self.write_draft(GOOD_BODY, sha="0" * 64)
        p = self.run_cli("check", "--spec", self.spec_path, "--draft", self.draft_path, "--json")
        self.assertEqual(p.returncode, 3)
        self.assertEqual(json.loads(p.stdout)["error"], "spec_drift")

    def test_hash_matches_check(self):
        p = self.run_cli("hash", "--spec", self.spec_path)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), wpc.sha256_text(SPEC))

    def test_list(self):
        body = GOOD_BODY + "\n## v2\n[s1]\n1 | 春风 | 又绿\n2 | Hold me | tight\n[s2]\n1 | 사랑해\n"
        self.write_draft(body)
        p = self.run_cli("list", "--draft", self.draft_path)
        self.assertEqual(p.stdout.split(), ["v1", "v2"])

    def test_version_all(self):
        bad_v1 = GOOD_BODY
        good_v2 = GOOD_BODY.replace("## v1", "## v2")
        self.write_draft(bad_v1 + "\n" + good_v2)
        p = self.run_cli("check", "--spec", self.spec_path, "--draft", self.draft_path,
                         "--version", "all", "--json")
        payload = json.loads(p.stdout)
        self.assertEqual([v["version"] for v in payload["versions"]], ["v1", "v2"])

    def test_explain(self):
        self.write_draft(GOOD_BODY)
        p = self.run_cli("check", "--spec", self.spec_path, "--draft", self.draft_path, "--explain")
        self.assertIn("seg1", p.stdout)
        self.assertIn("春·风", p.stdout)


class TestOptions(unittest.TestCase):
    def test_strict_upgrades_unclassified(self):
        spec = "## s1\n1 | 1 | zh\n"
        body = "## v1\n[s1]\n1 | 🎵\n"
        draft = make_draft(body, spec_text=spec)
        lenient = wpc.check(spec, draft)
        self.assertTrue(lenient.ok, lenient.violations)
        self.assertEqual(lenient.warnings[0]["kind"], "unclassified")
        strict = wpc.check(spec, draft, strict=True)
        self.assertFalse(strict.ok)
        self.assertEqual(strict.violations[0]["kind"], "unclassified")

    def test_digits_word_in_mixed(self):
        spec = "digits: word\n## s1\n1 | 2\n"
        body = "## v1\n[s1]\n1 | 2026年\n"
        self.assertTrue(wpc.check(spec, make_draft(body, spec_text=spec)).ok)

    def test_latin_word_mode(self):
        spec = "latin: word\n## s1\n1 | 3\n"
        body = "## v1\n[s1]\n1 | Hold me tight\n"
        self.assertTrue(wpc.check(spec, make_draft(body, spec_text=spec)).ok)

    def test_latin_letter_mode(self):
        spec = "latin: letter\n## s1\n1 | 4\n"
        body = "## v1\n[s1]\n1 | don't\n"
        self.assertTrue(wpc.check(spec, make_draft(body, spec_text=spec)).ok)


class TestExamples(unittest.TestCase):
    """examples/ 下的真实中英日韩混排歌词（M4 验收）。"""

    spec_path = os.path.join(ROOT, "examples", "spec.txt")
    draft_path = os.path.join(ROOT, "examples", "draft.txt")

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_default_version_passes(self):
        r = wpc.check(self.read(self.spec_path), self.read(self.draft_path))
        self.assertTrue(r.ok, r.violations)
        self.assertEqual(r.version, "v2")

    def test_v1_has_one_violation(self):
        r = wpc.check(self.read(self.spec_path), self.read(self.draft_path), "v1")
        self.assertFalse(r.ok)
        self.assertEqual(len(r.violations), 1)
        self.assertEqual(r.violations[0]["kind"], "too_many")


class TestCliFiles(unittest.TestCase):
    """BOM / CRLF 也要保证 hash 与 check 走同一套归一规则。"""

    def test_bom_crlf_hash_matches(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        spec_path = os.path.join(tmp.name, "spec.txt")
        draft_path = os.path.join(tmp.name, "draft.txt")
        with open(spec_path, "wb") as f:
            f.write(b"\xef\xbb\xbf## s1\r\n1 | 2 | zh\r\n")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "wpc.py"), "hash", "--spec", spec_path],
            capture_output=True, text=True, encoding="utf-8",
        )
        sha = proc.stdout.strip()
        self.assertEqual(len(sha), 64)
        with open(draft_path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(f"# spec: spec.txt sha256={sha}\r\n\r\n## v1\r\n[s1]\r\n1 | 春风\r\n")
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "wpc.py"), "check",
             "--spec", spec_path, "--draft", draft_path],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
