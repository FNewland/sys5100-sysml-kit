"""Message catalogue. English is the source; the French catalogue is a stub (rule titles only)
awaiting review by a francophone instructor. Missing entries fall back to English."""
from __future__ import annotations

FR_TITLES = {
    "RL-SHALL": "Absence de « doit »",
    "RL-MULTI": "Plus d'une obligation",
    "RL-COMB": "Conjonction qui combine des clauses",
    "RL-ANDOR": "« et/ou »",
    "RL-VAGUE": "Terme vague",
    "RL-UNVERIF": "Qualité non vérifiable",
    "RL-SUPERL": "Superlatif ou optimisation",
    "RL-ESCAPE": "Clause échappatoire",
    "RL-OPEN": "Liste ouverte",
    "RL-PASSIVE": "Voix passive sans agent",
    "RL-INFIN": "Infinitif superflu",
    "RL-WEAKVERB": "Verbe faible",
    "RL-PRONOUN": "Pronom",
    "RL-NEG": "Énoncé négatif",
    "RL-UNITS": "Nombre sans unité (ou unité hors SI)",
    "RL-TOL": "Valeur sans borne ni tolérance",
    "RL-TIME": "Terme temporel ambigu",
    "RL-SOLN": "Solution déguisée",
    "RL-ABBR": "Abréviation non définie",
    "RL-RATIONALE": "Justification absente",
    "RL-VERIF": "Méthode de vérification absente",
    "RL-ID": "Identifiant absent ou en double",
    "RL-TBD": "Valeur à déterminer (TBD)",
    "RL-LONG": "Exigence trop longue",
    "RL-UNIV": "Quantificateur universel",
    "RL-SUBJ": "Aucun sujet avant « doit »",
    "RL-SLASH": "Barre oblique entre deux mots",
}
UI = {
    "en": {"summary": "{n} requirement(s), {f} finding(s): {e} error, {w} warning, {i} info",
           "clean": "no findings", "note": "reqlint checks wording only; it cannot judge need, value or evidence."},
    "fr": {"summary": "{n} exigence(s), {f} constat(s) : {e} erreur, {w} avertissement, {i} info",
           "clean": "aucun constat", "note": "reqlint vérifie la formulation seulement [à réviser]."},
}


def title(rule_id: str, default: str, lang: str = "en") -> str:
    if lang == "fr":
        return FR_TITLES.get(rule_id, default)
    return default


def ui(key: str, lang: str = "en") -> str:
    return UI.get(lang, UI["en"]).get(key, UI["en"][key])
