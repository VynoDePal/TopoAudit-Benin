from app.surface_parser import parse_surface_to_m2


def test_parse_surface_to_m2_acceptance_examples():
    assert parse_surface_to_m2("05a 49ca") == 549
    assert parse_surface_to_m2("29ha 95a 38ca") == 299538


def test_parse_surface_to_m2_spec_examples():
    assert parse_surface_to_m2("2a08ca") == 208
    assert parse_surface_to_m2("43a 36ca") == 4336
    assert parse_surface_to_m2("5 a 49 ca") == 549


def test_parse_surface_to_m2_returns_none_for_missing_surface():
    assert parse_surface_to_m2("") is None
    assert parse_surface_to_m2("surface inconnue") is None
