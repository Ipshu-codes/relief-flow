from app.geo.routing import EstimateRoutingClient


def test_estimated_route_detours_around_verified_blockage():
    client = EstimateRoutingClient()
    result = client.compute_route(
        origin=(27.70, 85.30),
        destination=(27.70, 85.36),
        blockages=[{'id': 9, 'latitude': 27.70, 'longitude': 85.33, 'radius_km': 0.25}],
    )

    assert result['source'] == 'estimate'
    assert result['avoids_blockages'] is True
    assert result['blocked_segments_considered'] == [9]
    assert len(result['geometry']) == 3
    assert result['distance_km'] > result['straight_line_distance_km']


def test_estimated_route_ignores_blockage_outside_path():
    result = EstimateRoutingClient().compute_route(
        origin=(27.70, 85.30),
        destination=(27.70, 85.36),
        blockages=[{'id': 10, 'latitude': 27.80, 'longitude': 85.33, 'radius_km': 0.25}],
    )

    assert result['avoids_blockages'] is True
    assert result['blocked_segments_considered'] == []
    assert len(result['geometry']) == 2
