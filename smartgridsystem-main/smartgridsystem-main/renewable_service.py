import logging
import random
from datetime import datetime, timedelta
from db import db
from models import RenewableData
from api_client import CEAClient

logger = logging.getLogger(__name__)
cea_client = CEAClient()

CO2_FACTORS = {
    "solar":   0.82,
    "wind":    0.82,
    "hydro":   0.82,
    "biomass": 0.23,
    "others":  0.82,
}

def _persist_renewable_snapshot(raw):
    try:
        ts = datetime.utcnow()
        regions = raw.get("regions", {})
        capacity = raw.get("renewable_capacity", {})
        for region, sources in regions.items():
            for source_type, gen_value in sources.items():
                cap_value = capacity.get(source_type, 0)
                record = RenewableData(
                    timestamp=ts,
                    region=region,
                    type=source_type,
                    capacity=cap_value,
                    generation=gen_value,
                )
                db.session.add(record)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(f"Failed to persist renewable snapshot: {exc}")


def get_renewable_summary():
    raw = cea_client.get_renewable_data()
    try:
        _persist_renewable_snapshot(raw)
    except Exception as exc:
        logger.warning(f"DB persist skipped: {exc}")

    capacity   = raw.get("renewable_capacity", {})
    generation = raw.get("current_generation", {})
    regions    = raw.get("regions", {})

    total_capacity   = sum(capacity.values())
    total_generation = sum(generation.values())

    utilisation = {}
    for src in capacity:
        cap = capacity.get(src, 0)
        gen = generation.get(src, 0)
        utilisation[src] = round((gen / cap * 100) if cap > 0 else 0, 1)

    co2_avoided_per_hour = sum(
        generation.get(src, 0) * CO2_FACTORS.get(src, 0.82)
        for src in generation
    )

    highest_source = max(generation, key=generation.get) if generation else "N/A"

    regional_summary = {}
    for region, sources in regions.items():
        reg_total = sum(sources.values())
        regional_summary[region] = {
            "sources": sources,
            "total_generation": reg_total,
            "share_of_grid_pct": round(
                (reg_total / total_generation * 100) if total_generation > 0 else 0, 1
            ),
        }

    return {
        "timestamp":                   raw.get("timestamp", datetime.utcnow().isoformat()),
        "capacity":                    capacity,
        "current_generation":          generation,
        "total_capacity_mw":           total_capacity,
        "total_generation_mw":         total_generation,
        "overall_utilisation_pct":     round((total_generation / total_capacity * 100) if total_capacity > 0 else 0, 1),
        "utilisation_by_source":       utilisation,
        "co2_avoided_per_hour_tonnes": round(co2_avoided_per_hour, 1),
        "highest_source":              highest_source,
        "regional_breakdown":          regional_summary,
    }


def get_renewable_trends(days=7, source="all"):
    cutoff = datetime.utcnow() - timedelta(days=days)
    try:
        query = RenewableData.query.filter(RenewableData.timestamp >= cutoff)
        if source != "all":
            query = query.filter(RenewableData.type == source)
        records = query.order_by(RenewableData.timestamp).all()
    except Exception as exc:
        logger.error(f"DB query failed: {exc}")
        records = []

    if records:
        daily = {}
        for r in records:
            day_key = r.timestamp.strftime("%Y-%m-%d")
            if day_key not in daily:
                daily[day_key] = {}
            daily[day_key][r.type] = daily[day_key].get(r.type, 0) + r.generation
        trend_data = [{"date": d, "generation": vals} for d, vals in sorted(daily.items())]
    else:
        trend_data = _simulated_trends(days, source)

    return {"days": days, "source": source, "trend_data": trend_data}


def get_regional_renewable(region="all"):
    raw = cea_client.get_renewable_data()
    regions_data = raw.get("regions", {})

    if region != "all":
        filtered = {k: v for k, v in regions_data.items() if k == region.lower()}
        if not filtered:
            return {"error": f"Region '{region}' not found.", "available": list(regions_data.keys())}
        regions_data = filtered

    result = {}
    for reg, sources in regions_data.items():
        total = sum(sources.values())
        result[reg] = {
            "sources": sources,
            "total_mw": total,
            "source_mix_pct": {
                src: round((val / total * 100) if total > 0 else 0, 1)
                for src, val in sources.items()
            },
        }
    return {"region": region, "data": result}


def get_source_detail(source):
    valid_sources = {"solar", "wind", "hydro", "biomass", "others"}
    if source not in valid_sources:
        return {"error": f"Unknown source '{source}'. Valid: {sorted(valid_sources)}"}

    raw      = cea_client.get_renewable_data()
    capacity = raw.get("renewable_capacity", {})
    gen      = raw.get("current_generation", {})
    regions  = raw.get("regions", {})

    cap      = capacity.get(source, 0)
    curr_gen = gen.get(source, 0)
    util_pct = round((curr_gen / cap * 100) if cap > 0 else 0, 1)

    regional_breakdown = {reg: vals.get(source, 0) for reg, vals in regions.items()}
    top_region = max(regional_breakdown, key=regional_breakdown.get) if regional_breakdown else "N/A"

    return {
        "source":                      source,
        "capacity_mw":                 cap,
        "current_generation_mw":       curr_gen,
        "utilisation_pct":             util_pct,
        "co2_avoided_per_hour_tonnes": round(curr_gen * CO2_FACTORS.get(source, 0.82), 1),
        "top_region":                  top_region,
        "regional_breakdown":          regional_breakdown,
        "timestamp":                   raw.get("timestamp", datetime.utcnow().isoformat()),
    }


def _simulated_trends(days, source):
    sources = ["solar", "wind", "hydro", "biomass", "others"] if source == "all" else [source]
    base = {"solar": 39000, "wind": 21600, "hydro": 37440, "biomass": 5200, "others": 1100}
    data = []
    for i in range(days - 1, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        generation = {s: int(base.get(s, 10000) * (0.85 + random.random() * 0.30)) for s in sources}
        data.append({"date": day, "generation": generation})
    return data