"""Turn raw listings into per-model daily price stats, trends and deals."""
import statistics
from datetime import date, timedelta

from . import config


def _quantile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    pos = (len(sorted_vals) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def trim_outliers(vals: list[float]) -> list[float]:
    v = sorted(vals)
    if len(v) < 6:
        return v
    q1, q3 = _quantile(v, 0.25), _quantile(v, 0.75)
    iqr = q3 - q1
    return [x for x in v if q1 - 1.5 * iqr <= x <= q3 + 1.5 * iqr]


def summarize(vals: list[float]) -> dict | None:
    v = trim_outliers(vals)
    if len(v) < 3:
        return None
    return {
        "n": len(v),
        "median": round(statistics.median(v), 2),
        "p25": round(_quantile(v, 0.25), 2),
        "p75": round(_quantile(v, 0.75), 2),
        "low": round(v[0], 2),
    }


def daily_series(con, model_id: str, bucket: str = "used") -> list[dict]:
    """One point per day: stats of all listings seen in that day's latest run."""
    rows = con.execute(
        """
        SELECT r.day, l.total FROM listings l JOIN runs r ON r.id = l.run_id
        WHERE l.model_id = ? AND l.bucket = ?
          AND r.id = (SELECT MAX(r2.id) FROM runs r2 WHERE r2.day = r.day)
        ORDER BY r.day
        """,
        (model_id, bucket),
    ).fetchall()
    by_day: dict[str, list[float]] = {}
    for row in rows:
        by_day.setdefault(row["day"], []).append(row["total"])
    out = []
    for day, vals in sorted(by_day.items()):
        s = summarize(vals)
        if s:
            out.append({"day": day, **s})
    return out


def _value_on_or_before(series: list[dict], target: str) -> float | None:
    best = None
    for p in series:
        if p["day"] <= target:
            best = p["median"]
    return best


def pct(now: float | None, then: float | None) -> float | None:
    if not now or not then:
        return None
    return round((now - then) / then * 100, 1)


def model_report(con, model: dict) -> dict:
    used = daily_series(con, model["id"], "used")
    new = daily_series(con, model["id"], "new")
    cur = used[-1] if used else None
    today = date.fromisoformat(cur["day"]) if cur else date.today()
    rep = {
        "model": model,
        "series": used,
        "current": cur,
        "new_current": new[-1] if new else None,
        "chg_7d": pct(cur and cur["median"], _value_on_or_before(used, (today - timedelta(days=7)).isoformat())),
        "chg_30d": pct(cur and cur["median"], _value_on_or_before(used, (today - timedelta(days=30)).isoformat())),
        "low_90d": min((p["low"] for p in used[-90:]), default=None),
        "deals": [],
        "listings": [],
    }
    if model.get("gb") and cur:
        rep["per_gb"] = round(cur["median"] / model["gb"], 2)
    if cur:
        rows = con.execute(
            """
            SELECT * FROM listings WHERE model_id = ? AND bucket = 'used'
              AND run_id = (SELECT MAX(id) FROM runs) ORDER BY total
            """,
            (model["id"],),
        ).fetchall()
        trusted = [
            dict(r) for r in rows
            if (r["seller_pct"] or 0) >= config.MIN_FEEDBACK_PCT and (r["seller_score"] or 0) >= config.MIN_FEEDBACK_SCORE
            and r["total"] >= cur["p25"] * 0.6  # too-good-to-be-true filter
        ]
        rep["listings"] = trusted[:10]
        rep["deals"] = [r for r in trusted if r["total"] <= cur["median"] * config.DEAL_RATIO][:5]
    return rep


def market_index(reports: list[dict], cat: str, key: str) -> float | None:
    vals = [r[key] for r in reports if r["model"]["cat"] == cat and r[key] is not None]
    return round(sum(vals) / len(vals), 1) if vals else None
