#!/usr/bin/env python3
"""Web UI for Latin morphology study."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

if "LATIN_PROGRESS_FILE" not in os.environ:
    os.environ["LATIN_PROGRESS_FILE"] = str(Path.cwd() / ".latin-study-progress.json")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from study import (
    DEFAULT_FROM_RANK,
    DEFAULT_JSON,
    DEFAULT_TO_RANK,
    build_drill_index,
    drill_to_json,
    filter_words,
    find_drill,
    load_progress,
    load_words,
    mark_form_mastered,
    save_progress,
    word_completion_stats,
)

ROOT = Path(os.environ["LATIN_ROOT"]) if "LATIN_ROOT" in os.environ else Path(__file__).parent
WEB_ROOT = ROOT / "web"


@lru_cache(maxsize=1)
def vocabulary_index():
    words = load_words(DEFAULT_JSON)
    _, by_rank = build_drill_index(words)
    return words, by_rank


def scoped_bundle(from_rank: int | None, to_rank: int | None):
    words, by_rank = vocabulary_index()
    scoped = filter_words(words, start_rank=from_rank, end_rank=to_rank)
    scoped_drills = [d for entry in scoped for d in by_rank.get(entry["rank"], [])]
    scoped_keys = frozenset(d.form_key for d in scoped_drills)
    return scoped, by_rank, scoped_drills, scoped_keys


class ScopeFields(BaseModel):
    from_rank: int = DEFAULT_FROM_RANK
    to_rank: int = DEFAULT_TO_RANK
    all_words: bool = False


class FormAction(ScopeFields):
    form_key: str


class CheckAction(FormAction):
    answer: str = ""


app = FastAPI(title="Latin Study", version="1.0.0")


@app.get("/api/defaults")
def api_defaults():
    return {
        "from_rank": DEFAULT_FROM_RANK,
        "to_rank": DEFAULT_TO_RANK,
        "progress_file": str(
            os.environ.get("LATIN_PROGRESS_FILE", str(Path.cwd() / ".latin-study-progress.json"))
        ),
    }


@app.get("/api/stats")
def api_stats(from_rank: int = DEFAULT_FROM_RANK, to_rank: int = DEFAULT_TO_RANK, all_words: bool = False):
    from_r = None if all_words else from_rank
    to_r = None if all_words else to_rank
    scoped, by_rank, scoped_drills, scoped_keys = scoped_bundle(from_r, to_r)
    mastered = load_progress(by_rank)
    scoped_done = sum(1 for k in scoped_keys if k in mastered)
    words_done, word_total = word_completion_stats(scoped, by_rank, mastered)
    remaining = len([d for d in scoped_drills if d.form_key not in mastered])
    return {
        "from_rank": from_r,
        "to_rank": to_r,
        "all_words": all_words,
        "forms_mastered": scoped_done,
        "total_forms": len(scoped_drills),
        "forms_remaining": remaining,
        "words_complete": words_done,
        "word_total": word_total,
        "mastered_forms": sorted(k for k in scoped_keys if k in mastered),
    }


@app.get("/api/drills")
def api_drills(from_rank: int = DEFAULT_FROM_RANK, to_rank: int = DEFAULT_TO_RANK, all_words: bool = False):
    from_r = None if all_words else from_rank
    to_r = None if all_words else to_rank
    _, _, scoped_drills, _ = scoped_bundle(from_r, to_r)
    return {"drills": [drill_to_json(d) for d in scoped_drills]}


@app.get("/api/progress")
def api_progress():
    _, by_rank, _, _ = scoped_bundle(None, None)
    mastered = load_progress(by_rank)
    return {"mastered_forms": sorted(mastered)}


@app.post("/api/progress/reset")
def api_reset(from_rank: int = DEFAULT_FROM_RANK, to_rank: int = DEFAULT_TO_RANK, all_words: bool = False):
    from_r = None if all_words else from_rank
    to_r = None if all_words else to_rank
    _, by_rank, _, scoped_keys = scoped_bundle(from_r, to_r)
    mastered = load_progress(by_rank)
    if all_words:
        mastered = set()
    else:
        mastered = {k for k in mastered if k not in scoped_keys}
    save_progress(mastered, total_forms=len(scoped_keys))
    return api_stats(from_rank=from_rank, to_rank=to_rank, all_words=all_words)


@app.post("/api/hint")
def api_hint(body: FormAction):
    _, by_rank, _, _ = scoped_bundle(
        None if body.all_words else body.from_rank,
        None if body.all_words else body.to_rank,
    )
    drill = find_drill(by_rank, body.form_key)
    if not drill:
        raise HTTPException(status_code=404, detail="Unknown form")
    data = drill_to_json(drill, include_answer=True)
    return {
        "latin_form": data["latin_form"],
        "latin_sentence": data["latin_sentence"],
    }


@app.post("/api/check")
def api_check(body: CheckAction):
    from_r = None if body.all_words else body.from_rank
    to_r = None if body.all_words else body.to_rank
    _, by_rank, _, scoped_keys = scoped_bundle(from_r, to_r)
    drill = find_drill(by_rank, body.form_key)
    if not drill:
        raise HTTPException(status_code=404, detail="Unknown form")
    correct = drill.check(body.answer)
    answer = drill_to_json(drill, include_answer=True)
    mastered = load_progress(by_rank)
    scoped_total = len(scoped_keys)
    scoped_done = sum(1 for k in scoped_keys if k in mastered)

    if correct:
        mastered, scoped_done, scoped_total = mark_form_mastered(
            mastered,
            drill.form_key,
            scoped_form_keys=scoped_keys,
        )

    return {
        "correct": correct,
        "latin_form": answer["latin_form"],
        "latin_sentence": answer["latin_sentence"],
        "forms_mastered": scoped_done,
        "total_forms": scoped_total,
        "saved": correct and drill.form_key in scoped_keys,
    }


@app.get("/")
def index():
    return FileResponse(WEB_ROOT / "index.html")


app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


def main() -> None:
    import uvicorn

    host = os.environ.get("LATIN_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("LATIN_WEB_PORT", "8765"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
