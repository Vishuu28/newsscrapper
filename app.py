from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import html
import os
import re
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

COUNTRIES = ["india", "egypt", "hongcong"]
COUNTRY_LABELS = {"india": "India", "egypt": "Egypt", "hongcong": "Hong Kong"}

LANGUAGE_MODES = ["any", "english", "local"]
LANGUAGE_LABELS = {"any": "No language filter", "english": "English news", "local": "Local language news"}

REGION_CITY_FILTERS = {
    "india": {
        "regions": [
            {
                "name": "North India",
                "query_terms": ["north india", "delhi", "chandigarh", "lucknow", "jaipur", "punjab", "haryana", "uttar pradesh"],
                "cities": ["Delhi", "Lucknow", "Jaipur", "Chandigarh"],
            },
            {
                "name": "South India",
                "query_terms": ["south india", "bengaluru", "hyderabad", "chennai", "kochi", "kerala", "karnataka", "tamil nadu"],
                "cities": ["Bengaluru", "Hyderabad", "Chennai", "Kochi"],
            },
            {
                "name": "West India",
                "query_terms": ["west india", "mumbai", "pune", "ahmedabad", "goa", "maharashtra", "gujarat"],
                "cities": ["Mumbai", "Pune", "Ahmedabad", "Surat"],
            },
            {
                "name": "East India",
                "query_terms": ["east india", "kolkata", "bhubaneswar", "patna", "west bengal", "odisha", "bihar"],
                "cities": ["Kolkata", "Bhubaneswar", "Patna"],
            },
            {
                "name": "Central India",
                "query_terms": ["central india", "indore", "bhopal", "nagpur", "madhya pradesh", "chhattisgarh"],
                "cities": ["Indore", "Bhopal", "Nagpur"],
            },
            {
                "name": "North East India",
                "query_terms": ["north east india", "guwahati", "assam", "meghalaya", "mizoram", "tripura"],
                "cities": ["Guwahati", "Shillong"],
            },
        ],
        "cities": ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Chennai", "Kolkata", "Pune", "Ahmedabad"],
    },
    "egypt": {
        "regions": [
            {
                "name": "Greater Cairo",
                "query_terms": ["greater cairo", "cairo", "giza"],
                "cities": ["Cairo", "Giza"],
            },
            {
                "name": "Nile Delta",
                "query_terms": ["nile delta", "alexandria", "mansoura", "tanta"],
                "cities": ["Alexandria", "Mansoura", "Tanta"],
            },
            {
                "name": "Upper Egypt",
                "query_terms": ["upper egypt", "luxor", "aswan", "minya"],
                "cities": ["Luxor", "Aswan", "Minya"],
            },
            {
                "name": "Suez Region",
                "query_terms": ["suez region", "suez", "port said", "ismailia"],
                "cities": ["Suez", "Port Said", "Ismailia"],
            },
            {
                "name": "Sinai",
                "query_terms": ["sinai", "sharm el-sheikh", "north sinai", "south sinai"],
                "cities": ["Sharm El-Sheikh", "Arish"],
            },
        ],
        "cities": ["Cairo", "Alexandria", "Giza", "Port Said", "Suez", "Luxor", "Aswan"],
    },
    "hongcong": {
        "regions": [
            {
                "name": "Hong Kong Island",
                "query_terms": ["hong kong island", "central", "wan chai", "causeway bay"],
                "cities": ["Central", "Wan Chai", "Causeway Bay"],
            },
            {
                "name": "Kowloon",
                "query_terms": ["kowloon", "tsim sha tsui", "mong kok", "kwun tong"],
                "cities": ["Tsim Sha Tsui", "Mong Kok", "Kwun Tong"],
            },
            {
                "name": "New Territories",
                "query_terms": ["new territories", "sha tin", "yuen long", "tsuen wan"],
                "cities": ["Sha Tin", "Yuen Long", "Tsuen Wan"],
            },
            {
                "name": "Outlying Islands",
                "query_terms": ["outlying islands", "lantau", "tung chung", "cheung chau"],
                "cities": ["Tung Chung", "Cheung Chau"],
            },
        ],
        "cities": ["Central", "Wan Chai", "Tsim Sha Tsui", "Mong Kok", "Sha Tin", "Yuen Long", "Tung Chung"],
    },
}

