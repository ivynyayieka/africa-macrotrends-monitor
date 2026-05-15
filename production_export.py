# production_export.py
# Reads results.pkl written by sophisticated_search.py.
# Produces three output files:
#   africa-digest-YYYY-MM-DD.csv      full data export of all articles
#   news-digest-YYYY-MM-DD.html       production report (countries of presence + WAEMU + regional)
#   index.html                        archive landing page listing all past issues

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
DEMO_LABELS = {                # maps demographic detection keys to display labels
    "youth":     "youth",
    "women":     "women",
    "disabilit": "disabilities",
    "refugee":   "refugees",
}

PILLAR_ORDER = [               # controls the order pillars appear in the HTML output
    "Jobs & Employment",
    "Macroeconomy",
    "Digital Economy",
    "Governance",
    "Agrifood & Climate",
    "Workforce & Human Capital",
]

PILLAR_ICONS = {               # emoji icon shown next to each pillar label in the HTML
    "Jobs & Employment":         "💼",
    "Macroeconomy":              "📊",
    "Digital Economy":           "🌐",
    "Governance":                "🏛",
    "Agrifood & Climate":        "🌱",
    "Workforce & Human Capital": "🎓",
}

DEMO_COLOURS = {               # CSS background colours for demographic badge tags
    "youth":     "#2563eb",    # blue
    "women":     "#7c3aed",    # purple
    "disabilit": "#059669",    # green
    "refugee":   "#d97706",    # amber
}

# ── Production report configuration ──────────────────────────────────────────
MAX_PER_PILLAR = 2             # maximum articles shown per pillar per country in the production report

PRESENCE = [                   # countries where the organisation has a direct presence
    "Ethiopia", "Ghana", "Kenya", "Nigeria", "Rwanda", "Senegal", "Uganda",
]

WAEMU_MEMBERS = [              # member states of the West African Economic and Monetary Union
    "Benin", "Burkina Faso", "Côte d'Ivoire", "Guinea-Bissau",
    "Mali", "Niger", "Senegal", "Togo",
]

REGIONAL_SHOW = ["WAEMU", "Africa"]   # regional bloc searches to include in the production report


# ── HTML helper functions ─────────────────────────────────────────────────────

def esc(s):
    """Escape special HTML characters to prevent broken markup or XSS."""
    return (
        str(s)
        .replace("&", "&amp;")    # ampersand must be escaped first
        .replace("<", "&lt;")     # less-than sign
        .replace(">", "&gt;")     # greater-than sign
        .replace('"', "&quot;")   # double-quote inside attribute values
    )

def make_anchor(s):
    """Convert a string to a safe HTML id attribute value (letters, digits, underscores only)."""
    return re.sub(r"[^\w]", "_", s)   # replace anything that isn't alphanumeric or underscore


# ── PART 1: CSV EXPORT ────────────────────────────────────────────────────────

def build_csv(results, path):
    """Write all articles from all entities to a CSV file with one row per article."""
    fields = [                         # column names in the CSV header row
        "entity",                      # country or regional bloc name
        "pillar",                      # which of the 6 analytical pillars the article belongs to
        "title",                       # article headline
        "url",                         # direct article URL or Google News link
        "source",                      # publisher name
        "date",                        # publication date
        "demographics",                # comma-separated demographic labels found in the title
        "text_paragraph_1",            # first extracted paragraph (verbatim from article)
        "text_paragraph_2",            # second extracted paragraph
        "text_paragraph_3",            # third extracted paragraph
        "has_text",                    # "yes" if any paragraph text was extracted, "no" otherwise
        "is_google_link",              # "yes" if URL is still a Google News link (not resolved to publisher)
    ]
    rows = []                          # list of dicts, one per article
    for r in results:                  # loop through each entity
        entity = r["entity"]           # country or region name
        for pillar, articles in r["categories"].items():   # loop through each pillar for this entity
            for a in articles:         # loop through each article in this pillar
                paras = a.get("paragraphs", [])            # extracted text paragraphs (may be empty list)
                rows.append({
                    "entity":           entity,
                    "pillar":           pillar,
                    "title":            a["title"],
                    "url":              a["url"],
                    "source":           a.get("source", ""),
                    "date":             a.get("date", ""),
                    "demographics":     ", ".join(          # join all demographic labels with comma
                                            DEMO_LABELS.get(t, t)
                                            for t in a.get("demo_tags", [])
                                        ),
                    "text_paragraph_1": paras[0] if len(paras) > 0 else "",   # first para or blank
                    "text_paragraph_2": paras[1] if len(paras) > 1 else "",   # second para or blank
                    "text_paragraph_3": paras[2] if len(paras) > 2 else "",   # third para or blank
                    "has_text":         "yes" if paras else "no",
                    "is_google_link":   "yes" if "google.com" in a["url"] else "no",
                })
    with open(path, "w", newline="", encoding="utf-8") as f:   # open file for writing, UTF-8 for special characters
        writer = csv.DictWriter(f, fieldnames=fields)           # create a dict-based CSV writer
        writer.writeheader()           # write the column names as the first row
        writer.writerows(rows)         # write all article rows
    print(f"Saved CSV: {path}  ({len(rows)} rows)")

