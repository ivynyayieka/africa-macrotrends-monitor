# production_export.py
# Reads results.pkl written by sophisticated_search.py.
# Produces three output files:
#   africa-digest-YYYY-MM-DD.csv        full data export of all articles
#   news-digest-YYYY-MM-DD.html         production report for GitHub Pages
#   index.html                          archive landing page listing all past issues

# ── Imports ───────────────────────────────────────────────────────────────────
import pickle                  # loads the binary results file saved by sophisticated_search.py
import csv                     # writes the flat CSV data export
import os                      # file path construction and existence checks
import re                      # regular expressions for anchor-safe string cleaning
from datetime import datetime  # formats dates for display in the HTML

# ── Load results ──────────────────────────────────────────────────────────────
with open("results.pkl", "rb") as f:   # open the binary file written by sophisticated_search.py
    data = pickle.load(f)              # deserialise the dict back into Python objects

results   = data["results"]    # list of per-entity dicts, each with a "categories" sub-dict
generated = data["generated"]  # timestamp string e.g. "Mon, 14 May 2026 06:12 UTC"
TODAY     = data["today"]      # datetime object — used to format the production date
date_slug = data["date_slug"]  # YYYY-MM-DD string used in output filenames
total_a   = data["total_a"]    # total articles collected across all entities and pillars
total_t   = data["total_t"]    # subset of total_a where text was successfully extracted

print(f"Loaded {len(results)} entities | {total_a} articles | {total_t} with text")   # confirm load

# ── Tag labels and colours ────────────────────────────────────────────────────
# Tags are applied to articles where these terms appear in the title or text.
# DEMO_LABELS maps internal detection keys to display strings.
DEMO_LABELS = {
    "youth":     "Youth",           # youth employment / young people
    "women":     "Women",           # women's economic participation
    "disabilit": "Disabilities",    # disability (substring catches disability/disabilities)
    "refugee":   "Refugees",        # refugee / displaced worker issues
    "wdl":       "World Data Lab",  # World Data Lab mention in title or text
}

# DEMO_COLOURS maps each tag key to a dark colour used for the outlined tag badge
DEMO_COLOURS = {
    "youth":     "#1a3a5c",   # dark navy
    "women":     "#4a2060",   # deep plum
    "disabilit": "#1a5c3a",   # dark green
    "refugee":   "#7a3a10",   # dark amber
    "wdl":       "#5c1a1a",   # dark crimson — visually distinct from the demographics
}

# ── Production configuration ──────────────────────────────────────────────────
MAX_PER_COUNTRY = 3   # articles shown per country/region in the production report,
                      # pooled across all pillars and ranked by estimated reach score

# Countries where the organisation has a direct operational presence
PRESENCE = [
    "Ethiopia", "Ghana", "Kenya", "Nigeria", "Rwanda", "Senegal", "Uganda",   # Senegal also a WAEMU member but shown here only
]

# WAEMU member states — Senegal excluded here because it already appears under PRESENCE
WAEMU_MEMBERS = [
    "Benin", "Burkina Faso", "Côte d'Ivoire", "Guinea-Bissau",   # 7 members; Senegal is the 8th but shown under PRESENCE
    "Mali", "Niger", "Togo",
]

# Regional bloc queries to show in the Regional section
REGIONAL_SHOW = ["WAEMU", "Africa"]   # regional bloc queries shown in the Regional section

# Order pillars appear under each country in the production report
# Country-Specific Context always last — only shown when QRM keywords produced results
PILLAR_ORDER = [
    "Jobs & Employment",              # core employment signals — always first
    "Macroeconomy",                   # economic conditions and regional integration
    "Digital Economy",                # digital access, ICT, fintech, AI
    "Governance",                     # political signals, elections, civil society
    "Agrifood & Climate",             # food security, agriculture, climate
    "Workforce & Human Capital",      # education, skills, migration, health
    "Country-Specific Context",       # QRM-driven keywords — only appears where defined
]

