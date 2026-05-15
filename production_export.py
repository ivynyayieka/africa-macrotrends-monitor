# production_export.py
# Reads results.pkl written by sophisticated_search.py.
# Produces three output files:
#   africa-digest-YYYY-MM-DD.csv        full data export of all articles
#   news-digest-YYYY-MM-DD.html         production report for GitHub Pages
#   index.html                          archive landing page listing all past issues

# ── Standard library imports ──────────────────────────────────────────────────
import pickle    # loads the binary results file saved by sophisticated_search.py
import csv       # writes the CSV export
import os        # file path operations
import re        # regular expressions for cleaning anchor strings
from datetime import datetime   # formats dates for display

# ── Load results from disk ────────────────────────────────────────────────────
with open("results.pkl", "rb") as f:       # open the binary file written by sophisticated_search.py
    data = pickle.load(f)                  # deserialise — restores the full results dict

results   = data["results"]    # list of per-entity dicts, each containing a "categories" dict
generated = data["generated"]  # human-readable timestamp string e.g. "Mon, 14 May 2026 06:12 UTC"
TODAY     = data["today"]      # datetime object representing when the search ran
date_slug = data["date_slug"]  # YYYY-MM-DD string used in filenames
total_a   = data["total_a"]    # total number of articles collected across all entities
total_t   = data["total_t"]    # number of those articles where text was successfully extracted

print(f"Loaded {len(results)} entities | {total_a} articles | {total_t} with text")

# ── Shared display constants ──────────────────────────────────────────────────
DEMO_LABELS = {                # maps demographic detection keys to human-readable display labels
    "youth":     "Youth",
    "women":     "Women",
    "disabilit": "Disabilities",
    "refugee":   "Refugees",
    "wdl":       "World Data Lab",   # World Data Lab mention tag
}

DEMO_COLOURS = {               # CSS background colours for demographic and mention tags
    "youth":     "#1a3a5c",    # dark navy — matches accent colour, serious
    "women":     "#4a2060",    # deep plum
    "disabilit": "#1a5c3a",    # dark green
    "refugee":   "#7a3a10",    # dark amber
    "wdl":       "#5c1a1a",    # dark crimson — distinct from demographics
}

# ── Production report configuration ──────────────────────────────────────────
MAX_PER_COUNTRY = 3            # top N articles per country, pooled across all pillars, ranked by reach score

PRESENCE = [                   # countries where the organisation has a direct presence
    "Ethiopia", "Ghana", "Kenya", "Nigeria", "Rwanda", "Senegal", "Uganda",
]

WAEMU_MEMBERS = [              # WAEMU members excluding Senegal (which appears under Countries of Presence)
    "Benin", "Burkina Faso", "Côte d'Ivoire", "Guinea-Bissau",
    "Mali", "Niger", "Togo",
]

REGIONAL_SHOW = ["WAEMU", "Africa"]   # regional bloc searches to include


# ── Publisher reach scores ────────────────────────────────────────────────────
# Scored 1–10: 10 = global wire services, 9 = major international,
# 8 = leading African nationals, 7 = strong regional, 6 = smaller local,
# 3 = default for any unknown publisher.
PUBLISHER_REACH = {
    # Global wire services and tier-1 international
    "bbc":            10,   # BBC
    "reuters":        10,   # Reuters
    "apnews":         10,   # Associated Press
    "afp":            10,   # Agence France-Presse
    "bloomberg":      10,   # Bloomberg
    "aljazeera":       9,   # Al Jazeera
    "theguardian":     9,   # The Guardian
    "economist":       9,   # The Economist
    "ft.com":          9,   # Financial Times
    "washingtonpost":  9,   # Washington Post
    "nytimes":         9,   # New York Times
    "dw.com":          8,   # Deutsche Welle
    "france24":        8,   # France 24
    "rfi":             8,   # Radio France Internationale
    "voaafrica":       8,   # Voice of America Africa
    # Leading pan-African outlets
    "theafricareport": 8,   # The Africa Report
    "africafeeds":     7,   # Africa Feeds
    "africanews":      7,   # Africanews
    "quartz":          7,   # Quartz Africa
    # Leading national outlets by country
    "businessday":     8,   # Business Day (Nigeria)
    "premiumtimes":    8,   # Premium Times (Nigeria)
    "punch":           7,   # Punch (Nigeria)
    "thecable":        7,   # The Cable (Nigeria)
    "dailynation":     8,   # Daily Nation (Kenya)
    "nation.africa":   8,   # Nation Africa (Kenya)
    "standardmedia":   7,   # Standard Media (Kenya)
    "capitalfm.co.ke": 7,   # Capital FM Kenya
    "monitor.co.ug":   7,   # Daily Monitor (Uganda)
    "newvision":       7,   # New Vision (Uganda)
    "theeastafrican":  8,   # The East African
    "myjoyonline":     7,   # Joy Online (Ghana)
    "graphic.com":     7,   # Graphic Online (Ghana)
    "ghanaweb":        6,   # GhanaWeb
    "pulse.ng":        7,   # Pulse Nigeria
    "pulse.gh":        6,   # Pulse Ghana
    "dailynews.co.tz": 6,   # Daily News Tanzania
    "thecitizen.co.tz":7,   # The Citizen Tanzania
    "thestar.co.ke":   7,   # The Star Kenya
    "seneweb":         6,   # Seneweb (Senegal)
    "togofirst":       6,   # Togo First
    "abidjan.net":     6,   # Abidjan.net
    "africanreview":   6,   # African Review
    "cnbcafrica":      8,   # CNBC Africa
    "trendsnafrica":   5,   # Trends in Africa
}


