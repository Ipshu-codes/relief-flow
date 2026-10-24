import pytest

from app.services.sos import has_valid_location, parse_compact_sos


def test_compact_sos_parses_category_coordinates_and_message():
    parsed = parse_compact_sos('SOS|TRAPPED|27.7172,85.3240|water rising')
    assert parsed == {
        'category': 'TRAPPED',
        'latitude': 27.7172,
        'longitude': 85.324,
        'message': 'water rising',
    }


def test_compact_sos_rejects_invalid_category_or_coordinate():
    with pytest.raises(ValueError, match='category'):
        parse_compact_sos('SOS|FIRE|27.7,85.3|help')
    with pytest.raises(ValueError, match='outside valid'):
        parse_compact_sos('SOS|RESCUE|91,85.3|help')


def test_location_honesty_rejects_zero_or_partial_coordinates():
    assert has_valid_location(None, 85.3) is False
    assert has_valid_location(0, 85.3) is False
    assert has_valid_location(27.7, 0) is False
    assert has_valid_location(27.7, 85.3) is True
