"""Kurulu LibreOffice'in notebookbar.ui dosyasından sade şeridi üretir.

"Writer Sade Arayüz Taslağı" tasarımındaki sekme ve gruplar:
- REMOVE'daki sekmeler (sayfa + etiket) silinir.
- RENAME'deki sekmelerin etiketi Türkçe sade adla değiştirilir.
- GROUPS'taki sekmelerin içeriği adlı gruplarla yeniden kurulur. Her grup büyük
  düğmeler, küçük düğme satırları ve altında grup adından oluşur. Düğme öğeleri
  kaynak dosyadan kopyalanır (açılır menülü olanlar öyle kalır); kaynakta olmayan
  komut için düz düğme yazılır.
- Dosya sekmesinin başına "Dosya menüsünü aç" öğesi eklenir; eklentinin denetçisi
  sekme açılınca Dosya menüsünü gösterir.
- Bağlamsal sekmeler (Tablo, Resim, Çizim...) olduğu gibi kalır.

LibreOffice 7.4'te öğrenilenler (değiştirirken dikkat):
- Silinen öğelere işaret eden GtkSizeGroup girdileri kalırsa LibreOffice açılışta çöker.
- Dosya sekmesinin içeriği boşaltılırsa sekmeye tıklanınca şeridin tamamı kaybolur;
  bu yüzden o sekmeye yalnız öğe eklenir.
- Düğmeler yalnız GtkToolButton/GtkMenuToolButton/GtkToggleToolButton öğelerinden
  kopyalanır; menü öğeleri de action_name taşır.

Bu modül hem derlemede (denetim) hem paket kurulumunda (postinst) çalışır; yalnız standart
kütüphane kullanır.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET

FILE_TAB_COMMAND = ".uno:LinwasFileTab"
MORE_TOOLS_COMMAND = ".uno:LinwasMoreTools"
# "Daha fazla araç" düğmesi doğrudan LibreOffice'in tam şeride geçme komutunu çalıştırır.
# Eklentinin kendi komutu Calc'ta çalışmıyordu: şerit düğmenin hedefini eklentinin yakalayıcısı
# kurulmadan önce alıyor ve yenilemiyor (18 Ekim 2026, Xephyr'de tıklayarak doğrulandı).
FULL_RIBBON_COMMAND = ".uno:ToolbarMode?Mode:string=notebookbar.ui"
MORE_TOOLS_LABEL = "Daha fazla araç"
MORE_TOOLS_ICON = "cmd/lc_toolbarmode.png"
OUTPUT_NAME = "linwas_simple.ui"
MODULES = ("swriter", "scalc", "simpress")

REMOVE = {
    "swriter": ["References", "Extension", "Tools"],
    "scalc": ["Layout", "Review", "Extension", "Dev"],
    "simpress": ["Review", "Extension", "Dev"],
}
RENAME = {
    "swriter": {
        "Home": "Yaz",
        "Insert": "Ekle",
        "Layout": "Sayfa",
        "Review": "Gözden geçir",
        "View": "Görünüm",
    },
    "scalc": {"Home": "Tablo", "Insert": "Ekle", "Data": "Veri", "View": "Görünüm"},
    "simpress": {
        "Home": "Giriş",
        "Insert": "Ekle",
        "Layout": "Slayt",
        "SlideShow": "Gösteri",
        "View": "Görünüm",
    },
}
FILE_GROUPS = [("", [FILE_TAB_COMMAND], [])]
# İçeriği değiştirilmeyip başına grup eklenen sekmeler.
PREPEND = {"File"}
# Sekme -> [(grup adı, büyük düğmeler, [küçük düğme satırı, ...])]
GROUPS = {
    "swriter": {
        "File": FILE_GROUPS,
        # ONLYOFFICE / Word düzeni (18 Ekim 2026): grup adı yok, gruplar dikey çizgiyle ayrılır,
        # her grup iki sıra yalnız simgeli küçük düğme; stil galerisi şeridin yüksekliğini kullanır.
        "Home": [
            ("", [], [[".uno:Copy", ".uno:Cut"], [".uno:Paste", ".uno:FormatPaintbrush"]]),
            (
                "",
                [],
                [
                    [
                        ".uno:CharFontName",
                        ".uno:FontHeight",
                        ".uno:Grow",
                        ".uno:Shrink",
                        ".uno:ChangeCaseRotateCase",
                    ],
                    [
                        ".uno:Bold",
                        ".uno:Italic",
                        ".uno:Underline",
                        ".uno:Strikeout",
                        ".uno:SuperScript",
                        ".uno:SubScript",
                        ".uno:BackColor",
                        ".uno:Color",
                        ".uno:ResetAttributes",
                    ],
                ],
            ),
            (
                "",
                [],
                [
                    [
                        ".uno:DefaultBullet",
                        ".uno:DefaultNumbering",
                        ".uno:SetOutline",
                        ".uno:DecrementIndent",
                        ".uno:IncrementIndent",
                    ],
                    [".uno:LeftPara", ".uno:CenterPara", ".uno:RightPara", ".uno:JustifyPara"],
                ],
            ),
            (
                "",
                [],
                [
                    [".uno:LineSpacing", ".uno:ControlCodes"],
                    [".uno:BackgroundColor", ".uno:SetBorderStyle"],
                ],
            ),
            ("", [".uno:StylesPreview"], []),
            ("", [], [[".uno:SearchDialog"], [".uno:SelectAll"]]),
            ("", [MORE_TOOLS_COMMAND], []),
        ],
        "Insert": [
            ("Sayfa", [".uno:InsertPagebreak"], []),
            ("Tablo", [".uno:InsertTable"], []),
            ("Resim ve çizim", [".uno:InsertGraphic", ".uno:BasicShapes"], []),
            ("Bağlantı", [".uno:HyperlinkDialog"], [[".uno:InsertBookmark"]]),
            # Üç satır şeride sığmıyor, grup adı görünmez oluyor; iki satır.
            (
                "Üstbilgi ve altbilgi",
                [],
                [
                    [".uno:InsertPageHeader", ".uno:InsertPageFooter"],
                    [".uno:InsertPageNumberField"],
                ],
            ),
            ("Simge ve tarih", [".uno:CharmapControl"], [[".uno:InsertDateField"]]),
            ("", [MORE_TOOLS_COMMAND], []),
        ],
    },
    "scalc": {
        "File": FILE_GROUPS,
        # Writer "Yaz" ile aynı ONLYOFFICE / Excel düzeni (18 Ekim 2026)
        "Home": [
            ("", [], [[".uno:Copy", ".uno:Cut"], [".uno:Paste", ".uno:FormatPaintbrush"]]),
            (
                "",
                [],
                [
                    [".uno:CharFontName", ".uno:FontHeight", ".uno:Grow", ".uno:Shrink"],
                    [
                        ".uno:Bold",
                        ".uno:Italic",
                        ".uno:Underline",
                        ".uno:Strikeout",
                        ".uno:Color",
                        ".uno:BackgroundColor",
                        ".uno:SetBorderStyle",
                    ],
                ],
            ),
            (
                "",
                [],
                [
                    [".uno:AlignTop", ".uno:AlignVCenter", ".uno:AlignBottom", ".uno:WrapText"],
                    [
                        ".uno:AlignLeft",
                        ".uno:AlignHorizontalCenter",
                        ".uno:AlignRight",
                        ".uno:ToggleMergeCells",
                    ],
                ],
            ),
            (
                "",
                [],
                [
                    [".uno:NumberFormatType"],
                    [
                        ".uno:NumberFormatCurrency",
                        ".uno:NumberFormatPercent",
                        ".uno:NumberFormatDecimal",
                        ".uno:NumberFormatIncDecimals",
                        ".uno:NumberFormatDecDecimals",
                    ],
                ],
            ),
            ("", [], [[".uno:InsertCell", ".uno:DeleteCell"], [".uno:ResetAttributes"]]),
            (
                "",
                [],
                [
                    [
                        ".uno:AutoSum",
                        ".uno:FunctionDialog",
                        ".uno:SortAscending",
                        ".uno:SortDescending",
                    ],
                    [
                        ".uno:DataFilterAutoFilter",
                        ".uno:ConditionalFormatMenu",
                        ".uno:SearchDialog",
                    ],
                ],
            ),
            ("", [MORE_TOOLS_COMMAND], []),
        ],
    },
    "simpress": {"File": FILE_GROUPS},
}
# Kaynakta bulunmazsa açılır menülü düğme olarak yazılacak komutlar.
DROPDOWN = {
    ".uno:AutoSum",
    ".uno:InsertTable",
    ".uno:BasicShapes",
    ".uno:Color",
    ".uno:CharBackColor",
    ".uno:BackColor",
    ".uno:LineSpacing",
    ".uno:SetBorderStyle",
    ".uno:BackgroundColor",
    ".uno:ConditionalFormatMenu",
}
BUTTON_CLASSES = ("GtkToolButton", "GtkMenuToolButton", "GtkToggleToolButton")


class RibbonError(Exception):
    """Kaynak dosya beklenen yapıda değil (başka LibreOffice sürümü)."""


def _prop(parent: ET.Element, name: str, value: str) -> None:
    ET.SubElement(parent, "property", name=name).text = value


def _packing(child: ET.Element, **values: str) -> None:
    packing = ET.SubElement(child, "packing")
    for name, value in values.items():
        _prop(packing, name, value)


class _Builder:
    def __init__(self, root: ET.Element) -> None:
        self.counter = 0
        # Komut -> kaynaktaki ilk düğme öğesi (sınıfı ve özellikleriyle).
        self.buttons: dict[str, ET.Element] = {}
        for obj in root.iter("object"):
            if obj.get("class") not in BUTTON_CLASSES:
                continue
            command = next(
                (p.text for p in obj.findall("property") if p.get("name") == "action_name"), None
            )
            if command and command not in self.buttons:
                self.buttons[command] = obj

    def _id(self, prefix: str) -> str:
        self.counter += 1
        return f"Linwas-{prefix}-{self.counter}"

    def _object(
        self, parent: ET.Element, cls: str, prefix: str, **props: str
    ) -> tuple[ET.Element, ET.Element]:
        child = ET.SubElement(parent, "child")
        obj = ET.SubElement(child, "object", {"class": cls, "id": self._id(prefix)})
        _prop(obj, "visible", "True")
        for name, value in props.items():
            _prop(obj, name, value)
        return child, obj

    def _toolbox(
        self, parent: ET.Element, commands: list[str], large: bool, compact: bool = False
    ) -> None:
        # Büyük düğmeler: simge üstte, ad altta. Küçük satırlar: tek-iki düğmeyse ad yanında,
        # kalabalık biçim satırlarında yalnız simge (tasarımda K/T/A gibi). Adsız (sade) gruplarda
        # küçük düğmeler hep yalnız simge; adı ipucunda görünür (ONLYOFFICE / Word gibi).
        if large:
            style = "both"
        elif compact or len(commands) > 2:
            style = "icons"
        else:
            style = "both-horiz"
        child, box = self._object(
            parent,
            "sfxlo-NotebookbarToolBox",
            "Box",
            can_focus="True",
            valign="center",
            toolbar_style=style,
            show_arrow="False",
        )
        if large:
            _prop(box, "icon_size", "3")
        for command in commands:
            source = self.buttons.get(command)
            inner = ET.SubElement(box, "child")
            if command == MORE_TOOLS_COMMAND:
                item = ET.SubElement(
                    inner, "object", {"class": "GtkToolButton", "id": self._id("Button")}
                )
                _prop(item, "visible", "True")
                _prop(item, "action_name", FULL_RIBBON_COMMAND)
                _prop(item, "label", MORE_TOOLS_LABEL)
                _prop(item, "tooltip_text", "Bütün araçların olduğu tam şeride geç")
                _prop(item, "icon_name", MORE_TOOLS_ICON)
            elif source is not None:
                item = copy.deepcopy(source)
                item.set("id", self._id("Button"))
                inner.append(item)
            else:
                cls = "GtkMenuToolButton" if command in DROPDOWN else "GtkToolButton"
                item = ET.SubElement(inner, "object", {"class": cls, "id": self._id("Button")})
                _prop(item, "visible", "True")
                _prop(item, "action_name", command)
            _packing(inner, expand="False", homogeneous="False")
        _packing(child, expand="False", fill="True")

    def group(
        self,
        parent: ET.Element,
        title: str,
        large: list[str],
        rows: list[list[str]],
        separator: bool = False,
    ) -> None:
        # PriorityMergedHBox'ın her çocuğu VclOptionalBox olmalı.
        child, optional = self._object(
            parent, "VclOptionalBox", "Group", can_focus="False", valign="fill", vexpand="True"
        )
        if separator:
            # Gruplar arasında ince dikey çizgi (LibreOffice'in kendi şeridindeki gibi)
            sep_child, _ = self._object(
                optional,
                "GtkSeparator",
                "Separator",
                can_focus="False",
                margin_top="5",
                margin_bottom="5",
                orientation="vertical",
            )
            _packing(sep_child, expand="False", fill="True", padding="5")
        _, column = self._object(
            optional, "GtkBox", "Column", can_focus="False", orientation="vertical", spacing="2"
        )
        top_child, top = self._object(
            column, "GtkBox", "Row", can_focus="False", spacing="6", vexpand="True"
        )
        if large:
            self._toolbox(top, large, large=True)
        if rows:
            stack_child, stack = self._object(
                top,
                "GtkBox",
                "Stack",
                can_focus="False",
                valign="center",
                orientation="vertical",
                spacing="2",
            )
            for row in rows:
                self._toolbox(stack, row, large=False, compact=not title)
            _packing(stack_child, expand="False", fill="True")
        _packing(top_child, expand="True", fill="True")
        if title:
            label_child, _ = self._object(
                column, "GtkLabel", "Label", can_focus="False", label=title
            )
            _packing(label_child, expand="False", fill="True")
        _packing(child, expand="False", fill="True")


def build(module: str, source: str, target: str) -> None:
    """Sade şeridi üretir; yapı beklenenden farklıysa RibbonError verir."""
    if module not in REMOVE:
        raise RibbonError(f"unknown module {module}")
    try:
        tree = ET.parse(source)
    except (OSError, ET.ParseError) as e:
        raise RibbonError(f"{source}: {e}") from e
    root = tree.getroot()
    builder = _Builder(root)

    tabs = next((o for o in root.iter("object") if o.get("id") == "ContextContainer"), None)
    if tabs is None:
        raise RibbonError("ContextContainer not found")
    children = tabs.findall("child")

    def tab(name: str) -> tuple[ET.Element, ET.Element]:
        # Sekmeler etiket kimliğiyle bulunur ("HomeLabel");
        # sayfa kimlikleri uygulamaya göre değişiyor.
        for i, c in enumerate(children):
            if c.get("type") == "tab" and c.find("object").get("id") == f"{name}Label" and i > 0:
                return children[i - 1], c
        raise RibbonError(f"tab '{name}Label' not found")

    for name in REMOVE[module]:
        for c in tab(name):
            tabs.remove(c)

    for name, new in RENAME[module].items():
        _, label = tab(name)
        prop = next(p for p in label.find("object").findall("property") if p.get("name") == "label")
        prop.attrib.clear()
        prop.set("name", "label")
        prop.text = new

    for name, groups in GROUPS[module].items():
        page, _ = tab(name)
        merged = next(
            (o for o in page.iter("object") if o.get("class") == "sfxlo-PriorityMergedHBox"), None
        )
        if merged is None:
            raise RibbonError(f"'{name}' tab has no sfxlo-PriorityMergedHBox")
        if name in PREPEND:
            temp = ET.Element("temp")
            for title, large, rows in groups:
                builder.group(temp, title, large, rows)
            first = next(i for i, c in enumerate(merged) if c.tag == "child")
            for j, c in enumerate(temp.findall("child")):
                merged.insert(first + j, c)
            continue
        for c in merged.findall("child"):
            merged.remove(c)
        for i, (title, large, rows) in enumerate(groups):
            builder.group(merged, title, large, rows, separator=i > 0 and not title)

    remove_dangling_size_groups(root)
    tree.write(target, encoding="UTF-8", xml_declaration=True)


def remove_dangling_size_groups(root: ET.Element) -> None:
    """Silinmiş öğelere işaret eden GtkSizeGroup girdilerini temizler."""
    ids = {o.get("id") for o in root.iter("object")}
    for group in root.iter("object"):
        if group.get("class") == "GtkSizeGroup":
            for widgets in group.findall("widgets"):
                for w in widgets.findall("widget"):
                    if w.get("name") not in ids:
                        widgets.remove(w)


def dangling_size_groups(path: str) -> list[str]:
    """Denetim: silinmiş öğeye işaret eden boyut grubu girdileri (boş liste = sağlam)."""
    root = ET.parse(path).getroot()
    ids = {o.get("id") for o in root.iter("object")}
    return [
        f"{group.get('id')} -> {w.get('name')}"
        for group in root.iter("object")
        if group.get("class") == "GtkSizeGroup"
        for w in group.iter("widget")
        if w.get("name") not in ids
    ]
