# sophisticated_search.py
# Searches Google News RSS for 58 African countries + regional blocs
# across 6 analytical pillars, extracts article text, saves results.pkl

# ── Install dependencies if not already present ───────────────────────────────
import subprocess, sys                                         # stdlib modules for running shell commands
subprocess.run(                                                # run pip install silently
    [sys.executable, "-m", "pip", "install",                  # use the same python that is running this script
     "requests", "beautifulsoup4", "lxml", "-q"],              # libraries needed: HTTP, HTML parsing, fast XML parser
    check=False                                                # don't crash if pip has warnings
)

# ── Standard library imports ──────────────────────────────────────────────────
import requests                        # makes HTTP requests to fetch RSS feeds and article pages
import xml.etree.ElementTree as ET     # parses RSS XML into a navigable tree
import urllib.parse                    # builds and encodes URL query strings
import re                              # regular expressions for cleaning text and URLs
import time                            # sleep between requests so we don't hammer servers
import os                              # file path operations
import pickle                          # serialise results to disk so production_export.py can read them
from datetime import datetime, timedelta   # date arithmetic for the 7-day filter
from bs4 import BeautifulSoup              # parses HTML pages to extract article text

# ── Countries to search ───────────────────────────────────────────────────────
COUNTRIES = [                          # all 54 African countries + Western Sahara
    "Angola", "Burundi", "Benin", "Burkina Faso", "Botswana",
    "Central African Republic", "Côte d'Ivoire", "Cameroon",
    "Congo Kinshasa", "Congo Brazzaville", "Comoros", "Cape Verde",
    "Djibouti", "Algeria", "Egypt", "Eritrea", "Ethiopia", "Gabon",
    "Ghana", "Guinea", "Gambia", "Guinea-Bissau", "Equatorial Guinea",
    "Kenya", "Liberia", "Libya", "Lesotho", "Morocco", "Madagascar",
    "Mali", "Mozambique", "Mauritania", "Mauritius", "Malawi", "Namibia",
    "Niger", "Nigeria", "Rwanda", "Sudan", "Senegal", "Sierra Leone",
    "Somalia", "South Sudan", "São Tomé and Príncipe", "Eswatini", "Chad",
    "Togo", "Tunisia", "Tanzania", "Uganda", "South Africa", "Zambia",
    "Zimbabwe", "Western Sahara",
]

# ── Regional blocs to search in addition to individual countries ───────────────
REGIONAL = [
    "Africa",                                  # continent-wide search
    "Sahel",                                   # Sahel region search
    "WAEMU",                                   # West African Economic and Monetary Union acronym
    "West African Economic and Monetary Union", # full name search
]

ALL_ENTITIES = COUNTRIES + REGIONAL    # combined list — 58 searches total

# ── Search categories and their keyword strings ────────────────────────────────
# Each category maps to a list of keyword strings.
# Each keyword string becomes one RSS query for the entity.
# Results from all keyword strings in a category are merged and deduplicated.
CATEGORIES = {
    "Jobs & Employment": [                           # pillar 1: core jobs/employment signals
        '"jobs" OR "employment" OR "unemployment" OR "labour market" OR "labor market"',
        '"youth employment" OR "women employment" OR "disability" OR "refugee" OR "displaced"',
    ],
    "Macroeconomy": [                                # pillar 2: macroeconomic conditions
        '"national debt" OR "economic growth" OR "GDP" OR "inflation" OR "cost of living" OR "budget"',
        '"AfCFTA" OR "regional integration" OR "trade" OR "investment" OR "aid" OR "BRICS" OR "sanctions"',
    ],
    "Digital Economy": [                             # pillar 3: digital and tech landscape
        '"digital economy" OR "ICT" OR "internet access" OR "broadband" OR "digital literacy" OR "fintech"',
        '"electricity access" OR "data protection" OR "internet shutdown" OR "AI" OR "startup" OR "e-commerce"',
    ],
    "Governance": [                                  # pillar 4: political and governance signals
        '"civil unrest" OR "protests" OR "elections" OR "democracy" OR "civil society" OR "ECOWAS"',
        '"China Africa" OR "US Africa" OR "Russia Africa" OR "France Africa" OR "sanctions" OR "coup"',
    ],
    "Agrifood & Climate": [                          # pillar 5: food, agriculture and climate
        '"climate change" OR "floods" OR "drought" OR "food security" OR "agriculture" OR "green jobs"',
        '"smallholder" OR "food prices" OR "hunger" OR "renewable energy" OR "climate disaster"',
    ],
    "Workforce & Human Capital": [                   # pillar 6: education, skills and migration
        '"education" OR "TVET" OR "vocational training" OR "skills" OR "human capital" OR "school"',
        '"migration" OR "urbanization" OR "brain drain" OR "health" OR "social protection" OR "pension"',
    ],
}

