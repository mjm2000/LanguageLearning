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

from study_sentences import english_context, latin_context

ROOT = Path(os.environ["LATIN_ROOT"]) if "LATIN_ROOT" in os.environ else Path(__file__).parent
DEFAULT_JSON = ROOT / "latin-core-1000.json"
def progress_path() -> Path:
    env = os.environ.get("LATIN_PROGRESS_FILE")
    if env:
        return Path(env)
    return Path.cwd() / ".latin-study-progress.json"
PROGRESS_VERSION = 2
DEFAULT_FROM_RANK = 1
DEFAULT_TO_RANK = 10

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


def _clean_definition(text: str) -> str:
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
    return text


def _trim_gloss_piece(piece: str) -> str:
    piece = piece.strip()
    if "?" in piece:
        piece = piece.split("?", 1)[0]
    if "!" in piece:
        piece = piece.split("!", 1)[0]
    piece = re.split(r"\s*-\s*", piece, maxsplit=1)[0]
    piece = re.sub(r"\s*\+.*", "", piece)
    piece = re.sub(r"[^\w\s']", " ", piece)
    return re.sub(r"\s+", " ", piece).strip()


def merged_synonyms(text: str) -> str:
    """Join comma-separated glosses in the head definition (e.g. be / exist)."""
    text = _clean_definition(text)
    head = text
    for sep in (";", ":", "—"):
        if sep in head:
            head = head.split(sep, 1)[0]
    pieces = [_trim_gloss_piece(part) for part in head.split(",")]
    seen: list[str] = []
    for piece in pieces:
        if piece and piece not in seen:
            seen.append(piece)
    if not seen:
        return _trim_gloss_piece(head)
    if len(seen) == 1:
        return seen[0]
    return " / ".join(seen)


def speech_translation(text: str) -> str:
    return merged_synonyms(text).split(" / ", 1)[0]


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


def apply_paradigm_form_fix(
    entry: dict, *, gender: str, number: str, case: str, form: str
) -> str:
    """Correct known bad analyzer forms (e.g. quī vs. unusquisque)."""
    if strip_macrons(entry.get("lemma") or "") != "qui":
        return form
    if entry.get("rank") != 3:
        return form
    fixes = {
        ("Masc", "Sing", "Gen"): "cuius",
        ("Masc", "Sing", "Dat"): "cui",
    }
    return fixes.get((gender, number, case), form)


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
                form = apply_paradigm_form_fix(
                    entry, gender=gender, number=number, case=case, form=form
                )
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
    english = merged_synonyms(entry["translation"])
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


def drill_to_json(drill: FormDrill, *, include_answer: bool = False) -> dict:
    payload = {
        "form_key": drill.form_key,
        "rank": drill.rank,
        "lemma": drill.lemma,
        "english": drill.english,
        "form_prompt": drill.form_prompt,
        "morph_class": drill.morph_class,
        "part_of_speech": drill.part_of_speech,
        "english_sentence": english_context(drill),
    }
    if include_answer:
        payload["latin_form"] = drill.latin_form
        payload["latin_sentence"] = latin_context(drill)
    return payload


def find_drill(by_rank: dict[int, list[FormDrill]], form_key: str) -> FormDrill | None:
    for drills in by_rank.values():
        for drill in drills:
            if drill.form_key == form_key:
                return drill
    return None


def load_progress(by_rank: dict[int, list[FormDrill]]) -> set[str]:
    path = progress_path()
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
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
    path = progress_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def mark_form_mastered(
    mastered: set[str],
    form_key: str,
    *,
    scoped_form_keys: frozenset[str],
) -> tuple[set[str], int, int]:
    total = len(scoped_form_keys)
    if form_key in scoped_form_keys and form_key not in mastered:
        mastered = set(mastered)
        mastered.add(form_key)
        save_progress(mastered, total_forms=total)
    scoped_done = sum(1 for k in scoped_form_keys if k in mastered)
    return mastered, scoped_done, total


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
    print(f"[{remaining}/{total}]  #{drill.rank}  ({drill.part_of_speech})")
    print(f"Word: {drill.english}")
    print(f"English: {english_context(drill)}")
    print(f"Give: {drill.form_prompt}")
    print(f"Class: {drill.morph_class}")


def reveal_drill(drill: FormDrill) -> None:
    print(f"Answer: {drill.latin_form}")
    print(f"Latin: {latin_context(drill)}")


def show_latin_sentence(drill: FormDrill) -> None:
    print(f"Latin: {latin_context(drill)}")


def skip_remaining_forms(drills: list[FormDrill], index: int, rank: int) -> int:
    """Advance past unattempted forms of the same vocabulary entry."""
    index += 1
    while index < len(drills) and drills[index].rank == rank:
        index += 1
    return index


