"""
production_export.py
Reads results.pkl produced by sophisticated_search.py.
Outputs:
  - africa-digest-YYYY-MM-DD.csv        (full results, all entities)
  - news-digest-YYYY-MM-DD.html         (production report for GitHub Pages)
"""

import pickle
import csv
import os
import re
from datetime import datetime

# ── Load results ──────────────────────────────────────────────────────────────

with open("results.pkl", "rb") as f:
    data = pickle.load(f)

results   = data["results"]
generated = data["generated"]
TODAY     = data["today"]
date_slug = data["date_slug"]
total_a   = data["total_a"]
total_t   = data["total_t"]

print(f"Loaded {len(results)} entities | {total_a} articles | {total_t} with text")

# ── Shared constants ──────────────────────────────────────────────────────────

DEMO_LABELS = {
    "youth":     "youth",
    "women":     "women",
    "disabilit": "disabilities",
    "refugee":   "refugees",
}

PILLAR_ORDER = [
    "Jobs & Employment",
    "Macroeconomy",
    "Digital Economy",
    "Governance",
    "Agrifood & Climate",
    "Workforce & Human Capital",
]

PILLAR_ICONS = {
    "Jobs & Employment":         "💼",
    "Macroeconomy":              "📊",
    "Digital Economy":           "🌐",
    "Governance":                "🏛",
    "Agrifood & Climate":        "🌱",
    "Workforce & Human Capital": "🎓",
}

DEMO_COLOURS = {
    "youth":     "#2563eb",
    "women":     "#7c3aed",
    "disabilit": "#059669",
    "refugee":   "#d97706",
}

# ── Production config ─────────────────────────────────────────────────────────

MAX_PER_PILLAR = 2

PRESENCE = [
    "Ethiopia", "Ghana", "Kenya", "Nigeria", "Rwanda", "Senegal", "Uganda",
]

WAEMU_MEMBERS = [
    "Benin", "Burkina Faso", "Côte d'Ivoire", "Guinea-Bissau",
    "Mali", "Niger", "Senegal", "Togo",
]

REGIONAL_SHOW = ["WAEMU", "Africa"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

def make_anchor(s):
    return re.sub(r"[^\w]", "_", s)


# ── PART 1: CSV ───────────────────────────────────────────────────────────────

def build_csv(results, path):
    fields = [
        "entity", "pillar", "title", "url", "source", "date",
        "demographics",
        "text_paragraph_1", "text_paragraph_2", "text_paragraph_3",
        "has_text", "is_google_link",
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
                    "text_paragraph_1": paras[0] if len(paras) > 0 else "",
                    "text_paragraph_2": paras[1] if len(paras) > 1 else "",
                    "text_paragraph_3": paras[2] if len(paras) > 2 else "",
                    "has_text":         "yes" if paras else "no",
                    "is_google_link":   "yes" if "google.com" in a["url"] else "no",
                })
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved CSV: {path}  ({len(rows)} rows)")

csv_path = os.path.join(os.getcwd(), f"africa-digest-{date_slug}.csv")
build_csv(results, csv_path)


# ── PART 2: Production HTML ───────────────────────────────────────────────────

entity_map = {r["entity"]: r for r in results}
prod_date  = TODAY.strftime("%A %-d %B %Y")


def render_entity(entity_data, max_per_pillar=MAX_PER_PILLAR):
    html = ""
    for pillar in PILLAR_ORDER:
        articles = entity_data["categories"].get(pillar, [])
        if not articles:
            continue
        with_text    = [a for a in articles if a.get("paragraphs")]
        without_text = [a for a in articles if not a.get("paragraphs")]
        top = (with_text + without_text)[:max_per_pillar]
        if not top:
            continue
        icon = PILLAR_ICONS.get(pillar, "")
        html += f'<div class="pillar-block"><div class="pillar-label">{icon} {esc(pillar)}</div>\n'
        for a in top:
            is_google = "google.com" in a["url"]
            demo_html = ""
            if a.get("demo_tags"):
                demo_html = '<div class="demo-row">' + "".join(
                    f'<span class="dtag" style="background:{DEMO_COLOURS.get(t, "#888")}">'
                    f'{DEMO_LABELS.get(t, t)}</span>'
                    for t in a["demo_tags"]
                ) + "</div>"
            meta = " · ".join(p for p in [a.get("source", ""), a.get("date", "")] if p)
            paras = a.get("paragraphs", [])
            if paras:
                ex_html = (
                    '<div class="excerpt">'
                    + "".join(f"<p>{esc(p)}</p>" for p in paras)
                    + "</div>"
                )
            else:
                note = "Click to read →" if is_google else "Text not accessible"
                ex_html = f'<p class="no-text">{note}</p>'
            html += (
                f'<div class="card">\n'
                f'{demo_html}'
                f'<a class="card-title" href="{esc(a["url"])}" target="_blank" rel="noopener">'
                f'{esc(a["title"])}</a>\n'
                + (f'<div class="card-meta">{esc(meta)}</div>\n' if meta else "")
                + ex_html
                + "\n</div>\n"
            )
        html += "</div>\n"
    return html


