# Africa Employment & Development Monitor

Automated weekly news digest covering jobs, employment, and development topics across 58 African countries and regional blocs. Published to GitHub Pages every Monday.

**Live site:** https://ivynyayieka.github.io/africa-macrotrends-monitor/

---

## What it does

Each Monday at 06:00 UTC the pipeline runs automatically:

1. Searches Google News RSS for 58 African countries + regional blocs (Africa, Sahel, WAEMU, West African Economic and Monetary Union)
2. For each entity, runs searches across **6 analytical pillars** drawn from the Guiding Questions framework:
   - Jobs & Employment
   - Macroeconomy
   - Digital Economy
   - Governance
   - Agrifood & Climate
   - Workforce & Human Capital
3. Attempts to extract verbatim article text directly from publisher pages
4. Highlights articles mentioning **youth, women, people with disabilities, and refugees**
5. Publishes a production report filtered to Countries of Presence, WAEMU members, and regional blocs
6. Saves a full CSV export of all articles collected

---

## Output files

Each weekly run produces three new files committed to this repo:

| File | Description |
|------|-------------|
| `news-digest-YYYY-MM-DD.html` | Production report — filtered, designed, published to GitHub Pages |
| `africa-digest-YYYY-MM-DD.csv` | Full data export — all 58 entities, all pillars, all articles |
| `index.html` | Archive page — lists all past issues with links (updated each run) |

Files are never overwritten. Each run adds new dated files alongside previous ones, so the full history is preserved in the repo.

---

## Countries covered

### Countries of Presence (featured in production report)
Ethiopia · Ghana · Kenya · Nigeria · Rwanda · Senegal · Uganda

### WAEMU Members (featured in production report)
Benin · Burkina Faso · Côte d'Ivoire · Guinea-Bissau · Mali · Niger · Senegal · Togo

### All 54 African countries + Western Sahara (in full CSV)
Angola, Burundi, Benin, Burkina Faso, Botswana, Central African Republic, Côte d'Ivoire, Cameroon, Congo Kinshasa, Congo Brazzaville, Comoros, Cape Verde, Djibouti, Algeria, Egypt, Eritrea, Ethiopia, Gabon, Ghana, Guinea, Gambia, Guinea-Bissau, Equatorial Guinea, Kenya, Liberia, Libya, Lesotho, Morocco, Madagascar, Mali, Mozambique, Mauritania, Mauritius, Malawi, Namibia, Niger, Nigeria, Rwanda, Sudan, Senegal, Sierra Leone, Somalia, South Sudan, São Tomé and Príncipe, Eswatini, Chad, Togo, Tunisia, Tanzania, Uganda, South Africa, Zambia, Zimbabwe, Western Sahara

### Regional blocs
Africa · Sahel · WAEMU · West African Economic and Monetary Union

---

## Repository structure

```
africa-monitor/
├── sophisticated_search.py      Main search script — fetches RSS, extracts text, saves results.pkl
├── production_export.py         Export script — reads results.pkl, writes HTML and CSV outputs
├── .github/
│   └── workflows/
│       └── weekly-digest.yml    GitHub Actions workflow — runs the pipeline every Monday
├── index.html                   Archive page (auto-generated, updated each run)
├── news-digest-YYYY-MM-DD.html  Weekly production reports (one per run, never overwritten)
└── africa-digest-YYYY-MM-DD.csv Full data exports (one per run, never overwritten)
```

---

## How the search works

### Google News RSS
The pipeline queries Google News RSS with the format:
```
"Country Name" (keyword1 OR keyword2) after:YYYY-MM-DD
```
RSS is fetched directly — no API key, no cost, no third-party dependency.

### URL resolution (three methods in sequence)
Because Google News links are redirects that hit a consent wall in some regions, the pipeline tries three methods to get the real article URL:

1. **Follow Google redirect** — works for publishers that redirect cleanly without a consent gate
2. **Publisher site search** — searches the publisher's own site using common search endpoint patterns
3. **URL slug construction** — constructs likely article URLs from the title and tests them

If none succeed, the Google News link is kept as a clickable fallback.

### Text extraction
Once a real article URL is found, the page is fetched and parsed. Noise (ads, navbars, footers, paywalls, subscription prompts) is removed. Article body selectors are tried from most specific (`[itemprop='articleBody']`, `article`) to least specific (`main`, `#content`). Text is reproduced verbatim — no summarisation, no paraphrasing.

### Demographic tagging
Articles are tagged automatically if their title contains: `youth`, `women`, `disabilit` (catches disability/disabilities), or `refugee`. Tags are shown as coloured badges in the HTML output and recorded in the CSV.

---

## CSV columns

| Column | Description |
|--------|-------------|
| `entity` | Country or regional bloc name |
| `pillar` | Analytical pillar |
| `title` | Article headline |
| `url` | Direct article URL or Google News link |
| `source` | Publisher name |
| `date` | Publication date |
| `demographics` | Comma-separated demographic labels found in title |
| `text_paragraph_1` | First verbatim paragraph extracted from article |
| `text_paragraph_2` | Second verbatim paragraph |
| `text_paragraph_3` | Third verbatim paragraph |
| `has_text` | `yes` if text was extracted, `no` if only link available |
| `is_google_link` | `yes` if URL is still a Google News redirect |

---

## Running manually

### Trigger via GitHub Actions (no local setup needed)
1. Go to the repo on GitHub
2. Click the **Actions** tab
3. Click **Weekly Africa Digest** in the left sidebar
4. Click **Run workflow** → **Run workflow**
5. The run takes approximately 60 minutes
6. When complete, new files appear in the repo and the site updates automatically

### Run locally
```bash
# Clone the repo
git clone https://github.com/ivynyayieka/africa-monitor.git
cd africa-monitor

# Install dependencies (one time)
pip install requests beautifulsoup4 lxml

# Run the search (takes ~60 minutes for all 58 entities)
python sophisticated_search.py

# Generate HTML and CSV outputs
python production_export.py
```

For a quick test on 3 countries only, open `sophisticated_search.py` and change:
```python
TEST_MODE = False
```
to:
```python
TEST_MODE = True
```
then run. Takes about 5 minutes.

---

## Notes

- Article text is reproduced verbatim from source pages. Where text is not accessible (paywalled or blocked), only the title and link are shown.
- The production report shows a maximum of 2 articles per pillar per country, prioritising articles by estimated popularity (publisher reach, RSS position, and whether text was extracted).
- This digest is produced automatically. It has not been editorially reviewed. Kindly click each article title to read the full piece on the original publisher's site.
- Google News RSS is free and requires no authentication. The pipeline has no paid dependencies.