def run_session(
    drills: list[FormDrill],
    mastered: set[str],
    *,
    scoped_form_keys: frozenset[str],
    total_forms: int,
) -> tuple[set[str], bool]:
    total = len(drills)
    index = 0

    while index < len(drills):
        drill = drills[index]
        remaining = total - index
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
                return mastered, False
            if lowered in {"?", "hint"}:
                reveal_drill(drill)
                continue
            if lowered in {"s", "skip"}:
                print("Skipped — moving to next word.")
                index = skip_remaining_forms(drills, index, drill.rank)
                break

            if drill.check(answer):
                if drill.form_key not in mastered:
                    mastered.add(drill.form_key)
                    save_progress(mastered, total_forms=total_forms)
                    scoped_done = sum(1 for k in scoped_form_keys if k in mastered)
                    print(f"✓ Correct — {drill.latin_form}")
                    show_latin_sentence(drill)
                    print(f"  Saved ({scoped_done}/{total_forms} forms mastered in range).")
                else:
                    print(f"✓ Correct — {drill.latin_form}")
                    show_latin_sentence(drill)
                index += 1
                break

            print(f"✗ Not quite. Expected: {drill.latin_form}")
            show_latin_sentence(drill)
            print("  Moving to next word — missed forms come back next pass.")
            index = skip_remaining_forms(drills, index, drill.rank)
            break

    return mastered, True


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
            "  skip    skip this word's remaining forms (next pass)\n"
            "  quit    save and exit\n"
            "\n"
            "By default, studies ranks 1–10 and loops until every form in that\n"
            "range is mastered. Progress is saved per form in\n"
            ".latin-study-progress.json.\n"
            "\n"
            "Examples:\n"
            "  nix run .#study\n"
            "  nix run .#study -- --shuffle\n"
            "  nix run .#study -- --all-words\n"
            "  nix run .#study -- --reset"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_JSON)
    parser.add_argument(
        "--from-rank",
        type=int,
        default=DEFAULT_FROM_RANK,
        help=f"First vocabulary rank (default {DEFAULT_FROM_RANK})",
    )
    parser.add_argument(
        "--to-rank",
        type=int,
        default=DEFAULT_TO_RANK,
        help=f"Last vocabulary rank (default {DEFAULT_TO_RANK})",
    )
    parser.add_argument(
        "--all-words",
        action="store_true",
        help="Study the full vocabulary list instead of the first 10 words",
    )
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

    from_rank = None if args.all_words else args.from_rank
    to_rank = None if args.all_words else args.to_rank

    all_words = load_words(args.file)
    scoped = filter_words(all_words, start_rank=from_rank, end_rank=to_rank)
    _, by_rank = build_drill_index(all_words)
    scoped_drills = [d for entry in scoped for d in by_rank.get(entry["rank"], [])]
    scoped_form_keys = frozenset(d.form_key for d in scoped_drills)
    total_forms = len(scoped_drills)

    if args.reset:
        mastered: set[str] = set()
        save_progress(mastered, total_forms=total_forms)
        print("Progress reset.")
    else:
        mastered = load_progress(by_rank)

    if args.stats:
        remaining = [d for d in scoped_drills if d.form_key not in mastered]
        scoped_done = sum(1 for k in scoped_form_keys if k in mastered)
        words_done, word_total = word_completion_stats(scoped, by_rank, mastered)
        scope_label = "full list" if args.all_words else f"ranks {from_rank}–{to_rank}"
        print(f"Scope: {scope_label}")
        print(f"Forms mastered: {scoped_done}/{total_forms}")
        print(f"Forms remaining: {len(remaining)}")
        print(f"Words fully mastered: {words_done}/{word_total}")
        return

    if not args.review_mastered and mastered:
        scoped_mastered = len([d for d in scoped_drills if d.form_key in mastered])
        if scoped_mastered:
            print("Mastered forms are skipped. Use --review-mastered to include them.")

    study_drills = select_study_drills(
        scoped_drills,
        mastered,
        shuffle=args.shuffle,
        include_mastered=args.review_mastered,
    )
    if not study_drills:
        words_done, word_total = word_completion_stats(scoped, by_rank, mastered)
        print(f"\nAll done — {words_done}/{word_total} words fully mastered in this range.")
        return

    scope_label = "full list" if args.all_words else f"ranks {from_rank}–{to_rank}"
    print(f"Latin study — {scope_label}")
    print("Commands: ? (reveal)  skip  quit")

    try:
        pass_num = 0
        while True:
            study_drills = select_study_drills(
                scoped_drills,
                mastered,
                shuffle=args.shuffle,
                include_mastered=args.review_mastered,
            )
            if not study_drills:
                words_done, word_total = word_completion_stats(scoped, by_rank, mastered)
                print(
                    f"\nAll done — {words_done}/{word_total} words fully mastered "
                    f"({total_forms} forms)."
                )
                break

            pass_num += 1
            scoped_mastered = len([d for d in scoped_drills if d.form_key in mastered])
            words_done, word_total = word_completion_stats(scoped, by_rank, mastered)
            if pass_num == 1:
                print(
                    f"{len(study_drills)} form(s) to go "
                    f"({scoped_mastered}/{total_forms} forms mastered, "
                    f"{words_done}/{word_total} words complete)"
                )
            else:
                print(
                    f"\n--- Pass {pass_num}: {len(study_drills)} form(s) remaining "
                    f"({scoped_mastered}/{total_forms} forms mastered) ---"
                )

            mastered, finished = run_session(
                study_drills,
                mastered,
                scoped_form_keys=scoped_form_keys,
                total_forms=total_forms,
            )
            if not finished:
                remaining = len([d for d in scoped_drills if d.form_key not in mastered])
                print(f"\n{remaining} form(s) left. Run again to continue.")
                break
    except KeyboardInterrupt:
        save_progress(mastered, total_forms=total_forms)
        print("\nProgress saved.")


if __name__ == "__main__":
    main()
