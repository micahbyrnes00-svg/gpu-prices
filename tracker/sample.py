"""Synthetic listings for testing before eBay keys are approved. Never publish these."""
import hashlib
import math
import random

BASE = {
    "rtx-3060-12gb": 215, "rtx-3060-ti": 230, "rtx-3070": 285, "rtx-3080": 410, "rtx-3090": 780,
    "rtx-4060": 255, "rtx-4070": 470, "rtx-4070-super": 540, "rtx-4080": 920, "rtx-4090": 1850,
    "rx-6700-xt": 245, "rx-6800-xt": 370, "rx-7800-xt": 430, "rx-7900-xtx": 790,
    "ddr4-16gb-3200": 42, "ddr4-32gb-3200": 78, "ddr4-32gb-3600": 88, "ddr4-64gb-3200": 165,
    "ddr5-32gb-6000": 165, "ddr5-32gb-5600": 150, "ddr5-64gb-6000": 330, "ddr5-96gb-6400": 520,
}


def listings(model: dict, day_index: int) -> list[dict]:
    seed = int(hashlib.md5(f"{model['id']}-{day_index}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    base = BASE.get(model["id"], (model["min"] + model["max"]) / 2)
    # slow drift: GPUs drift down, RAM drifts up, plus a weekly wiggle
    drift = (0.0016 if model["cat"] == "ram" else -0.0009) * day_index
    level = base * (1 + drift + 0.02 * math.sin(day_index / 4 + len(model["id"])))
    out = []
    for n in range(rng.randint(25, 60)):
        bucket = "new" if rng.random() < 0.2 else "used"
        mult = 1.25 if bucket == "new" else 1.0
        price = round(max(model["min"], min(model["max"], rng.gauss(level * mult, level * 0.09))), 2)
        ship = rng.choice([0.0, 0.0, 9.99, 14.5, 19.99])
        out.append({
            "item_id": f"demo-{model['id']}-{day_index}-{n}",
            "title": f"{model['name']} {rng.choice(['Founders Edition', 'EVGA', 'MSI', 'ASUS', 'Gigabyte', 'Corsair', 'G.Skill'])} (demo)",
            "bucket": bucket,
            "price": price,
            "shipping": ship,
            "total": round(price + ship, 2),
            "url": "https://www.ebay.com/",
            "image": None,
            "seller_pct": rng.choice([96.5, 98.9, 99.4, 100.0, 100.0]),
            "seller_score": rng.randint(5, 4000),
        })
    return out