# Country + language edition for Google News RSS.
NEWS_REGION_BY_LANGUAGE = {
    "india": {
        "english": {"hl": "en-IN", "gl": "IN", "ceid": "IN:en", "accept": "en-IN,en;q=0.9"},
        "local": {"hl": "hi-IN", "gl": "IN", "ceid": "IN:hi", "accept": "hi-IN,hi;q=0.9,en;q=0.6"},
    },
    "egypt": {
        "english": {"hl": "en-EG", "gl": "EG", "ceid": "EG:en", "accept": "en-EG,en;q=0.9"},
        "local": {"hl": "ar-EG", "gl": "EG", "ceid": "EG:ar", "accept": "ar-EG,ar;q=0.9,en;q=0.5"},
    },
    "hongcong": {
        "english": {"hl": "en-HK", "gl": "HK", "ceid": "HK:en", "accept": "en-HK,en;q=0.9"},
        "local": {"hl": "zh-HK", "gl": "HK", "ceid": "HK:zh-Hant", "accept": "zh-HK,zh-Hant;q=0.9,en;q=0.5"},
    },
}

INDICES = ["bev", "fmcg", "cig", "drug", "food", "soft drink", "baby food"]
# "any" = no trend token in query or scoring (broad sector + country only).
TRENDS = ["any", "rising", "falling", "stable"]
TREND_LABELS = {
    "any": "Any / no trend filter",
    "rising": "Rising",
    "falling": "Falling",
    "stable": "Stable",
}

MAX_RESULTS_ALLOWED = (15, 20, 28, 35, 45)
DURATIONS = {
    "3 months": 90,
    "6 months": 180,
    "1 year": 365,
    "3 year": 1095,
}

INDEX_EXPANSIONS = {
    "bev": "beverage OR beverages OR drinks",
    "fmcg": "FMCG OR fast moving consumer goods",
    "cig": "cigarette OR tobacco",
    "drug": "pharma OR pharmaceutical OR medicine",
    "food": "food industry OR packaged food",
    "soft drink": "soft drink OR soda",
    "baby food": "baby food OR infant nutrition",
}

TREND_SYNONYMS = {
    "rising": ["rising", "growth", "increase", "surge", "gains", "climb", "expansion", "upward"],
    "falling": ["falling", "decline", "decrease", "drop", "slump", "contraction", "downward", "plunge"],
    "stable": ["stable", "steady", "flat", "unchanged", "plateau", "consistent"],
}

# Scoring boosts — use token_matches() so short tokens (e.g. "hk") do not match inside unrelated words.
COUNTRY_HINTS = {
    "india": ["india", "indian", "delhi", "mumbai", "bangalore", "bengaluru", "chennai", "kolkata", "hyderabad"],
    "egypt": ["egypt", "egyptian", "cairo", "alexandria", "giza"],
    "hongcong": [
        "hong kong",
        "hongkong",
        "kowloon",
        "hksar",
        "new territories",
        "lantau",
        "tsuen wan",
        "sha tin",
        "yuen long",
    ],
}

# At least one phrase must appear in title or description (stops India-heavy wire stories in HK/Egypt feeds).
COUNTRY_ANCHORS = {
    "india": [
        "india",
        "indian",
        "mumbai",
        "delhi",
        "bengaluru",
        "bangalore",
        "chennai",
        "hyderabad",
        "kolkata",
        "pune",
        "gurgaon",
        "gurugram",
        "noida",
        "ahmedabad",
    ],
    "egypt": ["egypt", "egyptian", "cairo", "alexandria", "giza", "suez", "luxor", "aswan", "sharm el-sheikh"],
    "hongcong": [
        "hong kong",
        "hongkong",
        "kowloon",
        "hksar",
        "new territories",
        "lantau",
        "tsim sha tsui",
        "wan chai",
        "central district",
        "香港",
        "港島",
    ],
}

# When searching for one country, strongly down-rank obvious other-region stories.
CROSS_REGION_DEBITS = {
    "hongcong": [
        "india",
        "indian",
        "mumbai",
        "delhi",
        "bengaluru",
        "bangalore",
        "chennai",
        "kolkata",
        "hyderabad",
        "modi",
        "rupee",
        "sensex",
        "nse",
        "bse",
        "new delhi",
    ],
    "egypt": [
        "india",
        "mumbai",
        "delhi",
        "bangalore",
        "bengaluru",
        "hong kong",
        "hongkong",
        "kowloon",
        "hksar",
    ],
    "india": [
        "cairo",
        "giza",
        "alexandria",
        "hong kong",
        "hongkong",
        "kowloon",
        "hksar",
    ],
}

