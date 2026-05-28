import os
import random
import pandas as pd

LOCATION_TO_ZONE = {
    "Koramangala":       "zone_01",
    "Hsr Layout":        "zone_02",
    "Indiranagar":       "zone_03",
    "Btm":               "zone_04",
    "Whitefield":        "zone_05",
    "Jayanagar":         "zone_06",
    "Marathahalli":      "zone_07",
    "Electronic City":   "zone_08",
    "Bannerghatta Road": "zone_09",
    "Rajajinagar":       "zone_10",
    "Malleshwaram":      "zone_11",
    "Yelahanka":         "zone_12",
    "Jp Nagar":          "zone_13",
    "Hebbal":            "zone_14",
    "Sarjapur Road":     "zone_15",
    "Bellandur":         "zone_16",
    "Banashankari":      "zone_17",
    "Mg Road":           "zone_18",
    "Cunningham Road":   "zone_19",
    "Kengeri":           "zone_20",
}


def load_restaurants(csv_path: str = None) -> list:
    if csv_path is None:
        # Default: two levels up from this file, then zomato/zomato.csv
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        csv_path = os.path.join(base, "zomato", "zomato.csv")

    df = pd.read_csv(csv_path, on_bad_lines="skip")
    df["location"] = df["location"].astype(str).str.strip().str.title()
    df["cuisines"] = df["cuisines"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.strip()

    df_filtered = df[df["location"].isin(LOCATION_TO_ZONE.keys())].copy()

    # Sample up to 2 restaurants per zone — avoids pandas 2.x groupby index issues
    chunks = []
    for location in LOCATION_TO_ZONE:
        subset = df_filtered[df_filtered["location"] == location]
        if len(subset) > 0:
            chunks.append(subset.sample(min(2, len(subset)), random_state=42))

    if not chunks:
        return []

    sample = pd.concat(chunks).head(30).reset_index(drop=True)

    restaurants = []
    for _, row in sample.iterrows():
        location_val = str(row["location"]).strip().title()
        zone_id = LOCATION_TO_ZONE.get(location_val, "zone_01")
        restaurants.append({
            "restaurant_id": f"rest_{len(restaurants)+1:02d}",
            "name": str(row["name"]).strip(),
            "zone_id": zone_id,
            "cuisine": str(row["cuisines"]).strip() if str(row["cuisines"]) != "nan" else "Multi-cuisine",
            "queue_depth": random.randint(2, 8),
            "status": "open",
            "avg_prep_minutes": random.randint(15, 30),
            "paused_at": None,
        })

    return restaurants