def reach_score(article, rss_position):
    """
    Compute an approximate popularity score for an article.
    Three components:
      publisher_score — based on known outlet reach (0–10)
      position_score  — RSS position 0 (top) adds 5, position 5+ adds 0
      text_score      — small bonus for articles where text was extracted
    """
    url_lo    = article.get("url", "").lower()       # lowercase URL for matching
    source_lo = article.get("source", "").lower()    # lowercase source name for matching
    publisher_score = max(                            # find highest matching publisher score
        (v for k, v in PUBLISHER_REACH.items() if k in url_lo or k in source_lo),
        default=3    # unknown publishers get 3 — not zero, may still be legitimate
    )
    position_score = max(0, 5 - rss_position)        # position 0 → 5pts, position 5+ → 0pts
    text_score     = 2 if article.get("paragraphs") else 0   # bonus for extracted text
    return publisher_score + position_score + text_score


def has_wdl_mention(article):
    """Return True if 'World Data Lab' or 'WDL' appears in the title or extracted paragraphs."""
    haystack = article.get("title", "").lower()      # start with the title
    for p in article.get("paragraphs", []):          # add each extracted paragraph
        haystack += " " + p.lower()
    return "world data lab" in haystack or " wdl " in haystack or haystack.startswith("wdl ")


def get_all_tags(article):
    """Return all tags for an article: demographic tags + WDL mention tag."""
    tags = list(article.get("demo_tags", []))        # copy demographic tags from search
    if has_wdl_mention(article):                     # check for World Data Lab mention
        tags.append("wdl")                           # add WDL tag if found
    return tags


# ── HTML helpers ──────────────────────────────────────────────────────────────