csv_path = os.path.join(os.getcwd(), f"africa-digest-{date_slug}.csv")   # full path for the CSV file
build_csv(results, csv_path)           # run the export


# ── PART 2: PRODUCTION HTML REPORT ───────────────────────────────────────────

entity_map = {r["entity"]: r for r in results}   # dict for quick lookup of entity data by name
prod_date  = TODAY.strftime("%A %-d %B %Y")       # e.g. "Monday 14 May 2026" for the masthead


def render_entity(entity_data, max_per_pillar=MAX_PER_PILLAR):
    """
    Render all pillars for one entity as HTML cards.
    Prioritises articles with extracted text over google-link-only articles.
    Shows up to max_per_pillar articles per pillar.
    """
    html = ""
    for pillar in PILLAR_ORDER:                    # iterate pillars in defined display order
        articles = entity_data["categories"].get(pillar, [])   # get articles for this pillar
        if not articles:                           # no articles found for this pillar — skip
            continue
        with_text    = [a for a in articles if a.get("paragraphs")]      # articles where text was extracted
        without_text = [a for a in articles if not a.get("paragraphs")]  # articles with only a link
        top = (with_text + without_text)[:max_per_pillar]   # prefer text articles, fill up to limit
        if not top:
            continue
        icon = PILLAR_ICONS.get(pillar, "")        # emoji icon for this pillar
        html += f'<div class="pillar-block"><div class="pillar-label">{icon} {esc(pillar)}</div>\n'
        for a in top:                              # render each selected article as a card
            is_google = "google.com" in a["url"]  # True if URL is still a Google News redirect
            demo_html = ""
            if a.get("demo_tags"):                 # if demographic keywords were found in the title
                demo_html = '<div class="demo-row">' + "".join(
                    f'<span class="dtag" style="background:{DEMO_COLOURS.get(t, "#888")}">'
                    f'{DEMO_LABELS.get(t, t)}</span>'
                    for t in a["demo_tags"]        # one coloured badge per demographic tag
                ) + "</div>"
            meta = " · ".join(                     # source name and date joined by a middle dot
                p for p in [a.get("source", ""), a.get("date", "")] if p
            )
            paras = a.get("paragraphs", [])
            if paras:                              # text was extracted — show it as an excerpt
                ex_html = (
                    '<div class="excerpt">'
                    + "".join(f"<p>{esc(p)}</p>" for p in paras)
                    + "</div>"
                )
            else:                                  # no text — show a short note instead
                note = "Click to read →" if is_google else "Text not accessible"
                ex_html = f'<p class="no-text">{note}</p>'
            html += (                              # assemble the full card HTML
                f'<div class="card">\n'
                f'{demo_html}'                     # demographic badges (may be empty string)
                f'<a class="card-title" href="{esc(a["url"])}" target="_blank" rel="noopener">'
                f'{esc(a["title"])}</a>\n'          # clickable article title
                + (f'<div class="card-meta">{esc(meta)}</div>\n' if meta else "")  # source · date line
                + ex_html                          # excerpt or "click to read" note
                + "\n</div>\n"
            )
        html += "</div>\n"                         # close pillar-block div
    return html


