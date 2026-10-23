"""Dokunmatik yüzey sağ tık yöntemi (backend/touchpad.py)."""

from pathlib import Path

from linwas.backend import touchpad

DEVICES = """I: Bus=0018 Vendor=06cb Product=ce7d Version=0100
N: Name="SYNA32CC:00 06CB:CE7D Touchpad"
P: Phys=i2c-SYNA32CC:00

I: Bus=0011 Vendor=0001 Product=0001 Version=ab83
N: Name="AT Translated Set 2 keyboard"
"""


def test_has_touchpad(tmp_path: Path):
    f = tmp_path / "devices"
    f.write_text(DEVICES)
    assert touchpad.has_touchpad(f)
    f.write_text(DEVICES.split("\n\n")[1])
    assert not touchpad.has_touchpad(f)
    assert not touchpad.has_touchpad(tmp_path / "missing")


def test_set_and_reset(monkeypatch):
    calls = []
    monkeypatch.setattr(touchpad.workgroups, "_gs", lambda *a: calls.append(a) or (0, ""))
    assert touchpad.set_corner_right_click(True)
    assert touchpad.set_corner_right_click(False)
    assert calls == [
        ("set", touchpad.SCHEMA, "click-method", "areas"),
        ("reset", touchpad.SCHEMA, "click-method"),
    ]


def test_should_offer_only_when_needed(monkeypatch):
    monkeypatch.setattr(touchpad, "supported", lambda: True)
    monkeypatch.setattr(touchpad, "has_touchpad", lambda: True)
    monkeypatch.setattr(touchpad, "click_method", lambda: "fingers")
    assert touchpad.should_offer()
    monkeypatch.setattr(touchpad, "click_method", lambda: "areas")
    assert not touchpad.should_offer()