# ── Publisher reach scores ────────────────────────────────────────────────────
# Used to rank articles by estimated audience size.
# Scale: 10 = global wire services, 9 = major international, 8 = leading African
# nationals, 7 = strong regional, 6 = smaller local, 3 = unknown (default).
PUBLISHER_REACH = {
    # Global wire services
    "bbc":             10,   # BBC
    "reuters":         10,   # Reuters
    "apnews":          10,   # Associated Press
    "afp":             10,   # Agence France-Presse
    "bloomberg":       10,   # Bloomberg
    # Major international
    "aljazeera":        9,   # Al Jazeera
    "theguardian":      9,   # The Guardian
    "economist":        9,   # The Economist
    "ft.com":           9,   # Financial Times
    "washingtonpost":   9,   # Washington Post
    "nytimes":          9,   # New York Times
    "dw.com":           8,   # Deutsche Welle
    "france24":         8,   # France 24
    "rfi":              8,   # Radio France Internationale
    "voaafrica":        8,   # Voice of America Africa
    # Pan-African
    "theafricareport":  8,   # The Africa Report
    "cnbcafrica":       8,   # CNBC Africa
    "theeastafrican":   8,   # The East African
    "africafeeds":      7,   # Africa Feeds
    "africanews":       7,   # Africanews
    "quartz":           7,   # Quartz Africa
    # Nigeria
    "businessday":      8,   # Business Day
    "premiumtimes":     8,   # Premium Times
    "punch":            7,   # Punch
    "thecable":         7,   # The Cable
    "pulse.ng":         7,   # Pulse Nigeria
    # Kenya
    "dailynation":      8,   # Daily Nation
    "nation.africa":    8,   # Nation Africa
    "standardmedia":    7,   # Standard Media
    "capitalfm.co.ke":  7,   # Capital FM Kenya
    "thestar.co.ke":    7,   # The Star Kenya
    # Uganda
    "monitor.co.ug":    7,   # Daily Monitor
    "newvision":        7,   # New Vision
    # Ghana
    "myjoyonline":      7,   # Joy Online
    "graphic.com":      7,   # Graphic Online
    "ghanaweb":         6,   # GhanaWeb
    "pulse.gh":         6,   # Pulse Ghana
    # Tanzania
    "thecitizen.co.tz": 7,   # The Citizen
    "dailynews.co.tz":  6,   # Daily News
    # West Africa / regional
    "seneweb":          6,   # Seneweb (Senegal)
    "togofirst":        6,   # Togo First
    "abidjan.net":      6,   # Abidjan.net (Côte d'Ivoire)
    "africanreview":    6,   # African Review
    "trendsnafrica":    5,   # Trends in Africa
}


def reach_score(article, rss_position):   # returns integer score — higher means more likely widely read
    """
    Estimate how widely-read an article is likely to be.
    Combines three signals:
      publisher_score — audience size of the outlet (from PUBLISHER_REACH)
      position_score  — how high the article ranked in the RSS feed
      text_score      — bonus if we successfully extracted the article text
    Returns a single integer; higher = more popular.
    """
    url_lo    = article.get("url",    "").lower()   # lowercase URL for publisher matching
    source_lo = article.get("source", "").lower()   # lowercase source name for matching
    publisher_score = max(                           # find the highest matching score in PUBLISHER_REACH
        (v for k, v in PUBLISHER_REACH.items() if k in url_lo or k in source_lo),   # match publisher by URL or source name
        default=3    # unknown publishers get 3 — not zero, may still be a legitimate outlet
    )
    position_score = max(0, 5 - rss_position)       # RSS position 0 → 5 pts; position 5+ → 0 pts
    text_score     = 2 if article.get("paragraphs") else 0   # bonus for articles with extracted text
    return publisher_score + position_score + text_score      # sum all three components


