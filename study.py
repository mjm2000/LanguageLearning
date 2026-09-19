#!/usr/bin/env python3
"""English → Latin vocabulary study with per-form declension/conjugation drills."""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(os.environ["LATIN_ROOT"]) if "LATIN_ROOT" in os.environ else Path(__file__).parent
DEFAULT_JSON = ROOT / "latin-core-1000.json"
PROGRESS_FILE = Path.cwd() / ".latin-study-progress.json"
PROGRESS_VERSION = 2

CASE_ORDER = ["Nom", "Gen", "Dat", "Acc", "Abl", "Voc"]
NUMBER_ORDER = ["Sing", "Plur"]
GENDER_ORDER = ["Masc", "Fem", "Neut", "Com"]
PERSON_ORDER = ["1", "2", "3"]

CASE_LABELS = {
    "Nom": "nominative",
    "Gen": "genitive",
    "Dat": "dative",
    "Acc": "accusative",
    "Abl": "ablative",
    "Voc": "vocative",
}
NUMBER_LABELS = {"Sing": "singular", "Plur": "plural"}
PERSON_LABELS = {"1": "1st person", "2": "2nd person", "3": "3rd person"}
TENSE_LABELS = {
    "Pres": "present",
    "Imp": "imperfect",
    "Fut": "future",
    "Perf": "perfect",
    "Plp": "pluperfect",
    "Past": "perfect",
    "Pqp": "pluperfect",
}
MOOD_LABELS = {
    "Ind": "indicative",
    "Sub": "subjunctive",
    "Imp": "imperative",
    "Inf": "infinitive",
}
VOICE_LABELS = {"Act": "active", "Pas": "passive"}
GENDER_LABELS = {
    "Masc": "masculine",
    "Fem": "feminine",
    "Neut": "neuter",
    "Com": "common",
}
VERB_FORM_LABELS = {
    "Inf": "infinitive",
    "Part": "participle",
    "Ger": "gerund",
    "Gdv": "gerundive",
    "Sup": "supine",
}


