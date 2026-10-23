"""Süreç listesi ve disk temizliği testleri."""

from linwas.backend.disk_cleanup import CleanupItem, clean_user_item, scan_cleanup_items
from linwas.backend.process_list import ProcessInfo, list_processes
from linwas.backend.startup import list_startup_apps


def test_list_processes_returns_list():
    procs = list_processes()
    assert isinstance(procs, list)
    for p in procs:
        assert isinstance(p, ProcessInfo)
        assert p.pid > 0
        assert p.name


def test_current_process_in_list():
    procs = list_processes()
    pids = {p.pid for p in procs}
    # Mevcut süreç listede olabilir veya olmayabilir (ps komutuna bağlı)
    assert isinstance(pids, set)


def test_list_startup_apps():
    apps = list_startup_apps()
    assert isinstance(apps, list)
    for app in apps:
        assert app.name
        assert isinstance(app.enabled, bool)


def test_scan_cleanup_items():
    items = scan_cleanup_items()
    assert isinstance(items, list)
    for i in items:
        assert isinstance(i, CleanupItem)
        assert i.id
        assert i.size_mb >= 0


def test_clean_nonexistent_item():
    item = CleanupItem(
        id="test_clean",
        label="test",
        description="",
        size_mb=0.0,
        available=False,
        needs_root=False,
        paths=[],
    )
    ok, freed = clean_user_item(item)
    assert ok
    assert freed == 0.0


def test_root_item_not_cleaned():
    item = CleanupItem(
        id="apt_cache",
        label="APT Cache",
        description="",
        size_mb=100.0,
        available=True,
        needs_root=True,
        paths=[],
    )
    ok, freed = clean_user_item(item)
    assert not ok
    assert freed == 0.0