def has_wdl_mention(article):   # returns True if World Data Lab is mentioned in title or extracted text
    """
    Return True if 'World Data Lab' or 'WDL' appears in the article title
    or any of the extracted text paragraphs.
    """
    haystack = article.get("title", "").lower()   # start with the title text
    for p in article.get("paragraphs", []):       # add each extracted paragraph
        haystack += " " + p.lower()   # accumulate all paragraph text for searching
    # check for full name or standalone acronym (spaces prevent matching e.g. "BWDL")
    return "world data lab" in haystack or " wdl " in haystack or haystack.startswith("wdl ")   # check full name or standalone acronym


def get_all_tags(article):   # returns combined list of demographic tags + WDL tag if applicable
    """
    Return the complete list of tags for one article:
    demographic detection keys + 'wdl' if World Data Lab is mentioned.
    """
    tags = list(article.get("demo_tags", []))   # copy existing demographic tags from the search
    if has_wdl_mention(article):                # check for World Data Lab in title/text
        tags.append("wdl")                      # add the WDL tag key
    return tags


# ── HTML helpers ──────────────────────────────────────────────────────────────

def esc(s):
    """Escape special HTML characters to prevent broken markup."""
    return (
        str(s)
        .replace("&", "&amp;")    # must come first — other replacements introduce &
        .replace("<", "&lt;")     # less-than
        .replace(">", "&gt;")     # greater-than
        .replace('"', "&quot;")   # double-quote inside attribute values
    )

def make_anchor(s):
    """Convert a country/region name to a valid HTML id attribute (alphanumeric + underscore)."""
    return re.sub(r"[^\w]", "_", s)   # replace spaces, apostrophes, accents etc with underscore


# ── PART 1: CSV EXPORT ────────────────────────────────────────────────────────

def build_csv(results, path):
    """Write one row per article to a CSV file with all metadata and extracted text."""
    fields = [
        "entity",           # country or regional bloc name
        "pillar",           # analytical pillar the article was found under
        "title",            # article headline
        "url",              # direct publisher URL or Google News redirect link
        "source",           # publisher name e.g. "BBC"
        "date",             # publication date formatted as "14 May 2026"
        "demographics",     # comma-separated demographic labels found in the title
        "wdl_mention",      # "yes" if World Data Lab appears in title or text
        "text_paragraph_1", # first extracted paragraph (verbatim from article page)
        "text_paragraph_2", # second extracted paragraph
        "text_paragraph_3", # third extracted paragraph
        "has_text",         # "yes" if any paragraph text was extracted, "no" otherwise
        "is_google_link",   # "yes" if the URL is still a Google News redirect
        "rss_position",     # article's position in the Google News RSS feed (0 = top)
        "reach_score",      # computed popularity score for this article
    ]
    rows = []                                          # accumulate one dict per article
    for r in results:                                  # loop through each entity (country/region)
        entity = r["entity"]                           # entity name string
        for pillar, articles in r["categories"].items():   # loop through each pillar's article list
            for a in articles:                         # loop through individual articles
                paras = a.get("paragraphs", [])        # extracted text paragraphs (may be empty)
                rows.append({
                    "entity":           entity,
                    "pillar":           pillar,
                    "title":            a["title"],
                    "url":              a["url"],
                    "source":           a.get("source", ""),
                    "date":             a.get("date", ""),
                    "demographics":     ", ".join(          # join all demographic labels with comma+space
                                            DEMO_LABELS.get(t, t)
                                            for t in a.get("demo_tags", [])
                                        ),
                    "wdl_mention":      "yes" if has_wdl_mention(a) else "no",
                    "text_paragraph_1": paras[0] if len(paras) > 0 else "",   # blank if not available
                    "text_paragraph_2": paras[1] if len(paras) > 1 else "",
                    "text_paragraph_3": paras[2] if len(paras) > 2 else "",
                    "has_text":         "yes" if paras else "no",
                    "is_google_link":   "yes" if "google.com" in a["url"] else "no",
                    "rss_position":     a.get("rss_position", ""),             # empty if not recorded
                    "reach_score":      reach_score(a, a.get("rss_position", 99)),   # 99 = unknown position
                })
    with open(path, "w", newline="", encoding="utf-8") as f:   # UTF-8 handles accented characters
        writer = csv.DictWriter(f, fieldnames=fields)           # writes rows as dicts keyed by field name
        writer.writeheader()    # write column names as first row
        writer.writerows(rows)  # write all article rows
    print(f"Saved CSV: {path}  ({len(rows)} rows)")

