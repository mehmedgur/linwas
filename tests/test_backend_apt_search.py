"""APT arama testleri."""

from linwas.backend.apt_search import AptPackage, search_apt


def test_search_returns_list():
    result = search_apt("vlc")
    assert isinstance(result, list)


def test_search_results_are_apt_packages():
    result = search_apt("vim")
    for pkg in result:
        assert isinstance(pkg, AptPackage)
        assert pkg.name
        assert isinstance(pkg.installed, bool)


def test_empty_query_returns_empty():
    assert search_apt("") == []
    assert search_apt("  ") == []


def test_nonsense_returns_empty_or_list():
    result = search_apt("xyzabcnotexist123456")
    assert isinstance(result, list)
