"""Normal (weekly) collection entry point.

Scrapes the dashboard as it currently stands - no historical date changing. Observations are saved
under today's run date (snapshot_date); the date the dashboard itself displays is stored separately
as dashboard_date. All logic lives in nbr_engine.py.

    python scrape_nbr_current.py --page cards
    python scrape_nbr_current.py --all-pages
"""
import sys

from src.scrapers.nbr_engine import run_cli

if __name__ == "__main__":
    sys.exit(run_cli("current"))