csv_path = os.path.join(os.getcwd(), f"africa-digest-{date_slug}.csv")   # dated filename
build_csv(results, csv_path)   # run the export


# ── PART 2: PRODUCTION HTML REPORT ───────────────────────────────────────────

entity_map = {r["entity"]: r for r in results}   # dict keyed by entity name for fast lookup
prod_date  = TODAY.strftime("%A %-d %B %Y")       # e.g. "Monday 14 May 2026" for the masthead


def get_top_articles(entity_data, n=MAX_PER_COUNTRY):
    """
    Pool all articles from all pillars for one entity, deduplicate by URL,
    sort by reach score descending, and return the top N.
    Returns list of (pillar_name, article) tuples so the pillar label is preserved.
    """
    seen_urls    = set()         # track URLs already added to prevent duplicates
    all_articles = []
    for pillar, articles in entity_data["categories"].items():   # merge across all pillars
        for a in articles:
            if a["url"] not in seen_urls:        # only add each URL once
                seen_urls.add(a["url"])
                all_articles.append((pillar, a)) # store (pillar, article) tuple
    # sort by reach score descending
    all_articles.sort(
        key=lambda pa: reach_score(pa[1], pa[1].get("rss_position", 99)),
        reverse=True
    )
    return all_articles[:n]                      # return top N (pillar, article) tuples


def render_article_card(a):
    """
    Render one article as a clean editorial card.
    No pillar label shown. No 'text not accessible' message.
    'Read article' appears as a hyperlink when no excerpt text is available.
    """
    is_google = "google.com" in a["url"]    # True if URL is a Google News redirect
    tags      = get_all_tags(a)             # all applicable tags (demographics + WDL)

    # Tag badges — small outlined text labels, no filled backgrounds, no emoji
    tags_html = ""
    if tags:
        tags_html = '<div class="tags">' + "".join(
            f'<span class="tag" style="border-color:{DEMO_COLOURS.get(t, "#555")};'
            f'color:{DEMO_COLOURS.get(t, "#555")}">'
            f'{DEMO_LABELS.get(t, t)}</span>'
            for t in tags         # one badge per tag
        ) + "</div>"

    # Source · date metadata line
    meta = " · ".join(p for p in [a.get("source", ""), a.get("date", "")] if p)

    # Excerpt block — show text if available, hyperlinked 'Read article' if not
    # Never show 'Text not accessible'
    paras = a.get("paragraphs", [])
    if paras:                                   # text was successfully extracted
        ex_html = (
            '<div class="excerpt">'
            + "".join(f"<p>{esc(p)}</p>" for p in paras)   # each paragraph wrapped in <p>
            + "</div>"
        )
    elif is_google or a.get("url"):             # no text but URL exists — show hyperlinked prompt
        ex_html = (
            f'<p class="read-link">'
            f'<a href="{esc(a["url"])}" target="_blank" rel="noopener">Read article</a>'
            f'</p>'
        )
    else:                                       # no URL at all — show nothing
        ex_html = ""

    return (
        '<article class="card">\n'
        + tags_html                             # tag badges (empty string if no tags)
        + f'<h4 class="card-hed">'
          f'<a href="{esc(a["url"])}" target="_blank" rel="noopener">'
          f'{esc(a["title"])}</a></h4>\n'       # clickable headline
        + (f'<p class="card-meta">{esc(meta)}</p>\n' if meta else "")   # source · date line
        + ex_html                               # excerpt paragraphs or 'Read article' link
        + "\n</article>\n"
    )


