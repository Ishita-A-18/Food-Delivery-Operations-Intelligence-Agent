def read_city_state(db) -> list:
    """Scan all zones, detect demand-supply imbalances, return ranked anomaly list."""
    zones = list(db.city_grid.find())
    anomalies = []

    for zone in zones:
        shortage = zone["active_orders"] - zone["idle_agents"]
        if zone["avg_wait_minutes"] > 35 and shortage > 5:
            # Prefer zones with clear surplus; fall back to any zone with idle agents
            surplus_zones = [
                z for z in zones
                if z["idle_agents"] > z["active_orders"] * 1.5
                and z["zone_id"] != zone["zone_id"]
            ]
            candidate_sources = surplus_zones or [
                z for z in zones
                if z["idle_agents"] > 3 and z["zone_id"] != zone["zone_id"]
            ]
            if candidate_sources:
                anomalies.append({
                    "zone": zone,
                    "agent_shortage": shortage,
                    "severity": zone["avg_wait_minutes"] / 60,
                    "candidate_sources": candidate_sources,
                })

    return sorted(anomalies, key=lambda x: x["severity"], reverse=True)
