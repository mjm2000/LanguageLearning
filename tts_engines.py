"""Pluggable TTS engines for Latin vocabulary playback."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from abc import ABC, abstractmethod
from pathlib import Path

import edge_tts
import orthography2ipa as o2i

_ROOT = Path(os.environ.get("LATIN_ROOT", Path(__file__).parent))


def openai_api_key() -> str | None:
    """OPENAI_API_KEY env var, or key from openai_key file."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key.strip()
    for key_file in (_ROOT / "openai_key", Path.cwd() / "openai_key"):
        if key_file.is_file():
            return key_file.read_text().strip()
    return None


OPENAI_CLASSICAL_INSTRUCTIONS = (
    "This is a Latin word. Pronounce it rhythmically, slowly and with emphasis, "
    "articulating each syllable and correctly stressing them. "
    "Use restored classical Latin pronunciation: v as w, c before e or i as k, "
    "ae as English 'eye', oe as English 'oy'. "
    "Pronounce it exactly like this: {text}"
)

OPENAI_ECCLESIASTICAL_INSTRUCTIONS = (
    "This is a Latin word. Pronounce it rhythmically, slowly and with emphasis, "
    "articulating each syllable and correctly stressing them. "
    "Use Italianate ecclesiastical Latin pronunciation. "
    "Pronounce it exactly like this: {text}"
)

OPENAI_ENGLISH_INSTRUCTIONS = "Speak clearly and naturally in English."

# IPA → ASCII for edge-tts classical fallback.
_IPA_SPEAKABLE = str.maketrans(
    {
        "ɡ": "g",
        "ɪ": "i",
        "ʊ": "u",
        "ɛ": "e",
        "ɔ": "o",
        "æ": "ae",
        "œ": "oe",
        "ŋ": "ng",
        "x": "kh",
        "j": "y",
        "ʃ": "sh",
        "ʒ": "zh",
        "θ": "th",
        "β": "b",
        "ɣ": "g",
        "ʍ": "wh",
    }
)