def strip_macrons(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def load_words(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)["words"]


def speech_latin(entry: dict) -> tuple[str, str]:
    raw = (entry.get("lemma") or entry["headword"]).split()[0]
    raw = re.sub(r"\([^)]*\)", "", raw).strip(" ,;")
    return strip_macrons(raw), raw


def speech_translation(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"→.*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    text = strip_macrons(text)
    text = re.sub(
        r"\b(?:interr|rel|indecl|abbrev|esp|coll|poet|transf|lit|fig|cf|pl|sing|"
        r"adj|adv|prep|conj|gen|dat|abl|acc|nom|m|f|n)\.\s*",
        "",
        text,
        flags=re.I,
    )
    for sep in (";", ":", "—", "→"):
        if sep in text:
            text = text.split(sep, 1)[0]
    if "?" in text:
        text = text.split("?", 1)[0]
    if "!" in text:
        text = text.split("!", 1)[0]
    text = re.split(r"\s*-\s*", text, maxsplit=1)[0]
    if "," in text:
        text = text.split(",", 1)[0]
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize(text: str) -> str:
    text = strip_macrons(text.strip().lower())
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"\s+", " ", text).strip(" ,;.")


def morph_class(entry: dict) -> str:
    label = entry.get("declension_or_conjugation")
    if label:
        return label
    pos = entry.get("part_of_speech") or ""
    if pos in {"Adverb", "Conjunction", "Preposition"} or pos.startswith("Adverb"):
        return "indeclinable"
    if ":" in pos:
        return pos.split(":", 1)[1].strip()
    return pos or "word"


def pos_category(entry: dict) -> str:
    pos = entry.get("part_of_speech") or ""
    return pos.split(":", 1)[0].strip()


def label_tmv(key: str) -> tuple[str, str, str]:
    tense, mood, voice = key.split("_", 2)
    return (
        TENSE_LABELS.get(tense, tense.lower()),
        MOOD_LABELS.get(mood, mood.lower()),
        VOICE_LABELS.get(voice, voice.lower()),
    )


@dataclass(frozen=True)
class FormDrill:
    rank: int
    lemma: str
    english: str
    latin_form: str
    form_key: str
    form_prompt: str
    morph_class: str
    part_of_speech: str

    def check(self, user_input: str) -> bool:
        return normalize(user_input) == normalize(self.latin_form)


def expand_noun_drills(entry: dict, *, english: str, lemma: str, morph: str) -> list[FormDrill]:
    paradigm = entry["paradigm"]
    drills: list[FormDrill] = []
    rank = entry["rank"]
    for number in NUMBER_ORDER:
        cases = paradigm.get(number)
        if not isinstance(cases, dict):
            continue
        number_label = NUMBER_LABELS[number]
        for case in CASE_ORDER:
            form = cases.get(case)
            if not form:
                continue
            case_label = CASE_LABELS[case]
            form_key = f"n:{rank}:{number}:{case}"
            form_prompt = f"{case_label} {number_label}"
            drills.append(
                FormDrill(
                    rank=rank,
                    lemma=lemma,
                    english=english,
                    latin_form=form,
                    form_key=form_key,
                    form_prompt=form_prompt,
                    morph_class=morph,
                    part_of_speech="Noun",
                )
            )
    return drills


def expand_adjective_drills(entry: dict, *, english: str, lemma: str, morph: str) -> list[FormDrill]:
    paradigm = entry["paradigm"]
    drills: list[FormDrill] = []
    rank = entry["rank"]
    for gender in GENDER_ORDER:
        numbers = paradigm.get(gender)
        if not isinstance(numbers, dict):
            continue
        gender_label = GENDER_LABELS[gender]
        for number in NUMBER_ORDER:
            cases = numbers.get(number)
            if not isinstance(cases, dict):
                continue
            number_label = NUMBER_LABELS[number]
            for case in CASE_ORDER:
                form = cases.get(case)
                if not form:
                    continue
                case_label = CASE_LABELS[case]
                form_key = f"a:{rank}:{gender}:{number}:{case}"
                form_prompt = f"{case_label} {number_label} {gender_label}"
                drills.append(
                    FormDrill(
                        rank=rank,
                        lemma=lemma,
                        english=english,
                        latin_form=form,
                        form_key=form_key,
                        form_prompt=form_prompt,
                        morph_class=morph,
                        part_of_speech=pos_category(entry),
                    )
                )
    return drills


def expand_verb_drills(entry: dict, *, english: str, lemma: str, morph: str) -> list[FormDrill]:
    paradigm = entry["paradigm"]
    drills: list[FormDrill] = []
    rank = entry["rank"]

    for tmv in sorted(paradigm.get("finite", {})):
        numbers = paradigm["finite"][tmv]
        if not isinstance(numbers, dict):
            continue
        tense_label, mood_label, voice_label = label_tmv(tmv)
        for number in NUMBER_ORDER:
            persons = numbers.get(number)
            if not isinstance(persons, dict):
                continue
            number_label = NUMBER_LABELS[number]
            for person in PERSON_ORDER:
                form = persons.get(person)
                if not form:
                    continue
                person_label = PERSON_LABELS[person]
                form_key = f"v:{rank}:{tmv}:{number}:{person}"
                form_prompt = (
                    f"{person_label} {number_label}, {tense_label} "
                    f"{mood_label} {voice_label}"
                )
                drills.append(
                    FormDrill(
                        rank=rank,
                        lemma=lemma,
                        english=english,
                        latin_form=form,
                        form_key=form_key,
                        form_prompt=form_prompt,
                        morph_class=morph,
                        part_of_speech="Verb",
                    )
                )

    for idx, nf in enumerate(paradigm.get("non_finite", [])):
        form = nf.get("form")
        if not form:
            continue
        verb_form = nf.get("verb_form") or "?"
        tense = TENSE_LABELS.get(nf.get("tense") or "", (nf.get("tense") or "").lower())
        voice = VOICE_LABELS.get(nf.get("voice") or "", (nf.get("voice") or "").lower())
        case = CASE_LABELS.get(nf.get("case") or "", "")
        gender = GENDER_LABELS.get(nf.get("gender") or "", "")
        number = NUMBER_LABELS.get(nf.get("number") or "", "")
        vf_label = VERB_FORM_LABELS.get(verb_form, verb_form.lower())

        parts = [vf_label]
        if tense:
            parts.append(tense)
        if voice:
            parts.append(voice)
        if case:
            parts.append(case)
        if gender:
            parts.append(gender)
        if number:
            parts.append(number)
        form_prompt = " ".join(parts)

        form_key = (
            f"vf:{rank}:{idx}:{verb_form}:{nf.get('tense')}:{nf.get('voice')}:"
            f"{nf.get('case')}:{nf.get('gender')}:{nf.get('number')}"
        )
        drills.append(
            FormDrill(
                rank=rank,
                lemma=lemma,
                english=english,
                latin_form=form,
                form_key=form_key,
                form_prompt=form_prompt,
                morph_class=morph,
                part_of_speech="Verb",
            )
        )

    return drills


def expand_indeclinable_drill(entry: dict, *, english: str, lemma: str, morph: str) -> list[FormDrill]:
    rank = entry["rank"]
    _, lemma_raw = speech_latin(entry)
    return [
        FormDrill(
            rank=rank,
            lemma=lemma,
            english=english,
            latin_form=lemma_raw,
            form_key=f"i:{rank}",
            form_prompt="dictionary form (indeclinable)",
            morph_class=morph,
            part_of_speech=pos_category(entry),
        )
    ]


def expand_drills(entry: dict) -> list[FormDrill]:
    lemma, _ = speech_latin(entry)
    english = speech_translation(entry["translation"])
    morph = morph_class(entry)
    paradigm = entry.get("paradigm")

    if not paradigm:
        return expand_indeclinable_drill(entry, english=english, lemma=lemma, morph=morph)

    if isinstance(paradigm, dict) and "finite" in paradigm:
        return expand_verb_drills(entry, english=english, lemma=lemma, morph=morph)

    if isinstance(paradigm, dict) and "Sing" in paradigm and isinstance(paradigm["Sing"], dict):
        if "Nom" in paradigm["Sing"]:
            return expand_noun_drills(entry, english=english, lemma=lemma, morph=morph)

    if isinstance(paradigm, dict):
        return expand_adjective_drills(entry, english=english, lemma=lemma, morph=morph)

    return expand_indeclinable_drill(entry, english=english, lemma=lemma, morph=morph)


def build_drill_index(words: list[dict]) -> tuple[list[FormDrill], dict[int, list[FormDrill]]]:
    all_drills: list[FormDrill] = []
    by_rank: dict[int, list[FormDrill]] = {}
    for entry in words:
        drills = expand_drills(entry)
        by_rank[entry["rank"]] = drills
        all_drills.extend(drills)
    return all_drills, by_rank


def load_progress(by_rank: dict[int, list[FormDrill]]) -> set[str]:
    if not PROGRESS_FILE.exists():
        return set()
    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()

    if data.get("version") == PROGRESS_VERSION and "mastered_forms" in data:
        return set(data["mastered_forms"])

    mastered: set[str] = set()
    for rank in data.get("mastered", []):
        for drill in by_rank.get(int(rank), []):
            mastered.add(drill.form_key)
    return mastered


def save_progress(mastered: set[str], *, total_forms: int) -> None:
    payload = {
        "version": PROGRESS_VERSION,
        "mastered_forms": sorted(mastered),
        "mastered_count": len(mastered),
        "total_forms": total_forms,
    }
    PROGRESS_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def filter_words(
    words: list[dict],
    *,
    start_rank: int | None,
    end_rank: int | None,
) -> list[dict]:
    selected = words
    if start_rank is not None:
        selected = [w for w in selected if w["rank"] >= start_rank]
    if end_rank is not None:
        selected = [w for w in selected if w["rank"] <= end_rank]
    return selected


def select_study_drills(
    drills: list[FormDrill],
    mastered: set[str],
    *,
    shuffle: bool,
    include_mastered: bool,
) -> list[FormDrill]:
    if include_mastered:
        pool = drills
    else:
        pool = [d for d in drills if d.form_key not in mastered]
    if shuffle:
        pool = pool.copy()
        random.shuffle(pool)
    else:
        pool = sorted(pool, key=lambda d: (d.rank, d.form_key))
    return pool


def prompt_line() -> str | None:
    try:
        return input("Latin: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None


def print_drill(drill: FormDrill, *, remaining: int, total: int) -> None:
    print()
    print(f"[{remaining}/{total}]  #{drill.rank}  {drill.lemma}  ({drill.part_of_speech})")
    print(f"English: {drill.english}")
    print(f"Give: {drill.form_prompt}")
    print(f"Class: {drill.morph_class}")


def reveal_drill(drill: FormDrill) -> None:
    print(f"Answer: {drill.latin_form}")


def run_session(
    drills: list[FormDrill],
    mastered: set[str],
    *,
    total_forms: int,
) -> set[str]:
    queue = drills.copy()
    retry: list[FormDrill] = []
    total = len(queue)

    while queue or retry:
        if queue:
            drill = queue.pop(0)
        else:
            print("\n--- Review missed forms ---")
            queue = retry
            retry = []
            total = len(queue)
            if not queue:
                break
            drill = queue.pop(0)

        remaining = len(queue) + len(retry) + 1
        print_drill(drill, remaining=remaining, total=total)

        while True:
            answer = prompt_line()
            if answer is None:
                save_progress(mastered, total_forms=total_forms)
                print("\nProgress saved.")
                raise SystemExit(0)

            lowered = answer.lower()
            if lowered in {"q", "quit", "exit"}:
                save_progress(mastered, total_forms=total_forms)
                print("\nProgress saved.")
                return mastered
            if lowered in {"?", "hint"}:
                reveal_drill(drill)
                continue
            if lowered in {"s", "skip"}:
                retry.append(drill)
                print("Skipped — will show again later.")
                break

            if drill.check(answer):
                if drill.form_key not in mastered:
                    mastered.add(drill.form_key)
                    save_progress(mastered, total_forms=total_forms)
                    print(f"✓ Correct — {drill.latin_form}")
                    print(f"  Saved ({len(mastered)}/{total_forms} forms mastered).")
                else:
                    print(f"✓ Correct — {drill.latin_form}")
                break

            print(f"✗ Not quite. Expected: {drill.latin_form}")
            retry.append(drill)
            break

    return mastered


def word_completion_stats(
    scoped_words: list[dict],
    by_rank: dict[int, list[FormDrill]],
    mastered: set[str],
) -> tuple[int, int]:
    complete = 0
    for entry in scoped_words:
        drills = by_rank.get(entry["rank"], [])
        if drills and all(d.form_key in mastered for d in drills):
            complete += 1
    return complete, len(scoped_words)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Study Latin vocabulary: English prompt plus a specific "
            "declension or conjugation form to produce."
        ),
        epilog=(
            "During a session:\n"
            "  type the Latin form and press Enter\n"
            "  ?       reveal the answer (form stays in rotation)\n"
            "  skip    try again later this session\n"
            "  quit    save and exit\n"
            "\n"
            "Progress is saved per form in .latin-study-progress.json.\n"
            "Mastered forms are skipped on the next run.\n"
            "\n"
            "Examples:\n"
            "  nix run .#study\n"
            "  nix run .#study -- --shuffle\n"
            "  nix run .#study -- --reset"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--from-rank", type=int)
    parser.add_argument("--to-rank", type=int)
    parser.add_argument("--shuffle", action="store_true", help="Randomize drill order")
    parser.add_argument("--reset", action="store_true", help="Clear saved progress")
    parser.add_argument(
        "--review-mastered",
        action="store_true",
        help="Include already mastered forms in this session",
    )
    parser.add_argument("--stats", action="store_true", help="Show progress summary and exit")
    args = parser.parse_args()

    if not args.file.exists():
        sys.exit(f"Vocabulary file not found: {args.file}")

    all_words = load_words(args.file)
    scoped = filter_words(all_words, start_rank=args.from_rank, end_rank=args.to_rank)
    _, by_rank = build_drill_index(all_words)
    scoped_drills = [d for entry in scoped for d in by_rank.get(entry["rank"], [])]
    total_forms = len(scoped_drills)

    if args.reset:
        mastered: set[str] = set()
        save_progress(mastered, total_forms=total_forms)
        print("Progress reset.")
    else:
        mastered = load_progress(by_rank)

    if args.stats:
        remaining = [d for d in scoped_drills if d.form_key not in mastered]
        words_done, word_total = word_completion_stats(scoped, by_rank, mastered)
        print(f"Forms mastered: {len(mastered)}/{total_forms}")
        print(f"Forms remaining: {len(remaining)}")
        print(f"Words fully mastered: {words_done}/{word_total}")
        return

    study_drills = select_study_drills(
        scoped_drills,
        mastered,
        shuffle=args.shuffle,
        include_mastered=args.review_mastered,
    )

    words_done, word_total = word_completion_stats(scoped, by_rank, mastered)
    print(
        f"Latin study — {len(study_drills)} form(s) this session "
        f"({len(mastered)}/{total_forms} forms mastered, "
        f"{words_done}/{word_total} words complete)"
    )
    if not args.review_mastered and mastered:
        print("Mastered forms are skipped. Use --review-mastered to include them.")

    if not study_drills:
        print("\nNothing left to study in this range. Use --reset to start over.")
        return

    print("Commands: ? (reveal)  skip  quit")
    try:
        run_session(study_drills, mastered, total_forms=total_forms)
    except KeyboardInterrupt:
        save_progress(mastered, total_forms=total_forms)
        print("\nProgress saved.")

    remaining = len([d for d in scoped_drills if d.form_key not in mastered])
    if remaining:
        print(f"\n{remaining} form(s) left. Run again to continue.")
    else:
        print("\nAll forms in range mastered.")


if __name__ == "__main__":
    main()
