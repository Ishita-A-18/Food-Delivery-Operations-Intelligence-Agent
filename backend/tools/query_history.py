def query_history(db, zone_id: str, time_of_day: str, event_type: str = None) -> dict:
    """Pull historical patterns and past resolved incidents for a zone."""
    # Try exact match first (zone + time of day)
    query = {"affected_zone": zone_id, "typical_time_of_day": time_of_day}
    if event_type:
        query["event_type"] = event_type
    pattern = db.historical_patterns.find_one(query)

    # Fallback 1: match by zone + event_type only (ignore time of day)
    if not pattern and event_type:
        pattern = db.historical_patterns.find_one({
            "affected_zone": zone_id,
            "event_type": event_type,
        })

    # Fallback 2: any pattern for this zone
    if not pattern:
        pattern = db.historical_patterns.find_one({"affected_zone": zone_id})

    past_incidents = list(
        db.action_log.find({"trigger_zone": zone_id, "status": "resolved"})
        .sort("created_at", -1)
        .limit(5)
    )

    # Strip ObjectIds for serialisation
    for inc in past_incidents:
        inc.pop("_id", None)

    return {
        "pattern": {k: v for k, v in pattern.items() if k != "_id"} if pattern else None,
        "past_incidents": past_incidents,
        "recommendation_basis": (
            pattern["notes"] if pattern
            else "No prior pattern — recommending standard redistribution."
        ),
    }