COUNTRY_QUOTED = {
    "india": '"India"',
    "egypt": '"Egypt"',
    "hongcong": '"Hong Kong"',
}

def get_news_region(country: str, language_mode: str) -> dict:
    country_cfg = NEWS_REGION_BY_LANGUAGE.get(country, NEWS_REGION_BY_LANGUAGE["india"])
    return country_cfg.get(language_mode, country_cfg["english"])


def get_region_config(country: str, region_name: str) -> dict | None:
    country_cfg = REGION_CITY_FILTERS.get(country, {})
    for region in country_cfg.get("regions", []):
        if region.get("name", "").lower() == (region_name or "").strip().lower():
            return region
    return None


def normalize_location_filters(country: str, region: str, city: str) -> tuple[str, str, list[str]]:
    region = (region or "").strip()
    city = (city or "").strip()
    region_cfg = get_region_config(country, region) if region else None
    if region and not region_cfg:
        region = ""
    if region_cfg and city:
        valid_cities = {c.lower() for c in region_cfg.get("cities", [])}
        if city.lower() not in valid_cities:
            city = ""
    region_terms = region_cfg.get("query_terms", []) if region_cfg else ([region] if region else [])
    return region, city, region_terms


def news_headers(country: str, language_mode: str = "english") -> dict:
    base = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    region = get_news_region(country, language_mode)
    base["Accept-Language"] = region.get("accept", "en-US,en;q=0.9")
    return base


def build_query(
    country: str,
    industry_index: str,
    trend: str,
    extra_terms: str,
    region_terms: list[str] | None = None,
    city: str = "",
) -> str:
    if industry_index in ("", "any", "all"):
        index_terms = "consumer market OR retail OR industry"
    else:
        index_terms = INDEX_EXPANSIONS.get(industry_index.lower(), industry_index)
    quoted = COUNTRY_QUOTED.get(country, country)
    location_bits = []
    if region_terms:
        location_bits.extend(f'"{r.strip()}"' for r in region_terms[:3] if r.strip())
    if city:
        location_bits.append(f'"{city.strip()}"')
    location_query = f" {' '.join(location_bits)}" if location_bits else ""
    trend_key = trend.strip().lower()
    if trend_key in ("", "any", "none"):
        base = f"{quoted}{location_query} ({index_terms})"
    else:
        base = f"{quoted}{location_query} ({index_terms}) {trend.strip()}"
    base = re.sub(r"\s+", " ", base).strip()
    extra = " ".join(t for t in extra_terms.split() if t)
    if extra:
        return f"{base} {extra}"
    return base


def clean_html_text(raw: str) -> str:
    cleaned = BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def sentence_split(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 25]


def summarize_text(text: str, max_sentences: int = 2) -> str:
    sentences = sentence_split(text)
    if not sentences:
        return "Summary unavailable."
    return " ".join(sentences[:max_sentences])


def parse_rss_items(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "").strip()
        description = clean_html_text(item.findtext("description") or "")
        if title and link:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "published": pub_date,
                    "source": source,
                    "description": description,
                }
            )
    return items


