import subprocess, sys                        # subprocess runs pip; sys gives the current Python executable
subprocess.run(                                   # install required libraries silently if not already present
    [sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4", "lxml", "-q"],
    check=False                                   # do not raise an error if pip prints warnings
)

import requests
import xml.etree.ElementTree as ET
import urllib.parse
import re
import time
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

COUNTRIES = [
    # West Africa
    "Angola", "Burundi", "Benin", "Burkina Faso", "Botswana",
    "Central African Republic", "Côte d'Ivoire", "Cameroon",
    "Congo Kinshasa", "Congo Brazzaville", "Comoros", "Cape Verde",
    # East & Horn of Africa
    "Djibouti", "Algeria", "Egypt", "Eritrea", "Ethiopia", "Gabon",
    "Ghana", "Guinea", "Gambia", "Guinea-Bissau", "Equatorial Guinea",
    "Kenya", "Liberia", "Libya", "Lesotho", "Morocco", "Madagascar",
    # Southern & Central Africa
    "Mali", "Mozambique", "Mauritania", "Mauritius", "Malawi", "Namibia",
    "Niger", "Nigeria", "Rwanda", "Sudan", "Senegal", "Sierra Leone",
    "Somalia", "South Sudan", "São Tomé and Príncipe", "Eswatini", "Chad",
    "Togo", "Tunisia", "Tanzania", "Uganda", "South Africa", "Zambia",
    "Zimbabwe", "Western Sahara",   # 54 countries + Western Sahara = 55 entries
]

REGIONAL = [                              # regional bloc queries run in addition to individual countries
    "Africa",                             # continent-wide search
    "Sahel",                              # Sahel region
    "WAEMU",                              # West African Economic and Monetary Union acronym
    "West African Economic and Monetary Union",   # full name search
]

ALL_ENTITIES = COUNTRIES + REGIONAL

# ── Search categories ─────────────────────────────────────────────────────────
# Each category has keyword strings that get OR-joined in the RSS query.
# Multiple keyword strings per category = multiple RSS calls, results merged.

CATEGORIES = {
    "Jobs & Employment": [
        '"jobs" OR "employment" OR "unemployment" OR "labour market" OR "labor market"',
        '"youth employment" OR "women employment" OR "disability" OR "refugee" OR "displaced"',
    ],
    "Macroeconomy": [
        '"national debt" OR "economic growth" OR "GDP" OR "inflation" OR "cost of living" OR "budget"',
        '"AfCFTA" OR "regional integration" OR "trade" OR "investment" OR "aid" OR "BRICS" OR "sanctions"',
    ],
    "Digital Economy": [
        '"digital economy" OR "ICT" OR "internet access" OR "broadband" OR "digital literacy" OR "fintech"',
        '"electricity access" OR "data protection" OR "internet shutdown" OR "AI" OR "startup" OR "e-commerce"',
    ],
    "Governance": [
        '"civil unrest" OR "protests" OR "elections" OR "democracy" OR "civil society" OR "ECOWAS"',
        '"China Africa" OR "US Africa" OR "Russia Africa" OR "France Africa" OR "sanctions" OR "coup"',
    ],
    "Agrifood & Climate": [
        '"climate change" OR "floods" OR "drought" OR "food security" OR "agriculture" OR "green jobs"',
        '"smallholder" OR "food prices" OR "hunger" OR "renewable energy" OR "climate disaster"',
    ],
    "Workforce & Human Capital": [
        '"education" OR "TVET" OR "vocational training" OR "skills" OR "human capital" OR "school"',
        '"migration" OR "urbanization" OR "brain drain" OR "health" OR "social protection" OR "pension"',
    ],
}


# ── Country-specific interests from QRM planning ─────────────────────────────
# Keywords drawn from the QRM Macrotrend planning report for each country.
# These run as an additional "Country-Specific Context" category for the
# relevant entities only. Entities not listed here skip this category entirely.
# For WAEMU, the keywords are applied to all member states individually
# AND to the "WAEMU" regional query.
COUNTRY_INTERESTS = {
    "Ethiopia": [
        '"rural employment" OR "peri-urban employment" OR "women employment" OR "agro processing"',
        '"manufacturing jobs" OR "digital economy" OR "dam" OR "agriculture jobs"',
        '"private sector" OR "enabling policy" OR "job creation" OR "oil shortage"',
        '"regional conflict" OR "elections Ethiopia" OR "employment Ethiopia"',
    ],
    "Rwanda": [
        '"urban employment" OR "rural employment" OR "RDP" OR "refugee employment"',
        '"tourism jobs" OR "hospitality jobs" OR "agriculture Rwanda" OR "agrifood"',
        '"digital economy Rwanda" OR "ICT Rwanda" OR "access to finance" OR "entrepreneurship"',
        '"MSMEs Rwanda" OR "workforce development Rwanda" OR "skilling" OR "TVET Rwanda"',
        '"regional conflict Rwanda" OR "migration Rwanda" OR "oil shortage"',
    ],
    "Ghana": [
        '"rural employment Ghana" OR "urban employment Ghana" OR "ultra poor Ghana"',
        '"women employment Ghana" OR "disability employment Ghana" OR "aquaculture"',
        '"agribusiness Ghana" OR "agro processing Ghana" OR "tourism Ghana"',
        '"24-hour economy" OR "digital economy Ghana" OR "entrepreneurship Ghana"',
        '"cedi depreciation" OR "oil shortage Ghana" OR "election Ghana"',
    ],
    "Kenya": [
        '"urbanization Kenya" OR "arid Kenya" OR "semi-arid Kenya" OR "young women Kenya"',
        '"agriculture Kenya" OR "digital economy Kenya" OR "manufacturing Kenya"',
        '"MSME Kenya" OR "workforce development Kenya" OR "entrepreneurship Kenya"',
        '"emigration Kenya" OR "domestic work abroad" OR "oil shortage Kenya"',
        '"service jobs Kenya" OR "high growth sectors Kenya" OR "2024 Kenya economy"',
    ],
    "Nigeria": [
        '"rural employment Nigeria" OR "urban employment Nigeria" OR "ultra poor Nigeria"',
        '"women employment Nigeria" OR "disability employment Nigeria"',
        '"agriculture Nigeria" OR "farming Nigeria" OR "agribusiness Nigeria"',
        '"green economy Nigeria" OR "climate jobs Nigeria" OR "digital economy Nigeria"',
        '"access to finance Nigeria" OR "trade Nigeria" OR "oil shortage Nigeria"',
        '"entrepreneurship Nigeria" OR "climate Nigeria"',
    ],
    "Uganda": [
        '"refugees Uganda" OR "host community Uganda" OR "RDP Uganda"',
        '"rural employment Uganda" OR "urban employment Uganda" OR "ultra poor Uganda"',
        '"agriculture Uganda" OR "climate Uganda" OR "tourism Uganda" OR "digital economy Uganda"',
        '"access to finance Uganda" OR "entrepreneurship Uganda" OR "MSMEs Uganda"',
        '"emigration Uganda" OR "domestic work abroad Uganda" OR "oil shortage Uganda"',
        '"informal sector Uganda" OR "new policies Uganda"',
    ],
    # Senegal keywords applied to Senegal only (Senegal is under PRESENCE, not WAEMU list)
    "Senegal": [
        '"rural agriculture Senegal" OR "water Senegal" OR "climate resilience Senegal"',
        '"urban skills Senegal" OR "digital access Senegal" OR "youth employment Senegal"',
        '"young women Senegal" OR "rural farmers Senegal" OR "refugees Senegal"',
        '"agrifood Senegal" OR "transport jobs Senegal" OR "professional services Senegal"',
        '"digital economy Senegal" OR "ICT Senegal" OR "tourism Senegal"',
        '"access to finance Senegal" OR "MSME Senegal" OR "TVET Senegal"',
        '"political instability Senegal" OR "displacement Senegal" OR "oil shortage Senegal"',
    ],
    # WAEMU keywords applied to all 7 WAEMU members + the "WAEMU" regional query
    "WAEMU": [
        '"rural agriculture WAEMU" OR "water WAEMU" OR "climate resilience WAEMU"',
        '"urban skills WAEMU" OR "digital access WAEMU" OR "youth employment WAEMU"',
        '"young women WAEMU" OR "rural farmers WAEMU" OR "refugees WAEMU"',
        '"agrifood WAEMU" OR "digital economy WAEMU" OR "tourism WAEMU"',
        '"access to finance WAEMU" OR "MSME WAEMU" OR "TVET WAEMU"',
        '"political instability WAEMU" OR "terrorism WAEMU" OR "oil shortage WAEMU"',
    ],
}

# WAEMU members that inherit the WAEMU keywords (applied individually per member)
WAEMU_INTEREST_MEMBERS = [
    "Benin", "Burkina Faso", "Côte d'Ivoire", "Guinea-Bissau",
    "Mali", "Niger", "Togo",
]


def get_country_interests(entity):
    """
    Return the list of keyword strings for an entity's Country-Specific Context category.
    WAEMU member states use the WAEMU keywords substituted with their own name.
    Returns empty list if no QRM interests are defined for this entity.
    """
    if entity in COUNTRY_INTERESTS:                      # direct match — Ethiopia, Rwanda, Ghana etc
        return COUNTRY_INTERESTS[entity]
    if entity in WAEMU_INTEREST_MEMBERS:                 # WAEMU member — substitute entity name into WAEMU keywords
        return [
            kw.replace("WAEMU", entity)                  # replace "WAEMU" placeholder with actual country name
            for kw in COUNTRY_INTERESTS["WAEMU"]
        ]
    return []                                            # no QRM interests for this entity — skip the category

DEMOGRAPHICS = ["youth", "women", "disabilit", "refugee"]   # substrings matched in article titles; "disabilit" catches disability/disabilities
DEMO_LABELS  = {"youth": "youth", "women": "women", "disabilit": "disabilities", "refugee": "refugees"}   # display labels for each demographic key
DEMO_COLOURS = {"youth": "#1a6fbf", "women": "#9b2e8a", "disabilit": "#2e8a4a", "refugee": "#bf6a1a"}   # badge colours in the HTML output

TEST_MODE = False  # set True to run only TEST_ENTITIES — useful for quick local testing
TEST_ENTITIES = COUNTRIES[:3] + ["Africa"]   # 3 countries + Africa regional when TEST_MODE is True

MAX_ARTICLES_PER_CAT = 5   # maximum articles collected per keyword string per category
MAX_PARAGRAPHS       = 3      # maximum paragraphs extracted from each article page
DELAY                = 0.8    # seconds between article fetches — keeps requests at human speed
TIMEOUT              = 12     # seconds before giving up on a single HTTP request
TODAY                = datetime.utcnow()                              # exact run time including hours and minutes
DATE_FROM            = (TODAY - timedelta(days=7)).strftime("%Y-%m-%d")  # one week ago for RSS date filter
TIME_SLUG            = TODAY.strftime("%Y-%m-%d-%H%M")                   # e.g. 2026-05-25-0142 — unique per run including same-day re-runs

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

BOILERPLATE = [
    "subscribe", "sign in", "sign up", "log in", "cookie policy", "privacy policy",
    "terms of use", "all rights reserved", "advertisement", "follow us", "share this",
    "enable javascript", "© 20", "you have reached", "become a member",
    "already a subscriber", "get unlimited", "to continue reading",
    "for full access", "free articles left", "digital subscription", "paywall",
]

BODY_SELECTORS = [
    "[itemprop='articleBody']", "article",
    "[class*='article-body']", "[class*='story-body']", "[class*='post-body']",
    "[class*='entry-content']", "[class*='post-content']", "[class*='article-content']",
    "[class*='article-text']", "[class*='story-text']", "[class*='content-body']",
    "[class*='body-text']", "[class*='body-copy']", "[class*='field-body']",
    "main", "#content", "#main", ".content",
]

NOISE_TAGS = [
    "script", "style", "nav", "header", "footer", "aside", "figure",
    "figcaption", "form", "button", "noscript", "iframe",
]

STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is",
    "are", "was", "were", "by", "as", "with", "its", "from", "this", "that",
    "have", "has", "will", "can", "but", "not", "been", "would", "about",
}

