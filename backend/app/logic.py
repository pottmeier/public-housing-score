import httpx
import math
import json
import redis
import os
import time
import logging
import asyncio

logger = logging.getLogger(__name__)

# Redis Verbindung für Caching
r = redis.Redis.from_url("redis://redis:6379", decode_responses=True)

# User Agent ist Pflicht für OSM services!
HEADERS = {"User-Agent": "HousingScoreMVP/1.0 (Student Project)"}


async def get_coordinates(address: str):
    """Geocoding via Nominatim mit Caching"""
    cache_key = f"geo:{address.lower()}"
    cached = r.get(cache_key)
    if cached:
        return json.loads(cached)

    url = "https://nominatim.openstreetmap.org/search"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url, params={"q": address, "format": "json", "limit": 1}, headers=HEADERS
        )
        data = resp.json()

    if data:
        res = {
            "lat": float(data[0]["lat"]),
            "lon": float(data[0]["lon"]),
            "display_name": data[0]["display_name"],
        }
        r.setex(cache_key, 86400, json.dumps(res))  # 24h Cache
        return res
    return None


def _matches_category_tags(tags: dict, category: str) -> bool:
    """Prüft ob ein OSM-Element zu einer Kategorie passt"""
    if category == "supermarket":
        return tags.get("shop") in ["supermarket", "grocery"]

    elif category == "doctor":
        return (
            tags.get("healthcare") in ["doctor", "pharmacy"]
            or tags.get("amenity") in ["doctors", "clinic", "hospital"]
            or tags.get("shop") == "chemist"
        )

    elif category == "public_transport":
        return (
            tags.get("highway") == "bus_stop"
            or tags.get("railway") in ["station", "halt", "tram_stop"]
            or tags.get("public_transport") in ["stop_position", "platform"]
        )

    elif category == "park":
        return tags.get("leisure") in ["park", "garden", "green_area"]

    return False