def esc(s):
    """Escape special HTML characters."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def make_anchor(s):
    """Convert string to safe HTML id."""
    return re.sub(r"[^\w]", "_", s)


# ── PART 1: CSV EXPORT ────────────────────────────────────────────────────────

def build_csv(results, path):
    """Write all articles from all entities to a flat CSV file."""
    fields = [
        "entity",          # country or regional bloc name
        "pillar",          # analytical pillar
        "title",           # article headline
        "url",             # direct article URL or Google News link
        "source",          # publisher name
        "date",            # publication date
        "demographics",    # comma-separated demographic labels found in title
        "wdl_mention",     # yes/no — whether World Data Lab is mentioned
        "text_paragraph_1",
        "text_paragraph_2",
        "text_paragraph_3",
        "has_text",        # yes if any paragraph text was extracted
        "is_google_link",  # yes if URL is still a Google News redirect
        "rss_position",    # position in Google News RSS feed (0 = top)
        "reach_score",     # computed popularity score
    ]
    rows = []
    for r in results:
        entity = r["entity"]
        for pillar, articles in r["categories"].items():
            for a in articles:
                paras = a.get("paragraphs", [])
                rows.append({
                    "entity":           entity,
                    "pillar":           pillar,
                    "title":            a["title"],
                    "url":              a["url"],
                    "source":           a.get("source", ""),
                    "date":             a.get("date", ""),
                    "demographics":     ", ".join(
                                            DEMO_LABELS.get(t, t)
                                            for t in a.get("demo_tags", [])
                                        ),
                    "wdl_mention":      "yes" if has_wdl_mention(a) else "no",
                    "text_paragraph_1": paras[0] if len(paras) > 0 else "",
                    "text_paragraph_2": paras[1] if len(paras) > 1 else "",
                    "text_paragraph_3": paras[2] if len(paras) > 2 else "",
                    "has_text":         "yes" if paras else "no",
                    "is_google_link":   "yes" if "google.com" in a["url"] else "no",
                    "rss_position":     a.get("rss_position", ""),
                    "reach_score":      reach_score(a, a.get("rss_position", 99)),
                })
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved CSV: {path}  ({len(rows)} rows)")

csv_path = os.path.join(os.getcwd(), f"africa-digest-{date_slug}.csv")
build_csv(results, csv_path)


# ── PART 2: PRODUCTION HTML REPORT ───────────────────────────────────────────

entity_map = {r["entity"]: r for r in results}
prod_date  = TODAY.strftime("%A %-d %B %Y")   # e.g. "Monday 14 May 2026"


def get_top_articles(entity_data, n=MAX_PER_COUNTRY):
    """
    Pool all articles across all pillars for one entity,
    sort by reach score descending, return top N.
    Deduplicates by URL in case the same article appeared in multiple pillars.
    """
    seen_urls = set()
    all_articles = []
    for pillar, articles in entity_data["categories"].items():
        for a in articles:
            if a["url"] not in seen_urls:          # deduplicate by URL
                seen_urls.add(a["url"])
                all_articles.append(a)
    return sorted(                                  # sort by reach score, highest first
        all_articles,
        key=lambda a: reach_score(a, a.get("rss_position", 99)),
        reverse=True
    )[:n]                                           # return top N


def render_article_card(a):
    """Render one article as an HTML card. No pillar label shown."""
    is_google = "google.com" in a["url"]           # True if URL is a Google News redirect
    tags      = get_all_tags(a)                    # demographic + WDL tags

    # Tag badges — small inline labels, no emoji, text only
    tags_html = ""
    if tags:
        tags_html = '<div class="tags">' + "".join(
            f'<span class="tag" style="border-color:{DEMO_COLOURS.get(t, "#555")};color:{DEMO_COLOURS.get(t, "#555")}">'
            f'{DEMO_LABELS.get(t, t)}</span>'
            for t in tags
        ) + "</div>"

    # Source and date line
    meta = " · ".join(p for p in [a.get("source", ""), a.get("date", "")] if p)

    # Excerpt or hyperlinked "Read article" — never show "Text not accessible"
    paras = a.get("paragraphs", [])
    if paras:
        ex_html = (
            '<div class="excerpt">'
            + "".join(f"<p>{esc(p)}</p>" for p in paras)
            + "</div>"
        )
    elif is_google or a.get("url"):                # has a URL — show hyperlinked read prompt
        ex_html = (
            f'<p class="read-link">'
            f'<a href="{esc(a["url"])}" target="_blank" rel="noopener">Read article</a>'
            f'</p>'
        )
    else:                                          # no URL at all — show nothing
        ex_html = ""

    return (
        '<article class="card">\n'
        + tags_html
        + f'<h4 class="card-hed"><a href="{esc(a["url"])}" target="_blank" rel="noopener">{esc(a["title"])}</a></h4>\n'
        + (f'<p class="card-meta">{esc(meta)}</p>\n' if meta else "")
        + ex_html
        + "\n</article>\n"
    )


def render_entity_block(entity, entity_data):
    """Render one country/region: heading + top N article cards."""
    articles = get_top_articles(entity_data)       # pool all pillars, sort by reach, take top 3
    if not articles:
        return ""                                  # no articles — skip this entity entirely
    anchor = make_anchor(entity)
    html   = f'<div class="entity-block" id="{anchor}">\n'
    html  += f'<h3 class="entity-hed">{esc(entity)}</h3>\n'
    for a in articles:
        html += render_article_card(a)
    html  += "</div>\n"
    return html


def render_section(section_label, section_id, entities):
    """Render one geographic section with a ruled header and entity blocks below."""
    body = ""
    for entity in entities:
        data = entity_map.get(entity)
        if not data:
            continue
        block = render_entity_block(entity, data)
        if block:
            body += block
    if not body:
        body = '<p class="empty">No results available this week.</p>\n'
    return (
        f'<section class="geo-section" id="{section_id}">\n'
        f'<div class="section-rule"><span class="section-label">{esc(section_label)}</span></div>\n'
        + body
        + "</section>\n"
    )


# ── Build sections ────────────────────────────────────────────────────────────
presence_html = render_section("Countries of Presence", "presence", PRESENCE)
waemu_html    = render_section("WAEMU",                 "waemu",    WAEMU_MEMBERS)
regional_html = render_section("Regional",              "regional", REGIONAL_SHOW)

# ── Build left sidebar nav ────────────────────────────────────────────────────
# Lists all countries and regions in reading order so the reader
# can see the full structure at a glance and jump directly to any country.
def sidebar_nav():
    html  = '<nav class="sidebar">\n'
    html += '<div class="sidebar-inner">\n'
    # Countries of Presence
    html += '<p class="nav-section-label">Countries of Presence</p>\n'
    for entity in PRESENCE:
        html += f'<a class="nav-link" href="#{make_anchor(entity)}">{esc(entity)}</a>\n'
    # WAEMU
    html += '<p class="nav-section-label">WAEMU</p>\n'
    for entity in WAEMU_MEMBERS:
        html += f'<a class="nav-link" href="#{make_anchor(entity)}">{esc(entity)}</a>\n'
    # Regional
    html += '<p class="nav-section-label">Regional</p>\n'
    for entity in REGIONAL_SHOW:
        html += f'<a class="nav-link" href="#{make_anchor(entity)}">{esc(entity)}</a>\n'
    html += '</div>\n</nav>\n'
    return html

nav_html = sidebar_nav()

# ── Assemble production HTML ──────────────────────────────────────────────────
prod_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly News Roundup: Africa Youth Employment &amp; Macrotrends — {prod_date}</title>
<style>
/* ── Reset ── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

/* ── Design tokens ── */
:root {{
  --paper:      #f5f2eb;   /* warm cream — aged newsprint feel */
  --ink:        #1a1a18;   /* near-black body text */
  --ink-2:      #3d3d38;   /* secondary text */
  --ink-3:      #7a7a72;   /* captions, metadata */
  --rule:       #ccc9be;   /* horizontal rules, borders */
  --rule-heavy: #1a1a18;   /* thick rules for section breaks */
  --accent:     #1c3d5c;   /* deep ink blue — headers, links */
  --serif:      "Georgia", "Times New Roman", serif;
  --sans:       "Helvetica Neue", "Arial", sans-serif;
  --mono:       "Courier New", monospace;
  --col-width:  680px;     /* main content column */
  --sidebar-w:  180px;     /* left sidebar width */
}}

/* ── Base ── */
html {{ scroll-behavior: smooth; font-size: 16px; }}
body {{
  font-family: var(--serif);
  background: var(--paper);
  color: var(--ink);
  line-height: 1.7;
}}

/* ── Page header — newspaper masthead style ── */
.masthead {{
  border-bottom: 3px double var(--rule-heavy);   /* double rule like a broadsheet */
  padding: 36px 24px 20px;
  text-align: center;
  max-width: 1100px;
  margin: 0 auto;
}}
.masthead-eyebrow {{
  font-family: var(--sans);
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: 10px;
}}
.masthead h1 {{
  font-family: var(--serif);
  font-size: clamp(26px, 4vw, 46px);
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--ink);
  margin-bottom: 10px;
}}
.masthead-dateline {{
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-top: 1px solid var(--rule);
  border-bottom: 1px solid var(--rule);
  padding: 7px 0;
  margin-top: 14px;
}}

/* ── Page layout: sidebar + content ── */
.page-wrap {{
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 0 0 80px;
}}

/* ── Left sidebar navigation ── */
.sidebar {{
  width: var(--sidebar-w);
  flex-shrink: 0;
  border-right: 1px solid var(--rule);
  position: sticky;
  top: 0;
  max-height: 100vh;
  overflow-y: auto;
  padding: 28px 0;
}}
.sidebar-inner {{
  padding: 0 16px;
}}
.nav-section-label {{
  font-family: var(--sans);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-3);
  border-bottom: 1px solid var(--rule);
  padding-bottom: 5px;
  margin: 20px 0 8px;
}}
.nav-section-label:first-child {{ margin-top: 0; }}
.nav-link {{
  display: block;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  padding: 3px 0;
  line-height: 1.4;
}}
.nav-link:hover {{ text-decoration: underline; }}

/* ── Main content column ── */
.content {{
  flex: 1;
  min-width: 0;
  padding: 28px 32px;
}}

/* ── Geographic section break ── */
.geo-section {{ margin-bottom: 60px; }}
.section-rule {{
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 32px;
  margin-top: 52px;
}}
.geo-section:first-child .section-rule {{ margin-top: 0; }}
.section-rule::before {{
  content: '';
  flex: 0 0 32px;
  height: 3px;
  background: var(--rule-heavy);   /* short thick rule before label */
}}
.section-rule::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--rule);         /* long thin rule after label */
}}
.section-label {{
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink);
  white-space: nowrap;
}}

/* ── Country/region heading ── */
.entity-block {{ margin-bottom: 44px; }}
.entity-hed {{
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  border-bottom: 1px solid var(--rule);
  padding-bottom: 8px;
  margin-bottom: 18px;
  letter-spacing: -0.01em;
}}

/* ── Article card — clean, editorial, no decorative borders ── */
.card {{
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--rule);   /* simple ruled separator between articles */
}}
.card:last-child {{
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}}
.card-hed {{
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.35;
  margin-bottom: 5px;
}}
.card-hed a {{
  color: var(--ink);
  text-decoration: none;
}}
.card-hed a:hover {{
  color: var(--accent);
  text-decoration: underline;
}}
.card-meta {{
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.03em;
  margin-bottom: 10px;
}}
.excerpt {{
  font-family: var(--serif);
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-2);
}}
.excerpt p {{ margin-bottom: 8px; }}
.excerpt p:last-child {{ margin: 0; }}
.read-link {{
  font-family: var(--sans);
  font-size: 12px;
  margin-top: 6px;
}}
.read-link a {{
  color: var(--accent);
  text-decoration: underline;
}}

/* ── Tags — small outlined labels, no filled backgrounds, text only ── */
.tags {{ margin-bottom: 8px; }}
.tag {{
  display: inline-block;
  font-family: var(--sans);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 6px;
  border: 1px solid currentColor;   /* uses the colour variable set inline */
  border-radius: 2px;
  margin-right: 5px;
  line-height: 1.6;
}}

/* ── Footer ── */
.footer {{
  border-top: 3px double var(--rule);   /* double rule mirrors masthead */
  padding: 32px 24px;
  text-align: center;
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.8;
  max-width: 1100px;
  margin: 0 auto;
}}
.footer strong {{ color: var(--ink-2); }}

/* ── Mobile: collapse sidebar to top list ── */
@media (max-width: 700px) {{
  .page-wrap {{ flex-direction: column; }}
  .sidebar {{
    width: 100%;
    position: static;
    max-height: none;
    border-right: none;
    border-bottom: 1px solid var(--rule);
    padding: 16px 0;
    overflow-y: visible;
  }}
  .sidebar-inner {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px 12px;
    padding: 0 16px;
  }}
  .nav-section-label {{
    width: 100%;
    margin: 10px 0 4px;
  }}
  .content {{ padding: 20px 16px; }}
}}

.empty {{ font-family: var(--sans); font-size: 13px; color: var(--ink-3); font-style: italic; }}
</style>
</head>
<body>

<!-- Newspaper-style masthead -->
<header class="masthead">
  <p class="masthead-eyebrow">Weekly News Roundup</p>
  <h1>Africa Youth Employment<br>&amp; Macrotrends</h1>
  <p class="masthead-dateline">{prod_date}</p>
</header>

<!-- Page body: sidebar + scrolling content -->
<div class="page-wrap">

  <!-- Left sidebar: full country/region index -->
  {nav_html}

  <!-- Main content: continuous scroll through all sections -->
  <main class="content">
    {presence_html}
    {waemu_html}
    {regional_html}
  </main>

</div>

<!-- Footer with scraping disclaimer -->
<footer class="footer">
  <strong>Weekly News Roundup: Africa Youth Employment &amp; Macrotrends</strong><br>
  {prod_date} &nbsp;·&nbsp; {generated}<br>
  Articles sourced from Google News RSS. Up to {MAX_PER_COUNTRY} articles per country, ranked by estimated reach.<br>
  Excerpts are reproduced verbatim from publisher pages where accessible.<br><br>
  This roundup is produced automatically through a news scraper. Kindly click each article
  title to read the full piece on the original publisher's site. Content has not been
  editorially reviewed.<br><br>
  Tags: <strong>Youth · Women · Disabilities · Refugees · World Data Lab</strong> —
  applied where mentioned in article titles or extracted text.
</footer>

</body>
</html>"""

