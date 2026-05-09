from dataclasses import dataclass


@dataclass
class Sample:
    timestamp: float
    speed_kmh: float
    distance_km: float
    incline_percent: float