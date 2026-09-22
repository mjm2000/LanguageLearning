#!/usr/bin/env python3
"""Build the 1000 most common Latin words dataset with declensions and translations."""

from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from pathlib import Path

from latincy_lexicon.generator import Generator

ROOT = Path(os.environ["LATIN_ROOT"]) if "LATIN_ROOT" in os.environ else Path(__file__).parent
CSV_PATH = ROOT / "dcc-core-vocabulary.csv"
ANALYZER_PATH = ROOT / "data" / "json" / "analyzer.json"
OUTPUT_JSON = ROOT / "latin-core-1000.json"
OUTPUT_CSV = ROOT / "latin-core-1000.csv"

CASE_ORDER = ["Nom", "Gen", "Dat", "Acc", "Abl", "Voc"]
NUMBER_ORDER = ["Sing", "Plur"]

VERB_TENSE_ORDER = [
    ("Pres", "Ind", "Act"),
    ("Imp", "Ind", "Act"),
    ("Fut", "Ind", "Act"),
    ("Perf", "Ind", "Act"),
    ("Plp", "Ind", "Act"),
    ("Pres", "Sub", "Act"),
    ("Imp", "Sub", "Act"),
    ("Perf", "Sub", "Act"),
    ("Plp", "Sub", "Act"),
    ("Pres", "Imp", "Act"),
    ("Fut", "Imp", "Act"),
    ("Pres", "Inf", "Act"),
    ("Pres", "Ind", "Pas"),
    ("Imp", "Ind", "Pas"),
    ("Fut", "Ind", "Pas"),
    ("Perf", "Ind", "Pas"),
    ("Plp", "Ind", "Pas"),
    ("Pres", "Sub", "Pas"),
    ("Imp", "Sub", "Pas"),
    ("Perf", "Sub", "Pas"),
    ("Plp", "Sub", "Pas"),
    ("Pres", "Imp", "Pas"),
    ("Fut", "Imp", "Pas"),
    ("Pres", "Inf", "Pas"),
]

POS_MAP = {
    "Noun: 1st Declension": "N",
    "Noun: 2nd Declension": "N",
    "Noun: 3rd Declension": "N",
    "Noun: 4th Declension": "N",
    "Noun: 5th Declension": "N",
    "Noun: Indeclinable": None,
    "Verb: 1st Conjugation": "V",
    "Verb: 2nd Conjugation": "V",
    "Verb: 3rd Conjugation -iō": "V",
    "Verb: 3rd Conjugation -ō": "V",
    "Verb: 4th Conjugation": "V",
    "Verb: Irregular": "V",
    "Verb: Deponent": "V",
    "Verb: Impersonal": "V",
    "Adjective: 1st and 2nd Declension": "ADJ",
    "Adjective: 3rd Declension": "ADJ",
    "Adjective: Indeclinable": None,
    "Adjective: Numeral": "NUM",
    "Pronoun": "PRON",
    "Adverb": None,
    "Preposition": None,
    "Conjunction": None,
}