# ── Demographic keyword fragments to detect in article titles ─────────────────
DEMOGRAPHICS = ["youth", "women", "disabilit", "refugee"]   # substrings to match (disabilit catches disability/disabilities)
DEMO_LABELS  = {                                             # human-readable labels for display
    "youth": "youth", "women": "women",
    "disabilit": "disabilities", "refugee": "refugees"
}
DEMO_COLOURS = {                                             # tag badge colours for the HTML output
    "youth": "#1a6fbf", "women": "#9b2e8a",
    "disabilit": "#2e8a4a", "refugee": "#bf6a1a"
}

# ── Run mode ──────────────────────────────────────────────────────────────────
TEST_MODE     = False                          # set True to run only 3 countries + Africa for quick testing
TEST_ENTITIES = COUNTRIES[:3] + ["Africa"]    # entities used when TEST_MODE is True

# ── Fetch limits and timing ───────────────────────────────────────────────────
MAX_ARTICLES_PER_CAT = 3      # maximum articles kept per keyword string per category
MAX_PARAGRAPHS       = 3      # maximum paragraphs extracted from each article page
DELAY                = 0.8    # seconds to wait between article fetches — avoids rate limiting
TIMEOUT              = 12     # seconds before giving up on a single HTTP request

# ── Date range ────────────────────────────────────────────────────────────────
TODAY     = datetime.utcnow()                              # current UTC time
DATE_FROM = (TODAY - timedelta(days=7)).strftime("%Y-%m-%d")  # one week ago in YYYY-MM-DD format

# ── HTTP headers sent with every request ─────────────────────────────────────
# Identifies us as a real browser so servers don't immediately block the request
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# ── Text patterns that indicate boilerplate rather than article content ────────
BOILERPLATE = [
    "subscribe", "sign in", "sign up", "log in", "cookie policy", "privacy policy",
    "terms of use", "all rights reserved", "advertisement", "follow us", "share this",
    "enable javascript", "© 20", "you have reached", "become a member",
    "already a subscriber", "get unlimited", "to continue reading",
    "for full access", "free articles left", "digital subscription", "paywall",
]

# ── CSS selectors tried in order to find the article body in a page ───────────
# Most specific (structured markup) first, least specific (main/content divs) last
BODY_SELECTORS = [
    "[itemprop='articleBody']", "article",
    "[class*='article-body']", "[class*='story-body']", "[class*='post-body']",
    "[class*='entry-content']", "[class*='post-content']", "[class*='article-content']",
    "[class*='article-text']", "[class*='story-text']", "[class*='content-body']",
    "[class*='body-text']", "[class*='body-copy']", "[class*='field-body']",
    "main", "#content", "#main", ".content",
]

# ── HTML tags that are never article content — removed before text extraction ──
NOISE_TAGS = [
    "script", "style", "nav", "header", "footer", "aside", "figure",
    "figcaption", "form", "button", "noscript", "iframe",
]

# ── Common short words ignored when matching article URLs to titles ────────────
STOPWORDS = {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is",
    "are", "was", "were", "by", "as", "with", "its", "from", "this", "that",
    "have", "has", "will", "can", "but", "not", "been", "would", "about",
}

# ── URL path fragments that indicate a non-article page (tag, category etc) ───
SKIP_PATTERNS = [
    "/search", "/tag/", "/tags/", "/category/", "/categories/", "/author/",
    "/page/", "/topic/", "/section/", "?s=", "?q=", "?query=", "?search=",
    "#", "javascript:", "mailto:", ".pdf", ".jpg", ".png", ".gif",
]


