from pydantic import BaseModel
from typing import List, Dict, Optional


class AddressRequest(BaseModel):
    address: str
    weights: Optional[Dict[str, float]] = None
    radius: Optional[int] = None
    workplace_address: Optional[str] = None
    workplace_weight: Optional[float] = None


class POI(BaseModel):
    lat: float
    lon: float
    distance: float


class ScoreComponent(BaseModel):
    category: str  # z.B. "Supermarkt"
    score: float  # 0-100
    nearest_po_dist: float  # Meter oder Minuten
    count_nearby: int
    nearest_poi: Optional[POI] = None
    nearby_pois: Optional[List[POI]] = None


class ScoreResponse(BaseModel):
    total_score: float
    address_display: str
    lat: float
    lon: float
    details: List[ScoreComponent]
    weights_applied: Dict[str, float]
    workplace_address: Optional[str] = None
    workplace_lat: Optional[float] = None
    workplace_lon: Optional[float] = None