def render_entity_block(entity, entity_data):
    """
    Render one country or region: a heading, then articles grouped by pillar.
    Top N articles are selected by reach score across all pillars, then
    grouped under their pillar label for display. Pillars shown in PILLAR_ORDER.
    Returns empty string if no articles — caller skips empty blocks.
    """
    top_pairs = get_top_articles(entity_data)  # list of (pillar, article) tuples, sorted by reach
    if not top_pairs:
        return ""                              # nothing to show — skip entirely

    # Group the top articles by pillar, preserving PILLAR_ORDER
    from collections import defaultdict
    by_pillar = defaultdict(list)
    for pillar, a in top_pairs:
        by_pillar[pillar].append(a)            # group articles under their pillar name

    anchor = make_anchor(entity)              # safe HTML id for in-page navigation
    html   = f'<div class="entity-block" id="{anchor}">\n'
    html  += f'<h3 class="entity-hed">{esc(entity)}</h3>\n'

    for pillar in PILLAR_ORDER:               # iterate in defined order so pillars appear consistently
        articles = by_pillar.get(pillar, [])
        if not articles:
            continue                          # this pillar has no top articles for this entity — skip
        html += f'<div class="pillar-block">\n'
        html += f'<div class="pillar-label">{esc(pillar)}</div>\n'   # plain text label, no emoji
        for a in articles:
            html += render_article_card(a)    # append one card per article
        html += "</div>\n"                   # close pillar-block

    html += "</div>\n"                       # close entity-block
    return html


def render_section(section_label, section_id, entities):
    """
    Render one geographic section: a ruled header + all entity blocks.
    Skips entities with no articles. Shows a fallback message if the whole section is empty.
    """
    body = ""
    for entity in entities:                    # loop through countries/regions in this section
        data  = entity_map.get(entity)         # look up this entity's search results
        if not data:
            continue                           # entity was not searched — skip
        block = render_entity_block(entity, data)
        if block:
            body += block                      # only add if there is content
    if not body:                               # entire section has no results
        body = '<p class="empty">No results available this week.</p>\n'
    return (
        f'<section class="geo-section" id="{section_id}">\n'
        f'<div class="section-rule">'
        f'<span class="section-label">{esc(section_label)}</span>'
        f'</div>\n'
        + body
        + "</section>\n"
    )


# Build the three geographic sections
presence_html = render_section("Countries of Presence", "presence", PRESENCE)
waemu_html    = render_section("WAEMU",                 "waemu",    WAEMU_MEMBERS)
regional_html = render_section("Regional",              "regional", REGIONAL_SHOW)


def sidebar_nav():
    """
    Build the left sidebar: a vertical index of all countries and regions
    with anchor links so the reader can jump directly to any section.
    On mobile this collapses to an inline list at the top of the page.
    """
    html  = '<nav class="sidebar">\n<div class="sidebar-inner">\n'
    html += '<p class="nav-section-label">Countries of Presence</p>\n'
    for entity in PRESENCE:                    # one link per country of presence
        html += f'<a class="nav-link" href="#{make_anchor(entity)}">{esc(entity)}</a>\n'
    html += '<p class="nav-section-label">WAEMU</p>\n'
    for entity in WAEMU_MEMBERS:              # one link per WAEMU member
        html += f'<a class="nav-link" href="#{make_anchor(entity)}">{esc(entity)}</a>\n'
    html += '<p class="nav-section-label">Regional</p>\n'
    for entity in REGIONAL_SHOW:              # one link per regional bloc
        html += f'<a class="nav-link" href="#{make_anchor(entity)}">{esc(entity)}</a>\n'
    html += '</div>\n</nav>\n'
    return html

nav_html  = sidebar_nav()                     # generate the sidebar HTML
prod_date = TODAY.strftime("%A %-d %B %Y")    # formatted date for masthead display

