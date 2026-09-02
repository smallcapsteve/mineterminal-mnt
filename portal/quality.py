"""Ingestion-time quality gate.

Call `reason_to_skip(summary)` after fetch_body. If it returns a non-empty
string, the event should not be ingested — the caller may log the reason
and move on.
"""
from __future__ import annotations
import re
from typing import Optional
from urllib.parse import urlparse

# ---------- language detection ----------

# French stopwords / function words that almost never appear in English PRs
_FR_WORDS = {
    "les", "des", "une", "pour", "dans", "avec", "sont", "plus", "cette",
    "nous", "vous", "leur", "leurs", "entre", "aux", "ses", "ces",
    "mais", "avoir", "être", "fait", "faire", "cet", "sur", "aussi",
    "encore", "sans", "après", "avant", "contre", "chez", "jusqu",
    "parce", "puisque", "société", "communiqué", "président", "diffusion",
    "exploration", "entreprise", "résultat", "résultats", "aujourd", "depuis",
    "annonce", "annoncent", "annonçait", "porteurs", "actionnaires",
    "financement", "offre", "placement", "courtier", "courtiers",
    "réalisation", "clôture", "clôturé", "conformément", "souscription",
}

# English stopwords — we weight their appearance to avoid false-positives on
# releases that happen to contain a few French words (e.g. a Quebec property name).
_EN_WORDS = {
    "the", "and", "that", "with", "this", "have", "will", "from", "company",
    "announcement", "shareholder", "shareholders", "board", "results",
    "quarter", "revenue", "chief", "president", "press", "release",
    "announces", "pleased", "today", "closing", "offering",
}

_FRENCH_URL_RE = re.compile(r"(?:[-_/])(french|francais|fr)(?:[-_/]|$)", re.I)
_FRENCH_HEADLINE_RE = re.compile(
    r"\b(?:annonce|annoncent|clôture|conformément|porteurs|placement privé|"
    r"offre publique|courtier|courtiers|plan d['’]|souscription)\b",
    re.I,
)


