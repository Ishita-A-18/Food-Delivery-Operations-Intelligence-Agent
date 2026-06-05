def read_city_state(db) -> list:
    """Scan all zones, detect demand-supply imbalances, return ranked anomaly list."""
    zones = list(db.city_grid.find())
    anomalies = []

    for zone in zones:
        shortage = zone["active_orders"] - zone["idle_agents"]
        # Act on any zone the simulation has flagged critical, or that hits watch thresholds.
        is_anomaly = (
            zone.get("status") == "critical"
            or (zone["avg_wait_minutes"] > 25 and shortage > 3)
        )
        if not is_anomaly:
            continue

        candidate_sources = [
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