SKIP_PATTERNS = [
    "/search", "/tag/", "/tags/", "/category/", "/categories/", "/author/",
    "/page/", "/topic/", "/section/", "?s=", "?q=", "?query=", "?search=",
    "#", "javascript:", "mailto:", ".pdf", ".jpg", ".png", ".gif",
]


# ── RSS fetch & parse ─────────────────────────────────────────────────────────

def fetch_rss(entity, keyword_string):
    q = f'"{entity}" ({keyword_string}) after:{DATE_FROM}'
    p = urllib.parse.urlencode({
        "q": q, "hl": "en-US", "gl": "US", "ceid": "US:en", "tbs": "qdr:w",
    })
    try:
        r = requests.get(
            f"https://news.google.com/rss/search?{p}",
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()
        return ET.fromstring(r.content).findall(".//item")
    except Exception:
        return []


def parse_item(item):
    def txt(tag):
        el = item.find(tag)
        return (el.text or "").strip() if el is not None else ""

    title  = txt("title")
    source = txt("source")
    date   = txt("pubDate")
    link   = txt("link")
    guid   = txt("guid")

    source_el  = item.find("source")
    source_url = source_el.get("url", "").rstrip("/") if source_el is not None else ""

    # Clean Google link — strip line-break artifacts
    raw_link = re.sub(r"\s+", "", link) if link else ""
    if not raw_link.startswith("http"):
        raw_link = re.sub(r"\s+", "", guid) if guid else ""
    if raw_link and not raw_link.startswith("http"):
        raw_link = f"https://news.google.com/rss/articles/{raw_link}"

    if source and title.endswith(" - " + source):
        title = title[:-(len(source) + 3)].strip()
    else:
        title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title).strip()

    try:
        date_fmt = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %Z").strftime("%-d %b %Y")
    except Exception:
        date_fmt = date[:16]

    title_lo  = title.lower()
    demo_tags = [k for k in DEMOGRAPHICS if k in title_lo]

    return {
        "title":       title,
        "source":      source,
        "source_url":  source_url,
        "google_link": raw_link,
        "date":        date_fmt,
        "demo_tags":   demo_tags,
    }


