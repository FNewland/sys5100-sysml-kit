"""reqlint rules.

Each rule has an id (RL-...), a severity, a quality *characteristic* it protects (names of
well-formed-requirement characteristics as commonly used in the INCOSE Guide to Writing
Requirements; the explanations here are the course's own paraphrase, not GtWR text), a rule
*family*, a one-line explanation and a fix tip.

Rules are heuristics. They find wording that often hides a problem; they cannot tell whether a
requirement is necessary, correct, feasible or traced to real evidence. That is your job.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable

ERROR, WARNING, INFO = "error", "warning", "info"
SEVERITY_ORDER = {INFO: 0, WARNING: 1, ERROR: 2}


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    characteristic: str
    family: str
    title: str
    explanation: str
    fix: str
    check: Callable  # (req, ctx) -> Iterable[Hit]


@dataclass
class Hit:
    start: int
    end: int
    evidence: str
    note: str = ""
    severity: str | None = None   # override (e.g. downgrade when a number is present)


# ------------------------------------------------------------------ helpers -- #
def _terms(terms: Iterable[str]) -> re.Pattern:
    parts = sorted({t for t in terms}, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(parts) + r")(?![\w-])", re.I)


def _hits(pattern: re.Pattern, text: str, start: int = 0) -> list[Hit]:
    return [Hit(m.start() + start, m.end() + start, m.group(0)) for m in pattern.finditer(text[start:])]


SHALL = re.compile(r"\bshall\b", re.I)


def _after_shall(text: str) -> int:
    m = SHALL.search(text)
    return m.start() if m else 0


UNITS = {
    # SI and SI-accepted symbols and names
    "m", "mm", "cm", "km", "um", "µm", "nm", "kg", "g", "mg", "t", "s", "ms", "us", "µs", "ns", "min", "h", "d",
    "Hz", "kHz", "MHz", "GHz", "W", "mW", "kW", "MW", "GW", "Wh", "kWh", "MWh", "mAh", "Ah", "J", "kJ", "MJ",
    "V", "mV", "kV", "A", "mA", "N", "kN", "Pa", "kPa", "MPa", "bar", "°C", "K", "dB", "dBm", "dBi", "L", "mL",
    "m/s", "km/h", "m/s^2", "m/s²", "m/s2", "rpm", "bit/s", "bps", "kbps", "kbit/s", "Mbps", "Mbit/s", "Gbps",
    "bit", "bits", "B", "kB", "MB", "GB", "TB", "lx", "lux", "cd", "ppm", "rad", "sr", "W/m^2", "W/m2", "%",
    "kW*h", "W*h", "m2", "m^2", "m³", "m3", "m^3", "g/km", "Wh/km", "N·m", "Nm",
    "second", "seconds", "minute", "minutes", "hour", "hours", "day", "days", "week", "weeks", "month", "months",
    "year", "years", "metre", "metres", "meter", "meters", "kilometre", "kilometres", "kilogram", "kilograms",
    "gram", "grams", "watt", "watts", "volt", "volts", "percent", "per", "decibels", "hertz", "litre", "litres",
}
NON_SI = {"mph", "ft", "feet", "foot", "inch", "inches", "lb", "lbs", "pound", "pounds", "°F", "mile", "miles",
          "oz", "ounce", "ounces", "gallon", "gallons", "yard", "yards", "knot", "knots", "psi"}
COUNT_WORDS = {"x", "×", "times", "of", "to", "and", "or", "out", "in", "per", "consecutive", "successive",
               "people", "persons", "users", "nodes", "packets", "frames", "stops", "items", "cycles", "trials",
               "runs", "alerts", "events", "residents", "households", "homes", "units", "modules", "sensors",
               "vehicles", "robots", "steps", "attempts", "faults", "readings", "samples", "messages", "parcels",
               "routes", "deliveries", "operators", "technicians", "languages", "channels", "percentile",
               "th", "st", "nd", "rd"}
NUMBER = re.compile(r"(?<![\w.\-/<'])(-?\d+(?:,\d{3})*(?:\.\d+)?)(?![\d])")


def _next_token(text: str, pos: int) -> tuple[str, str]:
    """(token immediately attached, next whitespace-separated token)."""
    attached = re.match(r"[^\s,;:)]*", text[pos:]).group(0)
    if not attached.rstrip("."):
        attached = ""                                  # sentence-final full stop
    rest = text[pos + len(attached):]
    nxt = re.match(r"\s*([^\s,;:()]+)", rest)
    return attached, (nxt.group(1) if nxt else "")


def _strip(tok: str) -> str:
    return tok.strip(".,;:()[]{}\"'")


def quantity_span(text: str, m: re.Match, unit: str | None) -> tuple[int, int, str]:
    """Span covering the number and its unit (attached or after one space)."""
    end = m.end()
    if unit:
        k = text.find(unit, m.end())
        if 0 <= k <= m.end() + 2:
            end = k + len(unit)
    return m.start(), end, text[m.start():end]


def _quantities(text: str):
    """Yield (match, unit_or_None, kind) for each number: kind in unit|count|bare|nonsi|skip."""
    for m in NUMBER.finditer(text):
        attached, nxt = _next_token(text, m.end())
        if attached:
            a = _strip(attached)
            if a.startswith("%") or a.startswith("°"):
                yield m, a, "unit"
                continue
            if a.startswith("-"):                      # 5-minute, 2-hour
                word = a[1:].lower().rstrip("s")
                yield m, a, ("unit" if word + "s" in UNITS or word in UNITS else "count")
                continue
            if a in UNITS:
                yield m, a, "unit"
                continue
            if a in NON_SI:
                yield m, a, "nonsi"
                continue
            yield m, None, "skip"                      # 95th, 3D, 2x, v2 ...
            continue
        n = _strip(nxt)
        if n in UNITS or n.lower() in UNITS or n.startswith("[") or n.startswith("%"):
            yield m, n, "unit"
        elif n in NON_SI or n.lower() in NON_SI:
            yield m, n, "nonsi"
        elif n.lower() in COUNT_WORDS or (len(n) > 3 and n.lower().endswith("s") and n.isalpha()):
            yield m, None, "count"
        elif 1900 <= abs(float(m.group(1).replace(",", ""))) <= 2100 and "." not in m.group(1):
            yield m, None, "skip"                      # a year
        else:
            yield m, None, "bare"


BOUND = re.compile(r"(?:\bat (?:least|most)\b|\bno (?:more|less|fewer|later|earlier|greater|wider|longer|"
                   r"heavier|higher|lower)\b|\bnot (?:more|less|exceed\w*)\b|\b(?:more|less|fewer|greater|"
                   r"higher|lower|wider|longer|shorter|heavier|lighter|faster|slower) than\b|\bup to\b|\bwithin\b|"
                   r"\bmaximum\b|\bminimum\b|\bmax\b|\bmin\b|\bor (?:more|less|fewer|better|higher|lower|faster|"
                   r"greater|longer|shorter)\b|\bexceed\w*\b|\bbelow\b|\babove\b|\bunder\b|\bover\b|\bbetween\b|"
                   r"±|\+/-|≤|≥|<=|>=|<|>|\btolerance\b|\baccuracy\b|\bpercentile\b|\bP\d\d\b|\bonce per\b)", re.I)


# -------------------------------------------------------------- rule checks -- #
WEAK_MODALS = _terms(["should", "will", "must", "may", "can", "could", "might", "needs to", "need to",
                      "is required to", "are required to", "has to", "have to"])


def c_shall(req, ctx):
    if SHALL.search(req.text):
        return []
    hits = _hits(WEAK_MODALS, req.text)
    return hits[:1] or [Hit(0, min(len(req.text), 30), req.text[:30])]


def c_multi(req, ctx):
    ms = list(SHALL.finditer(req.text))
    return [Hit(ms[1].start(), ms[1].end(), "shall ... shall", f"{len(ms)} 'shall's")] if len(ms) > 1 else []


COMB = re.compile(r"(?<![\w/-])(and|or|but|as well as|also|along with|in addition to|while|plus)(?![\w/-])", re.I)
COMB_OK_AFTER = re.compile(r"^\s*(more|less|fewer|better|higher|lower|faster|greater|longer|shorter|equal)\b", re.I)


def c_comb(req, ctx):
    t = req.text
    start = _after_shall(t)
    out = []
    for m in COMB.finditer(t, start):
        word = m.group(1).lower()
        before = t[max(0, m.start() - 40):m.start()].lower()
        if word == "and" and re.search(r"\bbetween\b[^,;]*$", before):
            continue                                  # between X and Y
        if word == "or" and COMB_OK_AFTER.match(t[m.end():]):
            continue                                  # 2 m or less
        if word in ("and", "or") and re.match(r"\s*/", t[m.end():]):
            continue
        if re.match(r"\s*shall\b", t[m.end():], re.I):
            continue                                  # '... and shall ...' is RL-MULTI's job
        out.append(Hit(m.start(), m.end(), m.group(0)))
    return out


ANDOR = re.compile(r"\band\s*/\s*or\b|\bor\s*/\s*and\b", re.I)


def c_andor(req, ctx):
    return _hits(ANDOR, req.text)


VAGUE = _terms(["appropriate", "appropriately", "adequate", "adequately", "sufficient", "sufficiently",
                "reasonable", "reasonably", "efficient", "efficiently", "effective", "effectively", "acceptable",
                "suitable", "suitably", "normal", "normally", "typical", "typically", "approximately", "roughly",
                "about", "around", "some", "several", "many", "few", "various", "numerous", "relevant",
                "significant", "significantly", "substantial", "substantially", "minimal", "large", "small",
                "high", "low", "fast", "slow", "enough", "good", "well", "better", "proper", "properly",
                "sensible", "nearly", "almost", "accurate", "accurately", "precise", "precisely", "generally", "usually", "mostly", "as much as", "a lot",
                "in a reasonable", "where relevant", "sufficient time", "etc"])


def c_vague(req, ctx):
    hits = []
    for h in _hits(VAGUE, req.text):
        w = h.evidence.lower()
        nxt = req.text[h.end:h.end + 12]
        if w in ("about", "around") and not re.match(r"\s*\d", nxt):
            continue                                  # 'about' as a preposition
        if w == "etc":
            continue                                  # RL-OPEN
        if w == "well" and req.text[max(0, h.start - 3):h.start].lower() == "as ":
            continue                                  # 'as well as' is RL-COMB's job
        hits.append(h)
    return hits


UNVERIF = _terms(["user-friendly", "user friendly", "easy", "easily", "simple", "simply", "intuitive",
                  "intuitively", "seamless", "seamlessly", "robust", "robustly", "reliable", "reliably", "secure",
                  "securely", "safe", "safely", "friendly", "attractive", "modern", "state-of-the-art",
                  "state of the art", "high-quality", "high quality", "best practice", "best practices",
                  "industry standard", "industry-standard", "maintainable", "scalable", "flexible", "comfortable",
                  "smart", "sustainable", "sustainably", "resilient", "convenient", "transparent", "accessible",
                  "fair", "ethical", "clean", "green", "nice", "pleasant", "smooth", "smoothly", "stable"])


def c_unverif(req, ctx):
    has_number = any(k == "unit" for _, _, k in _quantities(req.text))
    hits = _hits(UNVERIF, req.text)
    for h in hits:
        if has_number:
            h.severity = WARNING
            h.note = "a number is present: check it really measures this quality"
    return hits


SUPERL = re.compile(r"(?<![\w-])(?<!at )(?:best|worst|most|least|optimal|optimally|optimum|optimi[sz]\w*|maximi[sz]\w*|"
                    r"minimi[sz]\w*|highest|lowest|fastest|slowest|smallest|largest|greatest|ideal|ideally|"
                    r"perfect|perfectly|as \w+(?: \w+)? as possible|to the fullest|maximum possible|"
                    r"minimum possible)(?![\w-])", re.I)


def c_superl(req, ctx):
    return _hits(SUPERL, req.text)


ESCAPE = re.compile(r"(?<![\w-])(?:if|where|wherever|as far as|when|whenever) (?:possible|practical|practicable|"
                    r"feasible|appropriate|applicable|necessary|needed|required|reasonable)|as (?:appropriate|"
                    r"applicable|necessary|needed|required|practicable|possible|far as possible)|to the (?:extent|"
                    r"degree) (?:possible|practical|practicable|feasible)|unless otherwise (?:specified|agreed|"
                    r"directed|stated|noted)|subject to (?:availability|budget)|if (?:time|budget) (?:permits|allows)"
                    r"(?![\w-])", re.I)


def c_escape(req, ctx):
    return _hits(ESCAPE, req.text)


OPEN = re.compile(r"(?<![\w-])(?:etc\.?|et cetera|and so on|and so forth|including,? but not limited to|"
                  r"not limited to|such as|e\.g\.|for example|for instance|among others|and the like|and more|"
                  r"or similar|and other \w+|or other \w+)(?![\w-])", re.I)


def c_open(req, ctx):
    return _hits(OPEN, req.text)


IRREGULAR = {"sent", "shown", "made", "kept", "done", "given", "taken", "built", "set", "held", "known", "stored",
             "written", "seen", "run", "put", "found", "left", "read", "met", "sold", "told", "brought", "chosen",
             "driven", "flown", "drawn", "worn", "hidden", "broken", "spoken", "frozen", "bound", "fed", "led",
             "paid", "laid", "lit", "shut", "cut", "hit", "split", "spread", "struck", "thrown", "grown", "sewn",
             "won", "begun", "dealt", "meant", "felt", "lost", "sought", "taught", "caught", "bought", "fought"}
PASSIVE = re.compile(r"\bshall\s+(?:not\s+)?(?:be|have\s+been|been)\s+(?:\w+ly\s+)?([a-z]+)\b", re.I)


def c_passive(req, ctx):
    out = []
    for m in PASSIVE.finditer(req.text):
        w = m.group(1).lower()
        if w in ("able", "capable", "designed", "no", "not", "less", "more", "at", "within", "in", "on"):
            continue
        if w.endswith("ed") or w in IRREGULAR:
            tail = req.text[m.end():m.end() + 80]
            if re.match(r"^(?:[^.;]*?)\bby\b", tail):
                continue                               # agent named: 'shall be logged by the gateway'
            out.append(Hit(m.start(), m.end(), m.group(0)))
    return out


INFIN = re.compile(r"\bshall\s+(?:be\s+able\s+to|be\s+capable\s+of|have\s+the\s+(?:capability|ability|capacity)\s+to|"
                   r"be\s+designed\s+to|provide\s+(?:the\s+)?(?:ability|capability|means|functionality)\s+to|"
                   r"allow\s+(?:\w+\s+){0,3}to|enable\s+(?:\w+\s+){0,3}to|permit\s+(?:\w+\s+){0,3}to)", re.I)


def c_infin(req, ctx):
    return _hits(INFIN, req.text)


WEAKVERB = re.compile(r"\bshall\s+(?:\w+ly\s+)?(support|handle|facilitate|ensure|manage|address|accommodate|"
                      r"deal\s+with|consider|take\s+into\s+account|strive|aim|try|attempt|endeavou?r|seek)\b", re.I)


def c_weakverb(req, ctx):
    return [Hit(m.start(1), m.end(1), m.group(1)) for m in WEAKVERB.finditer(req.text)]


PRONOUN = _terms(["it", "its", "it's", "they", "them", "their", "theirs", "this", "these", "those", "he", "she",
                  "him", "her", "his", "hers", "we", "us", "our", "you", "your", "one's"])


def c_pronoun(req, ctx):
    out = []
    for h in _hits(PRONOUN, req.text):
        if h.evidence.lower() in ("us",) and req.text[h.start - 1:h.start] == ".":
            continue
        out.append(h)
    return out


NEG = re.compile(r"\bshall\s+not\b(?!\s+(?:exceed|be\s+(?:more|less|greater|longer|wider|higher|lower|heavier|"
                 r"larger|later|earlier)\s+than))|\bnever\b|\bno\s+longer\b|\bnot\s+(?:be\s+)?un\w+",
                 re.I)


def c_neg(req, ctx):
    return _hits(NEG, req.text)


def c_units(req, ctx):
    out = []
    for m, unit, kind in _quantities(req.text):
        if kind == "bare":
            out.append(Hit(m.start(), m.end(), m.group(0), "number with no unit"))
        elif kind == "nonsi":
            a, b, ev = quantity_span(req.text, m, unit)
            out.append(Hit(a, b, ev, "non-SI unit: state it in SI (metric)"))
    return out


def c_tol(req, ctx):
    q = [(m, u) for m, u, k in _quantities(req.text) if k == "unit"]
    if not q or BOUND.search(req.text):
        return []
    m, u = q[0]
    return [Hit(*quantity_span(req.text, m, u))]


TIME = re.compile(r"(?<![\w-])(?:soon|as soon as possible|asap|quickly|quick|promptly|prompt|immediately|"
                  r"immediate|instantly|instant|instantaneous(?:ly)?|in a timely (?:manner|fashion)|timely|"
                  r"real[- ]time|near[- ]real[- ]time|periodically|regularly|frequently|occasionally|eventually|"
                  r"rapidly|rapid|without delay|continuously|constantly|shortly|recently|often|sometimes|"
                  r"after a while|in good time|at all times|on time)(?![\w-])", re.I)


def c_time(req, ctx):
    return _hits(TIME, req.text)


SOLN_VERBS = re.compile(r"(?<![\w-])(?<!after )(?<!before )(?<!of )(?<!in )(?<!for )(?<!during )(?:use|uses|using|utili[sz]\w*|via|by means of|implemented (?:in|with|on|"
                        r"using)|built (?:on|with)|based on|powered by|running on)(?![\w-])", re.I)
SOLN_TECH = re.compile(r"(?<![\w-])(?:GPS|Bluetooth|BLE|Wi-?Fi|LoRa(?:WAN)?|5G|4G|LTE|Zigbee|Arduino|Raspberry Pi|"
                       r"ESP32|Python|Java|C\+\+|SQL|database|mobile app|app|cloud|AWS|Azure|LiDAR|lidar|"
                       r"cameras?|ultrasonic|blockchain|machine learning|neural network|deep learning|AI|Kalman|"
                       r"lithium|Li-ion|LFP|NMC|PLC|Android|iOS|web-based|web based|website|touchscreen|QR code|"
                       r"RFID|NFC|diesel generator|solar panels?)(?![\w-])")


def c_soln(req, ctx):
    return _hits(SOLN_VERBS, req.text) + [Hit(m.start(), m.end(), m.group(0)) for m in SOLN_TECH.finditer(req.text)]


KNOWN_ABBR = {"ID", "IDS", "SI", "UTC", "ISO", "IEC", "IEEE", "GNSS", "GPS", "NCR", "CR", "CCB", "ICD", "REQ",
              "TBD", "TBC", "TBR", "TODO", "USB", "AC", "DC", "PV", "IMU", "LED", "CSV", "PDF", "MW", "GW", "GB",
              "MB", "TB", "KB", "SMS", "CO", "UN", "EU", "CSA", "OK", "API", "CPU", "RAM", "OS", "UI", "HMI", "P95",
              "P99", "STRIDE", "FMEA", "FTA", "STPA", "MOE", "MOP", "TPM", "SYS", "RL", "ROM", "SN", "MG", "GN",
              "PS", "INT", "OBS", "DOC", "HYP", "TD", "RID", "AI", "ML", "WCAG", "AA", "AAA"}
ABBR = re.compile(r"(?<![\w-])([A-Z][A-Z0-9]{1,})(?![\w])")


def c_abbr(req, ctx):
    gloss = {g.upper() for g in (ctx.get("glossary") or set())}
    seen, out = set(), []
    for m in ABBR.finditer(req.text):
        a = m.group(1)
        if a.upper() in KNOWN_ABBR or a.upper() in gloss or a in seen or a.isdigit():
            continue
        if re.match(r"-\d", req.text[m.end():m.end() + 2]):
            continue                                   # an id prefix like REQ-04
        seen.add(a)
        out.append(Hit(m.start(), m.end(), a))
    return out


def c_rationale(req, ctx):
    if req.fields_present.get("rationale") and not (req.rationale or "").strip():
        return [Hit(0, 0, "(rationale empty)")]
    return []


METHOD = re.compile(r"^\s*(?:(?:test|analysis|inspection|demonstration|review(?:\s+of\s+design)?|rod|similarity|"
                    r"t|a|i|d|r)\b[\s,;/&+]*(?:and\s+)?)+$", re.I)


def c_verif(req, ctx):
    if not req.fields_present.get("verification"):
        return []
    v = (req.verification or "").strip()
    if not v:
        return [Hit(0, 0, "(verification method empty)")]
    if not METHOD.match(v):
        return [Hit(0, 0, v, "unrecognised method")]
    return []


def c_id(req, ctx):
    if not (req.id or "").strip() or req.id_generated:
        return [Hit(0, 0, "(no id)")]
    if ctx.get("duplicate_ids") and req.id in ctx["duplicate_ids"]:
        return [Hit(0, 0, req.id, "duplicate id")]
    return []


TBD = re.compile(r"(?<![\w-])(?:TBD|TBC|TBR|TODO|XXX|FIXME|to be (?:determined|confirmed|decided|defined|agreed))"
                 r"(?![\w-])|\?\?+|<[^>]{1,40}>|\[\s*(?:x+|\.\.\.|value|n)\s*\]", re.I)


def c_tbd(req, ctx):
    return _hits(TBD, req.text)


def c_long(req, ctx):
    n = len(re.findall(r"\b\w[\w'-]*\b", req.text))
    return [Hit(0, 0, f"{n} words")] if n > 40 else []


UNIV = _terms(["all", "every", "any", "always", "none", "anything", "everything", "everyone", "anyone",
               "whatever", "whenever", "wherever", "everywhere", "at all times", "in all cases", "under all conditions"])


def c_univ(req, ctx):
    return [h for h in _hits(UNIV, req.text)
            if not (h.evidence.lower() == "every" and re.match(r"\s+\d", req.text[h.end:]))]   # 'every 5 min'



LEAD_COND = re.compile(r"^\s*(?:when|if|while|during|after|before|once|on|upon|in|at|from|with|for|under|"
                       r"unless|until|derived from)\b[^,]*,\s*", re.I)


def c_subj(req, ctx):
    m = SHALL.search(req.text)
    if not m:
        return []
    head = LEAD_COND.sub("", req.text[:m.start()])
    head = re.sub(r"^[^:]{0,40}:\s*", "", head) if ":" in head else head    # 'Derived from REQ-04: the ...'
    words = re.findall(r"[A-Za-z][\w-]*", head)
    if not words:
        return [Hit(m.start(), m.end(), "shall", "nothing before 'shall'")]
    return []


SLASH = re.compile(r"(?<![\w/])([A-Za-z]{2,})/([A-Za-z]{2,})(?![\w/])")


def c_slash(req, ctx):
    out = []
    for m in SLASH.finditer(req.text):
        a, b = m.group(1), m.group(2)
        if f"{a}/{b}" in UNITS or (a in UNITS and b in UNITS) or {a.lower(), b.lower()} == {"and", "or"}:
            continue
        out.append(Hit(m.start(), m.end(), m.group(0)))
    return out


# --------------------------------------------------------------- catalogue -- #
RULES: list[Rule] = [
    Rule("RL-SHALL", ERROR, "Conforming", "Modal verb", "No 'shall'",
         "A binding requirement states its obligation with exactly one 'shall'; 'should', 'will', 'must' or "
         "'may' leave the reader guessing whether it is binding.",
         "Rewrite as '<subject> shall <verb> ...'. Put goals in a separate, labelled list.", c_shall),
    Rule("RL-MULTI", WARNING, "Singular", "Singularity", "More than one 'shall'",
         "Two obligations in one statement cannot be verified, traced or waived separately.",
         "Split into one requirement per 'shall', each with its own id.", c_multi),
    Rule("RL-COMB", WARNING, "Singular", "Singularity", "Combinator joins clauses",
         "'and', 'or', 'but', 'as well as' after the 'shall' often bundle two requirements or hide a choice.",
         "Split, or state the combination as one measurable condition; keep 'between X and Y' and '2 m or less'.",
         c_comb),
    Rule("RL-ANDOR", ERROR, "Unambiguous", "Non-ambiguity", "'and/or'",
         "'and/or' lets the reader pick either meaning, so two people verify different things.",
         "Decide: 'and' (both), 'or' (either) or 'at least one of'.", c_andor),
    Rule("RL-VAGUE", WARNING, "Unambiguous", "Precision", "Vague term",
         "Words like 'adequate', 'sufficient', 'fast', 'some' or 'several' have no agreed value.",
         "Replace the word with a quantity, a unit and a bound (e.g. 'within 10 s').", c_vague),
    Rule("RL-UNVERIF", ERROR, "Verifiable", "Precision", "Unverifiable quality",
         "Qualities like 'user-friendly', 'robust', 'safe' or 'intuitive' cannot pass or fail a test as written.",
         "Name the measure that shows the quality (task time, error rate, failure rate, stopping distance).",
         c_unverif),
    Rule("RL-SUPERL", WARNING, "Feasible", "Realism", "Superlative or optimisation",
         "'best', 'optimal', 'minimise' or 'as ... as possible' set no finish line; no design can be shown to meet it.",
         "State the threshold that is good enough, and put optimisation in the trade study.", c_superl),
    Rule("RL-ESCAPE", ERROR, "Verifiable", "Realism", "Escape clause",
         "'if possible', 'where practical', 'as appropriate' let the supplier decide whether the requirement applies.",
         "Delete the clause, or state the exact condition under which the requirement applies.", c_escape),
    Rule("RL-OPEN", ERROR, "Complete", "Completeness", "Open-ended list",
         "'etc.', 'such as', 'including' leave the list unbounded, so nobody knows when it is complete.",
         "List every item, or reference a controlled list (an ICD or table) by id.", c_open),
    Rule("RL-PASSIVE", WARNING, "Unambiguous", "Voice", "Passive voice without an agent",
         "'shall be logged' hides who or what does it, so responsibility and the verification subject are unclear.",
         "Make the responsible element the subject: 'The gateway shall log ...'.", c_passive),
    Rule("RL-INFIN", WARNING, "Verifiable", "Concision", "Superfluous infinitive",
         "'shall be able to', 'shall be capable of', 'shall allow X to' state a potential, not a behaviour you can test.",
         "Say what the subject shall do: 'shall stop within 1.5 m', not 'shall be able to stop'.", c_infin),
    Rule("RL-WEAKVERB", WARNING, "Unambiguous", "Precision", "Weak verb",
         "'support', 'handle', 'ensure', 'manage', 'facilitate' do not say what observable action is required.",
         "Use a verb whose result you can observe and measure (detect, transmit, store, stop, display).", c_weakverb),
    Rule("RL-PRONOUN", WARNING, "Unambiguous", "Non-ambiguity", "Pronoun",
         "'it', 'they', 'this' depend on context that disappears when the requirement is read on its own.",
         "Repeat the noun ('the robot', 'the gateway'). Each requirement must stand alone.", c_pronoun),
    Rule("RL-NEG", WARNING, "Verifiable", "Positive statement", "Negative statement",
         "'shall not ...' and 'never' describe an unbounded set of things to avoid, which is hard to verify.",
         "State the positive property to achieve; a bounded 'shall not exceed <value>' is acceptable.", c_neg),
    Rule("RL-UNITS", WARNING, "Unambiguous", "Quantification", "Number without unit (or non-SI unit)",
         "A bare number, or a non-SI unit, invites unit errors (the Mars Climate Orbiter lesson).",
         "Attach an SI unit to every quantity: '45 kg', '1.5 m', '10 s'.", c_units),
    Rule("RL-TOL", WARNING, "Verifiable", "Tolerance", "Value without bound or tolerance",
         "A single value ('shall weigh 10 kg') does not say whether 9.9 kg passes; tests need a limit or range.",
         "Use 'at least', 'no more than', 'within', 'between ... and ...' or 'nominal ± tolerance'.", c_tol),
    Rule("RL-TIME", WARNING, "Unambiguous", "Precision", "Ambiguous time word",
         "'immediately', 'quickly', 'real time', 'periodically' mean different durations to different readers.",
         "Give the time limit and what it is measured from: 'within 2 s of detection'.", c_time),
    Rule("RL-SOLN", INFO, "Appropriate", "Abstraction", "Possible solution in disguise",
         "Naming a technology or method ('using GPS', 'via an app') may fix the design before alternatives are traded.",
         "If it is a design choice, move it to the architecture; if a real constraint, cite who imposes it.", c_soln),
    Rule("RL-ABBR", INFO, "Comprehensible", "Uniformity", "Undefined abbreviation",
         "An acronym that is not in the glossary may mean different things to different readers.",
         "Define it in the project glossary (reqlint --glossary FILE) or spell it out.", c_abbr),
    Rule("RL-RATIONALE", WARNING, "Necessary", "Traceability", "Missing rationale",
         "Without a rationale, nobody can tell later why the value was chosen or whether it can change.",
         "Add one sentence: why this, why this value, and the evidence id (INT-/OBS-/DOC-/HYP-).", c_rationale),
    Rule("RL-VERIF", WARNING, "Verifiable", "Verification", "Missing or unrecognised verification method",
         "Every requirement needs a planned method so the verification matrix can be built.",
         "Name the method: Test, Analysis, Inspection or Demonstration (ECSS also lists Review of design).", c_verif),
    Rule("RL-ID", ERROR, "Traceable", "Uniqueness", "Missing or duplicate id",
         "A requirement without a unique id cannot be traced, verified or changed under control.",
         "Give each requirement a unique id with your team prefix (REQ-04, SN-007).", c_id),
    Rule("RL-TBD", WARNING, "Complete", "Completeness", "Placeholder (TBD/TBC/TODO)",
         "An open placeholder is a risk: it needs an owner and a closure date.",
         "Close it, or log it with an owner and date; placeholders are not allowed at the final gate.", c_tbd),
    Rule("RL-LONG", INFO, "Comprehensible", "Concision", "Long requirement",
         "More than about 40 words usually means several requirements or rationale mixed into the text.",
         "Move explanation to the rationale; split separate obligations.", c_long),
    Rule("RL-UNIV", WARNING, "Feasible", "Quantifiers", "Universal quantifier",
         "'all', 'any', 'always', 'every' claim more than any test can show and often hide exceptions.",
         "Use 'each' over a defined set, or bound the claim (conditions, percentile, duration).", c_univ),
    Rule("RL-SUBJ", ERROR, "Complete", "Completeness", "No subject before 'shall'",
         "The requirement does not say which entity carries the obligation.",
         "Start with the responsible element: 'The <system or element> shall ...'.", c_subj),
    Rule("RL-SLASH", WARNING, "Unambiguous", "Non-ambiguity", "Slash between words",
         "'sensor/camera' could mean either, both or one thing called by two names.",
         "Write 'and' or 'or' explicitly, or pick one term.", c_slash),
]
RULES_BY_ID = {r.id: r for r in RULES}