def build_section(section_title, section_id, entities):
    """
    Build one <section> block containing all entities in the given list.
    Skips entities with no articles to show.
    """
    html = f'<section id="{section_id}"><h2 class="section-title">{esc(section_title)}</h2>\n'
    found = False                                  # track whether any entity had articles
    for entity in entities:                        # loop through countries/regions in this section
        data = entity_map.get(entity)              # look up this entity's results
        if not data:                               # entity was not searched (e.g. not in results.pkl)
            continue
        body = render_entity(data)                 # render all pillars for this entity
        if not body:                               # entity had no articles in any pillar
            continue
        found = True
        html += (
            f'<div class="entity-block">'
            f'<h3 class="entity-name" id="{make_anchor(entity)}">{esc(entity)}</h3>\n'
            f'{body}</div>\n'
        )
    if not found:                                  # none of the entities in this section had results
        html += '<p class="empty">No results available for this section this week.</p>\n'
    return html + "</section>\n"                   # close the section


# Build the three sections of the production report
presence_html = build_section("Countries of Presence", "presence", PRESENCE)
waemu_html    = build_section("WAEMU Countries",        "waemu",    WAEMU_MEMBERS)
regional_html = build_section("Regional",               "regional", REGIONAL_SHOW)

# Build the demographic legend bar shown at the top of the report
demo_legend = "".join(
    f'<span class="dtag" style="background:{DEMO_COLOURS[k]}">{DEMO_LABELS[k]}</span>'
    for k in ["youth", "women", "disabilit", "refugee"]   # one badge per tracked demographic
)

# ── Assemble full production HTML ─────────────────────────────────────────────
prod_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Africa Employment &amp; Development Monitor — {prod_date}</title>
<style>
/* Reset: remove default browser margin/padding and use border-box sizing */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
/* CSS custom properties (variables) for consistent colours and fonts */
:root {{
  --ink:    #0f0f0f;   /* near-black for body text */
  --ink-2:  #3a3a3a;   /* slightly lighter for excerpts */
  --ink-3:  #777;      /* grey for metadata and secondary text */
  --paper:  #f8f6f1;   /* warm off-white page background */
  --card:   #ffffff;   /* pure white card backgrounds */
  --rule:   #e2ddd4;   /* warm grey for borders and dividers */
  --accent: #1a3a5c;   /* dark navy for masthead, country headings, links */
  --gold:   #b8832a;   /* warm gold for section labels and decorative accents */
  --serif:  Georgia, "Times New Roman", serif;    /* serif font for body text */
  --sans:   system-ui, -apple-system, "Segoe UI", sans-serif;   /* sans-serif for labels */
}}
html {{ scroll-behavior: smooth; }}   /* smooth scrolling when nav links are clicked */
body {{ font-family: var(--serif); background: var(--paper); color: var(--ink); font-size: 16px; line-height: 1.75; }}