def strip_macrons(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


_VOWELS = set("aeiouy")
_DIPHTHONGS = ("ae", "oe", "au", "eu", "ui", "ai", "oi")
_GRAVE = str.maketrans("aeiouAEIOU", "àèìòùÀÈÌÒÙ")


def macron_vowels(text: str) -> set[str]:
    nfd = unicodedata.normalize("NFD", text.lower())
    return {
        nfd[i - 1]
        for i, ch in enumerate(nfd)
        if unicodedata.category(ch) == "Mn" and i > 0
    }


def latin_syllables(word: str) -> list[str]:
    """Maximal-onset syllabification with qu/kw treated as consonant clusters."""
    w = strip_macrons(word.lower()).replace("qu", "qw").replace("kw", "kv")
    nuclei: list[tuple[int, int]] = []
    i = 0
    n = len(w)
    while i < n:
        if w[i] not in _VOWELS:
            i += 1
            continue
        start = i
        for dh in _DIPHTHONGS:
            if w.startswith(dh, i):
                i += len(dh)
                break
        else:
            i += 1
        nuclei.append((start, i))
    if not nuclei:
        return [word.lower()]

    bounds = [0]
    for k in range(len(nuclei) - 1):
        _, n_end = nuclei[k]
        n_next, _ = nuclei[k + 1]
        between = w[n_end:n_next]
        if not between:
            bounds.append(n_end)
        elif len(between) == 1:
            bounds.append(n_end)
        else:
            bounds.append(n_end + 1)
    bounds.append(len(w))

    return [
        w[bounds[k] : bounds[k + 1]].replace("qw", "qu").replace("kv", "kw")
        for k in range(len(bounds) - 1)
    ]


def penult_is_long(original: str, syllables: list[str]) -> bool:
    if len(syllables) < 2:
        return True
    penult = syllables[-2]
    if any(v in penult for v in macron_vowels(original)):
        return True
    if any(dh in penult for dh in _DIPHTHONGS):
        return True
    if re.search(r"[aeiouy][bcdfghjklmnpqrstvwxyz]$", penult):
        return True
    if re.search(r"[aeiouy][bcdfghjklmnpqrstvwxyz]{2,}", penult):
        return True
    return False


def stress_index(original: str, syllables: list[str]) -> int:
    if len(syllables) <= 1:
        return 0
    if penult_is_long(original, syllables):
        return len(syllables) - 2
    return max(0, len(syllables) - 3)


def mark_stressed_syllable(text: str, syllables: list[str], stress_idx: int) -> str:
    """ACL 2025 cue: uppercase the stressed syllable and grave-accent its vowel."""
    if stress_idx >= len(syllables):
        return text
    target = syllables[stress_idx]
    pos = text.lower().find(target.lower())
    if pos < 0:
        return text

    chunk = text[pos : pos + len(target)]
    marked: list[str] = []
    vowel_marked = False
    for ch in chunk:
        if not vowel_marked and ch.lower() in "aeiou":
            marked.append(ch.translate(_GRAVE).upper())
            vowel_marked = True
        else:
            marked.append(ch.upper())
    stressed = "".join(marked)
    tail = text[pos + len(target) :].lower()
    return text[:pos] + stressed + tail


def classical_orthography(word: str) -> str:
    """Orthographic classical prep from ACL 2025 Latin TTS research."""
    w = strip_macrons(word.lower())
    w = w.replace("qu", "kw")
    w = w.replace("ae", "ai").replace("oe", "oi")
    w = re.sub(r"c(?=[ei])", "k", w)
    w = re.sub(r"ge", "ghe", w)
    w = re.sub(r"gi", "ghi", w)
    w = w.replace("v", "w")
    w = re.sub(r"ch(?=[ei])", "k", w)
    return w


def classical_tts_form(word: str, *, original: str | None = None) -> str:
    """Preprocess a Latin word for LLM TTS (ACL 2025 workflow)."""
    source = original or word
    transformed = classical_orthography(word)
    orig_syllables = latin_syllables(source)
    trans_syllables = latin_syllables(transformed)
    idx = stress_index(source, orig_syllables)
    if len(trans_syllables) == len(orig_syllables):
        stress_idx = idx
    else:
        stress_idx = min(idx, len(trans_syllables) - 1)
    return mark_stressed_syllable(transformed, trans_syllables, stress_idx)


def ipa_to_speakable(ipa: str) -> str:
    text = unicodedata.normalize("NFD", ipa)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.translate(str.maketrans("", "", "ˈˌːˑ"))
    text = text.translate(_IPA_SPEAKABLE)
    return re.sub(r"[^\w]", "", text)


def classical_speech_form(word: str, *, original: str | None = None) -> str:
    try:
        ipa = o2i.transcribe(strip_macrons(word.lower()), "la-x-classic")
        speakable = ipa_to_speakable(ipa)
        if speakable:
            return speakable
    except Exception:
        pass
    return classical_tts_form(word, original=original)


def find_player() -> list[str]:
    ffplay_args = ["-nodisp", "-autoexit", "-loglevel", "quiet"]
    if shutil.which("ffplay"):
        return ["ffplay", *ffplay_args]
    try:
        result = subprocess.run(
            ["nix-shell", "-p", "ffmpeg", "--run", "which ffplay"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return [result.stdout.strip(), *ffplay_args]
    except OSError:
        pass
    if shutil.which("mpg123"):
        return ["mpg123", "-q"]
    return []


def play_file(path: Path, player: list[str]) -> None:
    subprocess.run([*player, str(path)], check=False)
    path.unlink(missing_ok=True)


class TTSEngine(ABC):
    name: str

    @abstractmethod
    async def synthesize_latin(self, word: str, accent: str, *, original: str | None = None) -> Path: ...

    @abstractmethod
    async def synthesize_english(self, text: str) -> Path: ...


class EdgeEngine(TTSEngine):
    name = "edge"

    VOICES = {
        "classical": "en-US-AndrewNeural",
        "ecclesiastical": "it-IT-GiuseppeMultilingualNeural",
        "english": "en-US-JennyNeural",
    }

    def __init__(self, rate: str = "-5%"):
        self.rate = rate

    def _latin_text(self, word: str, accent: str, *, original: str | None = None) -> str:
        if accent == "classical":
            return classical_tts_form(word, original=original)
        source = original or word
        syllables = latin_syllables(source)
        plain = strip_macrons(word.lower())
        return mark_stressed_syllable(plain, syllables, stress_index(source, syllables))

    async def synthesize_latin(self, word: str, accent: str, *, original: str | None = None) -> Path:
        text = self._latin_text(word, accent, original=original)
        voice = self.VOICES[accent]
        tmp = Path(tempfile.mkstemp(suffix=".mp3")[1])
        await edge_tts.Communicate(text, voice, rate=self.rate).save(str(tmp))
        return tmp

    async def synthesize_english(self, text: str) -> Path:
        tmp = Path(tempfile.mkstemp(suffix=".mp3")[1])
        await edge_tts.Communicate(text, self.VOICES["english"], rate=self.rate).save(str(tmp))
        return tmp


class OpenAIEngine(TTSEngine):
    """OpenAI gpt-4o-mini-tts — best Gen-AI option for classical Latin (ACL 2025)."""

    name = "openai"

    def __init__(
        self,
        *,
        voice: str = "onyx",
        latin_voice: str | None = None,
        english_voice: str | None = None,
    ):
        api_key = openai_api_key()
        if not api_key:
            raise RuntimeError(
                "Set OPENAI_API_KEY or put your key in openai_key in the project root."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai package: pip install openai") from exc

        self.client = OpenAI(api_key=api_key)
        self.latin_voice = latin_voice or voice
        self.english_voice = english_voice or voice

    def _latin_text(self, word: str, accent: str, *, original: str | None = None) -> str:
        if accent == "classical":
            return classical_tts_form(word, original=original)
        source = original or word
        syllables = latin_syllables(source)
        plain = strip_macrons(word.lower())
        return mark_stressed_syllable(plain, syllables, stress_index(source, syllables))

    def _create(self, text: str, voice: str, instructions: str) -> Path:
        tmp = Path(tempfile.mkstemp(suffix=".mp3")[1])
        with self.client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice=voice,
            input=text,
            instructions=instructions.format(text=text),
            response_format="mp3",
        ) as response:
            response.stream_to_file(tmp)
        return tmp

    async def synthesize_latin(self, word: str, accent: str, *, original: str | None = None) -> Path:
        text = self._latin_text(word, accent, original=original)
        instructions = (
            OPENAI_CLASSICAL_INSTRUCTIONS
            if accent == "classical"
            else OPENAI_ECCLESIASTICAL_INSTRUCTIONS
        )
        return self._create(text, self.latin_voice, instructions)

    async def synthesize_english(self, text: str) -> Path:
        return self._create(text, self.english_voice, OPENAI_ENGLISH_INSTRUCTIONS)


class MMSEngine(TTSEngine):
    """Meta MMS Latin neural TTS — free, local, Latin-trained (ecclesiastical-ish)."""

    name = "mms"

    _model = None
    _tokenizer = None

    def __init__(self, fallback: EdgeEngine | None = None):
        self.fallback = fallback or EdgeEngine()
        self._load_model()

    @classmethod
    def _load_model(cls) -> None:
        if cls._model is not None:
            return
        try:
            import torch
            from transformers import AutoTokenizer, VitsModel
        except ImportError as exc:
            raise RuntimeError(
                "MMS engine requires: pip install torch transformers scipy"
            ) from exc

        cls._tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-lat")
        cls._model = VitsModel.from_pretrained("facebook/mms-tts-lat")
        cls._model.eval()

    async def synthesize_latin(self, word: str, accent: str, *, original: str | None = None) -> Path:
        import scipy.io.wavfile

        text = strip_macrons(word.lower())
        inputs = self._tokenizer(text, return_tensors="pt")
        import torch

        with torch.no_grad():
            waveform = self._model(**inputs).waveform

        tmp_wav = Path(tempfile.mkstemp(suffix=".wav")[1])
        scipy.io.wavfile.write(
            tmp_wav,
            rate=self._model.config.sampling_rate,
            data=waveform.squeeze().numpy(),
        )
        tmp_mp3 = Path(tempfile.mkstemp(suffix=".mp3")[1])
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            try:
                result = subprocess.run(
                    ["nix-shell", "-p", "ffmpeg", "--run", "which ffmpeg"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                ffmpeg = result.stdout.strip() if result.returncode == 0 else None
            except OSError:
                ffmpeg = None
        if ffmpeg:
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "quiet", "-i", str(tmp_wav), str(tmp_mp3)],
                check=True,
            )
            tmp_wav.unlink(missing_ok=True)
            return tmp_mp3
        return tmp_wav

    async def synthesize_english(self, text: str) -> Path:
        return await self.fallback.synthesize_english(text)


def create_engine(name: str, **kwargs) -> TTSEngine:
    rate = kwargs.get("rate", "-5%")
    voice = kwargs.get("voice", "onyx")

    if name == "auto":
        if openai_api_key():
            try:
                return OpenAIEngine(voice=voice)
            except RuntimeError:
                pass
        return EdgeEngine(rate=rate)

    if name == "openai":
        return OpenAIEngine(voice=voice)
    if name == "mms":
        return MMSEngine(fallback=EdgeEngine(rate=rate))
    if name == "edge":
        return EdgeEngine(rate=rate)

    raise ValueError(f"Unknown engine: {name}")


def available_engines() -> list[str]:
    engines = ["edge", "auto"]
    if openai_api_key():
        engines.insert(0, "openai")
    try:
        import torch  # noqa: F401
        from transformers import VitsModel  # noqa: F401

        engines.append("mms")
    except ImportError:
        pass
    return engines
