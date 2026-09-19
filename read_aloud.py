#!/usr/bin/env python3
"""Read Latin vocabulary aloud with pluggable neural TTS engines."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from tts_engines import (
    available_engines,
    classical_tts_form,
    create_engine,
    find_player,
    play_file,
    strip_macrons,
)

ROOT = Path(os.environ["LATIN_ROOT"]) if "LATIN_ROOT" in os.environ else Path(__file__).parent
DEFAULT_JSON = ROOT / "latin-core-1000.json"
PROGRESS_FILE = Path.cwd() / ".latin-read-progress.json"


def clean_for_speech(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"→.*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;")
    return strip_macrons(text)


def speech_translation(text: str) -> str:
    """Reduce a dictionary entry to one short English gloss for TTS."""
    text = clean_for_speech(text)
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


def speech_latin(entry: dict) -> tuple[str, str]:
    """Return (display lemma, lemma with macrons for pronunciation)."""
    raw = (entry.get("lemma") or entry["headword"]).split()[0]
    raw = re.sub(r"\([^)]*\)", "", raw).strip(" ,;")
    return strip_macrons(raw), raw


def latin_spoken_form(lemma: str, accent: str, engine: str, *, original: str | None = None) -> str:
    source = original or lemma
    if accent == "classical":
        return classical_tts_form(lemma, original=source)
    return strip_macrons(lemma.lower())


@dataclass
class WordItem:
    rank: int
    lemma: str
    lemma_raw: str
    spoken: str
    english: str
    morph: str
    form: str

    def _morph_part(self) -> str:
        if self.morph and self.form:
            return f" ({self.morph}, {self.form})"
        if self.morph:
            return f" ({self.morph})"
        if self.form:
            return f" ({self.form})"
        return ""

    def overview_line(self) -> str:
        label = f"[{self.rank}]"
        morph = self._morph_part()
        if self.spoken != self.lemma.lower():
            return f"{label} {self.lemma}{morph} [{self.spoken}] — {self.english}"
        return f"{label} {self.lemma}{morph} — {self.english}"

    def speaking_line(self) -> str:
        label = f"[{self.rank}]"
        morph = self._morph_part()
        if self.spoken != self.lemma.lower():
            return f"▶ {label} {self.lemma}{morph} [{self.spoken}] — {self.english}"
        return f"▶ {label} {self.lemma}{morph} — {self.english}"


_ORDINAL_RE = re.compile(r"(\d+)(?:st|nd|rd|th)", re.I)


def class_number(label: str) -> str:
    nums = _ORDINAL_RE.findall(label)
    if nums:
        return "/".join(nums)
    lower = label.lower()
    if "irregular" in lower:
        return "irr"
    if "deponent" in lower:
        return "dep"
    if label == "Pronoun":
        return "pron"
    if label == "Numeral":
        return "num"
    return ""


def dictionary_form_label(entry: dict) -> str:
    pos = (entry.get("part_of_speech") or "").split(":", 1)[0].strip()
    if pos == "Verb":
        return "1sg pres ind act"
    if pos == "Noun":
        return "nom sg"
    if pos == "Adjective":
        return "nom sg masc"
    if pos == "Pronoun":
        return "nom sg"
    return "indecl"


def morphology_label(entry: dict) -> tuple[str, str]:
    pos = entry.get("part_of_speech") or ""
    source = entry.get("declension_or_conjugation") or pos
    number = class_number(source)

    if pos.startswith("Verb"):
        kind = f"conj {number}" if number else ""
    elif pos.startswith(("Noun", "Adjective")):
        kind = f"decl {number}" if number else ""
    else:
        kind = number

    return kind.strip(), dictionary_form_label(entry)


def build_items(
    entries: list[dict],
    *,
    accent: str,
    engine: str,
    full_translation: bool,
) -> list[WordItem]:
    items: list[WordItem] = []
    for entry in entries:
        lemma, lemma_raw = speech_latin(entry)
        spoken = latin_spoken_form(lemma, accent, engine, original=lemma_raw)
        translation = entry["translation"]
        english = (
            speech_translation(translation.split(";", 1)[0])
            if full_translation
            else speech_translation(translation)
        )
        morph, form = morphology_label(entry)
        items.append(
            WordItem(
                rank=entry["rank"],
                lemma=lemma,
                lemma_raw=lemma_raw,
                spoken=spoken,
                english=english,
                morph=morph,
                form=form,
            )
        )
    return items


async def speak_items(
    engine,
    accent: str,
    items: list[WordItem],
    player: list[str],
    *,
    latin_only: bool,
    english_only: bool,
    delay: float,
    gap: float,
) -> None:
    for index, item in enumerate(items):
        print(item.speaking_line(), flush=True)
        latin_path = english_path = None
        if not english_only:
            latin_path = await engine.synthesize_latin(
                item.lemma, accent, original=item.lemma_raw
            )
        if not latin_only and item.english:
            english_path = await engine.synthesize_english(item.english)
        if not english_only and latin_path:
            play_file(latin_path, player)
            if not latin_only and english_path and delay:
                time.sleep(delay)
        if not latin_only and english_path:
            play_file(english_path, player)
        if index < len(items) - 1 and gap:
            time.sleep(gap)


def load_words(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)["words"]


def load_progress() -> dict:
    if not PROGRESS_FILE.exists():
        return {"page": 0, "batch_size": 10}
    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"page": 0, "batch_size": 10}
    return {
        "page": int(data.get("page", 0)),
        "batch_size": int(data.get("batch_size", 10)),
    }


def save_progress(page: int, batch_size: int) -> None:
    PROGRESS_FILE.write_text(
        json.dumps({"page": page, "batch_size": batch_size}, indent=2) + "\n",
        encoding="utf-8",
    )


def resolve_page(*, next_batch: bool, reset: bool, batch_size: int) -> int:
    saved = load_progress()
    if reset:
        return 1
    if next_batch:
        if saved["batch_size"] != batch_size:
            print(
                f"Note: batch size changed ({saved['batch_size']} → {batch_size}); "
                "continuing by batch number.",
                file=sys.stderr,
            )
        return saved["page"] + 1
    if saved["page"] > 0:
        return saved["page"]
    return 1


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


def select_words(
    words: list[dict],
    *,
    page: int,
    batch_size: int,
    start_rank: int | None,
    end_rank: int | None,
    shuffle: bool,
) -> list[dict]:
    selected = filter_words(words, start_rank=start_rank, end_rank=end_rank)
    if shuffle:
        selected = selected.copy()
        random.shuffle(selected)
    else:
        selected = sorted(selected, key=lambda w: w["rank"])

    offset = (page - 1) * batch_size
    return selected[offset : offset + batch_size]


class Speaker:
    def __init__(self, engine_name: str, accent: str, rate: str, openai_voice: str | None):
        self.engine = create_engine(
            engine_name,
            rate=rate,
            voice=openai_voice or "onyx",
        )
        self.accent = accent
        self.engine_name = self.engine.name
        self.player = find_player()
        if not self.player:
            sys.exit(
                "No audio player found. Install ffmpeg.\n"
                "  nix-shell -p ffmpeg --run \"python3 read_aloud.py\""
            )

    def speak_latin(self, lemma: str, *, original: str | None = None) -> None:
        path = asyncio.run(
            self.engine.synthesize_latin(lemma, self.accent, original=original)
        )
        play_file(path, self.player)

    def speak_english(self, text: str) -> None:
        path = asyncio.run(self.engine.synthesize_english(text))
        play_file(path, self.player)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read Latin vocabulary aloud.",
        epilog=(
            "Batches (10 words each by default):\n"
            "  nix run .#read           # replay the most recent batch\n"
            "  nix run .#read -- -n     # next 10 words\n"
            "  nix run .#read -- --reset  # start over from the beginning\n"
            "\n"
            "Engines:\n"
            "  openai  — gpt-4o-mini-tts (best classical Latin; needs OPENAI_API_KEY)\n"
            "  mms     — Meta facebook/mms-tts-lat (free local neural Latin)\n"
            "  edge    — Microsoft Edge TTS (free, no key)\n"
            "  auto    — openai if OPENAI_API_KEY is set, else edge"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--file", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--from-rank", type=int)
    parser.add_argument("--to-rank", type=int)
    parser.add_argument(
        "-n",
        "--next",
        action="store_true",
        help="Read the next 10 words after the most recent batch",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Start again from the first batch",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Words per batch (default 10)",
    )
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.1,
        help="Pause between Latin and English for each word (default 0.1s)",
    )
    parser.add_argument(
        "--gap",
        type=float,
        default=0.1,
        help="Pause between words during playback (default 0.1s)",
    )
    parser.add_argument(
        "--accent",
        choices=("classical", "ecclesiastical"),
        default="classical",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "openai", "mms", "edge"),
        default="auto",
        help=f"TTS engine (available: {', '.join(available_engines())})",
    )
    parser.add_argument("--rate", default="-5%", help="Speech rate for edge engine")
    parser.add_argument("--openai-voice", default="onyx", help="OpenAI voice name")
    parser.add_argument("--full-translation", action="store_true")
    parser.add_argument("--latin-only", action="store_true")
    parser.add_argument("--english-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.latin_only and args.english_only:
        parser.error("Choose at most one of --latin-only and --english-only.")
    if args.next and args.reset:
        parser.error("Choose at most one of -n and --reset.")
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1.")
    if not args.file.exists():
        sys.exit(f"Vocabulary file not found: {args.file}")

    page = resolve_page(next_batch=args.next, reset=args.reset, batch_size=args.batch_size)

    all_words = load_words(args.file)
    selected = select_words(
        all_words,
        page=page,
        batch_size=args.batch_size,
        start_rank=args.from_rank,
        end_rank=args.to_rank,
        shuffle=args.shuffle,
    )
    if not selected:
        filtered_total = len(
            filter_words(all_words, start_rank=args.from_rank, end_rank=args.to_rank)
        )
        total_batches = max(1, (filtered_total + args.batch_size - 1) // args.batch_size)
        if args.next and page > total_batches:
            sys.exit(
                f"No more words — batch {page} is past the end "
                f"({total_batches} batch(es) total). Use --reset to start over."
            )
        sys.exit(
            f"No words in batch {page} "
            f"(batch size {args.batch_size}, {total_batches} batch(es) total)."
        )

    save_progress(page, args.batch_size)

    speaker = None if args.dry_run else Speaker(args.engine, args.accent, args.rate, args.openai_voice)

    accent_label = "restored classical" if args.accent == "classical" else "ecclesiastical"
    engine_label = speaker.engine_name if speaker else args.engine
    first_rank = selected[0]["rank"]
    last_rank = selected[-1]["rank"]
    print(
        f"Batch {page} — ranks {first_rank}-{last_rank} "
        f"({len(selected)} word(s)) — {accent_label} Latin via {engine_label} engine"
    )

    items = build_items(
        selected,
        accent=args.accent,
        engine=engine_label,
        full_translation=args.full_translation,
    )

    for item in items:
        print(item.overview_line())

    if args.dry_run:
        filtered_total = len(
            filter_words(all_words, start_rank=args.from_rank, end_rank=args.to_rank)
        )
        total_batches = max(1, (filtered_total + args.batch_size - 1) // args.batch_size)
        if page < total_batches:
            print("\nNext batch: nix run .#read -- -n")
        else:
            print("\nDone — no more batches. Use --reset to start over.")
        return

    print()
    try:
        asyncio.run(
            speak_items(
                speaker.engine,
                args.accent,
                items,
                speaker.player,
                latin_only=args.latin_only,
                english_only=args.english_only,
                delay=args.delay,
                gap=args.gap,
            )
        )
    except KeyboardInterrupt:
        print("\nStopped.")

    filtered_total = len(
        filter_words(all_words, start_rank=args.from_rank, end_rank=args.to_rank)
    )
    total_batches = max(1, (filtered_total + args.batch_size - 1) // args.batch_size)
    if page < total_batches:
        print("\nNext batch: nix run .#read -- -n")
    else:
        print("\nDone — no more batches. Use --reset to start over.")


if __name__ == "__main__":
    main()
