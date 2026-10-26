"""Historical backfill entry point.

Iterates the dates in nbr_backfill_dates.txt (select date -> verify -> scrape) for the chosen
page(s). All scraping, filter, KPI, table and MongoDB logic lives in nbr_engine.py.

    python scrape_nbr_backfill.py --page cards
    python scrape_nbr_backfill.py --page cards --page branches --headed
    python scrape_nbr_backfill.py --all-pages --dates-file nbr_backfill_dates.txt
"""
import sys

from nbr_engine import run_cli

if __name__ == "__main__":
    sys.exit(run_cli("backfill"))
