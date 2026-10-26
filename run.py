#!/usr/bin/env python3
"""Used GPU & RAM price tracker.

  python3 run.py collect            # pull current eBay listings into the database
  python3 run.py build              # regenerate the static site in docs/
  python3 run.py all                # collect + AI summaries + build
  python3 run.py demo --days 60     # fill a SEPARATE demo database with fake history and build (for testing)
"""
import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone


def collect(con, models, sample_day=None):
    from tracker import filters, sample
    cfg_models = models["models"]
    excl = models["global_exclude"]
    if sample_day is None:
        from tracker.ebay import EbayClient
        client = EbayClient()
        source, day = "ebay", datetime.now(timezone.utc).date().isoformat()
    else:
        source, day = "sample", sample_day.isoformat()
    cur = con.execute("INSERT INTO runs (ts, day, source) VALUES (?,?,?)",
                      (datetime.now(timezone.utc).isoformat(timespec="seconds"), day, source))
    run_id = cur.lastrowid
    total = 0
    for m in cfg_models:
        cat = models["categories"][m["cat"]]
        if sample_day is None:
            try:
                raw = client.search(m["query"], cat["ebay_category_id"], m["min"] * 0.8, m["max"] * 1.15)
            except Exception as e:  # one bad query shouldn't kill the run
                print(f"  ! {m['id']}: {e}", file=sys.stderr)
                continue
        else:
            raw = sample.listings(m, (sample_day - date(2026, 1, 1)).days)
        kept = [l for l in raw if l["item_id"] and filters.keep(l, m, excl)]
        con.executemany(
            "INSERT OR IGNORE INTO listings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(run_id, m["id"], l["item_id"], l["title"], l["bucket"], l["price"], l["shipping"], l["total"],
              l["url"], l["image"], l["seller_pct"], l["seller_score"]) for l in kept])
        total += len(kept)
        if sample_day is None:
            print(f"  {m['id']}: {len(kept)}/{len(raw)} kept")
    con.commit()
    return total


def build(con, models, use_ai=True):
    from tracker import ai, site, stats
    reports = [stats.model_report(con, m) for m in models["models"]]
    demo = con.execute("SELECT COUNT(*) FROM runs WHERE source='sample'").fetchone()[0] > 0
    summaries = ai.refresh(con, reports) if use_ai else {
        r[0]: r[1] for r in con.execute("SELECT model_id, text FROM summaries")}
    site.build(reports, summaries, demo)
    print(f"Built {len(reports)} model pages{' (DEMO)' if demo else ''}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["collect", "build", "all", "demo"])
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--no-ai", action="store_true")
    a = p.parse_args()

    if a.cmd == "demo":  # keep fake data away from the real database
        os.environ["DATA_DIR"] = os.environ.get("DEMO_DATA_DIR", "demo-data")
        os.environ.setdefault("SITE_DIR", "demo-site")
    from tracker import config, db
    models = config.load_models()
    con = db.connect()

    if a.cmd == "demo":
        con.execute("DELETE FROM listings"); con.execute("DELETE FROM runs"); con.execute("DELETE FROM summaries")
        start = date.today() - timedelta(days=a.days - 1)
        for i in range(a.days):
            collect(con, models, sample_day=start + timedelta(days=i))
        build(con, models, use_ai=not a.no_ai)
    if a.cmd in ("collect", "all"):
        print(f"Collected {collect(con, models)} listings")
    if a.cmd in ("build", "all"):
        build(con, models, use_ai=not a.no_ai and a.cmd == "all")


if __name__ == "__main__":
    main()