# ── Text extraction — identical to basic_news_search.ipynb ───────────────────

def is_boilerplate(text):
    if not text or len(text.strip()) < 55:
        return True
    return any(p in text.lower() for p in BOILERPLATE)


def extract_text_from_soup(soup):
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(
        r"ad|banner|cookie|paywall|subscribe|newsletter|popup|modal|"
        r"sidebar|promo|signup|related|share|widget|comment|social|tag|author-bio",
        re.I,
    )):
        tag.decompose()
    for sel in BODY_SELECTORS:
        try:
            container = soup.select_one(sel)
        except Exception:
            continue
        if not container:
            continue
        paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
        clean = [p for p in paras if not is_boilerplate(p)]
        if len(clean) >= 2:
            return clean[:MAX_PARAGRAPHS]
    best_div, best_len = None, 0
    for div in soup.find_all(["div", "section"]):
        paras = [p.get_text(" ", strip=True) for p in div.find_all("p", recursive=False)]
        clean = [p for p in paras if not is_boilerplate(p)]
        total = sum(len(p) for p in clean)
        if total > best_len and len(clean) >= 2:
            best_len, best_div = total, clean
    if best_div:
        return best_div[:MAX_PARAGRAPHS]
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    clean = [p for p in paras if not is_boilerplate(p)]
    return clean[:MAX_PARAGRAPHS] if len(clean) >= 2 else []


