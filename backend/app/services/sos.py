from math import asin, cos, radians, sin, sqrt

SOS_CATEGORIES = {'FOOD', 'MEDICINE', 'TRAPPED', 'RESCUE', 'OTHER'}
EARTH_RADIUS_KM = 6371.0


def parse_compact_sos(text: str) -> dict | None:
    if not text.startswith('SOS|'):
        return None
    parts = text.split('|', 3)
    if len(parts) != 4:
        raise ValueError('Compact SOS must be SOS|CATEGORY|LAT,LON|MESSAGE')
    _, raw_category, raw_coordinates, message = parts
    category = raw_category.strip().upper()
    if category not in SOS_CATEGORIES:
        raise ValueError('Unsupported compact SOS category')
    try:
        raw_latitude, raw_longitude = raw_coordinates.split(',', 1)
        latitude = float(raw_latitude.strip())
        longitude = float(raw_longitude.strip())
    except (ValueError, TypeError) as exc:
        raise ValueError('Compact SOS coordinates must be numeric LAT,LON') from exc
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Compact SOS coordinates are outside valid ranges')
    return {
        'category': category,
        'latitude': latitude,
        'longitude': longitude,
        'message': message.strip() or 'SOS assistance requested',
    }


def has_valid_location(latitude: float | None, longitude: float | None) -> bool:
    return (
        latitude is not None
        and longitude is not None
        and latitude != 0
        and longitude != 0
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    first_lat, first_lon = map(radians, first)
    second_lat, second_lon = map(radians, second)
    delta_lat = second_lat - first_lat
    delta_lon = second_lon - first_lon
    value = sin(delta_lat / 2) ** 2 + cos(first_lat) * cos(second_lat) * sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(value))
