import math

ZONE_COORDS = {
    "zone_01": (12.9352, 77.6245),  # Koramangala
    "zone_02": (12.9082, 77.6476),  # HSR Layout
    "zone_03": (12.9784, 77.6408),  # Indiranagar
    "zone_04": (12.9165, 77.6101),  # BTM Layout
    "zone_05": (12.9698, 77.7499),  # Whitefield
    "zone_06": (12.9308, 77.5835),  # Jayanagar
    "zone_07": (12.9591, 77.7001),  # Marathahalli
    "zone_08": (12.8399, 77.6770),  # Electronic City
    "zone_09": (12.8993, 77.5966),  # Bannerghatta Road
    "zone_10": (12.9901, 77.5552),  # Rajajinagar
    "zone_11": (13.0035, 77.5707),  # Malleshwaram
    "zone_12": (13.1005, 77.5963),  # Yelahanka
    "zone_13": (12.9079, 77.5859),  # JP Nagar
    "zone_14": (13.0351, 77.5967),  # Hebbal
    "zone_15": (12.9121, 77.6849),  # Sarjapur Road
    "zone_16": (12.9316, 77.6757),  # Bellandur
    "zone_17": (12.9253, 77.5468),  # Banashankari
    "zone_18": (12.9757, 77.6099),  # MG Road
    "zone_19": (12.9924, 77.5973),  # Cunningham Road
    "zone_20": (12.9218, 77.4823),  # Kengeri
}

MAX_SOURCE_DISTANCE_KM = 8.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def distance_km(zone_a: str, zone_b: str) -> float:
    if zone_a not in ZONE_COORDS or zone_b not in ZONE_COORDS:
        return 0.0
    la, lo = ZONE_COORDS[zone_a]
    lb, lo2 = ZONE_COORDS[zone_b]
    return _haversine_km(la, lo, lb, lo2)


def nearby_surplus_zones(
    target_zone_id: str,
    all_zones: list,
    max_km: float = MAX_SOURCE_DISTANCE_KM,
) -> list[tuple[float, dict]]:
    """Return (distance_km, zone) tuples for zones within max_km of target that have
    surplus idle agents (idle > 40% of active orders, and at least 3 idle).
    Sorted nearest first."""
    result = []
    for z in all_zones:
        zid = z["zone_id"]
        if zid == target_zone_id:
            continue
        dist = distance_km(target_zone_id, zid)
        surplus = z["idle_agents"] - max(2, int(z.get("active_orders", 0) * 0.4))
        if dist <= max_km and surplus > 0 and z["idle_agents"] >= 3:
            result.append((dist, z))
    result.sort(key=lambda x: x[0])
    return result


def multi_source_moves(
    db,
    target_zone_id: str,
    needed: int,
    all_zones: list,
) -> tuple[list, list]:
    """Pull agents from up to 3 nearby surplus zones.

    Priority order:
      1. Nearest first — zones are bucketed in 0.5 km bands so genuinely close zones
         are treated as equally proximate.
      2. Most abundant within the same band — the zone with more spare agents is
         preferred when two candidates are at similar distance.
    Allocation is greedy: each selected zone contributes as many agents as it can
    spare before moving to the next, so the closest zone is drained first.
    """
    nearby = nearby_surplus_zones(target_zone_id, all_zones)  # already distance-sorted
    if not nearby:
        return [], []

    def _sort_key(item: tuple) -> tuple:
        dist, z = item
        surplus = max(0, z["idle_agents"] - max(2, int(z.get("active_orders", 0) * 0.4)))
        # bucket distance to 0.5 km so zones at e.g. 2.1 km and 2.4 km tie on proximity
        return (round(dist * 2) / 2, -surplus)

    candidates = sorted(nearby[:5], key=_sort_key)[:3]

    moves: list = []
    descriptions: list = []
    remaining = needed

    for dist, source in candidates:
        if remaining <= 0:
            break
        surplus = max(0, source["idle_agents"] - max(2, int(source.get("active_orders", 0) * 0.4)))
        if surplus == 0:
            continue
        take = min(surplus, remaining)  # greedy: take as much as available here
        agents = list(db.agents.aggregate([
            {"$match": {"current_zone": source["zone_id"], "status": "idle"}},
            {"$sample": {"size": take}},
        ]))
        for a in agents:
            moves.append({
                "type": "move_agent",
                "agent_id": a["agent_id"],
                "from_zone": source["zone_id"],
                "to_zone": target_zone_id,
            })
        if agents:
            descriptions.append(f"{source['name']} ({len(agents)}, {dist:.1f} km)")
        remaining -= len(agents)

    return moves, descriptions