def try_google_link(google_url):
    """
    Exact logic from basic_news_search.ipynb:
    Follow the Google link. If it escapes google.com, extract text.
    Otherwise keep the Google link as a clickable fallback.
    """
    if not google_url:
        return google_url, []
    try:
        r = requests.get(
            google_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
        final = r.url
        if "google.com" not in final and "consent" not in final:
            soup = BeautifulSoup(r.content, "lxml")
            return final, extract_text_from_soup(soup)
    except Exception:
        pass
    return google_url, []


def find_article_url(source_url, title):
    """Publisher site search — exact logic from basic_news_search.ipynb."""
    if not source_url:
        return ""
    domain      = source_url.rstrip("/")
    domain_bare = re.sub(r"https?://(www\.)?", "", domain).split("/")[0]
    title_clean = re.sub(r"[^\w\s]", " ", title).strip()
    q_encoded   = urllib.parse.quote_plus(title_clean[:120])
    title_words = [
        w.lower() for w in title_clean.split()
        if len(w) > 3 and w.lower() not in STOPWORDS
    ][:8]
    if not title_words:
        return ""
    for search_url in [
        f"{domain}/search?q={q_encoded}",
        f"{domain}/search?query={q_encoded}",
        f"{domain}/search/{q_encoded}",
        f"{domain}/?s={q_encoded}",
        f"{domain}/search?text={q_encoded}",
        f"{domain}/search?term={q_encoded}",
        f"{domain}/search?keywords={q_encoded}",
        f"{domain}/search?p={q_encoded}",
    ]:
        try:
            r = requests.get(search_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code != 200:
                continue
            final = r.url
            parsed_path = urllib.parse.urlparse(final).path.strip("/")
            if (domain_bare in final
                    and not any(p in final for p in SKIP_PATTERNS)
                    and parsed_path
                    and len(parsed_path) >= 10):
                if sum(1 for w in title_words if w in final.lower()) >= 2:
                    return final
            soup = BeautifulSoup(r.content, "lxml")
            best_url, best_score = "", 0
            for a in soup.find_all("a", href=True):
                href = a.get("href", "").strip()
                if not href:
                    continue
                if not href.startswith("http"):
                    href = urllib.parse.urljoin(domain + "/", href)
                href = href.split("#")[0]
                if domain_bare not in href:
                    continue
                if any(p in href for p in SKIP_PATTERNS):
                    continue
                pp = urllib.parse.urlparse(href).path.strip("/")
                if not pp or len(pp) < 10:
                    continue
                combined = (a.get_text(strip=True) + " " + href).lower()
                s = sum(1 for w in title_words if w in combined)
                if s > best_score:
                    best_score, best_url = s, href
            if best_score >= 3:
                return best_url
        except Exception:
            continue
    return ""


def try_slug_on_domain(source_url, title):
    if not source_url or not title:
        return ""
    domain = source_url.rstrip("/")
    slug   = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    slug   = re.sub(r"\s+", "-", slug)
    slug   = re.sub(r"-+", "-", slug)[:120]
    for url in [
        f"{domain}/{slug}/",
        f"{domain}/{slug}",
        f"{domain}/news/{slug}/",
        f"{domain}/news/{slug}",
        f"{domain}/article/{slug}/",
        f"{domain}/articles/{slug}/",
        f"{domain}/stories/{slug}/",
    ]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8, allow_redirects=True)
            if r.status_code == 200 and "404" not in r.url and len(r.content) > 2000:
                if any(w.lower() in r.text.lower() for w in title.split()[:4]):
                    return r.url
        except Exception:
            continue
    return ""


def fetch_article_text(url):
    if not url:
        return [], url
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if any(p in r.url for p in ["/login", "/subscribe", "/signin", "/register"]):
            return [], r.url
        r.raise_for_status()
        return extract_text_from_soup(BeautifulSoup(r.content, "lxml")), r.url
    except Exception:
        return [], url


def resolve_article(parsed):
    """
    Exact resolution chain from basic_news_search.ipynb.
    Always returns (url, paragraphs) — url is never empty.
    """
    # 1. Follow Google link directly
    real_url, paragraphs = try_google_link(parsed["google_link"])

    # 2. Publisher site search (only if still on google)
    if not paragraphs and "google.com" in real_url:
        found = find_article_url(parsed["source_url"], parsed["title"])
        if found:
            paragraphs, final = fetch_article_text(found)
            real_url = final or found

    # 3. Slug construction (only if still on google)
    if not paragraphs and "google.com" in real_url:
        found = try_slug_on_domain(parsed["source_url"], parsed["title"])
        if found:
            paragraphs, final = fetch_article_text(found)
            real_url = final or found

    # 4. Retry text fetch if we have a real URL but no text
    if not paragraphs and real_url and "google.com" not in real_url:
        paragraphs, _ = fetch_article_text(real_url)

    # real_url is always set — worst case it's the Google link (clickable in browser)
    return real_url, paragraphs


# ── Process one entity ────────────────────────────────────────────────────────

def process_entity(entity):
    print(f"\n{'─'*50}")
    print(f"  {entity}")
    print(f"{'─'*50}")

    entity_result = {"entity": entity, "categories": {}}
    seen_titles   = set()

    # Run standard 6-pillar categories for every entity
    all_categories = dict(CATEGORIES)                        # start with the standard 6 pillars

    # Append Country-Specific Context if QRM keywords are defined for this entity
    country_kws = get_country_interests(entity)              # empty list if entity has no QRM data
    if country_kws:                                          # only add the category if there are keywords
        all_categories["Country-Specific Context"] = country_kws   # adds as a 7th category for this entity only

    for cat_name, keyword_list in all_categories.items():   # loop through all categories
        cat_articles = []

        for kw in keyword_list:
            if len(cat_articles) >= MAX_ARTICLES_PER_CAT:
                break
            items = fetch_rss(entity, kw)
            for rss_position, item in enumerate(items):  # enumerate gives 0-based RSS position
                if len(cat_articles) >= MAX_ARTICLES_PER_CAT:
                    break
                parsed = parse_item(item)
                if not parsed["title"] or parsed["title"] in seen_titles:
                    continue
                seen_titles.add(parsed["title"])

                print(f'    [{cat_name}] {parsed["title"]}')
                real_url, paragraphs = resolve_article(parsed)
                is_google = "google.com" in real_url
                status    = f"{len(paragraphs)}p" if paragraphs else ("google-link" if is_google else "no text")
                print(f'         → {real_url}  [{status}]')

                cat_articles.append({
                    "title":      parsed["title"],
                    "url":        real_url,
                    "source":     parsed["source"],
                    "date":       parsed["date"],
                    "paragraphs": paragraphs,
                    "demo_tags":  parsed["demo_tags"],
                    "is_google":    is_google,
                    "rss_position": rss_position,  # position in RSS feed (0 = top/most relevant)
                })
                time.sleep(DELAY)

        entity_result["categories"][cat_name] = cat_articles

    total     = sum(len(v) for v in entity_result["categories"].values())
    with_text = sum(1 for v in entity_result["categories"].values() for a in v if a["paragraphs"])
    print(f'  → {total} articles, {with_text} with text')
    return entity_result

# ── CHECKPOINT & SAVE ─────────────────────────────────────────────────────────
# Checkpoint system: after each entity completes, its result is appended to
# checkpoint.pkl. If the run is interrupted (timeout, error), re-running the
# script will load the checkpoint and skip entities already processed,
# continuing from where it left off rather than starting from scratch.

import pickle   # serialises Python objects to binary files

CHECKPOINT_PATH = "checkpoint.pkl"   # checkpoint file — rebuilt each run, deleted on success
RESULTS_PATH    = "results.pkl"      # final output read by production_export.py


def load_checkpoint():
    """Load partially completed results from a previous interrupted run."""
    if os.path.exists(CHECKPOINT_PATH):              # checkpoint file exists — a previous run was interrupted
        with open(CHECKPOINT_PATH, "rb") as f:       # open the binary checkpoint file
            cp = pickle.load(f)                      # deserialise the saved progress dict
        print(f"Resuming from checkpoint: {len(cp['results'])} entities already done")
        return cp["results"], set(cp["done_entities"])   # return saved results + set of completed entity names
    return [], set()                                 # no checkpoint — start fresh with empty results


def save_checkpoint(results, done_entities):
    """Write current progress to disk after each entity so a restart can resume from here."""
    with open(CHECKPOINT_PATH, "wb") as f:           # overwrite checkpoint with latest progress
        pickle.dump({
            "results":       results,                # all entity results collected so far
            "done_entities": list(done_entities),    # list of entity names already processed
        }, f)


# ── RUN WITH CHECKPOINT ───────────────────────────────────────────────────────

entities  = TEST_ENTITIES if TEST_MODE else ALL_ENTITIES   # choose test or full entity list
generated = TODAY.strftime("%a, %d %b %Y %H:%M UTC")      # human-readable timestamp for output files

print(f"Generated: {generated}  |  after:{DATE_FROM}")
print(f"Mode: {'TEST' if TEST_MODE else 'FULL'} — {len(entities)} entities × {len(CATEGORIES)} categories")
print("=" * 60)

# Load any checkpoint from a previous interrupted run — skips already-done entities
results, done_entities = load_checkpoint()

for entity in entities:
    if entity in done_entities:                      # this entity was completed in a previous run — skip it
        print(f"  [checkpoint] skipping {entity} — already done")
        continue
    result = process_entity(entity)                 # run the full search for this entity (~2–3 min each)
    results.append(result)                          # add this entity's results to the running list
    done_entities.add(entity)                       # record that this entity is now complete
    save_checkpoint(results, done_entities)         # write progress to disk immediately in case of future failure
    print(f"  [checkpoint saved — {len(done_entities)}/{len(entities)} done]")

total_a = sum(len(a) for r in results for a in r["categories"].values())            # total article count
total_t = sum(1 for r in results for v in r["categories"].values() for a in v if a["paragraphs"])  # with text
print(f"\nDone: {len(results)} entities | {total_a} articles | {total_t} with text")

# ── Save final results.pkl for production_export.py ───────────────────────────
with open(RESULTS_PATH, "wb") as f:
    pickle.dump({
        "results":   results,    # complete list of entity result dicts
        "generated": generated,  # timestamp string for display
        "today":     TODAY,      # datetime object for date formatting
        "date_slug": TIME_SLUG,                    # YYYY-MM-DD-HHMM — unique per run, prevents same-day overwrite
        "total_a":   total_a,    # total article count across all entities
        "total_t":   total_t,    # articles where text was successfully extracted
    }, f)
print(f"Saved {RESULTS_PATH}")

# Delete the checkpoint now that we have a complete results.pkl
if os.path.exists(CHECKPOINT_PATH):
    os.remove(CHECKPOINT_PATH)   # clean up — checkpoint no longer needed
    print(f"Deleted {CHECKPOINT_PATH} (run complete)")