# ── Assemble production HTML ──────────────────────────────────────────────────
# The HTML string uses double-braces {{ }} to escape literal braces inside
# the f-string (Python f-strings use single braces for expressions).
prod_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly News Roundup: Africa Youth Employment &amp; Macrotrends — {prod_date}</title>
<style>
/* Reset: remove browser default margin/padding; use border-box sizing */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

/* Design tokens — change these to restyle the whole report */
:root {{
  --paper:      #f5f2eb;   /* warm cream background — aged newsprint feel */
  --ink:        #1a1a18;   /* near-black body text */
  --ink-2:      #3d3d38;   /* slightly lighter for excerpts */
  --ink-3:      #7a7a72;   /* grey for captions and metadata */
  --rule:       #ccc9be;   /* warm grey for light borders */
  --rule-heavy: #1a1a18;   /* near-black for masthead double-rule */
  --accent:     #1c3d5c;   /* deep ink-blue for headings and links */
  --serif:      "Georgia", "Times New Roman", serif;
  --sans:       "Helvetica Neue", "Arial", sans-serif;
  --sidebar-w:  180px;     /* width of the left navigation sidebar */
}}

html {{ scroll-behavior: smooth; font-size: 16px; }}   /* smooth anchor scrolling */
body {{ font-family: var(--serif); background: var(--paper); color: var(--ink); line-height: 1.7; }}

