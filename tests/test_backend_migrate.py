"""Windows'tan taşıma backend testleri."""

from pathlib import Path

import pytest

from linwas.backend.migrate import (
    ImportItem,
    WindowsUser,
    _import_folder,
    find_windows_users,
    import_item,
    scan_import_items,
)


def test_find_windows_users_returns_list():
    result = find_windows_users()
    assert isinstance(result, list)
    # Gerçek sistemde Windows yoksa boş liste beklenir
    for u in result:
        assert isinstance(u, WindowsUser)
        assert u.user_path.is_dir()


@pytest.fixture
def fake_windows(tmp_path: Path) -> WindowsUser:
    """Sahte Windows dizin yapısı oluşturur."""
    user_path = tmp_path / "Users" / "TestUser"
    (user_path / "Documents").mkdir(parents=True)
    (user_path / "Documents" / "test.txt").write_text("hello")
    (user_path / "Pictures").mkdir()
    return WindowsUser(
        drive=tmp_path,
        user_name="TestUser",
        user_path=user_path,
        bitlocker=False,
        hibernated=False,
    )


def test_scan_import_items(fake_windows: WindowsUser, tmp_path: Path) -> None:
    items = scan_import_items(fake_windows)
    assert isinstance(items, list)
    # Documents klasörü bulunmalı
    docs = next((i for i in items if "documents" in i.id.lower()), None)
    assert docs is not None
    assert docs.available


def test_import_folder(fake_windows: WindowsUser, tmp_path: Path) -> None:
    dest = tmp_path / "dest_documents"
    item = ImportItem(
        id="folder_documents",
        label="Documents",
        description="test",
        source=fake_windows.user_path / "Documents",
        dest=dest,
        available=True,
    )
    ok = _import_folder(item, cb=None)
    assert ok
    assert (dest / "test.txt").exists()


def test_import_item_unknown_id_returns_false() -> None:
    item = ImportItem(
        id="unknown_type",
        label="X",
        description="",
        source=None,
        dest=None,
        available=False,
    )
    assert not import_item(item)