async def get_all_pois_single_query(lat: float, lon: float, radius=1500):
    """
    Holt ALLE POIs (alle Kategorien) in EINER großen Overpass-Query
    Nutzt "union" pattern um die Query-Komplexität zu minimieren
    """
    cache_key = f"kv:all:{round(lat, 4)}:{round(lon, 4)}:{radius}"

    # Prüfe Cache
    cached = r.get(cache_key)
    if cached:
        logger.info(f"Cache hit for all POIs")
        return json.loads(cached)

    logger.info("Building single combined Overpass query for all categories...")
    query_start = time.time()

    # WICHTIG: Nutze kompaktes Query-Format um Overpass nicht zu überlasten
    # Kombiniere so viele Tags wie möglich in weniger Queries
    query = f"""
    [out:json][timeout:25];
    (
      node["shop"~"supermarket|grocery"](around:{radius},{lat},{lon});
      way["shop"~"supermarket|grocery"](around:{radius},{lat},{lon});
      node["healthcare"~"doctor|pharmacy"](around:{radius},{lat},{lon});
      node["amenity"~"doctors|clinic|hospital"](around:{radius},{lat},{lon});
      way["healthcare"~"doctor|pharmacy"](around:{radius},{lat},{lon});
      way["amenity"~"doctors|clinic|hospital"](around:{radius},{lat},{lon});
      node["highway"="bus_stop"](around:{radius},{lat},{lon});
      way["highway"="bus_stop"](around:{radius},{lat},{lon});
      node["railway"~"station|halt|tram_stop"](around:{radius},{lat},{lon});
      way["railway"~"station|halt|tram_stop"](around:{radius},{lat},{lon});
      node["public_transport"~"stop_position|platform"](around:{radius},{lat},{lon});
      way["public_transport"~"stop_position|platform"](around:{radius},{lat},{lon});
      node["leisure"~"park|garden|green_area"](around:{radius},{lat},{lon});
      way["leisure"~"park|garden|green_area"](around:{radius},{lat},{lon});
    );
    out center;
    """

    logger.debug(f"Query size: {len(query)} bytes (optimized with regex unions)")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            logger.info("Sending combined Overpass query...")
            resp = await client.post(
                "https://overpass-api.de/api/interpreter",
                content=query,
                headers=HEADERS,
            )

            query_time = time.time() - query_start
            logger.info(
                f"Overpass response in {query_time:.2f}s (status: {resp.status_code})"
            )

            # Retry bei Rate Limit oder Timeout
            if resp.status_code == 429:
                logger.warning("Rate limited (429), waiting 5s and retrying...")
                await asyncio.sleep(5)
                return await get_all_pois_single_query(lat, lon, radius)

            if resp.status_code == 504:
                logger.warning("Gateway Timeout (504), waiting 3s and retrying...")
                await asyncio.sleep(3)
                return await get_all_pois_single_query(lat, lon, radius)

            if resp.status_code != 200:
                logger.warning(f"Overpass returned status {resp.status_code}")
                return {
                    "supermarket": [],
                    "doctor": [],
                    "public_transport": [],
                    "park": [],
                }

            data = resp.json()

            if "error" in data:
                logger.warning(f"Overpass error: {data.get('error')}")
                return {
                    "supermarket": [],
                    "doctor": [],
                    "public_transport": [],
                    "park": [],
                }

            elements = data.get("elements", [])
            logger.info(f"Received {len(elements)} elements from Overpass")

            # Kategorisiere die Ergebnisse
            results = {
                "supermarket": [],
                "doctor": [],
                "public_transport": [],
                "park": [],
            }

            for el in elements:
                p_lat = el.get("lat") or el.get("center", {}).get("lat")
                p_lon = el.get("lon") or el.get("center", {}).get("lon")

                if not (p_lat and p_lon):
                    continue

                poi = {"lat": p_lat, "lon": p_lon}
                tags = el.get("tags", {})

                # Kategorisiere based on tags
                if _matches_category_tags(tags, "supermarket"):
                    results["supermarket"].append(poi)
                if _matches_category_tags(tags, "doctor"):
                    results["doctor"].append(poi)
                if _matches_category_tags(tags, "public_transport"):
                    results["public_transport"].append(poi)
                if _matches_category_tags(tags, "park"):
                    results["park"].append(poi)

            # Log Statistiken
            logger.info(
                f"Results - supermarket: {len(results['supermarket'])}, doctor: {len(results['doctor'])}, "
                f"public_transport: {len(results['public_transport'])}, park: {len(results['park'])}"
            )

            # Cache für 1 Stunde
            r.setex(cache_key, 3600, json.dumps(results))

            return results

    except asyncio.TimeoutError:
        logger.warning("Overpass query timeout after 30s")
        return {
            "supermarket": [],
            "doctor": [],
            "public_transport": [],
            "park": [],
        }
    except Exception as e:
        logger.error(f"Overpass error: {e}", exc_info=True)
        return {
            "supermarket": [],
            "doctor": [],
            "public_transport": [],
            "park": [],
        }

    # Baue ONE große Query mit allen Tags
    logger.info("Building single combined Overpass query for all categories...")
    query_start = time.time()

    node_parts = []
    way_parts = []

    # Baue Overpass query - nutze union (|) um alle Tags zu kombinieren
    for category, tags in all_tags.items():
        for tag in tags:
            node_parts.append(f"node[{tag}](around:{radius},{lat},{lon});")
            way_parts.append(f"way[{tag}](around:{radius},{lat},{lon});")

    # Kombiniere zu EINER Query mit Timeout von 25s
    node_queries_str = "\n".join([f"      {q}" for q in node_parts])
    way_queries_str = "\n".join([f"      {q}" for q in way_parts])

    query = f"""
    [out:json][timeout:25];
    (
{node_queries_str}
{way_queries_str}
    );
    out center;
    """

    logger.debug(f"Query size: {len(query)} bytes")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            logger.info("Sending combined Overpass query to API...")
            resp = await client.post(
                "https://overpass-api.de/api/interpreter",
                content=query,
                headers=HEADERS,
            )

            query_time = time.time() - query_start
            logger.info(
                f"Overpass response received in {query_time:.2f}s (status: {resp.status_code})"
            )

            # Retry bei Rate Limit
            if resp.status_code == 429:
                logger.warning("Rate limited (429), waiting 5s and retrying...")
                await asyncio.sleep(5)
                return await get_all_pois_single_query(lat, lon, radius)

            if resp.status_code != 200:
                logger.warning(f"Overpass returned status {resp.status_code}")
                return {
                    "supermarket": [],
                    "doctor": [],
                    "public_transport": [],
                    "park": [],
                }

            data = resp.json()

            if "error" in data:
                logger.warning(f"Overpass error: {data.get('error')}")
                return {
                    "supermarket": [],
                    "doctor": [],
                    "public_transport": [],
                    "park": [],
                }

            elements = data.get("elements", [])
            logger.info(f"Received {len(elements)} elements from Overpass")

            # Kategorisiere die Ergebnisse
            results = {
                "supermarket": [],
                "doctor": [],
                "public_transport": [],
                "park": [],
            }

            for el in elements:
                p_lat = el.get("lat") or el.get("center", {}).get("lat")
                p_lon = el.get("lon") or el.get("center", {}).get("lon")

                if not (p_lat and p_lon):
                    continue

                poi = {"lat": p_lat, "lon": p_lon}
                tags = el.get("tags", {})

                # Kategorisiere based on tags
                if _matches_category_tags(tags, "supermarket"):
                    results["supermarket"].append(poi)
                if _matches_category_tags(tags, "doctor"):
                    results["doctor"].append(poi)
                if _matches_category_tags(tags, "public_transport"):
                    results["public_transport"].append(poi)
                if _matches_category_tags(tags, "park"):
                    results["park"].append(poi)

            # Log Statistiken
            logger.info(
                f"Results - supermarket: {len(results['supermarket'])}, doctor: {len(results['doctor'])}, "
                f"public_transport: {len(results['public_transport'])}, park: {len(results['park'])}"
            )

            # Cache für 1 Stunde
            r.setex(cache_key, 3600, json.dumps(results))

            return results

    except asyncio.TimeoutError:
        logger.warning("Overpass query timeout after 30s")
        return {
            "supermarket": [],
            "doctor": [],
            "public_transport": [],
            "park": [],
        }
    except Exception as e:
        logger.error(f"Overpass error: {e}", exc_info=True)
        return {
            "supermarket": [],
            "doctor": [],
            "public_transport": [],
            "park": [],
        }


async def get_nearby_pois(lat: float, lon: float, category: str, radius=1500):
    """
    Wrapper für die neue kombinierte Query
    Holt ALLE POIs auf einmal, gibt dann nur die für diese Kategorie zurück
    """
    # Hol ALLE POIs auf einmal
    all_results = await get_all_pois_single_query(lat, lon, radius)

    # Gib nur die für diese Kategorie zurück
    return all_results.get(category, [])


def calculate_score(
    dist_meters: float, ideal_dist: float = 300, decay: float = 1000
) -> float:
    """
    Berechnet Score (0-100) basierend auf Distanz.
    Nutzt Exponential Decay (Zerfall): Score sinkt, je weiter weg.
    """
    if dist_meters <= ideal_dist:
        return 100.0
    # Formel: 100 * e^(-(dist - ideal) / decay)
    return 100.0 * math.exp(-(dist_meters - ideal_dist) / decay)


def haversine_distance(lat1, lon1, lat2, lon2):
    """Berechnet Luftlinie in Metern (für MVP oft ausreichend schnell)"""
    R = 6371000  # Erdradius in Metern
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
