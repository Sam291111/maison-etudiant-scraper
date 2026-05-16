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

Serve the dashboard locally:

```bash
python3 listing_store/web_app.py
```

## Combined outputs

The combined store writes to `listing_store/outputs/`:

- `listings.sqlite3`
- `lyon_master_listings.xlsx`
- `active_listings.csv`
- `active_listings.json`
- `latest_pipeline_summary.json`
- `latest_refresh_status.json`

## Render deployment shape

The Render-friendly setup is:

1. A web service using the included `Dockerfile`
2. A persistent disk mounted at `/app/listing_store/outputs`
3. A cron job that sends `POST /admin/refresh` to the web service with `X-Refresh-Token`

The dashboard exposes:

- `/`
  Sortable listing table
- `/api/listings`
  Active merged listings as JSON
- `/api/summary`
  Latest pipeline summary
- `/api/refresh-status`
  Current or latest refresh run status
- `/download/master.xlsx`
  Combined workbook
- `/download/active.csv`
  Combined CSV
- `/download/active.json`
  Combined JSON

Example cron trigger:

```bash
curl -X POST "https://YOUR-RENDER-APP.onrender.com/admin/refresh" \
  -H "X-Refresh-Token: YOUR_REFRESH_TOKEN"
```
