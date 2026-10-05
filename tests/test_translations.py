"""Çeviri dosyası ve dil seçimi testleri.

Her `tr("...")` / `translate("...", "...")` metninin Türkçe çeviri dosyasında karşılığı olmalı.
Böylece yeni bir metin eklenip çevirisi unutulursa test başarısız olur.
"""

import ast
import xml.etree.ElementTree as ET
from pathlib import Path

from linwas.translations import selected_language

ROOT = Path(__file__).resolve().parent.parent
TS_FILE = ROOT / "linwas" / "i18n" / "linwas_tr.ts"


def _ts_entries() -> dict[tuple[str, str], str]:
    tree = ET.parse(TS_FILE)
    entries: dict[tuple[str, str], str] = {}
    for context in tree.getroot().iter("context"):
        name = context.findtext("name", default="")
        for message in context.iter("message"):
            source = message.findtext("source", default="")
            translation = message.findtext("translation", default="")
            entries[(name, source)] = translation
    return entries


def _source_strings() -> set[tuple[str, str]]:
    """Kaynak koddaki çevrilecek metinleri bulur.

    - `tr("...")`: modülde tanımlı `tr` yardımcı fonksiyonu; bağlam (context) o modülün
      `QCoreApplication.translate("<Bağlam>", text)` çağrısındaki ilk argümandır.
    - `QCoreApplication.translate("<Bağlam>", "...")`: doğrudan çağrılar.
    """
    found: set[tuple[str, str]] = set()
    for path in (ROOT / "linwas").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_context = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "translate"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Constant)
            ):
                context = node.args[0].value
                if isinstance(node.args[1], ast.Constant):
                    found.add((context, node.args[1].value))
                else:
                    module_context = context
        if module_context is None:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                found.add((module_context, node.args[0].value))
    return found


def test_ts_file_is_valid_xml_and_turkish():
    root = ET.parse(TS_FILE).getroot()
    assert root.tag == "TS"
    assert root.get("language") == "tr_TR"


def test_every_source_string_has_turkish_translation():
    entries = _ts_entries()
    missing = sorted(key for key in _source_strings() if not entries.get(key))
    assert not missing, f"Çevirisi eksik metinler: {missing}"


def test_no_unused_translations():
    unused = sorted(set(_ts_entries()) - _source_strings())
    assert not unused, f"Kodda artık kullanılmayan çeviriler: {unused}"


def test_placeholders_preserved():
    for (_, source), translation in _ts_entries().items():
        for token in ("{version}",):
            assert (token in source) == (token in translation), source


def test_selected_language_defaults_to_turkish():
    assert selected_language({}) == "tr"
    assert selected_language({"LINWAS_LANG": "EN"}) == "en"
    assert selected_language({"LINWAS_LANG": "de"}) == "tr"