def _norm_words(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _phrase_in(haystack: str, phrase: str) -> bool:
    if len(phrase) < 2:
        return False
    return phrase.lower() in haystack.lower()


def token_matches(text: str, phrase: str) -> bool:
    """Multi-word: substring. Long single token (5+): substring. Short tokens: word boundaries (avoids 'food' in 'seafood', 'hk' in 'Bangkok')."""
    phrase = phrase.strip().lower()
    if not phrase or len(phrase) < 2:
        return False
    lowered = text.lower()
    if " " in phrase:
        return phrase in lowered
    if len(phrase) >= 5:
        return phrase in lowered
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", lowered))


def build_scoring_profile(
    country: str,
    industry_index: str,
    trend: str,
    user_keywords: str,
    region_terms: list[str] | None = None,
    city: str = "",
) -> tuple[list[tuple[str, float, float]], list[str]]:
    """
    Returns (weighted_terms, industry_or_terms) where each tuple is
    (lowercase phrase, title_weight, description_weight).
    """
    weighted: list[tuple[str, float, float]] = []
    if industry_index in ("", "any", "all"):
        or_chunks = ["market", "industry", "retail", "business"]
        for generic in or_chunks:
            weighted.append((generic, 0.8, 0.45))
    else:
        industry_raw = INDEX_EXPANSIONS.get(industry_index.lower(), industry_index)
        or_chunks = [c.strip(" ()") for c in re.split(r"\s+OR\s+", industry_raw, flags=re.I) if c.strip()]
    for chunk in or_chunks:
        c = chunk.strip().lower()
        if len(c) >= 2:
            weighted.append((c, 2.2, 1.2))

    for hint in COUNTRY_HINTS.get(country, []):
        weighted.append((hint.lower(), 3.2, 1.7))

    trend_key = trend.strip().lower()
    if trend_key not in ("", "any", "none"):
        for syn in TREND_SYNONYMS.get(trend_key, [trend_key]):
            weighted.append((syn.lower(), 1.6, 0.9))

    for region_term in region_terms or []:
        rt = region_term.strip().lower()
        if rt:
            weighted.append((rt, 3.1, 1.7))
    if city:
        weighted.append((city.strip().lower(), 3.8, 2.0))

    for raw in re.split(r"[,;]+|\s+", user_keywords or ""):
        w = raw.strip().lower()
        if len(w) >= 2:
            weighted.append((w, 3.0, 1.6))

    return weighted, or_chunks


def relevance_score(title: str, description: str, profile: list[tuple[str, float, float]]) -> float:
    t = _norm_words(title)
    d = _norm_words(description)
    score = 0.0
    for phrase, wt, wd in profile:
        if not phrase:
            continue
        if token_matches(t, phrase):
            score += wt
        elif token_matches(d, phrase):
            score += wd
    return score


def cross_region_penalty(country: str, title: str, description: str) -> float:
    blob = _norm_words(f"{title} {description}")
    debit = 0.0
    for term in CROSS_REGION_DEBITS.get(country, []):
        if token_matches(blob, term):
            debit += 5.0 if len(term) >= 5 else 3.5
    return debit


TITLE_OTHER_REGION = {
    "hongcong": [
        "thailand",
        "bangkok",
        "philippines",
        "manila",
        "vietnam",
        "singapore",
        "jakarta",
        "indonesia",
        "malaysia",
        "taiwan",
        "taipei",
        "south korea",
        "seoul",
        "japan",
        "tokyo",
        "australia",
        "sydney",
        "melbourne",
        "india",
        "mumbai",
        "delhi",
        "bengaluru",
        "bangalore",
        "chennai",
        "kolkata",
        "hyderabad",
        "houston",
        " texas",
        "canada",
        "united states",
        "u.s.",
    ],
    "egypt": [
        "thailand",
        "bangkok",
        "hong kong",
        "kowloon",
        "singapore",
        "dubai",
        "uae",
        "saudi",
        "riyadh",
        "morocco",
        "india",
        "mumbai",
        "delhi",
        "bengaluru",
        "bangalore",
    ],
}


HK_IN_TEXT = re.compile(
    r"hong\s*kong|hongkong|kowloon|hksar|new territories|lantau|香港|港島",
    re.IGNORECASE,
)
EGYPT_IN_TEXT = re.compile(
    r"egypt|egyptian|cairo|alexandria|giza|suez|luxor|aswan|القاهرة|مصر",
    re.IGNORECASE,
)


def hk_lead_snippet_foreign_only(title: str) -> bool:
    """True if the headline opens about another region and does not name HK early (stops Thailand-led wires)."""
    lead = (title or "")[:110].lower()
    if HK_IN_TEXT.search(lead):
        return False
    foreign_opens = (
        "thailand",
        "bangkok",
        "philippines",
        "manila",
        "vietnam",
        "jakarta",
        "seoul",
        "tokyo",
        "mumbai",
        "delhi",
        "bangalore",
        "bengaluru",
        "kolkata",
        "chennai",
        "hyderabad",
        "singapore",
        "taipei",
        "kuala lumpur",
    )
    return any(f in lead for f in foreign_opens)


def hk_title_is_exclusively_other_region(title: str) -> bool:
    """Drop titles clearly about another country when they never name HK (stops India/Thailand wires)."""
    if HK_IN_TEXT.search(title):
        return False
    tl = _norm_words(title).lower()
    blocks = [
        "thailand",
        "bangkok",
        "philippines",
        "manila",
        "vietnam",
        "singapore",
        "jakarta",
        "indonesia",
        "malaysia",
        "taiwan",
        "taipei",
        "south korea",
        "seoul",
        "japan",
        "tokyo",
        "india",
        "mumbai",
        "delhi",
        "bengaluru",
        "bangalore",
        "chennai",
        "kolkata",
        "hyderabad",
    ]
    return any(b in tl for b in blocks)


def eg_title_is_exclusively_other_region(title: str) -> bool:
    if EGYPT_IN_TEXT.search(title):
        return False
    tl = _norm_words(title).lower()
    for term in TITLE_OTHER_REGION.get("egypt", []):
        if term in tl:
            return True
    return False


def has_anchor_in_text(country: str, text: str) -> bool:
    blob = _norm_words(text).lower()
    for anchor in COUNTRY_ANCHORS.get(country, []):
        a = anchor.strip().lower()
        if not a:
            continue
        if " " in a or len(a) >= 4:
            if a in blob:
                return True
        elif token_matches(blob, a):
            return True
    return False


def title_suggests_different_region(country: str, title: str) -> bool:
    """If the title is clearly about another country/region, do not accept HK/Egypt match from snippet/description only."""
    if country not in TITLE_OTHER_REGION:
        return False
    tl = _norm_words(title).lower()
    if has_anchor_in_text(country, title):
        return False
    for term in TITLE_OTHER_REGION[country]:
        if term in tl:
            return True
    return False


def passes_geo_gate(country: str, title: str, description: str) -> bool:
    """India: RSS already localized. HK/Egypt: need a real geo tie; block India stories that only mention HK in passing."""
    if country == "india":
        return True
    if country == "hongcong" and hk_lead_snippet_foreign_only(title):
        return False
    if country == "hongcong" and hk_title_is_exclusively_other_region(title):
        return False
    if country == "egypt" and eg_title_is_exclusively_other_region(title):
        return False
    if has_anchor_in_text(country, title):
        return True
    if has_anchor_in_text(country, description):
        return not title_suggests_different_region(country, title)
    return False


def passes_sub_location_gate(title: str, description: str, region_terms: list[str] | None = None, city: str = "") -> bool:
    if not region_terms and not city:
        return True
    blob = _norm_words(f"{title} {description}")
    if region_terms:
        has_region_hit = any(token_matches(blob, r.strip().lower()) for r in region_terms if r.strip())
        if not has_region_hit:
            return False
    if city and not token_matches(blob, city.strip().lower()):
        return False
    return True


def industry_match_count(title: str, description: str, or_chunks: list[str]) -> int:
    blob = _norm_words(f"{title} {description}")
    bl = blob.lower()
    n = 0
    for chunk in or_chunks:
        c = chunk.strip().lower()
        if not c:
            continue
        if " " in c:
            if c in bl:
                n += 1
        elif token_matches(blob, c):
            n += 1
    return n


def parse_terms(raw: str) -> list[str]:
    return [t.strip().lower() for t in re.split(r"[,;]+|\n+", raw or "") if len(t.strip()) >= 2]


def matches_exclude_terms(title: str, description: str, terms: list[str]) -> bool:
    """True if title or description should be dropped (blocked phrase present)."""
    if not terms:
        return False
    blob = _norm_words(f"{title} {description}").lower()
    for term in terms:
        if " " in term:
            if term in blob:
                return True
        elif len(term) >= 4 and term in blob:
            return True
        elif token_matches(blob, term):
            return True
    return False


ARTICLE_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_article_text(url: str, timeout_sec: int = 10) -> str:
    try:
        response = requests.get(url, headers=ARTICLE_FETCH_HEADERS, timeout=timeout_sec)
        response.raise_for_status()
    except Exception:
        return ""
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "footer", "header", "nav"]):
        tag.decompose()
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) > 60]
    return " ".join(paragraphs[:10]).strip()