# ── RSS FETCH ─────────────────────────────────────────────────────────────────

def fetch_rss(entity, keyword_string):
    """Build a Google News RSS URL for entity + keywords, return parsed XML items."""
    q = f'"{entity}" ({keyword_string}) after:{DATE_FROM}'   # search query: entity in quotes + keywords + date filter
    p = urllib.parse.urlencode({                              # encode parameters into a query string
        "q": q,          # the search query
        "hl": "en-US",   # interface language: English
        "gl": "US",      # geolocation: United States (avoids regional consent walls)
        "ceid": "US:en", # content edition
        "tbs": "qdr:w",  # time-based filter: past week
    })
    try:
        r = requests.get(                                     # fetch the RSS feed
            f"https://news.google.com/rss/search?{p}",       # Google News RSS endpoint
            headers=HEADERS, timeout=TIMEOUT,
        )
        r.raise_for_status()                                  # raise an error if HTTP status is 4xx or 5xx
        return ET.fromstring(r.content).findall(".//item")    # parse XML and return all <item> elements
    except Exception:
        return []                                             # return empty list on any error


def parse_item(item):
    """Extract title, source, date, Google redirect URL, and demographic tags from one RSS <item>."""
    def txt(tag):                                             # helper: get text content of a child tag
        el = item.find(tag)
        return (el.text or "").strip() if el is not None else ""

    title  = txt("title")    # article headline as given by Google News
    source = txt("source")   # publisher name e.g. "BBC"
    date   = txt("pubDate")  # publication date string in RFC 822 format
    link   = txt("link")     # Google News redirect URL (may contain line-break artifacts)
    guid   = txt("guid")     # Google News article token (cleaner than link for some items)

    source_el  = item.find("source")                                         # find the <source> element
    source_url = source_el.get("url", "").rstrip("/") if source_el is not None else ""  # publisher domain from url attribute

    raw_link = re.sub(r"\s+", "", link) if link else ""      # strip all whitespace from link (removes line-break artifacts)
    if not raw_link.startswith("http"):                       # if link was empty or malformed, fall back to guid
        raw_link = re.sub(r"\s+", "", guid) if guid else ""
    if raw_link and not raw_link.startswith("http"):          # if guid is just a token (no http), prepend the base URL
        raw_link = f"https://news.google.com/rss/articles/{raw_link}"

    if source and title.endswith(" - " + source):            # Google appends " - Source Name" to titles — strip it
        title = title[:-(len(source) + 3)].strip()
    else:
        title = re.sub(r"\s+-\s+[^-]{2,60}$", "", title).strip()  # generic strip of trailing " - anything"

    try:
        date_fmt = datetime.strptime(date, "%a, %d %b %Y %H:%M:%S %Z").strftime("%-d %b %Y")  # reformat date to "14 May 2026"
    except Exception:
        date_fmt = date[:16]                                  # if parsing fails, use first 16 chars of raw date string

    title_lo  = title.lower()                                 # lowercase title for demographic matching
    demo_tags = [k for k in DEMOGRAPHICS if k in title_lo]   # find which demographic keywords appear in the title

    return {
        "title":       title,        # cleaned article title
        "source":      source,       # publisher name
        "source_url":  source_url,   # publisher domain URL
        "google_link": raw_link,     # cleaned Google News redirect URL
        "date":        date_fmt,     # formatted date string
        "demo_tags":   demo_tags,    # list of matched demographic keys
    }


# ── TEXT EXTRACTION ───────────────────────────────────────────────────────────

def is_boilerplate(text):
    """Return True if the paragraph looks like navigation/subscribe text rather than article content."""
    if not text or len(text.strip()) < 55:    # very short strings are almost always UI fragments, not content
        return True
    return any(p in text.lower() for p in BOILERPLATE)   # check against known boilerplate phrases