/* Masthead: full-width dark banner at the top */
.masthead {{ background: var(--accent); color: #fff; padding: 52px 24px 40px; text-align: center; }}
.kicker {{ font-family: var(--sans); font-size: 10px; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase; opacity: 0.6; margin-bottom: 14px; }}
.masthead h1 {{ font-size: clamp(24px, 5vw, 42px); font-weight: 700; line-height: 1.15; letter-spacing: -0.02em; margin-bottom: 12px; }}
.masthead-date {{ font-family: var(--sans); font-size: 13px; opacity: 0.55; margin-bottom: 24px; }}
.masthead-note {{ font-family: var(--sans); font-size: 12px; opacity: 0.5; max-width: 520px; margin: 0 auto; line-height: 1.55; border-top: 1px solid rgba(255,255,255,0.15); padding-top: 18px; }}

/* Sticky navigation bar: stays at top when scrolling */
.nav {{ background: var(--accent); border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: center; position: sticky; top: 0; z-index: 50; }}
.nav a {{ font-family: var(--sans); font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.65); text-decoration: none; padding: 13px 22px; border-bottom: 2px solid transparent; transition: color .15s, border-color .15s; }}
.nav a:hover {{ color: #fff; border-bottom-color: var(--gold); }}

/* Thin legend bar below nav showing demographics and pillar icons */
.legend-bar {{ background: var(--card); border-bottom: 1px solid var(--rule); padding: 10px 24px; text-align: center; font-family: var(--sans); font-size: 11px; color: var(--ink-3); line-height: 2; }}
.legend-bar strong {{ color: var(--ink-2); }}

/* Main content area: centred, max 880px wide */
.container {{ max-width: 880px; margin: 0 auto; padding: 0 20px 80px; }}

/* Section: one per geographic grouping (Countries of Presence, WAEMU, Regional) */
section {{ margin-top: 60px; }}
.section-title {{ font-family: var(--sans); font-size: 10px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: var(--gold); border-bottom: 2px solid var(--accent); padding-bottom: 10px; margin-bottom: 36px; }}

/* Entity block: one per country or region within a section */
.entity-block {{ margin-bottom: 52px; }}
.entity-name {{ font-size: 24px; font-weight: 700; color: var(--accent); margin-bottom: 24px; padding-left: 14px; border-left: 4px solid var(--gold); }}

/* Pillar block: groups of cards within one entity, one per analytical pillar */
.pillar-block {{ margin-bottom: 24px; }}
.pillar-label {{ font-family: var(--sans); font-size: 10px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-3); padding: 5px 0; border-bottom: 1px solid var(--rule); margin-bottom: 12px; }}

/* Card: one article */
.card {{ background: var(--card); border: 1px solid var(--rule); border-left: 3px solid var(--gold); border-radius: 0 6px 6px 0; padding: 15px 18px; margin-bottom: 12px; }}
.card-title {{ font-family: var(--serif); font-size: 15px; font-weight: 700; color: var(--ink); text-decoration: none; display: block; margin-bottom: 4px; line-height: 1.4; }}
.card-title:hover {{ color: var(--accent); text-decoration: underline; }}
.card-meta {{ font-family: var(--sans); font-size: 11px; color: var(--ink-3); margin-bottom: 10px; }}
.excerpt {{ font-size: 14px; line-height: 1.75; color: var(--ink-2); margin-top: 8px; }}
.excerpt p {{ margin-bottom: 8px; }}
.excerpt p:last-child {{ margin: 0; }}
.no-text {{ font-family: var(--sans); font-size: 12px; color: var(--ink-3); font-style: italic; margin-top: 6px; }}

/* Demographic badge tags */
.demo-row {{ margin-bottom: 7px; }}
.dtag {{ display: inline-block; font-family: var(--sans); font-size: 9px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #fff; padding: 2px 8px; border-radius: 20px; margin-right: 4px; }}

/* Footer */
.footer {{ margin-top: 80px; padding: 36px 20px; border-top: 1px solid var(--rule); text-align: center; font-family: var(--sans); font-size: 12px; color: var(--ink-3); line-height: 1.8; }}
.footer strong {{ color: var(--ink-2); }}
.empty {{ font-family: var(--sans); font-size: 13px; color: var(--ink-3); font-style: italic; margin: 20px 0; }}
</style>
</head>
<body>

<!-- Masthead banner with title, date, and automated disclaimer -->
<div class="masthead">
  <div class="kicker">Weekly Intelligence Briefing</div>
  <h1>Africa Employment &amp;<br>Development Monitor</h1>
  <div class="masthead-date">{prod_date}</div>
  <div class="masthead-note">
    This roundup is produced automatically through a news scraper. Articles are sourced
    from Google News RSS across six analytical pillars. Kindly click each article title
    to read the full piece on the original publisher's site.
  </div>
</div>

<!-- Sticky navigation links to each section -->
<nav class="nav">
  <a href="#presence">Countries of Presence</a>
  <a href="#waemu">WAEMU</a>
  <a href="#regional">Regional</a>
</nav>

<!-- Thin bar showing demographic badges and pillar icons -->
<div class="legend-bar">
  <strong>Demographics:</strong> &nbsp;{demo_legend}&nbsp;&nbsp;|&nbsp;&nbsp;
  <strong>Pillars:</strong> 💼 Jobs &amp; Employment &nbsp;·&nbsp;
  📊 Macroeconomy &nbsp;·&nbsp; 🌐 Digital Economy &nbsp;·&nbsp;
  🏛 Governance &nbsp;·&nbsp; 🌱 Agrifood &amp; Climate &nbsp;·&nbsp;
  🎓 Workforce &amp; Human Capital
</div>

<!-- Main content: three geographic sections -->
<div class="container">
{presence_html}
{waemu_html}
{regional_html}
</div>

<!-- Footer with generation metadata and repeat of demographic legend -->
<div class="footer">
  <strong>Africa Employment &amp; Development Monitor</strong><br>
  Generated automatically · {generated}<br>
  Source: Google News RSS · Up to {MAX_PER_PILLAR} articles per pillar per country<br>
  Excerpts reproduced verbatim from source pages. Click any title to read in full.<br><br>
  {demo_legend} — demographic tags appear where mentioned in article titles
</div>

</body>
</html>"""

# ── Save the production report with a date-stamped filename ──────────────────
prod_filename = f"news-digest-{date_slug}.html"                   # e.g. news-digest-2026-05-14.html
prod_path     = os.path.join(os.getcwd(), prod_filename)          # full path in current directory
with open(prod_path, "w", encoding="utf-8") as f:
    f.write(prod_html)
print(f"Saved production report: {prod_path}")


# ── Update the archive index.html ─────────────────────────────────────────────
# index.html lists all past digest issues as a simple linked list.
# Each run adds the new issue to the top. Existing links are preserved.

index_path = os.path.join(os.getcwd(), "index.html")   # path to the archive page

archive_entries = []                         # will hold (filename, display_date) tuples
if os.path.exists(index_path):              # if an index already exists, extract its links
    with open(index_path, "r", encoding="utf-8") as f:
        existing = f.read()
    for m in re.finditer(                   # find all existing digest links in the current index
        r'href="(news-digest-[\d-]+\.html)"[^>]*>([^<]+)<', existing
    ):
        entry = (m.group(1), m.group(2))    # (filename, label) e.g. ("news-digest-2026-05-07.html", "Monday 7 May 2026")
        if entry not in archive_entries:
            archive_entries.append(entry)

this_entry = (prod_filename, prod_date)     # entry for this week's digest
if this_entry not in archive_entries:       # only add if not already listed (avoids duplicates on re-run)
    archive_entries.insert(0, this_entry)   # insert at top so newest issue appears first

archive_rows = "\n".join(                   # build one <li> per issue
    f'<li><a href="{fn}">{label}</a></li>'
    for fn, label in archive_entries
)

# ── Build the archive index page ──────────────────────────────────────────────
index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Africa Employment &amp; Development Monitor</title>
<style>
/* Reset and base */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{ --accent: #1a3a5c; --gold: #b8832a; --paper: #f8f6f1; --ink: #0f0f0f; --ink-3: #777; --rule: #e2ddd4; }}
body {{ font-family: Georgia, serif; background: var(--paper); color: var(--ink); }}
/* Masthead matches the digest pages for visual consistency */
.masthead {{ background: var(--accent); color: #fff; padding: 60px 24px; text-align: center; }}
.kicker {{ font-family: system-ui, sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase; opacity: 0.6; margin-bottom: 14px; }}
h1 {{ font-size: clamp(24px, 5vw, 40px); font-weight: 700; line-height: 1.2; margin-bottom: 10px; }}
.sub {{ font-family: system-ui, sans-serif; font-size: 13px; opacity: 0.55; }}
/* Centred content container */
.container {{ max-width: 640px; margin: 60px auto; padding: 0 20px 80px; }}
h2 {{ font-family: system-ui, sans-serif; font-size: 11px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--gold); border-bottom: 2px solid var(--accent); padding-bottom: 8px; margin-bottom: 24px; }}
/* Issue list: one item per weekly digest */
ul {{ list-style: none; }}
li {{ border-bottom: 1px solid var(--rule); }}
li a {{ display: block; padding: 14px 0; font-size: 16px; color: var(--accent); text-decoration: none; }}
li a:hover {{ color: var(--gold); }}
.footer {{ margin-top: 60px; text-align: center; font-family: system-ui, sans-serif; font-size: 12px; color: var(--ink-3); }}
</style>
</head>
<body>
<!-- Archive landing page header -->
<div class="masthead">
  <div class="kicker">Weekly Intelligence Briefing</div>
  <h1>Africa Employment &amp;<br>Development Monitor</h1>
  <div class="sub">Automated weekly digest · Google News RSS · Six analytical pillars</div>
</div>
<!-- List of all past issues, newest first -->
<div class="container">
  <h2>All Issues</h2>
  <ul>
{archive_rows}
  </ul>
</div>
<div class="footer">
  Generated automatically each Monday.<br>
  Articles sourced from Google News RSS. No editorial curation.
</div>
</body>
</html>"""

with open(index_path, "w", encoding="utf-8") as f:
    f.write(index_html)
print(f"Saved archive index: {index_path}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\nFiles ready to commit to africa-monitor repo:")
print(f"  {prod_filename}              ← this week's digest")
print(f"  index.html                   ← archive listing all issues")
print(f"  africa-digest-{date_slug}.csv  ← full data export")
