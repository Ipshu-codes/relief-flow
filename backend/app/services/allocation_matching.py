from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..geo.routing import EstimateRoutingClient
from ..models import Location, Need, Organization, Resource, ResourceMovement, ResourceStock, RoadBlockage


RESOURCE_TYPE_BY_CATEGORY = {
    'water': {'water'},
    'food': {'food'},
    'medical': {'medicine'},
    'shelter': {'shelter', 'equipment'},
    'rescue': {'equipment'},
    'technical_repair': {'equipment'},
    'other': set(),
}
UNIT_ALIASES = {
    'liters': 'litre',
    'liter': 'litre',
    'litres': 'litre',
    'l': 'litre',
    'kilograms': 'kilogram',
    'kilograms.': 'kilogram',
    'kg': 'kilogram',
    'packs': 'pack',
    'kits': 'kit',
    'units': 'unit',
}


def normalize_unit(value: str) -> str:
    normalized = value.strip().casefold()
    return UNIT_ALIASES.get(normalized, normalized)


def build_allocation_options(db: Session, need: Need) -> dict:
    if need.quantity_requested <= 0:
        return {'remaining_quantity': 0.0, 'options': []}
    need_location = db.get(Location, need.location_id)
    if (
        need_location is None
        or need_location.latitude is None
        or need_location.longitude is None
    ):
        return {'remaining_quantity': 0.0, 'options': [], 'reason': 'need_location_missing_coordinates'}

    movements = db.scalars(
        select(ResourceMovement).where(
            ResourceMovement.need_id == need.id,
            ResourceMovement.status != 'cancelled',
        )
    ).all()
    outstanding_allocations = sum(
        max(0.0, movement.quantity - movement.quantity_confirmed)
        for movement in movements
    )
    remaining = max(
        0.0,
        need.quantity_requested - need.quantity_fulfilled - outstanding_allocations,
    )
    if remaining <= 0:
        return {'remaining_quantity': 0.0, 'options': []}

    expected_types = RESOURCE_TYPE_BY_CATEGORY.get(need.category, set())
    if not expected_types:
        return {'remaining_quantity': remaining, 'options': []}
    expected_unit = normalize_unit(need.unit)
    blockages = db.scalars(
        select(RoadBlockage).where(
            RoadBlockage.verified.is_(True),
            RoadBlockage.cleared_at.is_(None),
            RoadBlockage.expires_at > datetime.now(timezone.utc),
        )
    ).all()
    routing = EstimateRoutingClient()
    options = []
    stock_rows = db.execute(
        select(ResourceStock, Resource, Organization)
        .join(Resource, Resource.id == ResourceStock.resource_id)
        .join(Organization, Organization.id == ResourceStock.organization_id)
        .where(
            Resource.resource_type.in_(expected_types),
            ResourceStock.quantity_available > 0,
        )
        .order_by(ResourceStock.id)
    ).all()
    for stock, resource, organization in stock_rows:
        if normalize_unit(resource.unit) != expected_unit:
            continue
        if stock.location_id is None:
            continue
        stock_location = db.get(Location, stock.location_id)
        if (
            stock_location is None
            or stock_location.latitude is None
            or stock_location.longitude is None
        ):
            continue
        route = routing.compute_route(
            origin=(stock_location.latitude, stock_location.longitude),
            destination=(need_location.latitude, need_location.longitude),
            blockages=[
                {
                    'id': item.id,
                    'latitude': item.latitude,
                    'longitude': item.longitude,
                    'radius_km': item.radius_km,
                }
                for item in blockages
            ],
        )
        if not route['avoids_blockages']:
            continue
        quantity = min(remaining, stock.quantity_available)
        coverage = quantity / remaining
        route_factor = max(0.0, 1 - route['duration_min'] / 120)
        options.append({
            'stock_id': stock.id,
            'resource_id': resource.id,
            'resource_type': resource.resource_type,
            'unit': resource.unit,
            'organization_id': organization.id,
            'organization_name': organization.name,
            'location_id': stock.location_id,
            'quantity_available': stock.quantity_available,
            'quantity': quantity,
            'route': route,
            'score': round(coverage * 80 + route_factor * 20, 2),
        })
    options.sort(
        key=lambda item: (-item['score'], item['route']['duration_min'], item['stock_id'])
    )
    return {'remaining_quantity': remaining, 'options': options}