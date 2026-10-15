# Business & Management Job Market — live dashboard

A faculty-jobs dashboard that refreshes itself nightly via GitHub Actions and
publishes to GitHub Pages. Seeded with 49 real listings compiled by hand; from
then on it updates on its own.

## What's here

- `index.html` — the dashboard. Fetches `data/jobs.json` on load; no backend needed.
- `data/jobs.json` — the data, seeded with the current snapshot.
- `scraper.py` — pulls fresh listings and rewrites `data/jobs.json`.
- `.github/workflows/update-jobs.yml` — runs the scraper nightly (03:00 UTC)
  and deploys the result to GitHub Pages.

## Setup (10 minutes, one time)

1. **Create a repo** on GitHub (public or private — Pages works with either
   on a paid plan; public repos get Pages free).
2. **Push these files** to it:
   ```
   git init
   git add .
   git commit -m "Initial dashboard"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
3. **Enable Pages**: repo → Settings → Pages → Build and deployment → Source:
   "GitHub Actions" (not "Deploy from a branch" — the workflow handles that).
4. **Enable Actions write access**: repo → Settings → Actions → General →
   Workflow permissions → "Read and write permissions". This lets the nightly
   job commit the refreshed `data/jobs.json` back to the repo.
5. **Run it once manually** to confirm it works: Actions tab → "Refresh
   business & management jobs" → Run workflow. Check the run log for the
   per-source status line (which sources returned results, which failed).
6. Your live URL will be `https://<you>.github.io/<repo>/`.

After that, it runs nightly on its own — no further action needed.

## Important limitations, honestly

- **Not every job board can be scraped.** HigherEdJobs and the Chronicle of
  Higher Education sit behind bot-protection (Incapsula/Cloudflare) that
  blocks simple scripted requests — I tested this directly and confirmed it.
  Scraping those reliably would need real browser automation (Playwright
  with stealth plugins) and sails closer to violating their Terms of
  Service, so `scraper.py` deliberately skips them. The sources it does use
  (EconJobMarket, THEunijobs, AcademicKeys) are chosen because they're
  either RSS or plain server-rendered HTML.
- **Source selectors can break.** `theunijobs` and `academickeys` scrape
  HTML structure (CSS classes), which sites change without notice. If a
  source starts returning 0 matches in the workflow log, its selectors
  likely need updating in `scraper.py` — that's expected maintenance for
  any scraper, not a one-time build.
- **Coverage will likely narrow** from the original 49 hand-picked listings
  (which included Chronicle/HigherEdJobs items) down to whatever the
  scrapable sources carry. Expect the feed to lean more European/Asian over
  time, since THEunijobs and EconJobMarket skew that way, and US-specific
  academic boards are the hardest to scrape.
- **Stale listings expire.** Anything not re-confirmed by a source within
  120 days drops out automatically (edit `STALE_DAYS` in `scraper.py` to
  change this).

## Extending it

To add a source: write a `source_<name>()` function in `scraper.py` that
returns a list of dicts with `employer`, `position`, `sub`, `location`,
`type`, `posted`, `url`, then add it to the `SOURCES` dict. Wrap it in
exactly the try/except pattern the others use — one broken source should
never take down the rest of the pipeline.

## Running locally

```
pip install beautifulsoup4 lxml
python3 scraper.py          # refreshes data/jobs.json
python3 -m http.server       # then open http://localhost:8000
```

(Opening `index.html` directly via `file://` won't work — browsers block
`fetch()` on local files. Use the http server above, or GitHub Pages once
deployed.)