def extract_text_from_soup(soup):
    """Remove noise from a parsed HTML page and return up to MAX_PARAGRAPHS clean paragraphs."""
    for tag in soup(NOISE_TAGS):              # remove all script, style, nav etc tags
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(   # remove elements whose class name suggests ads/popups/sidebars
        r"ad|banner|cookie|paywall|subscribe|newsletter|popup|modal|"
        r"sidebar|promo|signup|related|share|widget|comment|social|tag|author-bio",
        re.I,
    )):
        tag.decompose()

    for sel in BODY_SELECTORS:                # try each selector from most to least specific
        try:
            container = soup.select_one(sel)  # find the first matching element
        except Exception:
            continue
        if not container:                     # selector matched nothing — try next
            continue
        paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]   # extract text from all <p> tags inside
        clean = [p for p in paras if not is_boilerplate(p)]                       # filter out boilerplate paragraphs
        if len(clean) >= 2:                   # need at least 2 real paragraphs to be confident we found the body
            return clean[:MAX_PARAGRAPHS]     # return up to MAX_PARAGRAPHS paragraphs

    # Fallback: find the div/section with the most paragraph text
    best_div, best_len = None, 0
    for div in soup.find_all(["div", "section"]):                                # scan all divs and sections
        paras = [p.get_text(" ", strip=True) for p in div.find_all("p", recursive=False)]  # direct <p> children only
        clean = [p for p in paras if not is_boilerplate(p)]
        total = sum(len(p) for p in clean)   # total character count of clean paragraphs in this div
        if total > best_len and len(clean) >= 2:   # keep the div with the most content
            best_len, best_div = total, clean
    if best_div:
        return best_div[:MAX_PARAGRAPHS]     # return paragraphs from the richest div

    # Last resort: all <p> tags on the entire page
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    clean = [p for p in paras if not is_boilerplate(p)]
    return clean[:MAX_PARAGRAPHS] if len(clean) >= 2 else []   # return if enough content, else empty list


# ── URL RESOLUTION — METHOD 1 ─────────────────────────────────────────────────

def try_google_link(google_url):
    """
    Follow the Google News redirect URL.
    If it escapes google.com entirely, we have the real article — extract text.
    If it stays on google.com (consent wall etc), keep the Google URL as a
    clickable fallback so the user can still open it in their browser.
    """
    if not google_url:                        # nothing to follow
        return google_url, []
    try:
        r = requests.get(                     # follow all HTTP redirects
            google_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True
        )
        final = r.url                         # URL after all redirects have been followed
        if "google.com" not in final and "consent" not in final:   # successfully reached a publisher page
            soup = BeautifulSoup(r.content, "lxml")                # parse the publisher's HTML
            return final, extract_text_from_soup(soup)             # return real URL + extracted text
    except Exception:
        pass
    return google_url, []    # redirect stayed on google — return original URL and no text


# ── URL RESOLUTION — METHOD 2 ─────────────────────────────────────────────────