/* Masthead — newspaper broadsheet header style */
.masthead {{
  border-bottom: 3px double var(--rule-heavy);   /* double rule like a broadsheet newspaper */
  padding: 36px 24px 20px;
  text-align: center;
  max-width: 1100px;
  margin: 0 auto;
}}
.masthead-eyebrow {{                             /* small uppercase label above the title */
  font-family: var(--sans);
  font-size: 10px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin-bottom: 10px;
}}
.masthead h1 {{
  font-family: var(--serif);
  font-size: clamp(26px, 4vw, 46px);   /* responsive — large on desktop, readable on mobile */
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.02em;
  color: var(--ink);
  margin-bottom: 10px;
}}
.masthead-dateline {{                            /* date line with thin rules above and below */
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

/* Page body layout: sidebar on left, content on right */
.page-wrap {{
  max-width: 1100px;
  margin: 0 auto;
  display: flex;                /* side-by-side on desktop */
  align-items: flex-start;
  padding: 0 0 80px;
}}

/* Left sidebar navigation */
.sidebar {{
  width: var(--sidebar-w);
  flex-shrink: 0;               /* sidebar never shrinks — content column takes remaining space */
  border-right: 1px solid var(--rule);
  position: sticky;             /* sidebar stays visible while content scrolls */
  top: 0;
  max-height: 100vh;            /* never taller than the viewport */
  overflow-y: auto;             /* scrollable if the country list exceeds the viewport height */
  padding: 28px 0;
}}
.sidebar-inner {{ padding: 0 16px; }}
.nav-section-label {{            /* section heading inside sidebar e.g. "Countries of Presence" */
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
.nav-section-label:first-child {{ margin-top: 0; }}   /* no top margin for first label */
.nav-link {{                     /* individual country/region link in sidebar */
  display: block;
  font-family: var(--sans);
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  padding: 3px 0;
  line-height: 1.4;
}}
.nav-link:hover {{ text-decoration: underline; }}

/* Main content area */
.content {{
  flex: 1;          /* takes all remaining horizontal space after sidebar */
  min-width: 0;     /* prevents flex overflow on narrow screens */
  padding: 28px 32px;
}}

/* Geographic section — one per grouping (Presence, WAEMU, Regional) */
.geo-section {{ margin-bottom: 60px; }}
.section-rule {{                 /* ruled divider with section label centred in it */
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 32px;
  margin-top: 52px;
}}
.geo-section:first-child .section-rule {{ margin-top: 0; }}   /* no top margin for first section */
.section-rule::before {{         /* short thick bar to the left of the label */
  content: '';
  flex: 0 0 32px;
  height: 3px;
  background: var(--rule-heavy);
}}
.section-rule::after {{          /* long thin rule to the right of the label */
  content: '';
  flex: 1;
  height: 1px;
  background: var(--rule);
}}
.section-label {{
  font-family: var(--sans);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ink);
  white-space: nowrap;           /* label never wraps onto two lines */
}}

/* Entity block — one per country or region */
.entity-block {{ margin-bottom: 44px; }}
.entity-hed {{                   /* country/region heading with underline rule */
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 700;
  color: var(--accent);
  border-bottom: 1px solid var(--rule);
  padding-bottom: 8px;
  margin-bottom: 18px;
  letter-spacing: -0.01em;
}}

/* Article card — plain ruled separator, no border-box or background */
.card {{
  margin-bottom: 24px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--rule);   /* simple rule between articles */
}}
.card:last-child {{              /* no rule or padding after the last card */
  border-bottom: none;
  margin-bottom: 0;
  padding-bottom: 0;
}}
.card-hed {{                     /* article headline */
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 700;
  line-height: 1.35;
  margin-bottom: 5px;
}}
.card-hed a {{                   /* headline link — dark ink, underlines on hover */
  color: var(--ink);
  text-decoration: none;
}}
.card-hed a:hover {{ color: var(--accent); text-decoration: underline; }}
.card-meta {{                    /* source · date line */
  font-family: var(--sans);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.03em;
  margin-bottom: 10px;
}}
.excerpt {{                      /* verbatim article text */
  font-family: var(--serif);
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-2);
}}
.excerpt p {{ margin-bottom: 8px; }}
.excerpt p:last-child {{ margin: 0; }}
.read-link {{                    /* 'Read article' hyperlink shown when no text is available */
  font-family: var(--sans);
  font-size: 12px;
  margin-top: 6px;
}}
.read-link a {{ color: var(--accent); text-decoration: underline; }}

/* Tag badges — outlined text labels, no filled backgrounds, no emoji */
.tags {{ margin-bottom: 8px; }}
.tag {{
  display: inline-block;
  font-family: var(--sans);
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 6px;
  border: 1px solid currentColor;   /* border colour set inline via style attribute */
  border-radius: 2px;
  margin-right: 5px;
  line-height: 1.6;
}}

/* Footer */
.footer {{
  border-top: 3px double var(--rule);   /* double rule mirrors the masthead */
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

/* Mobile: collapse sidebar to a horizontal list at the top */
@media (max-width: 700px) {{
  .page-wrap {{ flex-direction: column; }}   /* stack sidebar above content */
  .sidebar {{
    width: 100%;
    position: static;             /* no longer sticky on mobile */
    max-height: none;
    border-right: none;
    border-bottom: 1px solid var(--rule);
    padding: 16px 0;
    overflow-y: visible;
  }}
  .sidebar-inner {{               /* lay links out horizontally on mobile */
    display: flex;
    flex-wrap: wrap;
    gap: 4px 12px;
    padding: 0 16px;
  }}
  .nav-section-label {{ width: 100%; margin: 10px 0 4px; }}   /* full-width labels on mobile */
  .content {{ padding: 20px 16px; }}
}}

.empty {{ font-family: var(--sans); font-size: 13px; color: var(--ink-3); font-style: italic; }}
</style>
</head>
<body>

<!-- Newspaper-style masthead with title, kicker, and dateline -->
<header class="masthead">
  <p class="masthead-eyebrow">Weekly News Roundup</p>
  <h1>Africa Youth Employment<br>&amp; Macrotrends</h1>
  <p class="masthead-dateline">{prod_date}</p>
</header>

<!-- Page body: sticky sidebar on left, scrolling content on right -->
<div class="page-wrap">

  <!-- Left sidebar: full index of all countries and regions with anchor links -->
  {nav_html}

  <!-- Main content: Countries of Presence → WAEMU → Regional in one continuous scroll -->
  <main class="content">
    {presence_html}
    {waemu_html}
    {regional_html}
  </main>

</div>

<!-- Footer with scraping disclaimer and tag legend -->
<footer class="footer">
  <strong>Weekly News Roundup: Africa Youth Employment &amp; Macrotrends</strong><br>
  {prod_date} &nbsp;·&nbsp; {generated}<br>
  Articles sourced from Google News RSS · Top {MAX_PER_COUNTRY} per country ranked by estimated reach<br>
  Excerpts reproduced verbatim from publisher pages where accessible<br><br>
  This roundup is produced automatically through a news scraper. Kindly click each article
  title to read the full piece on the original publisher's site. Content has not been
  editorially reviewed.<br><br>
  Tags applied where terms appear in article titles or extracted text:
  <strong>Youth · Women · Disabilities · Refugees · World Data Lab</strong>
</footer>

</body>
</html>"""

# ── Save the production report ────────────────────────────────────────────────
prod_filename = f"news-digest-{date_slug}.html"           # e.g. news-digest-2026-05-25.html
prod_path     = os.path.join(os.getcwd(), prod_filename)  # full path in the working directory
with open(prod_path, "w", encoding="utf-8") as f:
    f.write(prod_html)                                    # write the assembled HTML to disk
print(f"Saved production report: {prod_path}")


# ── Update the archive index.html ─────────────────────────────────────────────
# index.html is the landing page listing all past digest issues.
# Each run reads the existing index, extracts any links already there,
# prepends this week's entry, and rewrites the file.

index_path      = os.path.join(os.getcwd(), "index.html")
archive_entries = []   # will hold (filename, display_date) tuples, newest first

if os.path.exists(index_path):                            # index exists from a previous run
    with open(index_path, "r", encoding="utf-8") as f:
        existing = f.read()                               # read the current archive page
    for m in re.finditer(                                 # find all existing issue links
        r'href="(news-digest-[\d-]+\.html)"[^>]*>([^<]+)<', existing
    ):
        entry = (m.group(1), m.group(2))                  # (filename, display label)
        if entry not in archive_entries:
            archive_entries.append(entry)                 # preserve existing entries

this_entry = (prod_filename, prod_date)                   # this week's entry
if this_entry not in archive_entries:                     # avoid duplicates on re-run
    archive_entries.insert(0, this_entry)                 # newest issue goes at the top

archive_rows = "\n".join(                                 # build one <li> per issue
    f'    <li><a href="{fn}">{label}</a></li>'
    for fn, label in archive_entries
)

# Build the archive index page — minimal, matches the digest's visual style
index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly News Roundup: Africa Youth Employment &amp; Macrotrends</title>
<style>
/* Reset and base */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{ --paper: #f5f2eb; --ink: #1a1a18; --ink-3: #7a7a72; --accent: #1c3d5c; --rule: #ccc9be; }}
body {{ font-family: Georgia, serif; background: var(--paper); color: var(--ink); }}
/* Masthead — matches digest pages for visual consistency */
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
/* Content container */
.container {{ max-width: 600px; margin: 52px auto 80px; padding: 0 20px; }}
h2 {{ font-family: sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); border-bottom: 1px solid var(--rule); padding-bottom: 8px; margin-bottom: 20px; }}
/* Issue list — one item per weekly digest, newest first */
ul {{ list-style: none; }}
li {{ border-bottom: 1px solid var(--rule); }}
li a {{ display: block; padding: 14px 0; font-size: 16px; color: var(--accent); text-decoration: none; }}
li a:hover {{ color: var(--ink); }}
/* Footer */
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
    f.write(index_html)                                   # write the updated archive page
print(f"Saved archive index: {index_path}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\nFiles ready to commit to africa-macrotrends-monitor repo:")
print(f"  {prod_filename}              ← this week's digest")
print(f"  index.html                   ← updated archive listing")
print(f"  africa-digest-{date_slug}.csv  ← full data export")
