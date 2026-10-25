from math import asin, cos, radians, sin, sqrt
from typing import Iterable

EARTH_RADIUS_KM = 6371.0
ROAD_FACTOR = 1.4
AVERAGE_SPEED_KMH = 35.0
DETOUR_CLEARANCE_KM = 0.15


class EstimateRoutingClient:
    def __init__(
        self,
        road_factor: float = ROAD_FACTOR,
        average_speed_kmh: float = AVERAGE_SPEED_KMH,
    ):
        self.road_factor = road_factor
        self.average_speed_kmh = average_speed_kmh

    def compute_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        blockages: Iterable[dict],
    ) -> dict:
        blockages = list(blockages)
        origin_xy, destination_xy, reference_latitude = _project_pair(origin, destination)
        direct_blockages = []
        for blockage in blockages:
            point_xy = _project(blockage['latitude'], blockage['longitude'], reference_latitude)
            distance, along = _point_segment_distance(point_xy, origin_xy, destination_xy)
            radius_km = float(blockage.get('radius_km', 0.25))
            if distance <= radius_km:
                direct_blockages.append(
                    {
                        'id': int(blockage['id']),
                        'radius_km': radius_km,
                        'along': along,
                        'projected_xy': _segment_point(origin_xy, destination_xy, along),
                        'point_xy': point_xy,
                    }
                )
        direct_blockages.sort(key=lambda item: item['along'])
        endpoints = [origin, destination]
        selected_path = endpoints
        avoids_blockages = not direct_blockages

        if direct_blockages:
            candidates = []
            dx = destination_xy[0] - origin_xy[0]
            dy = destination_xy[1] - origin_xy[1]
            length = sqrt(dx * dx + dy * dy)
            if length > 0:
                perpendicular = (-dy / length, dx / length)
                for side in (1, -1):
                    waypoints = []
                    for blockage in direct_blockages:
                        offset = blockage['radius_km'] + DETOUR_CLEARANCE_KM
                        projected_x, projected_y = blockage['projected_xy']
                        waypoint_xy = (
                            projected_x + side * perpendicular[0] * offset,
                            projected_y + side * perpendicular[1] * offset,
                        )
                        waypoints.append(_unproject(waypoint_xy, reference_latitude))
                    candidate = [origin, *waypoints, destination]
                    if _path_clears_blockages(candidate, blockages, reference_latitude):
                        candidates.append(candidate)
            if candidates:
                selected_path = min(candidates, key=_path_distance_km)
                avoids_blockages = True

        distance_km = _path_distance_km(selected_path) * self.road_factor
        straight_line_distance_km = _haversine_km(origin, destination)
        geometry = [
            {'latitude': latitude, 'longitude': longitude}
            for latitude, longitude in selected_path
        ]
        return {
            'geometry': geometry,
            'distance_km': distance_km,
            'straight_line_distance_km': straight_line_distance_km,
            'duration_min': distance_km / self.average_speed_kmh * 60,
            'blocked_segments_considered': [item['id'] for item in direct_blockages],
            'avoids_blockages': avoids_blockages,
            'source': 'estimate',
        }


def _haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    first_latitude, first_longitude = map(radians, first)
    second_latitude, second_longitude = map(radians, second)
    delta_latitude = second_latitude - first_latitude
    delta_longitude = second_longitude - first_longitude
    value = (
        sin(delta_latitude / 2) ** 2
        + cos(first_latitude) * cos(second_latitude) * sin(delta_longitude / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * asin(sqrt(value))


def _project_pair(first: tuple[float, float], second: tuple[float, float]):
    reference_latitude = (first[0] + second[0]) / 2
    return (
        _project(*first, reference_latitude),
        _project(*second, reference_latitude),
        reference_latitude,
    )


def _project(latitude: float, longitude: float, reference_latitude: float) -> tuple[float, float]:
    x = EARTH_RADIUS_KM * radians(longitude) * cos(radians(reference_latitude))
    y = EARTH_RADIUS_KM * radians(latitude)
    return x, y


def _unproject(point: tuple[float, float], reference_latitude: float) -> tuple[float, float]:
    x, y = point
    latitude = y / EARTH_RADIUS_KM * 180 / 3.141592653589793
    longitude = x / (EARTH_RADIUS_KM * cos(radians(reference_latitude))) * 180 / 3.141592653589793
    return latitude, longitude


def _segment_point(
    start: tuple[float, float],
    end: tuple[float, float],
    fraction: float,
) -> tuple[float, float]:
    return (
        start[0] + (end[0] - start[0]) * fraction,
        start[1] + (end[1] - start[1]) * fraction,
    )


def _point_segment_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return sqrt((point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2), 0.0
    along = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
    closest = _segment_point(start, end, along)
    distance = sqrt((point[0] - closest[0]) ** 2 + (point[1] - closest[1]) ** 2)
    return distance, along


def _path_distance_km(path: list[tuple[float, float]]) -> float:
    return sum(_haversine_km(start, end) for start, end in zip(path, path[1:]))


def _path_clears_blockages(
    path: list[tuple[float, float]],
    blockages: Iterable[dict],
    reference_latitude: float,
) -> bool:
    points = [
        (
            _project(item['latitude'], item['longitude'], reference_latitude),
            float(item.get('radius_km', 0.25)),
        )
        for item in blockages
    ]
    for start, end in zip(path, path[1:]):
        start_xy = _project(*start, reference_latitude)
        end_xy = _project(*end, reference_latitude)
        if any(_point_segment_distance(point, start_xy, end_xy)[0] <= radius for point, radius in points):
            return False
    return True