# ── Save production report ────────────────────────────────────────────────────
prod_filename = f"news-digest-{date_slug}.html"              # e.g. news-digest-2026-05-25.html
prod_path     = os.path.join(os.getcwd(), prod_filename)
with open(prod_path, "w", encoding="utf-8") as f:
    f.write(prod_html)
print(f"Saved production report: {prod_path}")


# ── Update archive index.html ─────────────────────────────────────────────────
index_path      = os.path.join(os.getcwd(), "index.html")
archive_entries = []                                         # list of (filename, display_date) tuples

if os.path.exists(index_path):                              # preserve existing issue links
    with open(index_path, "r", encoding="utf-8") as f:
        existing = f.read()
    for m in re.finditer(r'href="(news-digest-[\d-]+\.html)"[^>]*>([^<]+)<', existing):
        entry = (m.group(1), m.group(2))
        if entry not in archive_entries:
            archive_entries.append(entry)

this_entry = (prod_filename, prod_date)
if this_entry not in archive_entries:
    archive_entries.insert(0, this_entry)                   # newest issue first

archive_rows = "\n".join(
    f'    <li><a href="{fn}">{label}</a></li>'
    for fn, label in archive_entries
)

index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly News Roundup: Africa Youth Employment &amp; Macrotrends</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{ --paper: #f5f2eb; --ink: #1a1a18; --ink-3: #7a7a72; --accent: #1c3d5c; --rule: #ccc9be; }}
body {{ font-family: Georgia, serif; background: var(--paper); color: var(--ink); }}
.masthead {{
  border-bottom: 3px double var(--ink);
  padding: 48px 24px 24px;
  text-align: center;
  max-width: 700px;
  margin: 0 auto;
}}
.eyebrow {{ font-family: sans-serif; font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 12px; }}
h1 {{ font-size: clamp(24px, 5vw, 40px); font-weight: 700; line-height: 1.15; margin-bottom: 10px; }}
.dateline {{ font-family: sans-serif; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); border-top: 1px solid var(--rule); padding-top: 10px; margin-top: 14px; }}
.container {{ max-width: 600px; margin: 52px auto 80px; padding: 0 20px; }}
h2 {{ font-family: sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); border-bottom: 1px solid var(--rule); padding-bottom: 8px; margin-bottom: 20px; }}
ul {{ list-style: none; }}
li {{ border-bottom: 1px solid var(--rule); }}
li a {{ display: flex; justify-content: space-between; padding: 14px 0; font-size: 16px; color: var(--accent); text-decoration: none; }}
li a:hover {{ color: var(--ink); }}
.footer {{ text-align: center; font-family: sans-serif; font-size: 11px; color: var(--ink-3); padding: 32px 24px; border-top: 1px solid var(--rule); max-width: 700px; margin: 0 auto; line-height: 1.7; }}
</style>
</head>
<body>
<div class="masthead">
  <p class="eyebrow">Archive</p>
  <h1>Weekly News Roundup:<br>Africa Youth Employment &amp; Macrotrends</h1>
  <p class="dateline">All issues</p>
</div>
<div class="container">
  <h2>Issues</h2>
  <ul>
{archive_rows}
  </ul>
</div>
<div class="footer">
  Produced automatically each Monday from Google News RSS.<br>
  Content has not been editorially reviewed.
</div>
</body>
</html>"""

with open(index_path, "w", encoding="utf-8") as f:
    f.write(index_html)
print(f"Saved archive index: {index_path}")

print(f"\nFiles ready to commit:")
print(f"  {prod_filename}")
print(f"  index.html")
print(f"  africa-digest-{date_slug}.csv")
