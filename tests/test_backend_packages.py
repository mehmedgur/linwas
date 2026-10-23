"""APT paket sorgulama testleri."""

from linwas.backend.packages import _APT_LINE, UpgradablePackage, list_upgradable


def _parse(line: str) -> UpgradablePackage | None:
    m = _APT_LINE.match(line.strip())
    if not m:
        return None
    name, source, available, installed = m.groups()
    return UpgradablePackage(
        name=name,
        installed_version=installed,
        available_version=available,
        is_security="-security" in source,
        source=source,
    )


def test_parse_normal_line():
    line = (
        "vim/jammy-updates 2:8.2.3995-1ubuntu2.12 amd64 [upgradable from: 2:8.2.3995-1ubuntu2.11]"
    )
    pkg = _parse(line)
    assert pkg is not None
    assert pkg.name == "vim"
    assert pkg.available_version == "2:8.2.3995-1ubuntu2.12"
    assert pkg.installed_version == "2:8.2.3995-1ubuntu2.11"
    assert not pkg.is_security
    assert pkg.source == "jammy-updates"


def test_parse_security_line():
    line = "openssl/jammy-security 3.0.2-0ubuntu1.12 amd64 [upgradable from: 3.0.2-0ubuntu1.11]"
    pkg = _parse(line)
    assert pkg is not None
    assert pkg.is_security
    assert pkg.source == "jammy-security"


def test_parse_header_line_returns_none():
    assert _parse("Listing... Done") is None


def test_parse_empty_returns_none():
    assert _parse("") is None


def test_list_upgradable_returns_list():
    # Gerçek APT çağrısı yapar; hata durumunda boş liste beklenir
    result = list_upgradable()
    assert isinstance(result, list)
    for pkg in result:
        assert isinstance(pkg, UpgradablePackage)
        assert pkg.name
