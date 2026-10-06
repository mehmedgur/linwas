"""Sürücü algılama testleri."""

from linwas.backend.drivers import DriverCandidate, DriverCategory, list_drivers


def test_list_drivers_returns_list():
    result = list_drivers()
    assert isinstance(result, list)
    for d in result:
        assert isinstance(d, DriverCandidate)
        assert d.package
        assert isinstance(d.recommended, bool)
        assert isinstance(d.installed, bool)
        assert d.category in list(DriverCategory)


def test_recommended_comes_first():
    """Önerilen sürücüler listede önce olmalı (varsa)."""
    drivers = list_drivers()
    if len(drivers) >= 2:
        recommended = [i for i, d in enumerate(drivers) if d.recommended]
        not_recommended = [i for i, d in enumerate(drivers) if not d.recommended]
        if recommended and not_recommended:
            assert max(recommended) < min(not_recommended)