def strip_macrons(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def parse_lemma(headword: str, part_of_speech: str) -> str | None:
    """Extract dictionary lemma from a DCC headword string."""
    hw = headword.strip()
    if not hw:
        return None

    # Remove parenthetical notes like (adv.) or (pl.)
    hw = re.sub(r"\([^)]*\)", "", hw).strip()

    # Adjective pattern: magnus-a-um, adversus -a -um, or acer acris acre
    if part_of_speech.startswith("Adjective"):
        if re.search(r"\s-[a-zāēīōū]", hw, re.I):
            return hw.split()[0]
        if re.search(r"-[a-zāēīōū]+-[a-zāēīōū]+", hw, re.I):
            return hw.split("-")[0].strip()
        parts = hw.split()
        if len(parts) >= 3 and not parts[1].endswith("."):
            return parts[0]
        return parts[0]

    # Verb: first principal part
    if part_of_speech.startswith("Verb"):
        return hw.split()[0]

    # Noun with hyphen genitive ending: terra-ae f.
    m = re.match(r"^([^\s-]+)(?:\s|-)", hw)
    if m and part_of_speech.startswith("Noun"):
        first = m.group(1)
        parts = hw.split()
        if len(parts) >= 2 and re.match(r"^[a-zāēīōū]+(?:is|us|eris|oris|is)?$", parts[1], re.I):
            # rēx rēgis, corpus corporis
            if not parts[1].endswith("."):
                return first
        return first

    # Pronoun: first form (hic, quī, etc.)
    if part_of_speech == "Pronoun":
        return hw.split()[0]

    # Preposition / conjunction with variants: ā ab abs
    if part_of_speech in {"Preposition", "Conjunction", "Adverb"}:
        return hw.split()[0]

    return hw.split()[0]


def parse_feats(feats: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not feats:
        return result
    for part in feats.split("|"):
        if "=" in part:
            key, value = part.split("=", 1)
            result[key] = value
    return result


def format_noun_paradigm(forms) -> dict:
    table: dict[str, dict[str, str | None]] = {
        number: {case: None for case in CASE_ORDER} for number in NUMBER_ORDER
    }
    for form in forms:
        feats = parse_feats(form.feats)
        case = feats.get("Case")
        number = feats.get("Number")
        if case in CASE_ORDER and number in NUMBER_ORDER and table[number][case] is None:
            table[number][case] = form.form
    return table


def format_adjective_paradigm(forms) -> dict:
    by_gender: dict[str, dict] = {}
    for form in forms:
        feats = parse_feats(form.feats)
        gender = feats.get("Gender", "Masc")
        by_gender.setdefault(gender, []).append(form)

    result = {}
    for gender, gender_forms in by_gender.items():
        result[gender] = format_noun_paradigm(gender_forms)
    return result


def format_verb_paradigm(forms) -> dict:
    finite: dict[str, dict[str, dict[str, str | None]]] = {}
    non_finite: list[dict] = []

    for form in forms:
        feats = parse_feats(form.feats)
        verb_form = feats.get("VerbForm")
        if verb_form == "Fin":
            mood = feats.get("Mood", "?")
            tense = feats.get("Tense", "?")
            voice = feats.get("Voice", "Act")
            number = feats.get("Number", "?")
            person = feats.get("Person", "?")
            key = f"{tense}_{mood}_{voice}"
            finite.setdefault(key, {}).setdefault(number, {})[person] = form.form
        elif verb_form in {"Inf", "Part", "Ger", "Gdv", "Sup", "Fin"} or verb_form:
            non_finite.append(
                {
                    "form": form.form,
                    "verb_form": verb_form,
                    "tense": feats.get("Tense"),
                    "voice": feats.get("Voice"),
                    "case": feats.get("Case"),
                    "gender": feats.get("Gender"),
                    "number": feats.get("Number"),
                    "mood": feats.get("Mood"),
                }
            )

    return {"finite": finite, "non_finite": non_finite}


def _generate_forms(gen: Generator, lemma: str, pos_filter: str | None):
    candidates = [lemma]
    stripped = strip_macrons(lemma)
    if stripped != lemma:
        candidates.append(stripped)

    pos_filters: list[str | None] = [pos_filter]
    if pos_filter == "PRON":
        pos_filters.extend([None])
    elif pos_filter == "ADJ":
        pos_filters.append(None)

    seen: set[tuple[str, str, str, str]] = set()
    collected = []

    for cand in candidates:
        for pos in pos_filters:
            try:
                forms = gen.generate(cand, pos=pos, sort="paradigm") if pos else gen.generate(
                    cand, sort="paradigm"
                )
            except TypeError:
                forms = gen.generate(cand, pos=pos) if pos else gen.generate(cand)
            for form in forms:
                key = (form.form, form.lemma, form.upos, form.feats)
                if key not in seen:
                    seen.add(key)
                    collected.append(form)
            if collected:
                return collected
    return collected


def patch_known_paradigm_errors(entry: dict) -> None:
    """Fix conflated analyzer forms (quī mixed with unusquisque)."""
    if entry.get("rank") != 3 or entry.get("lemma") != "quī":
        return
    paradigm = entry.get("paradigm")
    if not isinstance(paradigm, dict):
        return
    masc = paradigm.get("Masc")
    if not isinstance(masc, dict):
        return
    sing = masc.get("Sing")
    if not isinstance(sing, dict):
        return
    if sing.get("Gen") == "uniuscuiusque":
        sing["Gen"] = "cuius"
    if sing.get("Dat") == "unicuique":
        sing["Dat"] = "cui"


def compact_forms(forms) -> list[dict]:
    return [
        {
            "form": f.form,
            "pos": f.upos,
            "features": parse_feats(f.feats),
        }
        for f in forms
    ]


def main() -> None:
    gen = Generator.from_json(str(ANALYZER_PATH))

    entries: list[dict] = []
    missing_paradigms: list[str] = []

    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            headword = row["Headword"]
            definition = row["Definition"]
            pos_label = row["Part of Speech"]
            semantic_group = row["Semantic Group"]
            rank = int(row["Frequency Rank"])

            lemma = parse_lemma(headword, pos_label)
            pos_filter = POS_MAP.get(pos_label)

            entry = {
                "rank": rank,
                "headword": headword,
                "lemma": lemma,
                "translation": definition,
                "part_of_speech": pos_label,
                "semantic_group": semantic_group,
                "declension_or_conjugation": None,
                "principal_parts": None,
                "paradigm": None,
                "forms": None,
            }

            if pos_filter and lemma:
                forms = _generate_forms(gen, lemma, pos_filter)

                if forms:
                    entry["forms"] = compact_forms(forms)
                    if pos_filter == "N":
                        entry["paradigm"] = format_noun_paradigm(forms)
                        entry["declension_or_conjugation"] = pos_label.replace("Noun: ", "")
                    elif pos_filter in {"ADJ", "NUM"}:
                        entry["paradigm"] = format_adjective_paradigm(forms)
                        entry["declension_or_conjugation"] = pos_label.replace("Adjective: ", "")
                    elif pos_filter == "V":
                        entry["paradigm"] = format_verb_paradigm(forms)
                        entry["declension_or_conjugation"] = pos_label.replace("Verb: ", "")
                        entry["principal_parts"] = headword.split(";")[0].strip()
                    elif pos_filter == "PRON":
                        entry["paradigm"] = format_adjective_paradigm(forms)
                        entry["declension_or_conjugation"] = "Pronoun"
                else:
                    missing_paradigms.append(f"{rank}: {headword} ({lemma})")
            elif pos_label.startswith("Verb"):
                entry["principal_parts"] = headword.split(";")[0].strip()
                entry["declension_or_conjugation"] = pos_label.replace("Verb: ", "")

            patch_known_paradigm_errors(entry)
            entries.append(entry)

    entries.sort(key=lambda e: e["rank"])

    output = {
        "source": "Dickinson College Commentaries Latin Core Vocabulary",
        "source_url": "https://dcc.dickinson.edu/latin-core-list1",
        "license": "CC BY-SA 3.0",
        "morphology_source": "Whitaker's Words via latincy-lexicon",
        "word_count": len(entries),
        "words": entries,
        "missing_paradigms": missing_paradigms,
    }

    OUTPUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "headword",
                "lemma",
                "translation",
                "part_of_speech",
                "declension_or_conjugation",
                "semantic_group",
                "form_count",
            ]
        )
        for entry in entries:
            form_count = len(entry["forms"]) if entry["forms"] else 0
            writer.writerow(
                [
                    entry["rank"],
                    entry["headword"],
                    entry["lemma"],
                    entry["translation"],
                    entry["part_of_speech"],
                    entry["declension_or_conjugation"] or "",
                    entry["semantic_group"],
                    form_count,
                ]
            )

    with_paradigm = sum(1 for e in entries if e["forms"])
    print(f"Processed {len(entries)} words")
    print(f"Generated paradigms for {with_paradigm} words")
    print(f"Missing paradigms: {len(missing_paradigms)}")
    if missing_paradigms[:10]:
        print("First missing:")
        for item in missing_paradigms[:10]:
            print(f"  - {item}")
    print(f"Wrote {OUTPUT_JSON}")
    print(f"Wrote {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