def _fetch_item_body(item: dict, timeout_sec: int) -> tuple[dict, str]:
    return item, fetch_article_text(item["link"], timeout_sec=timeout_sec)


def fetch_article_bodies_parallel(items: list[dict], *, timeout_sec: int, max_workers: int) -> list[tuple[dict, str]]:
    if not items:
        return []
    workers = max(1, min(max_workers, len(items)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda it: _fetch_item_body(it, timeout_sec), items))


def fetch_news(
    country: str,
    industry_index: str,
    trend: str,
    duration: str,
    keywords: str = "",
    exclude: str = "",
    region: str = "",
    city: str = "",
    language_mode: str = "english",
    strict: bool = False,
    broaden: bool = False,
    max_results: int = 28,
) -> list[dict]:
    country = (country or "any").strip().lower()
    industry_index = (industry_index or "any").strip().lower()
    duration = (duration or "any").strip().lower()

    if country not in COUNTRIES and country not in ("", "any", "all"):
        raise ValueError("Invalid country")
    if industry_index not in INDICES and industry_index not in ("", "any", "all"):
        raise ValueError("Invalid index")
    if duration not in DURATIONS and duration not in ("", "any", "all"):
        raise ValueError("Invalid duration")

    try:
        mr = int(max_results or 28)
    except (TypeError, ValueError):
        mr = 28
    if mr not in MAX_RESULTS_ALLOWED:
        mr = min(MAX_RESULTS_ALLOWED, key=lambda x: abs(x - mr))
    max_results = max(15, mr)
    exclude_terms = parse_terms(exclude)

    if duration in DURATIONS:
        days = DURATIONS[duration]
        threshold_dt = datetime.now(timezone.utc) - timedelta(days=days)
        from_date = threshold_dt.strftime("%Y-%m-%d")
    else:
        threshold_dt = datetime.now(timezone.utc) - timedelta(days=3650)
        from_date = ""
    keywords = (keywords or "").strip()
    feed_country = country if country in COUNTRIES else "india"
    query_country = country if country in COUNTRIES else ""
    region, city, region_terms = normalize_location_filters(feed_country, region, city)
    language_mode = (language_mode or "english").strip().lower()
    if language_mode not in LANGUAGE_MODES:
        language_mode = "english"
    query = build_query(
        query_country,
        industry_index,
        trend,
        keywords,
        region_terms=region_terms,
        city=city,
    )
    if from_date:
        query += f" after:{from_date}"

    region_cfg = get_news_region(feed_country, language_mode)
    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={region_cfg['hl']}&gl={region_cfg['gl']}&ceid={region_cfg['ceid']}"
    )

    hdrs = news_headers(feed_country, language_mode=language_mode)
    response = requests.get(rss_url, headers=hdrs, timeout=14)
    response.raise_for_status()

    items = parse_rss_items(response.text)
    profile, or_chunks = build_scoring_profile(
        query_country,
        industry_index,
        trend,
        keywords,
        region_terms=region_terms,
        city=city,
    )

    min_score = 4.0 if strict else 2.35
    if keywords:
        min_score += 0.55
    if broaden:
        min_score -= 0.95
    score_floor = max(0.85, min_score - (2.4 if broaden else 1.65))
    if country not in COUNTRIES and industry_index in ("", "any", "all") and trend.strip().lower() in ("", "any", "none"):
        min_score = 0.35
        score_floor = 0.0

    min_industry_hits = 1 if strict else 0

    def score_item(title: str, desc: str, page_snippet: str = "") -> float:
        base = relevance_score(title, desc, profile)
        if page_snippet:
            base += relevance_score("", page_snippet, profile) * 0.35
        if country in COUNTRIES:
            base -= cross_region_penalty(country, title, desc)
        return base

    candidates: list[tuple[float, dict]] = []
    seen = set()

    for item in items[:120]:
        link = item["link"]
        if link in seen:
            continue
        published = item["published"]
        if published:
            try:
                published_dt = parsedate_to_datetime(published).astimezone(timezone.utc)
                if duration in DURATIONS and published_dt < threshold_dt:
                    continue
            except Exception:
                pass
        seen.add(link)

        title = item["title"]
        desc = item["description"]

        if matches_exclude_terms(title, desc, exclude_terms):
            continue

        if country in COUNTRIES and not passes_geo_gate(country, title, desc):
            continue
        if not passes_sub_location_gate(title, desc, region_terms=region_terms, city=city):
            continue

        ind_hits = industry_match_count(title, desc, or_chunks)
        if ind_hits < min_industry_hits:
            continue

        s = score_item(title, desc)
        if s < score_floor:
            continue

        candidates.append((s, item))

    candidates.sort(key=lambda x: x[0], reverse=True)
    # Prefer items above min_score, but fill toward max_results using the wider floor pool.
    primary = [(s, it) for s, it in candidates if s >= min_score]
    secondary = [(s, it) for s, it in candidates if s < min_score]
    ordered = primary + secondary

    fetch_cap = min(max_results + 8, 36)
    to_fetch = [it for _, it in ordered[:fetch_cap]]

    page_timeout = int(os.environ.get("SCRAPE_PAGE_TIMEOUT", "6"))
    page_timeout = max(3, min(page_timeout, 12))
    max_workers = int(os.environ.get("SCRAPE_FETCH_WORKERS", "10"))
    max_workers = max(4, min(max_workers, 16))

    loaded = fetch_article_bodies_parallel(
        to_fetch,
        timeout_sec=page_timeout,
        max_workers=max_workers,
    )

    results = []
    for item, page_text in loaded:
        if len(results) >= max_results:
            break
        link = item["link"]
        summary = summarize_text(page_text) if page_text else summarize_text(item["description"])
        snippet = (page_text or "")[:1200]
        blob = item["description"] + " " + snippet
        if matches_exclude_terms(item["title"], blob, exclude_terms):
            continue
        score = score_item(item["title"], item["description"], snippet)
        if country in COUNTRIES and not passes_geo_gate(country, item["title"], blob):
            continue
        if not passes_sub_location_gate(item["title"], blob, region_terms=region_terms, city=city):
            continue
        results.append(
            {
                "title": item["title"],
                "link": link,
                "published": item["published"],
                "source": item["source"] or "Unknown",
                "summary": summary,
                "relevance": round(max(score, 0.0), 1),
            }
        )

    results.sort(key=lambda r: r.get("relevance", 0), reverse=True)
    return results


