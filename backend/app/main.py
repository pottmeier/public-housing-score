from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.models import AddressRequest, ScoreResponse, ScoreComponent, POI
from app.logic import (
    get_coordinates,
    get_nearby_pois,
    haversine_distance,
    calculate_score,
)
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="Housing Convenience Score API")

# CORS erlauben für Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_WEIGHTS = {
    "supermarket": 0.3,
    "doctor": 0.2,
    "public_transport": 0.3,
    "park": 0.2,
}

DEFAULT_WORKPLACE_WEIGHT = 0.2

# Standardmäßige ideale Distanzen in Metern
DEFAULT_IDEAL_DISTANCES = {
    "supermarket": 300,
    "doctor": 500,
    "public_transport": 400,
    "park": 400,
    "workplace": 1000,
}


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration"""
    return {"status": "healthy"}


@app.post("/api/score", response_model=ScoreResponse)
async def create_score(req: AddressRequest):
    request_start = time.time()
    logger.info(f"Starting score calculation for address: {req.address}")

    # Use custom weights or defaults
    weights = req.weights if req.weights else DEFAULT_WEIGHTS.copy()

    # Use custom ideal_distances or defaults
    ideal_distances = (
        req.ideal_distances if req.ideal_distances else DEFAULT_IDEAL_DISTANCES.copy()
    )

    # Workplace handling
    workplace_weight = (
        req.workplace_weight if req.workplace_weight else DEFAULT_WORKPLACE_WEIGHT
    )
    workplace_geo = None

    if req.workplace_address:
        workplace_geo = await get_coordinates(req.workplace_address)
        if not workplace_geo:
            logger.warning(
                f"Could not geocode workplace address: {req.workplace_address}"
            )
        else:
            logger.info(
                f"Workplace geocoded: {workplace_geo['display_name']} ({workplace_geo['lat']}, {workplace_geo['lon']})"
            )
            weights["workplace"] = workplace_weight

    # Normalize weights to sum to 1.0
    weight_sum = sum(weights.values())
    weights = {k: v / weight_sum for k, v in weights.items()}

    # Use custom radius or default to 1500m
    search_radius = req.radius if req.radius else 1500

    # 1. Geocoding
    geo = await get_coordinates(req.address)
    if not geo:
        raise HTTPException(status_code=404, detail="Adresse nicht gefunden")

    logger.info(
        f"Geocoding successful: {geo['display_name']} ({geo['lat']}, {geo['lon']})"
    )

    # 2. Hole POIs - nutzt intern ONE große kombinierte Overpass-Query
    logger.info(
        f"Starting POI query for {len(weights)} categories via single combined Overpass query"
    )
    poi_query_start = time.time()

    poi_tasks = [
        get_nearby_pois(geo["lat"], geo["lon"], category, radius=search_radius)
        for category in weights.keys()
        if category != "workplace"
    ]

    all_pois = await asyncio.gather(*poi_tasks) if poi_tasks else list()

    poi_query_time = time.time() - poi_query_start
    logger.info(f"POI query completed in {poi_query_time:.2f}s")

    details = []
    total_score = 0

    # 3. Verarbeite die Ergebnisse
    pois_index = 0
    for category, weight in weights.items():
        min_dist = 99999
        nearest_poi = None
        nearby_pois_list = []
        cat_score = 0
        pois = None

        if category == "workplace":
            if workplace_geo:
                min_dist = haversine_distance(
                    geo["lat"], geo["lon"], workplace_geo["lat"], workplace_geo["lon"]
                )
                nearest_poi = POI(
                    lat=workplace_geo["lat"],
                    lon=workplace_geo["lon"],
                    distance=round(min_dist, 0),
                )
                ideal_dist_workplace = ideal_distances.get(
                    "workplace", DEFAULT_IDEAL_DISTANCES["workplace"]
                )
                decay_workplace = ideal_dist_workplace * 1.3
                cat_score = calculate_score(
                    min_dist, ideal_dist=ideal_dist_workplace, decay=decay_workplace
                )
                logger.info(
                    f"workplace: distance to workplace is {min_dist:.0f}m, ideal_dist={ideal_dist_workplace}m, decay={decay_workplace:.0f}m"
                )
            else:
                cat_score = 0
                logger.warning("workplace: No workplace address provided!")
        else:
            pois = all_pois[pois_index] if pois_index < len(all_pois) else None
            pois_index += 1

            if pois:
                pois_with_dist = [
                    {
                        **p,
                        "distance": haversine_distance(
                            geo["lat"], geo["lon"], p["lat"], p["lon"]
                        ),
                    }
                    for p in pois
                ]
                pois_with_dist.sort(key=lambda x: x["distance"])

                min_dist = pois_with_dist[0]["distance"]
                nearest_poi = POI(
                    lat=pois_with_dist[0]["lat"],
                    lon=pois_with_dist[0]["lon"],
                    distance=round(pois_with_dist[0]["distance"], 0),
                )

                nearby_pois_list = [
                    POI(lat=p["lat"], lon=p["lon"], distance=round(p["distance"], 0))
                    for p in pois_with_dist
                ]

                logger.info(
                    f"{category}: found {len(pois)} POIs, nearest at {min_dist:.0f}m"
                )

            ideal_dist_cat = ideal_distances.get(
                category, DEFAULT_IDEAL_DISTANCES.get(category, 300)
            )
            decay_cat = ideal_dist_cat * 1.3
            cat_score = calculate_score(
                min_dist, ideal_dist=ideal_dist_cat, decay=decay_cat
            )
            logger.info(
                f"{category}: ideal_dist={ideal_dist_cat}m, decay={decay_cat:.0f}m"
            )

            if not pois:
                cat_score = 0
                logger.warning(f"{category}: No POIs found!")

        poi_count = 0
        if category == "workplace" and workplace_geo:
            poi_count = 1
        elif category != "workplace":
            poi_count = len(pois) if pois else 0

        details.append(
            ScoreComponent(
                category=category,
                score=round(cat_score, 1),
                nearest_po_dist=round(min_dist, 0),
                count_nearby=poi_count,
                nearest_poi=nearest_poi,
                nearby_pois=nearby_pois_list if nearby_pois_list else None,
            )
        )

        total_score += cat_score * weight

    total_time = time.time() - request_start
    logger.info(
        f"Score calculation completed in {total_time:.2f}s (POI queries: {poi_query_time:.2f}s, total score: {total_score:.1f})"
    )

    return ScoreResponse(
        total_score=round(total_score, 1),
        address_display=geo["display_name"],
        lat=geo["lat"],
        lon=geo["lon"],
        details=details,
        weights_applied=weights,
        workplace_address=workplace_geo["display_name"] if workplace_geo else None,
        workplace_lat=workplace_geo["lat"] if workplace_geo else None,
        workplace_lon=workplace_geo["lon"] if workplace_geo else None,
    )
