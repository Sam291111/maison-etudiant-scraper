ENTIRELY AI GENERATED - CODE MAY NOT WORK IN (NEAR)FUTURE 


# Accommodation Scrapers

This project now has four source scrapers plus a combined listing store and a small web dashboard layer.

## Current layout

- `scrapers/immojeune/`
  ImmoJeune scraper, recon, and outputs.
- `scrapers/la_carte_des_colocs/`
  La Carte des Colocs scraper, recon, and outputs.
- `scrapers/location_etudiant/`
  Location Étudiant scraper, recon, and outputs.
- `scrapers/studapart/`
  Studapart scraper, recon, and outputs.
- `shared/`
  Small shared helpers and the common normalized listing shape.
- `listing_store/`
  Cross-source SQLite store, pipeline runner, exports, and web dashboard.
- `data_store/`
  Tracked persistent store for GitHub Actions runs.
- `docs/`
  Static GitHub Pages dashboard and published data/downloads.

## Useful commands

Run one scraper:

```bash
python3 scrapers/immojeune/scraper.py --max-pages 6
python3 scrapers/la_carte_des_colocs/scraper.py
python3 scrapers/location_etudiant/scraper.py
python3 scrapers/studapart/scraper.py
```

Refresh the combined store from existing scraper outputs:

```bash
python3 listing_store/update_store.py
```

Run the full pipeline end to end:

```bash
python3 listing_store/run_pipeline.py
```

Publish the static Pages assets locally from tracked data:

```bash
python3 listing_store/publish_pages.py --input-dir data_store --output-dir docs
```

Serve the dashboard locally:

```bash
python3 listing_store/web_app.py
```

## Combined outputs

Local ad-hoc runs write to `listing_store/outputs/`:

- `listings.sqlite3`
- `lyon_master_listings.xlsx`
- `active_listings.csv`
- `active_listings.json`
- `latest_pipeline_summary.json`
- `latest_refresh_status.json`

GitHub Actions refresh runs write the tracked store to `data_store/`:

- `listings.sqlite3`
- `lyon_master_listings.xlsx`
- `active_listings.csv`
- `active_listings.json`
- `latest_pipeline_summary.json`

## Recommended Free Deployment

The preferred free setup is:

1. `Refresh Listing Data` GitHub Actions workflow
2. `Deploy Pages` GitHub Actions workflow
3. GitHub Pages serving the `docs/` folder output

The refresh workflow:

- runs all four scrapers on a daily schedule
- runs ImmoJeune without a fixed page cap, so it keeps going until the site stops returning result cards
- updates the tracked SQLite store in `data_store/`
- republishes `docs/data/` and `docs/downloads/`
- commits refreshed data back to `main`
- opens GitHub issue alerts when new listings appear, listings disappear, or the refresh workflow fails

The Pages deploy workflow:

- deploys the static `docs/` folder to GitHub Pages whenever it changes

### One-time GitHub setup

1. In repo `Settings` -> `Actions` -> `General`, allow workflows to have read and write permissions.
2. In repo `Settings` -> `Pages`, set the source to `GitHub Actions`.
3. Optionally run `Refresh Listing Data` manually once to seed the first full snapshot.

### Static dashboard URLs

Once Pages is live, the dashboard exposes:

- `/`
  Sortable listing table plus latest new/removed panels and a map view for listings with coordinates
- `/data/active_listings.json`
  Active merged listings as JSON
- `/data/latest_pipeline_summary.json`
  Latest pipeline summary
- `/data/new_in_run.json`
  Listings first seen in the latest run
- `/data/removed_in_run.json`
  Listings missing in the latest run
- `/downloads/lyon_master_listings.xlsx`
  Combined workbook
- `/downloads/active_listings.csv`
  Combined CSV