@app.route("/")
def home():
    return render_template(
        "index.html",
        countries=COUNTRIES,
        country_options=["any"] + COUNTRIES,
        country_labels=COUNTRY_LABELS,
        language_modes=LANGUAGE_MODES,
        language_labels=LANGUAGE_LABELS,
        region_city_filters=REGION_CITY_FILTERS,
        indices=INDICES,
        index_options=["any"] + INDICES,
        trends=TRENDS,
        trend_labels=TREND_LABELS,
        duration_options=["any"] + list(DURATIONS.keys()),
        max_results_options=MAX_RESULTS_ALLOWED,
    )


@app.route("/search", methods=["POST"])
def search():
    payload = request.get_json(force=True)
    country = (payload.get("country") or "any").strip().lower()
    industry_index = (payload.get("index") or "any").strip().lower()
    trend = (payload.get("trend") or "any").strip()
    duration = (payload.get("duration") or "any").strip().lower()
    keywords = (payload.get("keywords") or "").strip()
    exclude = (payload.get("exclude") or "").strip()
    region = (payload.get("region") or "").strip()
    city = (payload.get("city") or "").strip()
    language_mode = (payload.get("language_mode") or "english").strip().lower()
    strict = bool(payload.get("strict"))
    broaden = bool(payload.get("broaden"))
    try:
        max_results = int(payload.get("max_results") or 28)
    except (TypeError, ValueError):
        max_results = 28

    if trend.lower() not in TRENDS:
        return jsonify({"error": "Invalid trend"}), 400
    if country not in COUNTRIES and country not in ("any", "all", ""):
        return jsonify({"error": "Invalid country"}), 400
    if industry_index not in INDICES and industry_index not in ("any", "all", ""):
        return jsonify({"error": "Invalid index"}), 400
    if duration not in DURATIONS and duration not in ("any", "all", ""):
        return jsonify({"error": "Invalid duration"}), 400
    if language_mode not in LANGUAGE_MODES:
        return jsonify({"error": "Invalid language mode"}), 400

    try:
        data = fetch_news(
            country,
            industry_index,
            trend,
            duration,
            keywords=keywords,
            exclude=exclude,
            region=region,
            city=city,
            language_mode=language_mode,
            strict=strict,
            broaden=broaden,
            max_results=max_results,
        )
        return jsonify({"results": data, "count": len(data)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    # Locked-down / corporate Windows often blocks multiprocessing shared memory used by
    # Werkzeug's interactive debugger (DebuggedApplication + PIN). Keep use_debugger off.
    want_debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")
    app.run(
        host=host,
        port=port,
        debug=want_debug,
        use_reloader=False,
        use_debugger=False,
        threaded=True,
    )
