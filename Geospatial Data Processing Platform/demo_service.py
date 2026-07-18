"""Deterministic, credential-free scan service used by the public prototype."""

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence
from uuid import uuid4


ALLOWED_SIGNALS = {"ponding", "patching", "discoloration"}


class ScanValidationError(ValueError):
    """Raised when a scan request contains unsupported parameters."""


@dataclass(frozen=True)
class Area:
    id: str
    name: str
    region: str
    area_km2: float
    footprint_count: int
    imagery_coverage: float


@dataclass(frozen=True)
class Lead:
    id: int
    area_id: str
    name: str
    address: str
    roof_area_m2: int
    opportunity_score: int
    signals: Sequence[str]
    longitude: float
    latitude: float


AREAS = {
    "waterloo": Area("waterloo", "North Waterloo", "Waterloo Region, ON", 2.4, 148, 0.96),
    "kitchener": Area("kitchener", "Kitchener Innovation District", "Waterloo Region, ON", 1.8, 126, 0.94),
    "cambridge": Area("cambridge", "Cambridge Industrial Park", "Waterloo Region, ON", 3.1, 213, 0.97),
}


LEADS = (
    Lead(1, "waterloo", "Northfield Commerce Centre", "Northfield Dr E, Waterloo", 4280, 92, ("ponding", "discoloration"), -80.5361, 43.4912),
    Lead(2, "waterloo", "Conestoga Industrial Building", "Davenport Rd, Waterloo", 3150, 84, ("patching", "discoloration"), -80.5295, 43.4882),
    Lead(3, "waterloo", "Colby Drive Warehouse", "Colby Dr, Waterloo", 5840, 78, ("ponding",), -80.5451, 43.4820),
    Lead(4, "waterloo", "Labrador Drive Complex", "Labrador Dr, Waterloo", 2690, 69, ("patching",), -80.5202, 43.4811),
    Lead(5, "waterloo", "Parkside Distribution", "Parkside Dr, Waterloo", 6320, 57, ("discoloration",), -80.5318, 43.4790),
    Lead(6, "kitchener", "Victoria Street Works", "Victoria St N, Kitchener", 4720, 89, ("ponding", "patching"), -80.4991, 43.4620),
    Lead(7, "kitchener", "Breithaupt Block Annex", "Breithaupt St, Kitchener", 2410, 81, ("discoloration",), -80.4932, 43.4573),
    Lead(8, "kitchener", "Glasgow Commerce Hub", "Glasgow St, Kitchener", 5190, 73, ("patching", "discoloration"), -80.5121, 43.4514),
    Lead(9, "kitchener", "King West Workshop", "King St W, Kitchener", 1980, 62, ("ponding",), -80.5062, 43.4491),
    Lead(10, "cambridge", "Pinebush Logistics Centre", "Pinebush Rd, Cambridge", 8340, 95, ("ponding", "patching", "discoloration"), -80.3261, 43.4115),
    Lead(11, "cambridge", "Franklin Manufacturing", "Franklin Blvd, Cambridge", 6150, 86, ("patching",), -80.3022, 43.3987),
    Lead(12, "cambridge", "Sheldon Drive Warehouse", "Sheldon Dr, Cambridge", 4860, 76, ("ponding", "discoloration"), -80.3148, 43.4052),
    Lead(13, "cambridge", "Hespeler Commerce Park", "Hespeler Rd, Cambridge", 3570, 67, ("discoloration",), -80.3217, 43.4181),
)


def list_areas() -> List[Dict[str, Any]]:
    return [asdict(area) for area in AREAS.values()]


def run_demo_scan(payload: Dict[str, Any]) -> Dict[str, Any]:
    started_at = time.perf_counter()
    area_id = payload.get("area", "waterloo")
    if area_id not in AREAS:
        raise ScanValidationError("area must be one of: {}".format(", ".join(AREAS)))

    minimum_score = parse_integer(payload.get("minimum_score", 65), "minimum_score", 0, 100)
    page = parse_integer(payload.get("page", 1), "page", 1, 10_000)
    per_page = parse_integer(payload.get("per_page", 20), "per_page", 1, 100)
    signals = payload.get("signals", sorted(ALLOWED_SIGNALS))
    if not isinstance(signals, list) or not signals:
        raise ScanValidationError("signals must be a non-empty array")
    unknown_signals = set(signals) - ALLOWED_SIGNALS
    if unknown_signals:
        raise ScanValidationError("unsupported signals: {}".format(", ".join(sorted(unknown_signals))))

    matches = [
        lead for lead in LEADS
        if lead.area_id == area_id
        and lead.opportunity_score >= minimum_score
        and set(lead.signals).intersection(signals)
    ]
    matches.sort(key=lambda lead: lead.opportunity_score, reverse=True)
    start = (page - 1) * per_page
    selected = matches[start:start + per_page]
    area = AREAS[area_id]

    return {
        "scan_id": str(uuid4()),
        "mode": "simulation",
        "disclaimer": "Synthetic scores identify sample candidates, not confirmed roof damage.",
        "criteria": {"area": area_id, "minimum_score": minimum_score, "signals": signals},
        "summary": {
            "footprints_analyzed": area.footprint_count,
            "matches": len(matches),
            "imagery_coverage": area.imagery_coverage,
            "processing_ms": round((time.perf_counter() - started_at) * 1000, 3),
        },
        "pagination": {"page": page, "per_page": per_page, "total": len(matches)},
        "data": [serialize_lead(lead) for lead in selected],
    }


def parse_integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ScanValidationError("{} must be an integer".format(field))
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ScanValidationError("{} must be an integer".format(field))
    if not minimum <= parsed <= maximum:
        raise ScanValidationError("{} must be between {} and {}".format(field, minimum, maximum))
    return parsed


def serialize_lead(lead: Lead) -> Dict[str, Any]:
    return {
        "id": lead.id,
        "name": lead.name,
        "address": lead.address,
        "roof_area_m2": lead.roof_area_m2,
        "opportunity_score": lead.opportunity_score,
        "signals": list(lead.signals),
        "location": {"type": "Point", "coordinates": [lead.longitude, lead.latitude]},
    }
