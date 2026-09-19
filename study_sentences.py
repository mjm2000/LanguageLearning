"""English and Latin context sentences for morphology drills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from study import FormDrill


@dataclass(frozen=True)
class MorphInfo:
    kind: str
    case: str | None = None
    number: str | None = None
    gender: str | None = None
    person: str | None = None
    tense: str | None = None
    mood: str | None = None
    voice: str | None = None
    verb_form: str | None = None


def gloss(word: str) -> str:
    return word.split(",")[0].split()[0].strip()


def gloss_plural(word: str, plural: bool) -> str:
    if not plural:
        return word
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def _english_head(gender: str | None, plural: bool) -> str:
    if gender == "Fem":
        return "women" if plural else "woman"
    if gender == "Neut":
        return "towns" if plural else "town"
    return "soldiers" if plural else "soldier"


def _participle_gloss(word: str, tense: str | None) -> str:
    if word == "be":
        return "about to be" if tense == "Fut" else "being"
    if tense == "Fut":
        return f"about to {word}"
    return f"{word}ing"


def parse_morph(drill: FormDrill) -> MorphInfo:
    parts = drill.form_key.split(":")
    kind = parts[0]
    if kind == "n":
        return MorphInfo(kind="noun", number=parts[2], case=parts[3])
    if kind == "a":
        return MorphInfo(kind="adj", gender=parts[2], number=parts[3], case=parts[4])
    if kind == "v":
        tense, mood, voice = parts[2].split("_", 2)
        return MorphInfo(
            kind="verb_finite",
            tense=tense,
            mood=mood,
            voice=voice,
            number=parts[3],
            person=parts[4],
        )
    if kind == "vf":
        return MorphInfo(
            kind="verb_nonfinite",
            verb_form=parts[3] if len(parts) > 3 else None,
            tense=parts[4] if len(parts) > 4 and parts[4] != "None" else None,
            voice=parts[5] if len(parts) > 5 and parts[5] != "None" else None,
            case=parts[6] if len(parts) > 6 and parts[6] != "None" else None,
            gender=parts[7] if len(parts) > 7 and parts[7] != "None" else None,
            number=parts[8] if len(parts) > 8 and parts[8] != "None" else None,
        )
    return MorphInfo(kind="indecl")


def _plural(number: str | None) -> bool:
    return number == "Plur"


def _noun_english(w: str, morph: MorphInfo) -> str:
    pl = _plural(morph.number)
    word = gloss_plural(w, pl)
    case = morph.case or "Nom"
    if case == "Nom":
        return f"The {word} {'are' if pl else 'is'} here." if pl else f"The {word} is good."
    if case == "Gen":
        return (
            f"The fields of the {word} are wide."
            if pl
            else f"The edge of the {word} is long."
        )
    if case == "Dat":
        return f"I gave it to the {word}." if not pl else f"We spoke to the {word}."
    if case == "Acc":
        return f"I see the {word}." if not pl else f"We found the {word}."
    if case == "Abl":
        return f"The farmer worked in the {word}." if not pl else f"They traveled through the {word}."
    if case == "Voc":
        return f"O {word}, hear me!" if not pl else f"O {word}, listen!"
    return f"The {word} fits this form."


def _noun_latin(form: str, morph: MorphInfo) -> str:
    pl = _plural(morph.number)
    case = morph.case or "Nom"
    if case == "Nom":
        return f"{form} bona {'sunt' if pl else 'est'}."
    if case == "Gen":
        return f"Finis {form} longus {'sunt' if pl else 'est'}."
    if case == "Dat":
        return f"Agricola {form} parat."
    if case == "Acc":
        return f"Video {form}."
    if case == "Abl":
        return f"Agricola in {form} laborat."
    if case == "Voc":
        return f"O {form}, audi!"
    return f"{form}."


def _adj_noun(gender: str | None, pl: bool) -> str:
    if gender == "Fem":
        return "feminae" if pl else "femina"
    if gender == "Neut":
        return "oppida" if pl else "oppidum"
    return "milites" if pl else "miles"


def _pronoun_english(w: str, morph: MorphInfo) -> str:
    pl = _plural(morph.number)
    case = morph.case or "Nom"
    if case == "Nom":
        return f"{w.capitalize()} {'are' if pl else 'is'} here."
    if case == "Gen":
        return f"The book of {w} is lost." if not pl else f"The books of {w} are lost."
    if case == "Dat":
        return f"I gave it to {w}."
    if case == "Acc":
        return f"I see {w}." if not pl else f"We see {w}."
    if case == "Abl":
        return f"I came with {w}."
    if case == "Voc":
        return f"O {w}, listen!"
    return f"{w.capitalize()} fits this form."


def _pronoun_latin(form: str, morph: MorphInfo) -> str:
    pl = _plural(morph.number)
    case = morph.case or "Nom"
    if case == "Nom":
        return f"{form} hic {'sunt' if pl else 'est'}."
    if case == "Gen":
        return f"Liber {form} amissus est."
    if case == "Dat":
        return f"Donum {form} dedi."
    if case == "Acc":
        return f"Video {form}."
    if case == "Abl":
        return f"Cum {form} veni."
    if case == "Voc":
        return f"O {form}, audi!"
    return f"{form}."


def _adj_english(w: str, morph: MorphInfo) -> str:
    pl = _plural(morph.number)
    case = morph.case or "Nom"
    gender = morph.gender or "Masc"
    head = _english_head(gender, pl)
    if case == "Nom":
        if gender == "Neut":
            return f"The {w} {head} {'are' if pl else 'is'} near."
        return f"The {w} {head} {'are' if pl else 'is'} here."
    if case == "Gen":
        return f"The name of the {w} {head} is known."
    if case == "Dat":
        return f"We trust the {w} {head}."
    if case == "Acc":
        return f"I see the {w} {head}."
    if case == "Abl":
        return f"With the {w} {head}, we marched."
    if case == "Voc":
        return f"O {w} {head}, stay!"
    return f"The {w} {head} fits this form."


def _adj_latin(form: str, morph: MorphInfo) -> str:
    pl = _plural(morph.number)
    gender = morph.gender or "Masc"
    head = _adj_noun(gender, pl)
    case = morph.case or "Nom"
    if case == "Nom":
        return f"{form} {head} {'sunt' if pl else 'est'}."
    if case == "Gen":
        return f"Nomen {form} notum est."
    if case == "Dat":
        return f"{form} {head} credimus."
    if case == "Acc":
        return f"Video {form} {head}."
    if case == "Abl":
        return f"Cum {form} {head} ambulavimus."
    if case == "Voc":
        return f"O {form} {head}, mane!"
    return f"{form} {head}."


def _be_english(person: str, number: str, tense: str, mood: str) -> str:
    pl = number == "Plur"
    if mood == "Imp":
        if person == "2":
            return "Be strong!" if not pl else "Be ready, all of you!"
        return "Let there be peace."
    if mood == "Sub":
        if person == "1":
            return "I wish I were brave." if tense in {"Imp", "Pres"} else "I may be ready."
        if person == "2":
            return "You should be careful."
        return "It is good that he be here." if tense in {"Pres", "Imp"} else "He may be late."
    if tense in {"Perf", "Past"}:
        mapping = {
            ("1", "Sing"): "I was tired.",
            ("2", "Sing"): "You were late.",
            ("3", "Sing"): "He was here.",
            ("1", "Plur"): "We were ready.",
            ("2", "Plur"): "You were friends.",
            ("3", "Plur"): "They were strong.",
        }
        return mapping.get((person, number), "They were here.")
    if tense == "Fut":
        mapping = {
            ("1", "Sing"): "I will be there.",
            ("2", "Sing"): "You will be fine.",
            ("3", "Sing"): "He will be king.",
            ("1", "Plur"): "We will be allies.",
            ("2", "Plur"): "You will be safe.",
            ("3", "Plur"): "They will be here.",
        }
        return mapping.get((person, number), "They will be here.")
    if tense == "Imp":
        mapping = {
            ("1", "Sing"): "I was reading while I was tired.",
            ("2", "Sing"): "You were always kind.",
            ("3", "Sing"): "He was a leader.",
            ("1", "Plur"): "We were young.",
            ("2", "Plur"): "You were in Rome.",
            ("3", "Plur"): "They were afraid.",
        }
        return mapping.get((person, number), "They were here.")
    mapping = {
        ("1", "Sing"): "I am ready.",
        ("2", "Sing"): "You are strong.",
        ("3", "Sing"): "He is here.",
        ("1", "Plur"): "We are friends.",
        ("2", "Plur"): "You are students.",
        ("3", "Plur"): "They are brave.",
    }
    return mapping.get((person, number), "They are here.")


def _verb_english(w: str, morph: MorphInfo) -> str:
    person = morph.person or "3"
    number = morph.number or "Sing"
    tense = morph.tense or "Pres"
    mood = morph.mood or "Ind"
    voice = morph.voice or "Act"
    pl = number == "Plur"

    if w == "be":
        return _be_english(person, number, tense, mood)

    if mood == "Imp":
        if person == "2":
            return f"{w.capitalize()} this!" if not pl else f"{w.capitalize()} it now, all of you!"
        return f"Let him {w}."
    if mood == "Sub":
        if person == "1":
            return f"I wish I could {w}." if tense in {"Pres", "Imp"} else f"I may have {w}ed."
        if person == "2":
            return f"You should {w}."
        return f"It is good that he {w}s." if tense == "Pres" else f"He may {w}."
    if voice == "Pas":
        if person == "1":
            return f"I am {w}ed." if tense == "Pres" else f"I was {w}ed."
        if person == "2":
            return f"You are {w}ed." if tense == "Pres" else f"You were {w}ed."
        return f"He is {w}ed." if tense == "Pres" else f"He was {w}ed."
    if tense in {"Perf", "Past"}:
        mapping = {
            ("1", "Sing"): f"I {w}ed it.",
            ("2", "Sing"): f"You {w}ed well.",
            ("3", "Sing"): f"He {w}ed quickly.",
            ("1", "Plur"): f"We {w}ed together.",
            ("2", "Plur"): f"You {w}ed often.",
            ("3", "Plur"): f"They {w}ed yesterday.",
        }
        return mapping.get((person, number), f"They {w}ed.")
    if tense == "Fut":
        mapping = {
            ("1", "Sing"): f"I will {w} soon.",
            ("2", "Sing"): f"You will {w} later.",
            ("3", "Sing"): f"He will {w} tomorrow.",
            ("1", "Plur"): f"We will {w} together.",
            ("2", "Plur"): f"You will {w} now.",
            ("3", "Plur"): f"They will {w} at dawn.",
        }
        return mapping.get((person, number), f"They will {w}.")
    if tense == "Imp":
        mapping = {
            ("1", "Sing"): f"I was {w}ing when he arrived.",
            ("2", "Sing"): f"You were {w}ing often.",
            ("3", "Sing"): f"He was {w}ing every day.",
            ("1", "Plur"): f"We were {w}ing together.",
            ("2", "Plur"): f"You were {w}ing in the forum.",
            ("3", "Plur"): f"They were {w}ing at home.",
        }
        return mapping.get((person, number), f"They were {w}ing.")
    mapping = {
        ("1", "Sing"): f"I {w} every day.",
        ("2", "Sing"): f"You {w} well.",
        ("3", "Sing"): f"He {w}s quickly.",
        ("1", "Plur"): f"We {w} together.",
        ("2", "Plur"): f"You {w} often.",
        ("3", "Plur"): f"They {w} at dawn.",
    }
    return mapping.get((person, number), f"They {w}.")


def _be_latin(form: str, morph: MorphInfo) -> str:
    person = morph.person or "3"
    number = morph.number or "Sing"
    mood = morph.mood or "Ind"
    if mood == "Imp" and person == "2":
        return f"{form} fortis!" if number == "Sing" else f"{form} parati!"
    if person == "1":
        return f"Ego {form} fortis." if number == "Sing" else f"Nos {form} parati."
    if person == "2":
        return f"Tu {form} fortis." if number == "Sing" else f"Vos {form} fortes."
    return f"Is {form} fortis." if number == "Sing" else f"Ii {form} fortes."


def _verb_latin(form: str, morph: MorphInfo, *, lemma: str = "") -> str:
    person = morph.person or "3"
    number = morph.number or "Sing"
    mood = morph.mood or "Ind"
    voice = morph.voice or "Act"

    if lemma == "sum":
        return _be_latin(form, morph)

    if mood == "Imp" and person == "2":
        return f"{form}, serve!" if number == "Sing" else f"{form}, milites!"

    if voice == "Pas":
        if person == "1":
            return f"A {form}." if number == "Sing" else f"A {form}."
        if person == "3":
            return f"Ab hoste {form}." if number == "Sing" else f"Ab hostibus {form}."
        return f"{form}."

    if person == "1":
        return f"Ego {form}." if number == "Sing" else f"Nos {form}."
    if person == "2":
        return f"Tu {form}." if number == "Sing" else f"Vos {form}."
    return f"Is {form}." if number == "Sing" else f"Ii {form}."


def _nonfinite_english(w: str, morph: MorphInfo) -> str:
    vf = morph.verb_form or "Inf"
    if vf == "Inf":
        return f"They want to {w}."
    if vf == "Part":
        gender = morph.gender or "Masc"
        pl = _plural(morph.number)
        head = _english_head(gender, pl)
        part = _participle_gloss(w, morph.tense)
        return f"The {part} {head} {'are' if pl else 'is'} coming."
    if vf == "Ger":
        return f"He is good at {w}ing."
    if vf == "Gdv":
        return f"It must be {w}ed."
    if vf == "Sup":
        return f"He went to {w}."
    return f"It is time to {w}."


def _nonfinite_latin(form: str, morph: MorphInfo) -> str:
    vf = morph.verb_form or "Inf"
    if vf == "Inf":
        return f"Volunt {form}."
    if vf == "Part":
        gender = morph.gender or "Masc"
        head = _adj_noun(gender, _plural(morph.number))
        return f"{form} {head} venit."
    if vf == "Ger":
        return f"Bonus ad {form}."
    if vf == "Gdv":
        return f"{form} est."
    if vf == "Sup":
        return f"Iit {form}."
    return f"{form}."


def _indecl_english(w: str, pos: str) -> str:
    pos = pos.lower()
    if "conjunction" in pos:
        return f"Caesar {w} Pompey marched to Rome."
    if "preposition" in pos:
        return f"He walked {w} the city gates."
    if "adverb" in pos:
        return f"We must leave {w}."
    if "pronoun" in pos:
        if w in {"who", "which", "what"}:
            return f"{w.capitalize()} is calling?"
        return f"{w.capitalize()} are going home."
    return f"Say {w} in this sentence."


def _indecl_latin(form: str, pos: str) -> str:
    pos = pos.lower()
    if "conjunction" in pos:
        return f"Caesar {form} Pompeius Romam ambulant."
    if "preposition" in pos:
        return f"Ambulavit {form} portas urbis."
    if "adverb" in pos:
        return f"{form.capitalize()} discedere debemus."
    if "pronoun" in pos:
        return f"{form.capitalize()} vocat?"
    return f"{form}."


def english_context(drill: FormDrill) -> str:
    w = gloss(drill.english)
    morph = parse_morph(drill)
    if morph.kind == "noun":
        return _noun_english(w, morph)
    if morph.kind == "adj":
        if drill.part_of_speech == "Pronoun":
            return _pronoun_english(w, morph)
        return _adj_english(w, morph)
    if morph.kind == "verb_finite":
        return _verb_english(w, morph)
    if morph.kind == "verb_nonfinite":
        return _nonfinite_english(w, morph)
    return _indecl_english(w, drill.part_of_speech)


def latin_context(drill: FormDrill) -> str:
    form = drill.latin_form
    morph = parse_morph(drill)
    if morph.kind == "noun":
        return _noun_latin(form, morph)
    if morph.kind == "adj":
        if drill.part_of_speech == "Pronoun":
            return _pronoun_latin(form, morph)
        return _adj_latin(form, morph)
    if morph.kind == "verb_finite":
        return _verb_latin(form, morph, lemma=drill.lemma)
    if morph.kind == "verb_nonfinite":
        return _nonfinite_latin(form, morph)
    return _indecl_latin(form, drill.part_of_speech)