def build_section(section_title, section_id, entities):
    html = f'<section id="{section_id}"><h2 class="section-title">{esc(section_title)}</h2>\n'
    found = False
    for entity in entities:
        data = entity_map.get(entity)
        if not data:
            continue
        body = render_entity(data)
        if not body:
            continue
        found = True
        html += (
            f'<div class="entity-block">'
            f'<h3 class="entity-name" id="{make_anchor(entity)}">{esc(entity)}</h3>\n'
            f'{body}</div>\n'
        )
    if not found:
        html += '<p class="empty">No results available for this section this week.</p>\n'
    return html + "</section>\n"


presence_html = build_section("Countries of Presence", "presence", PRESENCE)
waemu_html    = build_section("WAEMU Countries",        "waemu",    WAEMU_MEMBERS)
regional_html = build_section("Regional",               "regional", REGIONAL_SHOW)

demo_legend = "".join(
    f'<span class="dtag" style="background:{DEMO_COLOURS[k]}">{DEMO_LABELS[k]}</span>'
    for k in ["youth", "women", "disabilit", "refugee"]
)

prod_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Africa Employment &amp; Development Monitor — {prod_date}</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --ink:    #0f0f0f;
  --ink-2:  #3a3a3a;
  --ink-3:  #777;
  --paper:  #f8f6f1;
  --card:   #ffffff;
  --rule:   #e2ddd4;
  --accent: #1a3a5c;
  --gold:   #b8832a;
  --serif:  Georgia, "Times New Roman", serif;
  --sans:   system-ui, -apple-system, "Segoe UI", sans-serif;
}}
html {{ scroll-behavior: smooth; }}
body {{ font-family: var(--serif); background: var(--paper); color: var(--ink); font-size: 16px; line-height: 1.75; }}