def _token_counts(text: str) -> tuple[int, int]:
    tokens = [t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ']+", text)]
    fr = sum(1 for t in tokens if t in _FR_WORDS)
    en = sum(1 for t in tokens if t in _EN_WORDS)
    return fr, en


def is_french(headline: str, body: str, source_url: str = "") -> bool:
    if source_url and _FRENCH_URL_RE.search(source_url):
        return True
    h = headline or ""
    if h and _FRENCH_HEADLINE_RE.search(h):
        return True
    text = h + "\n" + (body or "")
    if not text.strip():
        return False
    fr, en = _token_counts(text[:4000])
    # More French stopwords than English → likely French.
    # Guard: require at least 3 French hits to avoid noise on short bodies.
    return fr >= 3 and fr > en


# ---------- substantive-body detection ----------

_ARCHIVE_TEASER_RE = re.compile(
    r'(?:class="entry-title"|"more-link"|"read-more"|>read more<|'
    r'class="post-content-inner"|class="post-archive")',
    re.I,
)

_TEASER_TAIL_RE = re.compile(r"\.\.\.\s*(?:read\s+more)?\s*$", re.I)


def is_substantive(headline: str, body: str, raw_html: str = "") -> tuple[bool, str]:
    """Return (ok, reason). body must be ≥ ~400 chars of real content."""
    h = (headline or "").strip()
    b = (body or "").strip()
    if not b:
        return False, "empty body"
    # Compare clean (lowered, whitespace-squashed) strings
    def _norm(s):
        return re.sub(r"\s+", " ", s.lower()).strip()
    nb = _norm(b)
    nh = _norm(h)
    # Drop headline from body for length measurement
    nb_nohd = nb.replace(nh, "", 1).strip()
    if len(nb_nohd) < 350:
        return False, f"short body ({len(nb_nohd)} chars after headline)"
    if _TEASER_TAIL_RE.search(b[-200:]):
        return False, "teaser tail (...read more)"
    if raw_html and _ARCHIVE_TEASER_RE.search(raw_html[:4000]):
        return False, "archive/teaser markup"
    return True, ""


# ---------- external-URL detection ----------

def _host(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
        if h.startswith("www."):
            h = h[4:]
        return h
    except Exception:
        return ""


def _registrable(host: str) -> str:
    """Return the registrable (~eTLD+1) portion for subdomain-tolerant matching.
    Naive two-label heuristic — good enough for corporate sites."""
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    # handle a few compound TLDs we actually see
    last2 = ".".join(parts[-2:])
    if last2 in ("co.uk", "com.au", "co.nz", "co.za", "com.mx", "com.br"):
        return ".".join(parts[-3:])
    return last2


# Wire-service hosts: legitimate AS source for wire adapters (newsfile/cnw/etc.),
# but NEVER for company_ir_wp / companysite (those should point to the company's IR page).
_WIRE_HOSTS = {
    "globenewswire.com", "prnewswire.com", "newsfilecorp.com",
    "accesswire.com", "accessnewswire.com", "businesswire.com",
    "newswire.ca",
}
# Aggregator / social / news-portal hosts: never a company IR site, always reject.
_AGGREGATOR_HOSTS = {
    "youtube.com", "youtu.be", "twitter.com", "x.com", "linkedin.com",
    "facebook.com", "instagram.com", "tiktok.com", "threads.net",
    "vimeo.com", "soundcloud.com", "spotify.com",
    "news.metal.com", "kitco.com", "junior-mining.com", "mining.com",
    "seekingalpha.com", "yahoo.com", "finance.yahoo.com",
    "stockwatch.com", "stockhouse.com", "ceo.ca",
}
# Adapters whose source_url is expected to be on a wire host
_WIRE_ADAPTERS = {"newsfile", "cnw", "accesswire", "globenewswire",
    "businesswire", "prnewswire",
}
# Back-compat alias (some code may still import this)
_BLOCKED_HOSTS = _AGGREGATOR_HOSTS | _WIRE_HOSTS


def is_external_to_site(summary: dict) -> Optional[str]:
    """Reject events whose source_url host is obviously not the company IR site.

    Compares summary['source_url'] host to the adapter-injected _cfg_website
    host at the registrable-domain level (subdomains OK). Also blocks a fixed
    list of social / aggregator / wire hosts that are never valid IR sites.
    """
    src_url = (summary.get("source_url") or "").strip()
    if not src_url:
        return None  # let is_substantive handle it
    src_host = _host(src_url)
    if not src_host:
        return None
    src_name = (summary.get("_source_name") or "").strip().lower()
    # Aggregators/social are always blocked regardless of adapter
    if src_host in _AGGREGATOR_HOSTS:
        return f"external host: {src_host}"
    # Wire hosts are blocked only when adapter expects a company-IR URL
    if src_host in _WIRE_HOSTS and src_name not in _WIRE_ADAPTERS:
        return f"external host: {src_host}"
    # Wire adapters (newsfile/cnw/etc.) publish from the wire by definition;
    # don't compare the wire host to the cfg's company website.
    if src_name in _WIRE_ADAPTERS:
        return None
    cfg_site = (summary.get("_cfg_website") or "").strip()
    if not cfg_site:
        return None  # no ground truth to compare against
    cfg_host = _host(cfg_site)
    if not cfg_host:
        return None
    if _registrable(src_host) == _registrable(cfg_host):
        return None
    return f"source_url host {src_host} != cfg website {cfg_host}"


# ---------- generic-article detection ----------

# URL slug patterns that almost always indicate educational / blog content
# rather than a dated news release
_GENERIC_URL_RE = re.compile(
    r"/(?:"
    r"what-is-[a-z0-9-]+|"
    r"what-are-[a-z0-9-]+|"
    r"how-to-[a-z0-9-]+|"
    r"guide-to-[a-z0-9-]+|"
    r"[a-z0-9-]+-guide(?:-[a-z0-9-]+)?|"
    r"step-by-step-[a-z0-9-]+|"
    r"energy-transition-[a-z0-9-]+|"
    r"project-development-[a-z0-9-]+|"
    r"understanding-[a-z0-9-]+|"
    r"introduction-to-[a-z0-9-]+|"
    r"the-role-of-[a-z0-9-]+|"
    r"future-of-[a-z0-9-]+"
    r")(?:/|$)",
    re.I,
)

# Headline patterns for educational content
_GENERIC_HEADLINE_RE = re.compile(
    r"^\s*(?:"
    r"what\s+(?:is|are)\b|"
    r"how\s+(?:to|does|do)\b|"
    r"(?:a\s+)?(?:beginner['']?s\s+)?guide\s+to\b|"
    r"(?:the\s+)?(?:complete|ultimate|essential)\s+guide\b|"
    r"understanding\s+[a-z]|"
    r"introduction\s+to\b|"
    r"the\s+role\s+of\b|"
    r"(?:the\s+)?future\s+of\b|"
    r"step\s*[-]?\s*by\s*[-]?\s*step\b|"
    r"everything\s+you\s+need\s+to\s+know\b"
    r")",
    re.I,
)


def is_generic_article(headline: str, source_url: str) -> Optional[str]:
    """Reject events that look like blog/educational articles, not news releases."""
    url = source_url or ""
    h = headline or ""
    if url and _GENERIC_URL_RE.search(url):
        return f"generic article URL slug"
    if h and _GENERIC_HEADLINE_RE.search(h):
        return f"generic article headline"
    return None


# ---------- combined gate ----------

def reason_to_skip(summary: dict) -> Optional[str]:
    """Return a short reason string if the event should be skipped, else None."""
    headline = summary.get("raw_headline", "") or ""
    body = summary.get("raw_body", "") or ""
    raw_html = summary.get("raw_html", "") or ""
    source_url = summary.get("source_url", "") or ""
    # External-URL check first (fast, no body needed)
    why_ext = is_external_to_site(summary)
    if why_ext:
        return why_ext
    # Generic-article check (URL + headline only)
    why_gen = is_generic_article(headline, source_url)
    if why_gen:
        return why_gen
    if is_french(headline, body, source_url):
        return "french/non-english"
    ok, why = is_substantive(headline, body, raw_html)
    if not ok:
        return why
    return None


# _GENERIC_HEADLINE_V2_PATCH — append-only additional patterns caught from
# GDN.CN content-marketing purge. This supplements (does not replace) the
# existing _GENERIC_HEADLINE_RE check via a separate function.
import re as _re_gh2

_GENERIC_HEADLINE_V2_RE = _re_gh2.compile(
    r"(?:"
    r"^\s*why\s+[a-z][a-z\s-]{3,60}\s+matters?\s*\??\s*$|"
    r"^\s*what\s+makes\s+[a-z]|"
    r"^\s*what\s+drives\s+[a-z]|"
    r"\bexplained\s*\??\s*$|"
    r"\s+explained\s*$|"
    r"\bmatters?\s*\??\s*$|"
    r"^\s*countdown\s+to\b|"
    r"^\s*(?:invest|investing)\s+in\b|"
    r"\btapping\s+into\b|"
    r"^\s*a\s+proactive\s+approach\b|"
    r"^\s*a\s+deep\s+dive\s+into\b|"
    r"^\s*empowering\s+[a-z]|"
    r"^\s*golden\s+opportunity\b|"
    r"\bmodel\s*$|"
    r"\bstrategy\s+that\s+holds\s+up\s*$|"
    r"\bsurpasses\b|"
    r"^\s*(?:junior\s+)?mining\s+stocks\b|"
    r"\s+that\s+holds\s+up\s*\??\s*$|"
    r"\s+meaning\s+explained\s*$"
    r")",
    _re_gh2.I,
)

# Re-wrap the existing is_generic_article so both V1 and V2 patterns apply
_v2_prev_is_generic_article = is_generic_article

def is_generic_article(headline, source_url):  # noqa: F811
    v1 = _v2_prev_is_generic_article(headline, source_url)
    if v1 is not None:
        return v1
    h = headline or ""
    if h and _GENERIC_HEADLINE_V2_RE.search(h):
        return "generic article headline (v2)"
    return None
# END _GENERIC_HEADLINE_V2_PATCH

# _GERMAN_LANG_PATCH — append-only German detection. Matches the V2_PATCH
# convention above: extends the existing reason_to_skip without replacing it.
# Discovered events: BAR/EPG/BATT/GRUV had German releases ingested because
# the language gate only checked French.
import re as _re_de

_DE_WORDS = {
    "der", "die", "das", "und", "ein", "eine", "einen", "einer", "eines",
    "dem", "den", "des", "wir", "sind", "ist", "wird", "werden", "wurde",
    "wurden", "von", "mit", "bei", "aus", "auf", "fuer", "für", "uber",
    "über", "sowie", "noch", "schon", "gegen", "ohne", "oder", "aber",
    "weil", "damit", "dass", "dies", "diese", "dieser", "dieses", "nicht",
    "nach", "vor", "zwischen", "unter", "sich", "gemeinsam", "heute",
    "heutigen", "heutige", "rechnung", "jahr", "jahres", "quartal",
    "quartals", "aktionär", "aktionäre", "aktionärs", "aktionären",
    "aktien", "gesellschaft", "vorstand", "aufsichtsrat", "unternehmen",
    "kapital", "beschluss", "beschlüsse", "bekanntmachung",
    "bekanntmachungen", "meldepflichtige", "wertpapier", "wertpapiere",
    "vorläufige", "endgültige", "ergebnisse", "meldung", "mitteilung",
    "mitteilungen", "platzierung", "wertpapierprospekt", "geht", "gibt",
    "bekannt", "ankündigung", "erwerb", "voran",
}

# Headline-only triggers — almost certainly German if any of these appear
_DE_HEADLINE_RE = _re_de.compile(
    r"\b(?:Bekanntmachung|Mitteilung|Meldepflichtige|Wertpapierprospekt|"
    r"Aktionär|Aktionäre|Hauptversammlung|Vorstand|Aufsichtsrat|"
    r"gemäß|gemäss|Platzierung|Stimmrechtsmitteilung|"
    r"hochauflösende|geophysikalische|Untersuchungen|Zuteilung|"
    r"Erwerb|gibt\s+\w+\s+bekannt)\b",
    _re_de.I,
)

_DE_URL_RE = _re_de.compile(r"(?:^|/)(?:german|deutsch|de|de-DE|de_DE)(?:/|$)", _re_de.I)


def is_german(headline: str, body: str, source_url: str = "") -> bool:
    if source_url and _DE_URL_RE.search(source_url):
        return True
    h = headline or ""
    if h and _DE_HEADLINE_RE.search(h):
        return True
    text = h + "\n" + (body or "")
    if not text.strip():
        return False
    tokens = [t.lower() for t in _re_de.findall(r"[A-Za-zÀ-ÿß']+", text[:4000])]
    de = sum(1 for t in tokens if t in _DE_WORDS)
    en = sum(1 for t in tokens if t in _EN_WORDS)
    # Require at least 3 German hits and more German than English to avoid
    # noise on short bodies / property names containing "der" etc.
    return de >= 3 and de > en


# Re-wrap reason_to_skip so the German check runs after French
_de_prev_reason_to_skip = reason_to_skip

def reason_to_skip(summary):  # noqa: F811
    why = _de_prev_reason_to_skip(summary)
    if why is not None:
        return why
    headline = summary.get("raw_headline", "") or ""
    body = summary.get("raw_body", "") or ""
    source_url = summary.get("source_url", "") or ""
    if is_german(headline, body, source_url):
        return "german/non-english"
    return None
# END _GERMAN_LANG_PATCH
