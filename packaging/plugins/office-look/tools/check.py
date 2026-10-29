# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""linwas-office-look paket ağacını kurulu LibreOffice'e göre denetler (derlemede çalışır).

Kullanım: python3 check.py <paket ağacı kökü>

Yakalanan hatalar LibreOffice 7.4 denemelerinde görülen sessiz arızalara karşılık gelir:
- Modes girdisinde zorunlu alan eksikse LibreOffice girdiyi siler.
- Var olan set düğümüne oor:op="replace" uygulanırsa düğümün diğer alanları silinir.
- <dependency> dosyası kurulu değilse LibreOffice .xcd dosyasını hiç yüklemez.
- ooSetupFactoryDefaultFilter ya da eklentideki biçimler tanımsız süzgeci gösteremez.
- Sade şeritte silinmiş öğeye işaret eden GtkSizeGroup girdisi LibreOffice'i çökertir.
"""

from __future__ import annotations

import ast
import glob
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cli  # noqa: E402
import ribbon  # noqa: E402

OOR = "{http://openoffice.org/2001/registry}"
MANIFEST = "{http://openoffice.org/2001/manifest}"
LO = "/usr/lib/libreoffice/share"
XCD_DIR = "usr/lib/libreoffice/share/registry"
EXTENSION_DIR = "usr/lib/libreoffice/share/extensions/linwas-office-look"

errors: list[str] = []


def name(node: ET.Element) -> str | None:
    return node.get(OOR + "name")


def child(node: ET.Element | None, tag: str, wanted: str) -> ET.Element | None:
    if node is None:
        return None
    return next((c for c in node if c.tag == tag and name(c) == wanted), None)


def components(root: ET.Element, wanted: str) -> list[ET.Element]:
    return [c for c in root.iter(OOR + "component-data") if name(c) == wanted]


def system_xcds(exclude: set[str]) -> dict[str, ET.Element]:
    """Kurulu LibreOffice'in xcd dosyaları; paketin kendi (önceden kurulmuş) dosyaları hariç."""
    return {
        os.path.basename(f)[:-4]: ET.parse(f).getroot()
        for f in sorted(glob.glob(f"{LO}/registry/*.xcd"))
        if os.path.basename(f) not in exclude
    }


def filter_names(system: dict[str, ET.Element]) -> set[str]:
    names: set[str] = set()
    for root in system.values():
        for comp in components(root, "Filter"):
            filters = child(comp, "node", "Filters")
            if filters is not None:
                names |= {name(c) for c in filters}
    return names


def required_mode_fields(system: dict[str, ET.Element]) -> set[str]:
    for schema in system["main"].iter(OOR + "component-schema"):
        if name(schema) == "ToolbarMode":
            for group in schema.iter("group"):
                if name(group) == "ModeEntry":
                    return {name(p) for p in group.findall("prop") if p.find("value") is None}
    raise SystemExit("check.py: ModeEntry template not found in main.xcd")


def existing_set_items(system: dict[str, ET.Element]) -> set[tuple]:
    """Sistem xcd'lerinde oor:op="replace" ile tanımlı set öğelerinin tam yolları."""
    paths: set[tuple] = set()

    def walk(node: ET.Element, path: tuple) -> None:
        for c in node:
            if c.tag == "node":
                p = (*path, name(c))
                if c.get(OOR + "op") == "replace":
                    paths.add(p)
                walk(c, p)

    for root in system.values():
        for comp in root.iter(OOR + "component-data"):
            walk(comp, (comp.get(OOR + "package"), name(comp)))
    return paths


def check_xcd(root: ET.Element, label: str, system: dict[str, ET.Element]) -> None:
    for dep in root.findall("dependency"):
        if dep.get("file") not in system:
            errors.append(f"{label}: dependency '{dep.get('file')}' not installed, file is ignored")

    existing = existing_set_items(system)

    def walk(node: ET.Element, path: tuple) -> None:
        for c in node:
            if c.tag == "node":
                p = (*path, name(c))
                if c.get(OOR + "op") == "replace" and p in existing:
                    errors.append(f"{label}: replace on existing node {'/'.join(p[2:])}")
                walk(c, p)

    for comp in root.iter(OOR + "component-data"):
        walk(comp, (comp.get(OOR + "package"), name(comp)))

    required = required_mode_fields(system)
    for comp in components(root, "ToolbarMode"):
        apps = child(comp, "node", "Applications")
        for app in list(apps) if apps is not None else []:
            modes = child(app, "node", "Modes")
            for mode in list(modes) if modes is not None else []:
                missing = required - {name(p) for p in mode.findall("prop")}
                if missing:
                    errors.append(
                        f"{label}: {name(app)}/Modes/{name(mode)} missing {sorted(missing)}"
                    )

    known = filter_names(system)
    for comp in components(root, "Setup"):
        factories = child(child(comp, "node", "Office"), "node", "Factories")
        for factory in list(factories) if factories is not None else []:
            p = child(factory, "prop", "ooSetupFactoryDefaultFilter")
            value = p.findtext("value") if p is not None else None
            if value and value not in known:
                errors.append(f"{label}: {name(factory)} uses unknown filter '{value}'")


def check_extension(tree: str, system: dict[str, ET.Element]) -> None:
    root = os.path.join(tree, EXTENSION_DIR)
    manifest = ET.parse(os.path.join(root, "META-INF/manifest.xml")).getroot()
    for entry in manifest:
        path = entry.get(MANIFEST + "full-path")
        if not os.path.exists(os.path.join(root, path)):
            errors.append(f"extension: manifest entry '{path}' missing")
        elif path.endswith(".xcu"):
            ET.parse(os.path.join(root, path))
    with open(os.path.join(root, "office_look.py"), encoding="utf-8") as f:
        module = ast.parse(f.read())
    formats = next(
        (
            ast.literal_eval(node.value)
            for node in module.body
            if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "FORMATS"
        ),
        None,
    )
    if formats is None:
        errors.append("extension: FORMATS not found")
        return
    known = filter_names(system)
    for kind, entries in formats.items():
        for entry in entries:
            if entry[2] not in known:
                errors.append(f"extension: {kind} uses unknown filter '{entry[2]}'")


def check_ribbons(system: dict[str, ET.Element]) -> None:
    """Sade şeridi bu makinedeki LibreOffice'ten üretir, üretilecek xcd'yi de denetler."""
    with tempfile.TemporaryDirectory() as tmp:
        apps = []
        for module, app in cli.APPS.items():
            source = os.path.join(cli.UI_DIR.format(module=module), "notebookbar.ui")
            target = os.path.join(tmp, f"{module}.ui")
            try:
                ribbon.build(module, source, target)
            except ribbon.RibbonError as e:
                errors.append(f"ribbon {module}: {e}")
                continue
            for problem in ribbon.dangling_size_groups(target):
                errors.append(f"ribbon {module}: dangling size group {problem}")
            apps.append(app)
        check_xcd(ET.fromstring(cli._ribbon_xcd(apps)), "ribbon xcd", system)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check.py <package tree>")
    tree = sys.argv[1]
    files = sorted(glob.glob(os.path.join(tree, XCD_DIR, "*.xcd")))
    system = system_xcds({os.path.basename(f) for f in files} | {os.path.basename(cli.RIBBON_XCD)})
    for f in files:
        check_xcd(ET.parse(f).getroot(), os.path.basename(f), system)
    check_extension(tree, system)
    check_ribbons(system)
    for e in errors:
        print(f"check.py: error: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