.masthead {{ background: var(--accent); color: #fff; padding: 52px 24px 40px; text-align: center; }}
.kicker {{ font-family: var(--sans); font-size: 10px; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase; opacity: 0.6; margin-bottom: 14px; }}
.masthead h1 {{ font-size: clamp(24px, 5vw, 42px); font-weight: 700; line-height: 1.15; letter-spacing: -0.02em; margin-bottom: 12px; }}
.masthead-date {{ font-family: var(--sans); font-size: 13px; opacity: 0.55; margin-bottom: 24px; }}
.masthead-note {{ font-family: var(--sans); font-size: 12px; opacity: 0.5; max-width: 520px; margin: 0 auto; line-height: 1.55; border-top: 1px solid rgba(255,255,255,0.15); padding-top: 18px; }}

.nav {{ background: var(--accent); border-top: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: center; position: sticky; top: 0; z-index: 50; }}
.nav a {{ font-family: var(--sans); font-size: 11px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: rgba(255,255,255,0.65); text-decoration: none; padding: 13px 22px; border-bottom: 2px solid transparent; transition: color .15s, border-color .15s; }}
.nav a:hover {{ color: #fff; border-bottom-color: var(--gold); }}

.legend-bar {{ background: var(--card); border-bottom: 1px solid var(--rule); padding: 10px 24px; text-align: center; font-family: var(--sans); font-size: 11px; color: var(--ink-3); line-height: 2; }}
.legend-bar strong {{ color: var(--ink-2); }}

.container {{ max-width: 880px; margin: 0 auto; padding: 0 20px 80px; }}

section {{ margin-top: 60px; }}
.section-title {{ font-family: var(--sans); font-size: 10px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: var(--gold); border-bottom: 2px solid var(--accent); padding-bottom: 10px; margin-bottom: 36px; }}

.entity-block {{ margin-bottom: 52px; }}
.entity-name {{ font-size: 24px; font-weight: 700; color: var(--accent); margin-bottom: 24px; padding-left: 14px; border-left: 4px solid var(--gold); }}

.pillar-block {{ margin-bottom: 24px; }}
.pillar-label {{ font-family: var(--sans); font-size: 10px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-3); padding: 5px 0; border-bottom: 1px solid var(--rule); margin-bottom: 12px; }}

.card {{ background: var(--card); border: 1px solid var(--rule); border-left: 3px solid var(--gold); border-radius: 0 6px 6px 0; padding: 15px 18px; margin-bottom: 12px; }}
.card-title {{ font-family: var(--serif); font-size: 15px; font-weight: 700; color: var(--ink); text-decoration: none; display: block; margin-bottom: 4px; line-height: 1.4; }}
.card-title:hover {{ color: var(--accent); text-decoration: underline; }}
.card-meta {{ font-family: var(--sans); font-size: 11px; color: var(--ink-3); margin-bottom: 10px; }}
.excerpt {{ font-size: 14px; line-height: 1.75; color: var(--ink-2); margin-top: 8px; }}
.excerpt p {{ margin-bottom: 8px; }}
.excerpt p:last-child {{ margin: 0; }}
.no-text {{ font-family: var(--sans); font-size: 12px; color: var(--ink-3); font-style: italic; margin-top: 6px; }}

.demo-row {{ margin-bottom: 7px; }}
.dtag {{ display: inline-block; font-family: var(--sans); font-size: 9px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #fff; padding: 2px 8px; border-radius: 20px; margin-right: 4px; }}

.footer {{ margin-top: 80px; padding: 36px 20px; border-top: 1px solid var(--rule); text-align: center; font-family: var(--sans); font-size: 12px; color: var(--ink-3); line-height: 1.8; }}
.footer strong {{ color: var(--ink-2); }}
.empty {{ font-family: var(--sans); font-size: 13px; color: var(--ink-3); font-style: italic; margin: 20px 0; }}
</style>
</head>
<body>

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

<nav class="nav">
  <a href="#presence">Countries of Presence</a>
  <a href="#waemu">WAEMU</a>
  <a href="#regional">Regional</a>
</nav>

<div class="legend-bar">
  <strong>Demographics:</strong> &nbsp;{demo_legend}&nbsp;&nbsp;|&nbsp;&nbsp;
  <strong>Pillars:</strong> 💼 Jobs &amp; Employment &nbsp;·&nbsp;
  📊 Macroeconomy &nbsp;·&nbsp; 🌐 Digital Economy &nbsp;·&nbsp;
  🏛 Governance &nbsp;·&nbsp; 🌱 Agrifood &amp; Climate &nbsp;·&nbsp;
  🎓 Workforce &amp; Human Capital
</div>

<div class="container">
{presence_html}
{waemu_html}
{regional_html}
</div>

<div class="footer">
  <strong>Africa Employment &amp; Development Monitor</strong><br>
  Generated automatically · {generated}<br>
  Source: Google News RSS · Up to {MAX_PER_PILLAR} articles per pillar per country<br>
  Excerpts reproduced verbatim from source pages. Click any title to read in full.<br><br>
  {demo_legend} — demographic tags appear where mentioned in article titles
</div>

</body>
</html>"""

# File named by date for GitHub Pages archive
prod_filename = f"news-digest-{date_slug}.html"
prod_path     = os.path.join(os.getcwd(), prod_filename)
with open(prod_path, "w", encoding="utf-8") as f:
    f.write(prod_html)
print(f"Saved production report: {prod_path}")

# Also write/update an index.html that lists all digests published
# This lets ivynyayieka.github.io/index.html act as an archive page
index_path = os.path.join(os.getcwd(), "index.html")

# Read existing archive entries if index exists
archive_entries = []
if os.path.exists(index_path):
    with open(index_path, "r", encoding="utf-8") as f:
        existing = f.read()
    # Extract existing digest links
    for m in re.finditer(r'href="(news-digest-[\d-]+\.html)"[^>]*>([^<]+)<', existing):
        entry = (m.group(1), m.group(2))
        if entry not in archive_entries:
            archive_entries.append(entry)

# Add this week if not already there
this_entry = (prod_filename, prod_date)
if this_entry not in archive_entries:
    archive_entries.insert(0, this_entry)

archive_rows = "\n".join(
    f'<li><a href="{fn}">{label}</a></li>'
    for fn, label in archive_entries
)

index_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Africa Employment &amp; Development Monitor</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{ --accent: #1a3a5c; --gold: #b8832a; --paper: #f8f6f1; --ink: #0f0f0f; --ink-3: #777; --rule: #e2ddd4; }}
body {{ font-family: Georgia, serif; background: var(--paper); color: var(--ink); }}
.masthead {{ background: var(--accent); color: #fff; padding: 60px 24px; text-align: center; }}
.kicker {{ font-family: system-ui, sans-serif; font-size: 10px; font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase; opacity: 0.6; margin-bottom: 14px; }}
h1 {{ font-size: clamp(24px, 5vw, 40px); font-weight: 700; line-height: 1.2; margin-bottom: 10px; }}
.sub {{ font-family: system-ui, sans-serif; font-size: 13px; opacity: 0.55; }}
.container {{ max-width: 640px; margin: 60px auto; padding: 0 20px 80px; }}
h2 {{ font-family: system-ui, sans-serif; font-size: 11px; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: var(--gold); border-bottom: 2px solid var(--accent); padding-bottom: 8px; margin-bottom: 24px; }}
ul {{ list-style: none; }}
li {{ border-bottom: 1px solid var(--rule); }}
li a {{ display: block; padding: 14px 0; font-size: 16px; color: var(--accent); text-decoration: none; }}
li a:hover {{ color: var(--gold); }}
.footer {{ margin-top: 60px; text-align: center; font-family: system-ui, sans-serif; font-size: 12px; color: var(--ink-3); }}
</style>
</head>
<body>
<div class="masthead">
  <div class="kicker">Weekly Intelligence Briefing</div>
  <h1>Africa Employment &amp;<br>Development Monitor</h1>
  <div class="sub">Automated weekly digest · Google News RSS · Six analytical pillars</div>
</div>
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
print(f"\nFiles ready to commit:")
print(f"  {prod_filename}  ← this week's digest")
print(f"  index.html        ← archive listing (links to all issues)")
print(f"  africa-digest-{date_slug}.csv  ← full data export")