def find_article_url(source_url, title):
    """
    Search the publisher's own site using their internal search endpoint.
    Tries 8 common search URL patterns (e.g. /search?q=, /?s=, /search/query).
    Scores result links by how many title words appear in the URL or link text.
    Returns the best-matching article URL, or empty string if none found.
    """
    if not source_url:
        return ""
    domain      = source_url.rstrip("/")                                         # publisher base URL
    domain_bare = re.sub(r"https?://(www\.)?", "", domain).split("/")[0]         # just the hostname e.g. "vellum.co.ke"
    title_clean = re.sub(r"[^\w\s]", " ", title).strip()                         # remove punctuation from title
    q_encoded   = urllib.parse.quote_plus(title_clean[:120])                      # URL-encode the title for search queries
    title_words = [                                                               # meaningful words from the title
        w.lower() for w in title_clean.split()
        if len(w) > 3 and w.lower() not in STOPWORDS
    ][:8]
    if not title_words:                       # title has no meaningful words — nothing to match against
        return ""
    for search_url in [                       # try each common search endpoint pattern
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
            if r.status_code != 200:          # search endpoint returned an error — try next pattern
                continue
            final = r.url                     # URL after redirects (search may redirect directly to article)
            parsed_path = urllib.parse.urlparse(final).path.strip("/")           # path portion of the final URL
            if (domain_bare in final                              # stays on publisher domain
                    and not any(p in final for p in SKIP_PATTERNS)  # not a tag/category page
                    and parsed_path                               # has a real path (not just homepage)
                    and len(parsed_path) >= 10):                  # path is long enough to be an article
                if sum(1 for w in title_words if w in final.lower()) >= 2:      # at least 2 title words in URL
                    return final              # search redirected straight to the article
            soup = BeautifulSoup(r.content, "lxml")   # parse search results page
            best_url, best_score = "", 0
            for a in soup.find_all("a", href=True):   # scan all links on the search results page
                href = a.get("href", "").strip()
                if not href:
                    continue
                if not href.startswith("http"):        # resolve relative URLs to absolute
                    href = urllib.parse.urljoin(domain + "/", href)
                href = href.split("#")[0]              # strip URL fragment
                if domain_bare not in href:            # link goes to a different domain — skip
                    continue
                if any(p in href for p in SKIP_PATTERNS):   # link is a tag/category/search page — skip
                    continue
                pp = urllib.parse.urlparse(href).path.strip("/")
                if not pp or len(pp) < 10:             # path too short to be an article — skip
                    continue
                combined = (a.get_text(strip=True) + " " + href).lower()        # combine link text and URL for matching
                s = sum(1 for w in title_words if w in combined)                 # count title words found
                if s > best_score:                     # keep the best-matching link seen so far
                    best_score, best_url = s, href
            if best_score >= 3:                        # require at least 3 title words to match before trusting the result
                return best_url
        except Exception:
            continue
    return ""                                  # no matching article found on publisher site


# ── URL RESOLUTION — METHOD 3 ─────────────────────────────────────────────────

def try_slug_on_domain(source_url, title):
    """
    Construct likely article URLs from the title slug and try fetching them directly.
    Many African news sites use simple slug-based URL patterns like /news/article-title/.
    Returns the URL if we get a real page back, empty string otherwise.
    """
    if not source_url or not title:
        return ""
    domain = source_url.rstrip("/")
    slug   = re.sub(r"[^\w\s-]", "", title.lower()).strip()   # remove punctuation, lowercase
    slug   = re.sub(r"\s+", "-", slug)                        # replace spaces with hyphens
    slug   = re.sub(r"-+", "-", slug)[:120]                   # collapse multiple hyphens, limit length
    for url in [                              # try each common article URL pattern
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
            if r.status_code == 200 and "404" not in r.url and len(r.content) > 2000:   # page exists and has content
                if any(w.lower() in r.text.lower() for w in title.split()[:4]):          # first 4 title words appear in page
                    return r.url             # this URL loads the article
        except Exception:
            continue
    return ""


def fetch_article_text(url):
    """Fetch a known article URL and extract text. Returns (paragraphs, final_url)."""
    if not url:
        return [], url
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if any(p in r.url for p in ["/login", "/subscribe", "/signin", "/register"]):  # redirected to a login wall
            return [], r.url
        r.raise_for_status()                  # error on bad HTTP status
        return extract_text_from_soup(BeautifulSoup(r.content, "lxml")), r.url         # parse and extract
    except Exception:
        return [], url


def resolve_article(parsed):
    """
    Try all three URL resolution methods in sequence, stopping when we get text.
    Always returns (url, paragraphs) — url is never empty, worst case is the Google link.
    """
    real_url, paragraphs = try_google_link(parsed["google_link"])   # method 1: follow Google redirect

    if not paragraphs and "google.com" in real_url:                 # method 1 failed — still on google
        found = find_article_url(parsed["source_url"], parsed["title"])   # method 2: search publisher site
        if found:
            paragraphs, final = fetch_article_text(found)
            real_url = final or found

    if not paragraphs and "google.com" in real_url:                 # method 2 also failed
        found = try_slug_on_domain(parsed["source_url"], parsed["title"])   # method 3: try URL slug construction
        if found:
            paragraphs, final = fetch_article_text(found)
            real_url = final or found

    if not paragraphs and real_url and "google.com" not in real_url:   # have real URL but no text yet
        paragraphs, _ = fetch_article_text(real_url)                   # one more try at extracting text

    return real_url, paragraphs   # worst case: real_url is the Google link, paragraphs is []


# ── PROCESS ONE ENTITY ────────────────────────────────────────────────────────

def process_entity(entity):
    """Run all 6 category searches for one country or regional bloc, return structured results."""
    print(f"\n{'─'*50}")
    print(f"  {entity}")                       # show which entity we are processing
    print(f"{'─'*50}")

    entity_result = {"entity": entity, "categories": {}}   # container for this entity's results
    seen_titles   = set()                                   # track titles already collected to avoid duplicates across categories

    for cat_name, keyword_list in CATEGORIES.items():       # loop through each of the 6 pillars
        cat_articles = []                                   # articles collected for this pillar

        for kw in keyword_list:                             # loop through each keyword string for this pillar
            if len(cat_articles) >= MAX_ARTICLES_PER_CAT:  # already have enough articles for this pillar — stop
                break
            items = fetch_rss(entity, kw)                  # fetch RSS items for this entity + keyword combination
            for rss_position, item in enumerate(items):   # enumerate gives us the 0-based position in the RSS feed
                if len(cat_articles) >= MAX_ARTICLES_PER_CAT:   # re-check limit inside inner loop
                    break
                parsed = parse_item(item)                   # extract structured data from the RSS item
                if not parsed["title"] or parsed["title"] in seen_titles:   # skip empty or duplicate titles
                    continue
                seen_titles.add(parsed["title"])            # mark this title as seen

                print(f'    [{cat_name}] {parsed["title"]}')   # log the article being processed
                real_url, paragraphs = resolve_article(parsed)  # attempt to get real URL and text
                is_google = "google.com" in real_url            # flag whether we only have a Google link
                status    = f"{len(paragraphs)}p" if paragraphs else ("google-link" if is_google else "no text")
                print(f'         → {real_url}  [{status}]')    # log outcome

                cat_articles.append({                      # store the enriched article record
                    "title":        parsed["title"],
                    "url":          real_url,
                    "source":       parsed["source"],
                    "date":         parsed["date"],
                    "paragraphs":   paragraphs,
                    "demo_tags":    parsed["demo_tags"],
                    "is_google":    is_google,
                    "rss_position": rss_position,          # position in the RSS feed (0 = top result, Google's most relevant)
                })
                time.sleep(DELAY)                          # pause before next request

        entity_result["categories"][cat_name] = cat_articles   # store this pillar's articles

    total     = sum(len(v) for v in entity_result["categories"].values())            # total articles across all pillars
    with_text = sum(1 for v in entity_result["categories"].values() for a in v if a["paragraphs"])   # how many have extracted text
    print(f'  → {total} articles, {with_text} with text')
    return entity_result


# ── RUN ───────────────────────────────────────────────────────────────────────

entities  = TEST_ENTITIES if TEST_MODE else ALL_ENTITIES    # choose test or full entity list
results   = []                                              # will hold one dict per entity
generated = TODAY.strftime("%a, %d %b %Y %H:%M UTC")       # human-readable timestamp for output files

print(f"Generated: {generated}  |  after:{DATE_FROM}")
print(f"Mode: {'TEST' if TEST_MODE else 'FULL'} — {len(entities)} entities × {len(CATEGORIES)} categories")
print("=" * 60)

for entity in entities:                        # process each entity one at a time (sequential, not parallel)
    results.append(process_entity(entity))

total_a = sum(len(a) for r in results for a in r["categories"].values())              # total article count
total_t = sum(1 for r in results for v in r["categories"].values() for a in v if a["paragraphs"])  # articles with text
print(f"\nDone: {len(results)} entities | {total_a} articles | {total_t} with text")

# ── SAVE results to disk ──────────────────────────────────────────────────────
# Pickle serialises the results dict to a binary file so production_export.py
# can load it without re-running the search (which takes ~60 minutes)
with open("results.pkl", "wb") as f:
    pickle.dump({
        "results":   results,    # list of per-entity dicts
        "generated": generated,  # timestamp string
        "today":     TODAY,      # datetime object (used to format dates in export)
        "date_slug": TODAY.strftime("%Y-%m-%d"),   # YYYY-MM-DD for filenames
        "total_a":   total_a,    # total article count
        "total_t":   total_t,    # articles with extracted text
    }, f)
print("Saved results.pkl")       # production_export.py will read this file
