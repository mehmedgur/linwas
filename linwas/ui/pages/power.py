"""Güç ve pil sayfası (masaüstü bilgisayarda "Güç"; pil bölümleri gizli).

Üstte güç planı seçimi ve sık ayarlar, altta Windows'taki gibi "Gelişmiş güç seçenekleri"
ağaç listesi (her satırda Prizde / Pilde). Plan şifresiz değiştirilir (kurulu pakette); plan
ayarları root helper'ın `power.save_config` işlemiyle kaydedilir (kararlar.md › Güç ve pil).
"""

from __future__ import annotations

import copy
import shutil
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QPointF,
    QProcess,
    QRectF,
    Qt,
    QThread,
    QTime,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from linwas.backend import hibernate_setup, power, power_support
from linwas.core import hibernate, power_agent, power_apply, powerplan
from linwas.core.powerplan import AUTO, SECTIONS, SETTINGS, SPECS, PowerConfig
from linwas.core.tasks import Task, TaskStep
from linwas.ui import icons
from linwas.ui.pages import power_texts as texts
from linwas.ui.pages.base import BasePage
from linwas.ui.pages.power_report_view import PowerReportCard
from linwas.ui.widgets.card import Card
from linwas.ui.widgets.option_tile import OptionTile

# Hazırda bekletme yoksa listeden çıkarılan değerler (seçiliyse yine gösterilir)
_HIBERNATE_VALUES = {"hibernate", "hybrid-sleep", "Hibernate", "HybridSleep"}
# "Sık kullanılan ayarlar" kartındaki ayarlar
_QUICK = ("screen_off", "sleep_after")
# Yerleşik planların simgeleri (özel planlar: "settings")
_PLAN_ICONS = {"power-saver": "leaf", "balanced": "scale", "performance": "bolt"}
_PLAN_COLUMNS = 3
# Gelişmiş ayar satırlarında seçim kutusu ve "Varsayılan" bağlantısının genişliği (sütunlar hizalı)
_ADV_COMBO_MIN = 215
_ADV_COMBO_MAX = 240
_ADV_RESET_WIDTH = 96
_ADV_TEXT_MIN = 280
_ON_TILE = "tile:#5e5ce6"


def tr(text: str) -> str:
    return QCoreApplication.translate("PowerPage", text)


def _duration_text(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        return tr("{h} h {m} min").format(h=hours, m=mins)
    if hours:
        return tr("{h} h").format(h=hours)
    return tr("{m} min").format(m=mins)


def _status_text(status: str) -> str:
    return {
        "Charging": tr("Charging"),
        "Discharging": tr("On battery"),
        "Full": tr("Fully charged"),
        "Not charging": tr("Plugged in, not charging"),
    }.get(status, tr("Unknown"))


def _level_role(percent: int) -> str:
    """Pil yüzdesine göre renk rolü (icons.color_for)."""
    if percent <= 15:
        return "danger"
    if percent <= 30:
        return "warning"
    return "success"


class BatteryGauge(QWidget):
    """Pil biçiminde doluluk göstergesi (macOS/Windows pil simgesi gibi, büyük)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._percent = 0
        self._charging = False
        self.setFixedSize(104, 52)

    def set_level(self, percent: int, charging: bool) -> None:
        self._percent = max(0, min(100, percent))
        self._charging = charging
        self.setAccessibleName(tr("Battery: {n}%").format(n=self._percent))
        self.update()

    def paintEvent(self, _event: object) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline = QColor(icons.color_for("secondary"))
        body = QRectF(1.5, 1.5, self.width() - 12, self.height() - 3)
        painter.setPen(QPen(outline, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(body, 10, 10)
        # Uç
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(outline)
        tip_h = body.height() * 0.38
        painter.drawRoundedRect(
            QRectF(body.right() + 2, body.center().y() - tip_h / 2, 6, tip_h), 2.5, 2.5
        )
        # Doluluk
        inner = body.adjusted(5, 5, -5, -5)
        width = inner.width() * self._percent / 100
        if width > 0:
            painter.setBrush(QColor(icons.color_for(_level_role(self._percent))))
            painter.drawRoundedRect(QRectF(inner.left(), inner.top(), width, inner.height()), 6, 6)
        if self._charging:
            # Şimşek (şarj oluyor)
            cx, cy, h = body.center().x(), body.center().y(), body.height() * 0.62
            path = [
                (cx + 2, cy - h / 2),
                (cx - 7, cy + 2),
                (cx - 1, cy + 2),
                (cx - 3, cy + h / 2),
                (cx + 7, cy - 3),
                (cx + 1, cy - 3),
            ]
            painter.setPen(QPen(QColor(icons.color_for("normal")), 1.2))
            painter.setBrush(QColor("#ffffff"))
            painter.drawPolygon(QPolygonF([QPointF(x, y) for x, y in path]))
        painter.end()


def _tile_frame(parent: QWidget) -> QFrame:
    """Kart içindeki yuvarlak köşeli kutu (seçim kartlarıyla aynı stil, tıklanmaz)."""
    frame = QFrame(parent)
    frame.setObjectName("OptionTile")
    return frame


def _title_label(text: str, parent: QWidget) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setObjectName("OptionTitle")
    lbl.setWordWrap(True)
    return lbl


def _note_label(text: str, parent: QWidget) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setObjectName("OptionNote")
    lbl.setWordWrap(True)
    return lbl


class _LoadWorker(QThread):
    done = Signal(object)

    def run(self) -> None:
        batteries = power.list_batteries()
        self.done.emit(
            {
                "batteries": batteries,
                "config": powerplan.load_config(),
                "support": power_support.detect(laptop=bool(batteries)),
                "status": power_apply.read_status(),
                "ppd": power.power_profiles()[1],
                "state": powerplan.read_power_state(),
                "service": power_apply.service_state(),
                "hibernate_setup": hibernate_setup.check(),
                "agent": power_support.agent_running(),
                "taken_over": power_support.taken_over(),
            }
        )


class _SwitchWorker(QThread):
    done = Signal(bool)

    def __init__(self, plan_id: str) -> None:
        super().__init__()
        self._plan_id = plan_id

    def run(self) -> None:
        ok = power.switch_plan(self._plan_id)
        if ok:
            power_agent.apply_now()
        self.done.emit(ok)


class _AgentWorker(QThread):
    """Kaydettikten sonra masaüstü ayarlarını hemen uygular (ajanın 20 sn'sini beklemeden)."""

    def run(self) -> None:
        power_agent.apply_now()


class PowerPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loaded = False
        self._workers: list[QThread] = []
        self._battery_name = ""
        self._laptop = power.is_laptop()
        self._saved: PowerConfig = powerplan.default_config()
        self._draft: PowerConfig = powerplan.default_config()
        self._support: power_support.PowerSupport | None = None
        self._edit_plan = powerplan.DEFAULT_PLAN
        self._filling = False
        self._pending_save = False
        self._service_ok = True  # linwas-power.service çalışıyor mu (değilse ayarlar kilitli)
        self._pending_takeover = False

        scroll = QScrollArea(self)
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        outer = QVBoxLayout(content)
        outer.setContentsMargins(36, 28, 36, 28)
        outer.setSpacing(12)

        title = QLabel(tr("Power & Battery") if self._laptop else tr("Power"), content)
        title.setObjectName("H1")
        outer.addWidget(title)
        outer.addWidget(
            self._secondary(
                tr(
                    "Choose how your computer balances speed and energy use. Plans switch "
                    "automatically when you plug in or unplug."
                )
                if self._laptop
                else tr("Choose how your computer balances speed and energy use."),
                content,
            )
        )

        # Sıra: yönetim durumu → pil → plan → sık ayarlar → gelişmiş (açık) → otomasyon → tanılama
        self._control_card = self._build_control_card(content)
        outer.addWidget(self._control_card)
        self._battery_card = self._build_battery_card(content)
        outer.addWidget(self._battery_card)
        self._battery_card.setVisible(self._laptop)
        self._plan_card = self._build_plan_card(content)
        outer.addWidget(self._plan_card)
        self._quick_card = self._build_quick_card(content)
        outer.addWidget(self._quick_card)
        self._advanced_card = self._build_advanced_card(content)
        outer.addWidget(self._advanced_card)
        self._automation_card = self._build_automation_card(content)
        outer.addWidget(self._automation_card)
        self._report_card = PowerReportCard(content)
        self._report_card.task_run_now.connect(self.task_run_now)
        self._report_card.ui_action.connect(self._on_report_action)
        outer.addWidget(self._report_card)
        self._hibernate_card = self._build_hibernate_card(content)
        outer.addWidget(self._hibernate_card)

        outer.addStretch(1)
        scroll.setWidget(content)

        # Kaydet çubuğu: kaydırılan içeriğin dışında, sayfanın altında sabit (hep görünür)
        self._save_bar = Card(self)
        row = QHBoxLayout()
        row.setSpacing(10)
        self._dirty_lbl = QLabel(tr("You have unsaved changes."), self._save_bar)
        self._dirty_lbl.setObjectName("OptionTitle")
        row.addWidget(self._dirty_lbl, 1)
        discard = QPushButton(tr("Discard"), self._save_bar)
        discard.clicked.connect(self._discard)
        row.addWidget(discard)
        save = QPushButton(tr("Save changes"), self._save_bar)
        save.setProperty("primary", True)
        save.setDefault(True)
        save.clicked.connect(self._save)
        row.addWidget(save)
        self._save_bar.layout.addLayout(row)
        self._save_bar.hide()

        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(0)
        page.addWidget(scroll, 1)
        bar_box = QHBoxLayout()
        bar_box.setContentsMargins(36, 8, 36, 16)
        bar_box.addWidget(self._save_bar)
        page.addLayout(bar_box)

    # --- Kartlar ---

    def _h2(self, text: str, parent: QWidget) -> QLabel:
        h = QLabel(text, parent)
        h.setObjectName("H2")
        return h

    def _secondary(self, text: str, parent: QWidget) -> QLabel:
        lbl = QLabel(text, parent)
        lbl.setObjectName("Secondary")
        lbl.setWordWrap(True)
        return lbl

    def _build_control_card(self, parent: QWidget) -> Card:
        """Güç yönetimi: Linwas mı yönetiyor; eksikler listesi ve tek düğmeyle devralma."""
        card = Card(parent)
        row = QHBoxLayout()
        row.setSpacing(16)
        self._control_icon = QLabel(card)
        self._control_icon.setFixedSize(48, 48)
        icons.bind(self._control_icon, "power", "tile", 48)
        row.addWidget(self._control_icon, 0, Qt.AlignmentFlag.AlignTop)
        box = QVBoxLayout()
        box.setSpacing(4)
        self._control_title = self._h2(tr("Checking power management…"), card)
        self._control_title.setWordWrap(True)
        box.addWidget(self._control_title)
        self._control_lbl = self._secondary("", card)
        box.addWidget(self._control_lbl)
        self._control_checks = QVBoxLayout()
        self._control_checks.setSpacing(6)
        self._control_checks.setContentsMargins(0, 6, 0, 0)
        box.addLayout(self._control_checks)
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 8, 0, 0)
        self._take_over_btn = QPushButton(tr("Let Linwas manage power"), card)
        self._take_over_btn.setProperty("primary", True)
        self._take_over_btn.clicked.connect(self._take_over)
        buttons.addWidget(self._take_over_btn)
        self._give_back_btn = QPushButton(tr("Give control back"), card)
        self._give_back_btn.setToolTip(
            tr("Turns the Linwas power service off and the other power tools on again")
        )
        self._give_back_btn.clicked.connect(self._give_back)
        buttons.addWidget(self._give_back_btn)
        buttons.addStretch(1)
        box.addLayout(buttons)
        row.addLayout(box, 1)
        card.layout.addLayout(row)
        return card

    def _check_row(self, ok: bool, text: str) -> QWidget:
        """Denetim satırı: yeşil onay ya da turuncu bilgi simgesi + metin."""
        line = QWidget(self._control_card)
        line.setObjectName("CardRow")
        lay = QHBoxLayout(line)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        glyph = QLabel(line)
        glyph.setFixedSize(18, 18)
        icons.bind(glyph, "check" if ok else "info", "success" if ok else "warning", 18)
        lay.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        lbl = QLabel(text, line)
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        return line

    def _build_battery_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Battery"), card))

        # Özet: pil göstergesi + büyük yüzde + durum ve kalan süre
        hero = QHBoxLayout()
        hero.setSpacing(18)
        self._gauge = BatteryGauge(card)
        hero.addWidget(self._gauge, 0, Qt.AlignmentFlag.AlignVCenter)
        texts_box = QVBoxLayout()
        texts_box.setSpacing(2)
        self._level_pct = QLabel("", card)
        self._level_pct.setObjectName("H1")
        texts_box.addWidget(self._level_pct)
        self._bat_lbl = QLabel(tr("Reading battery information…"), card)
        self._bat_lbl.setObjectName("OptionTitle")
        self._bat_lbl.setWordWrap(True)
        texts_box.addWidget(self._bat_lbl)
        hero.addLayout(texts_box, 1)
        card.layout.addLayout(hero)

        # Bilgi kutuları: sağlık, şarj döngüsü, güç kaynağı
        stats = QHBoxLayout()
        stats.setSpacing(10)
        self._stat_health = self._stat_tile(tr("Battery health"), card)
        self._stat_cycles = self._stat_tile(tr("Charge cycles"), card)
        self._stat_source = self._stat_tile(tr("Power source"), card)
        for frame, _value, _note in (self._stat_health, self._stat_cycles, self._stat_source):
            stats.addWidget(frame, 1)
        card.layout.addLayout(stats)

        # Yapıcı öneri (ör. pil yıpranmışsa ne yapılabilir)
        self._bat_tip = QLabel("", card)
        self._bat_tip.setObjectName("Warning")
        self._bat_tip.setWordWrap(True)
        self._bat_tip.hide()
        card.layout.addWidget(self._bat_tip)

        # Pil koruma (yalnızca destekleyen cihazlarda)
        self._limit_box = _tile_frame(card)
        box = QHBoxLayout(self._limit_box)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(12)
        shield = QLabel(self._limit_box)
        shield.setFixedSize(32, 32)
        icons.bind(shield, "battery", "tile", 32)
        box.addWidget(shield, 0, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(_title_label(tr("Battery protection"), self._limit_box))
        info.addWidget(
            _note_label(
                tr(
                    "Stopping charging at 80% helps the battery last longer if the laptop is "
                    "usually plugged in."
                )
                + " "
                + tr("The limit is kept after restarting."),
                self._limit_box,
            )
        )
        box.addLayout(info, 1)
        self._limit = QComboBox(self._limit_box)
        for pct in power.CHARGE_LIMITS:
            text = tr("No limit (100%)") if pct == 100 else tr("Stop at {n}%").format(n=pct)
            self._limit.addItem(text, pct)
        box.addWidget(self._limit, 0, Qt.AlignmentFlag.AlignVCenter)
        limit_btn = QPushButton(tr("Apply"), self._limit_box)
        limit_btn.clicked.connect(self._apply_limit)
        box.addWidget(limit_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._limit_box.hide()
        card.layout.addWidget(self._limit_box)
        return card

    def _stat_tile(self, caption: str, parent: QWidget) -> tuple[QFrame, QLabel, QLabel]:
        """Küçük bilgi kutusu: gri başlık, kalın değer, altında kısa yorum."""
        frame = _tile_frame(parent)
        box = QVBoxLayout(frame)
        box.setContentsMargins(14, 10, 14, 10)
        box.setSpacing(2)
        box.addWidget(_note_label(caption, frame))
        value = QLabel("", frame)
        value.setObjectName("H2")
        box.addWidget(value)
        note = _note_label("", frame)
        box.addWidget(note)
        return frame, value, note

    def _build_plan_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Power plan"), card))
        self._now_lbl = self._secondary("", card)
        card.layout.addWidget(self._now_lbl)
        self._ppd_warn = QLabel("", card)
        self._ppd_warn.setObjectName("Warning")
        self._ppd_warn.setWordWrap(True)
        self._ppd_warn.hide()
        card.layout.addWidget(self._ppd_warn)
        # Planlar yan yana seçim kartları (Windows 11 güç modu, macOS enerji kipi gibi)
        self._plan_box = QGridLayout()
        self._plan_box.setSpacing(10)
        for col in range(_PLAN_COLUMNS):
            self._plan_box.setColumnStretch(col, 1)
        card.layout.addLayout(self._plan_box)
        self._plan_group = QButtonGroup(self)
        self._plan_group.idClicked.connect(self._on_plan_clicked)
        self._plan_ids: list[str] = []
        self._plan_tiles: list[OptionTile] = []

        row = QHBoxLayout()
        for text, slot in (
            (tr("New plan…"), self._new_plan),
            (tr("Import…"), self._import_plan),
        ):
            btn = QPushButton(text, card)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        row.addStretch(1)
        reapply = QPushButton(tr("Reapply plan"), card)
        reapply.setToolTip(
            tr("Sets this plan's settings again, e.g. after changing them elsewhere")
        )
        reapply.clicked.connect(self._reapply)
        row.addWidget(reapply)
        card.layout.addLayout(row)
        return card

    def _build_quick_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        title_row = QHBoxLayout()
        self._quick_title = self._h2("", card)
        title_row.addWidget(self._quick_title, 1)
        all_btn = QPushButton(tr("All settings of this plan"), card)
        all_btn.setToolTip(tr("Go to the advanced power settings"))
        all_btn.clicked.connect(lambda: self._on_report_action("advanced"))
        title_row.addWidget(all_btn)
        card.layout.addLayout(title_row)
        # Satırlar: solda ad + açıklama, sağda Prizde / Pilde seçimleri
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        self._quick_combos: dict[tuple[str, str], QComboBox] = {}
        self._quick_heads: list[QWidget] = []
        for col, (text, icon_name) in enumerate(
            ((tr("Plugged in"), "plug"), (tr("On battery"), "battery")), start=1
        ):
            head = QWidget(card)
            head.setObjectName("CardRow")
            head_row = QHBoxLayout(head)
            head_row.setContentsMargins(0, 0, 0, 0)
            head_row.setSpacing(6)
            glyph = QLabel(head)
            icons.bind(glyph, icon_name, "secondary", 16)
            head_row.addWidget(glyph)
            lbl = QLabel(text, head)
            lbl.setObjectName("Secondary")
            head_row.addWidget(lbl, 1)
            grid.addWidget(head, 0, col)
            self._quick_heads.append(head)
        for i, sid in enumerate(_QUICK):
            line = 1 + i * 2
            if i:
                sep = QFrame(card)
                sep.setObjectName("Separator")
                sep.setFixedHeight(1)
                grid.addWidget(sep, line - 1, 0, 1, 3)
            name_box = QVBoxLayout()
            name_box.setSpacing(1)
            name_box.addWidget(_title_label(texts.setting_name(sid), card))
            help_text = texts.setting_help(sid)
            if help_text:
                name_box.addWidget(self._secondary(help_text, card))
            grid.addLayout(name_box, line, 0)
            for col, src in enumerate(powerplan.SOURCES, start=1):
                combo = QComboBox(card)
                combo.currentIndexChanged.connect(
                    lambda _i, s=sid, so=src, c=combo: self._on_combo(s, so, c)
                )
                grid.addWidget(combo, line, col, Qt.AlignmentFlag.AlignVCenter)
                self._quick_combos[(sid, src)] = combo
        card.layout.addLayout(grid)
        return card

    def _build_advanced_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Advanced power settings"), card))
        card.layout.addWidget(
            self._secondary(
                tr(
                    "Every setting of the plans, like Windows' advanced power options. Most "
                    "people do not need to change these."
                ),
                card,
            )
        )
        self._adv_toggle = QToolButton(card)
        self._adv_toggle.setObjectName("DetailsToggle")
        self._adv_toggle.setCheckable(True)
        self._adv_toggle.toggled.connect(self._on_advanced_toggled)
        card.layout.addWidget(self._adv_toggle)
        self._adv_body = QWidget(card)
        self._adv_body.setObjectName("CardRow")  # kartın zemini (gri şerit olmasın)
        body = QVBoxLayout(self._adv_body)
        body.setContentsMargins(0, 0, 0, 0)
        card.layout.addWidget(self._adv_body)

        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Plan:"), card))
        self._edit_combo = QComboBox(card)
        self._edit_combo.currentIndexChanged.connect(self._on_edit_plan_changed)
        row.addWidget(self._edit_combo, 1)
        self._rename_btn = QPushButton(tr("Rename…"), card)
        self._rename_btn.clicked.connect(self._rename_plan)
        row.addWidget(self._rename_btn)
        self._delete_btn = QPushButton(tr("Delete"), card)
        self._delete_btn.clicked.connect(self._delete_plan)
        row.addWidget(self._delete_btn)
        export_btn = QPushButton(tr("Export…"), card)
        export_btn.clicked.connect(self._export_plan)
        row.addWidget(export_btn)
        body.addLayout(row)

        # Ayar listesi düz düzen: açılır kapanır bölümler, her ayar bir satır. (Önceki ağaç
        # listesinde satır yüksekliği içeriğe uymuyor, kaydırınca yazılar kayıyordu.)
        self._adv_list = QVBoxLayout()
        self._adv_list.setSpacing(6)
        body.addLayout(self._adv_list)
        self._tree_combos: dict[tuple[str, str], QComboBox] = {}
        self._reset_btns: dict[str, QToolButton] = {}
        self._section_open = {"display", "buttons", "cpu"}

        row = QHBoxLayout()
        reset = QPushButton(tr("Restore plan defaults"), card)
        reset.clicked.connect(self._reset_plan)
        row.addWidget(reset)
        reset_all = QPushButton(tr("Restore all defaults"), card)
        reset_all.clicked.connect(self._reset_all)
        row.addWidget(reset_all)
        row.addStretch(1)
        body.addLayout(row)
        body.addWidget(
            self._secondary(
                tr(
                    '"System default" means Linwas does not change that setting. Settings '
                    'under "all plans" are the same for every plan.'
                ),
                card,
            )
        )
        # Bütün ayarlar baştan görünür (kullanıcı kararı, 17 Ekim 2026); istenirse gizlenir
        self._adv_toggle.setChecked(True)
        self._on_advanced_toggled(True)
        return card

    def _build_automation_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        card.layout.addWidget(self._h2(tr("Automatic plan switching"), card))
        card.layout.addWidget(
            self._secondary(
                tr("Linwas can change the plan for you. Turn on what you need and save."), card
            )
        )

        # Düşük pil
        self._saver_box = _tile_frame(card)
        box = QVBoxLayout(self._saver_box)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(12)
        glyph = QLabel(self._saver_box)
        glyph.setFixedSize(32, 32)
        icons.bind(glyph, "leaf", "tile", 32)
        head.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(_title_label(tr("Battery saver"), self._saver_box))
        titles.addWidget(
            _note_label(
                tr("Switches to a thriftier plan when the battery runs low."), self._saver_box
            )
        )
        head.addLayout(titles, 1)
        box.addLayout(head)
        row = QHBoxLayout()
        row.setContentsMargins(44, 0, 0, 0)
        self._saver_chk = QCheckBox(tr("When the battery falls to"), self._saver_box)
        self._saver_chk.toggled.connect(self._on_automation)
        row.addWidget(self._saver_chk)
        self._saver_pct = QSpinBox(self._saver_box)
        self._saver_pct.setRange(5, 50)
        self._saver_pct.setSuffix("%")
        self._saver_pct.valueChanged.connect(self._on_automation)
        row.addWidget(self._saver_pct)
        row.addWidget(QLabel(tr("switch to"), self._saver_box))
        self._saver_plan = QComboBox(self._saver_box)
        self._saver_plan.currentIndexChanged.connect(self._on_automation)
        row.addWidget(self._saver_plan, 1)
        box.addLayout(row)
        self._saver_box.setVisible(self._laptop)
        card.layout.addWidget(self._saver_box)

        # Zamanlama
        sched_box = _tile_frame(card)
        box = QVBoxLayout(sched_box)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(6)
        head = QHBoxLayout()
        head.setSpacing(12)
        glyph = QLabel(sched_box)
        glyph.setFixedSize(32, 32)
        icons.bind(glyph, "clock", "tile", 32)
        head.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(_title_label(tr("Schedule"), sched_box))
        titles.addWidget(
            _note_label(tr("Uses another plan at set hours, e.g. Power saver at night."), sched_box)
        )
        head.addLayout(titles, 1)
        box.addLayout(head)
        row = QHBoxLayout()
        row.setContentsMargins(44, 0, 0, 0)
        self._sched_chk = QCheckBox(tr("Every day from"), sched_box)
        self._sched_chk.toggled.connect(self._on_automation)
        row.addWidget(self._sched_chk)
        self._sched_start = QTimeEdit(sched_box)
        self._sched_start.setDisplayFormat("HH:mm")
        self._sched_start.timeChanged.connect(self._on_automation)
        row.addWidget(self._sched_start)
        row.addWidget(QLabel(tr("to"), sched_box))
        self._sched_end = QTimeEdit(sched_box)
        self._sched_end.setDisplayFormat("HH:mm")
        self._sched_end.timeChanged.connect(self._on_automation)
        row.addWidget(self._sched_end)
        row.addWidget(QLabel(tr("use"), sched_box))
        self._sched_plan = QComboBox(sched_box)
        self._sched_plan.currentIndexChanged.connect(self._on_automation)
        row.addWidget(self._sched_plan, 1)
        box.addLayout(row)
        card.layout.addWidget(sched_box)
        card.layout.addWidget(
            self._secondary(
                tr("Low battery switching comes first, then the schedule, then the selected plan."),
                card,
            )
        )
        return card

    def _build_hibernate_card(self, parent: QWidget) -> Card:
        card = Card(parent)
        row = QHBoxLayout()
        row.setSpacing(14)
        self._hibernate_icon = QLabel(card)
        self._hibernate_icon.setFixedSize(40, 40)
        icons.bind(self._hibernate_icon, "moon", "tile", 40)
        row.addWidget(self._hibernate_icon, 0, Qt.AlignmentFlag.AlignTop)
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(self._h2(tr("Hibernate"), card))
        self._hibernate_lbl = self._secondary("", card)
        box.addWidget(self._hibernate_lbl)

        # Kurulum (Windows'taki hiberfil.sys gibi swap dosyası): boyut + düğme
        self._hib_setup = QWidget(card)
        setup = QHBoxLayout(self._hib_setup)
        setup.setContentsMargins(0, 8, 0, 0)
        setup.setSpacing(10)
        setup.addWidget(QLabel(tr("Swap file size:"), self._hib_setup))
        self._hib_size = QSpinBox(self._hib_setup)
        self._hib_size.setSuffix(" GB")
        self._hib_size.setAccessibleName(tr("Swap file size"))
        setup.addWidget(self._hib_size)
        setup.addStretch(1)
        self._hib_setup_btn = QPushButton(tr("Set up hibernation"), self._hib_setup)
        self._hib_setup_btn.setProperty("primary", True)
        self._hib_setup_btn.clicked.connect(self._setup_hibernate)
        setup.addWidget(self._hib_setup_btn)
        self._hib_setup.hide()
        box.addWidget(self._hib_setup)

        # Kurulduktan sonra: yeniden başlat / dene / kaldır
        self._hib_actions = QHBoxLayout()
        self._hib_actions.setContentsMargins(0, 8, 0, 0)
        self._hib_restart_btn = QPushButton(tr("Restart now"), card)
        self._hib_restart_btn.setProperty("primary", True)
        self._hib_restart_btn.clicked.connect(self._restart_now)
        self._hib_try_btn = QPushButton(tr("Hibernate now"), card)
        self._hib_try_btn.clicked.connect(self._hibernate_now)
        self._hib_remove_btn = QPushButton(tr("Remove hibernation"), card)
        self._hib_remove_btn.clicked.connect(self._remove_hibernate)
        for btn in (self._hib_restart_btn, self._hib_try_btn, self._hib_remove_btn):
            btn.hide()
            self._hib_actions.addWidget(btn)
        self._hib_actions.addStretch(1)
        box.addLayout(self._hib_actions)
        row.addLayout(box, 1)
        card.layout.addLayout(row)
        self._hib_check = hibernate_setup.SetupCheck()
        return card

    # --- Yükleme ---

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        if not self._dirty():
            self._reload()

    def on_tasks_finished(self) -> None:
        if self._loaded:
            if self._pending_save:
                self._pending_save = False
                self._keep(_AgentWorker())
            if self._pending_takeover:
                self._pending_takeover = False
                self._start_agent()
            self._reload(force=True)

    def _keep(self, worker: QThread) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker))
        worker.start()

    def _reload(self, force: bool = False) -> None:
        if self._dirty() and not force:
            return
        self._loaded = True
        worker = _LoadWorker()
        worker.done.connect(self._on_loaded)
        self._keep(worker)

    def _on_loaded(self, data: dict) -> None:
        self._fill_battery(data["batteries"])
        self._support = data["support"]
        self._laptop = self._support.laptop
        self._saved = data["config"]
        self._draft = copy.deepcopy(self._saved)
        if self._draft.plan(self._edit_plan) is None:
            self._edit_plan = self._draft.active
        self._fill_all()
        self._fill_status(data["status"], data["ppd"], data["state"])
        self._fill_service(data["service"])
        self._fill_control(
            data["service"], self._support.conflicts, data["agent"], data["taken_over"]
        )
        self._hib_check = data["hibernate_setup"]
        self._fill_hibernate(self._support.hibernate)

    def _fill_battery(self, batteries: list) -> None:
        if not batteries:
            self._battery_card.hide()
            return
        bat: power.Battery = batteries[0]
        self._battery_name = bat.name
        level = bat.capacity or 0
        charging = bat.status == "Charging"
        self._gauge.set_level(level, charging)
        self._level_pct.setText(f"{bat.capacity}%" if bat.capacity is not None else "")
        status = _status_text(bat.status)
        if bat.minutes_left:
            left = _duration_text(bat.minutes_left)
            if charging:
                status += " · " + tr("full in about {t}").format(t=left)
            else:
                status += " · " + tr("about {t} left").format(t=left)
        self._bat_lbl.setText(status)

        frame, value, note = self._stat_health
        frame.setVisible(bat.health is not None)
        tip = ""
        if bat.health is not None:
            value.setText(f"{bat.health}%")
            if bat.health >= 80:
                note.setText(tr("Good"))
            elif bat.health >= 60:
                note.setText(tr("Worn"))
                tip = tr(
                    "The battery holds less charge than when it was new. Battery protection and "
                    "the Power saver plan help it last longer."
                )
            else:
                note.setText(tr("Needs replacing soon"))
                tip = tr(
                    "The battery has lost much of its capacity. Consider replacing it; until "
                    "then, keep the laptop plugged in for long work."
                )
        frame, value, note = self._stat_cycles
        frame.setVisible(bool(bat.cycle_count))
        value.setText(str(bat.cycle_count or ""))
        note.setText(tr("Full charge and discharge"))
        frame, value, note = self._stat_source
        on_battery = bat.status == "Discharging"
        value.setText(tr("Battery") if on_battery else tr("Mains"))
        note.setText(_status_text(bat.status))
        if on_battery and level <= 20 and not tip:
            tip = tr("The battery is low. Plug in the charger soon.")
        self._bat_tip.setText(tip)
        self._bat_tip.setVisible(bool(tip))
        if bat.charge_limit is not None:
            self._limit_box.show()
            idx = self._limit.findData(bat.charge_limit)
            if idx >= 0:
                self._limit.setCurrentIndex(idx)

    def _fill_status(self, status: dict, ppd_now: str, state: powerplan.PowerState) -> None:
        source = tr("plugged in") if state.on_ac else tr("on battery")
        if not status:
            plan, reason = powerplan.effective_plan(self._saved, state)
        else:
            plan = self._saved.plan(str(status.get("plan"))) or self._saved.plan(self._saved.active)
            reason = str(status.get("reason", "active"))
        if plan is None:
            return
        line = tr("Now using: {plan} ({source})").format(plan=texts.plan_name(plan), source=source)
        if reason == "battery_saver":
            line += " — " + tr("because the battery is low")
        elif reason == "schedule":
            line += " — " + tr("because of the schedule")
        self._now_lbl.setText(line)

        # Sistem menüsünden güç kipi değiştirildiyse uyar
        want = self._saved.value(plan, "ppd_profile", "ac" if state.on_ac else "bat")
        if want != AUTO and ppd_now and ppd_now != want:
            self._ppd_warn.setText(
                tr(
                    "The power mode was changed from the system menu ({now}). This plan uses "
                    "{want}; it is set again when the plan or power source changes, or when "
                    'you press "Reapply plan".'
                ).format(
                    now=texts.value_text("ppd_profile", ppd_now),
                    want=texts.value_text("ppd_profile", want),
                )
            )
            self._ppd_warn.show()
        else:
            self._ppd_warn.hide()

    def _fill_service(self, service: str) -> None:
        """Servis çalışmıyorsa uygulanamayacak ayarları kilitler (neden yönetim kartında)."""
        usable = service == "running"
        self._service_ok = usable
        for card in (self._plan_card, self._quick_card, self._advanced_card, self._automation_card):
            card.setEnabled(usable)
            card.setToolTip("" if usable else tr("Needs the Linwas power service"))
        self._update_dirty()

    def _fill_control(
        self,
        service: str,
        tools: list[power_support.ConflictTool],
        agent: bool,
        taken_over: bool,
    ) -> None:
        while self._control_checks.count():
            item = self._control_checks.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        checks: list[tuple[bool, str]] = []
        if service == "running":
            checks.append((True, tr("The Linwas power service is running.")))
        elif service == "missing":
            checks.append(
                (
                    False,
                    tr(
                        "Linwas is running from source code; the power service comes with the "
                        "installed package. Plan settings are locked, battery information works."
                    ),
                )
            )
        else:
            checks.append(
                (False, tr("The Linwas power service is stopped, so plans are not applied."))
            )
        if tools:
            names = ", ".join(t.name for t in tools)
            checks.append(
                (
                    False,
                    tr(
                        "{names} also manages power; the two would override each other. Until "
                        "it is turned off, Linwas does not change processor, USB/PCIe/disk, "
                        "wireless and graphics card settings."
                    ).format(names=names),
                )
            )
        else:
            checks.append((True, tr("No other power tool is active.")))
        if power_agent.is_supported_desktop() and service != "missing":
            checks.append(
                (True, tr("Desktop settings (screen, sleep) follow the plan."))
                if agent
                else (
                    False,
                    tr("The desktop part is not running; screen and sleep times are not set."),
                )
            )
        for ok, text in checks:
            self._control_checks.addWidget(self._check_row(ok, text))

        managed = all(ok for ok, _ in checks)
        icons.bind(self._control_icon, "power", _ON_TILE if managed else "tile", 48)
        if managed:
            self._control_title.setText(tr("Linwas manages power on this computer"))
            self._control_lbl.setText(
                tr(
                    "Plans, automatic switching and the settings below are applied by Linwas. "
                    "Changes in the system menu are set back when the plan or power source "
                    "changes."
                )
            )
        else:
            self._control_title.setText(tr("Linwas does not fully manage power yet"))
            self._control_lbl.setText(
                tr(
                    "One click fixes the items below: other power tools are turned off (not "
                    "removed), the Linwas power service is started and the plan is applied. "
                    "You can give control back at any time."
                )
            )
        fixable = bool(tools) or service == "stopped" or (not agent and service == "running")
        self._take_over_btn.setVisible(not managed)
        self._take_over_btn.setEnabled(fixable)
        self._give_back_btn.setVisible(taken_over)

    def _take_over(self) -> None:
        self._pending_takeover = True
        self.task_run_now.emit(
            Task(
                label=tr("Let Linwas manage power"),
                steps=[TaskStep(op_id="power.take_over", params={})],
            )
        )

    def _give_back(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Give control back"),
            tr(
                "The Linwas power service is turned off and the power tools it turned off are "
                "turned on again. Linwas plans are no longer applied. Continue?"
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.task_run_now.emit(
                Task(
                    label=tr("Give power management back"),
                    steps=[TaskStep(op_id="power.give_back", params={})],
                )
            )

    def _start_agent(self) -> None:
        """Devraldıktan sonra masaüstü ajanı çalışmıyorsa başlatır (oturum yeniden açılmadan)."""
        if power_support.AGENT_PATH.exists() and not power_support.agent_running():
            QProcess.startDetached(str(power_support.AGENT_PATH), [])

    def _on_advanced_toggled(self, shown: bool) -> None:
        self._adv_body.setVisible(shown)
        self._adv_toggle.setText(
            tr("Hide advanced settings") if shown else tr("Show advanced settings")
        )

    def _default_value(self, sid: str, src: str) -> str:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return AUTO
        # Yerleşik plan: fabrika değeri; özel plan: "Sistem varsayılanı"
        base = powerplan.factory_plan(plan.id) if plan.builtin else powerplan.PowerPlan(plan.id)
        return powerplan.default_config().value(base, sid, src)

    def _update_reset_buttons(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        unsupported = self._support.unsupported if self._support else {}
        for sid, btn in self._reset_btns.items():
            changed = any(
                self._draft.value(plan, sid, src) != self._default_value(sid, src)
                for src in powerplan.SOURCES
            )
            # Varsayılandaysa düğme görünmez ama yer tutar (sütun zıplamasın)
            btn.setText(tr("Default") if changed else "")
            btn.setEnabled(changed and sid not in unsupported)

    def _reset_setting(self, sid: str) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        spec = SPECS[sid]
        target = plan.values if spec.per_plan else self._draft.globals
        pair = {src: self._default_value(sid, src) for src in powerplan.SOURCES}
        if pair == {"ac": AUTO, "bat": AUTO}:
            target.pop(sid, None)
        else:
            target[sid] = pair
        self._filling = True
        try:
            for combos in (self._quick_combos, self._tree_combos):
                for src in powerplan.SOURCES:
                    combo = combos.get((sid, src))
                    if combo is not None:
                        self._fill_combo(combo, sid, pair[src])
        finally:
            self._filling = False
        self._update_reset_buttons()
        self._update_dirty()

    def _fill_hibernate(self, info: power_support.HibernateInfo) -> None:
        check = self._hib_check
        icons.bind(self._hibernate_icon, "moon", _ON_TILE if info.available else "tile", 40)
        self._hib_setup.hide()
        self._hib_restart_btn.setVisible(check.installed and check.reboot_needed)
        self._hib_try_btn.setVisible(info.available)
        self._hib_remove_btn.setVisible(check.installed)
        if check.installed and check.reboot_needed:
            self._hibernate_lbl.setText(
                tr(
                    "Hibernation is set up. Restart the computer once to finish; after that "
                    "you can choose it for sleep, the lid and buttons."
                )
            )
            return
        if info.available:
            self._hibernate_lbl.setText(
                tr(
                    "Hibernate is available. It saves your open work to the disk and turns the "
                    "computer off completely; it uses no power and opens where you left off. "
                    "You can choose it for sleep, the lid and buttons."
                )
            )
            return
        if check.possible:
            # Eksik yalnızca swap/resume: Linwas kurabilir
            free_max = max(check.minimum_gb, check.free_gb - hibernate.SPARE_GB)
            self._hib_size.setRange(check.minimum_gb, min(hibernate.MAX_SIZE_GB, free_max))
            self._hib_size.setValue(min(check.recommended_gb, free_max))
            self._hibernate_lbl.setText(
                tr(
                    "Hibernate saves your open work to the disk and turns the computer off "
                    "completely. On Linux it needs swap space as big as the memory "
                    "({ram} GB); this computer does not have enough. Linwas can create a "
                    "swap file for it, like Windows' hiberfil.sys. Free space on the system "
                    "disk: {free} GB."
                ).format(ram=check.ram_gb, free=check.free_gb)
            )
            self._hib_setup.show()
            return
        lines = [tr("Hibernate is not available on this computer:")]
        reasons = check.problems or info.reasons
        lines += [
            f"• {texts.hibernate_setup_problem_text(r)}"
            if check.problems
            else f"• {texts.hibernate_reason_text(r)}"
            for r in reasons
        ]
        self._hibernate_lbl.setText("\n".join(lines))

    def _setup_hibernate(self) -> None:
        size = self._hib_size.value()
        warn = (
            "\n\n"
            + tr(
                "This is smaller than the memory. Hibernation may fail when the memory is "
                "nearly full."
            )
            if size < self._hib_check.recommended_gb
            else ""
        )
        answer = QMessageBox.question(
            self,
            tr("Set up hibernation"),
            tr(
                "Linwas will create a {n} GB swap file (/swapfile) on the system disk and set "
                "the computer to wake from it. Writing the file can take a few minutes. "
                "Afterwards the computer must be restarted once.\n\nContinue?"
            ).format(n=size)
            + warn,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        steps: list[TaskStep] = []
        if shutil.which("timeshift"):
            steps.append(
                TaskStep(
                    op_id="snapshot.timeshift_create",
                    label=tr("System backup (Timeshift)"),
                    params={},
                )
            )
        steps.append(
            TaskStep(
                op_id="hibernate.setup",
                label=tr("Create the swap file and set up waking"),
                params={"size_gb": str(size)},
            )
        )
        self.task_run_now.emit(Task(label=tr("Set up hibernation"), steps=steps))

    def _remove_hibernate(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Remove hibernation"),
            tr(
                "The swap file is deleted and hibernation is turned off. Settings that use "
                "hibernate should be changed to sleep. Continue?"
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.task_run_now.emit(
                Task(
                    label=tr("Remove hibernation"),
                    steps=[TaskStep(op_id="hibernate.remove", params={})],
                )
            )

    def _restart_now(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Restart now"),
            tr("Save your work and close your programs. Restart the computer now?"),
        )
        if answer == QMessageBox.StandardButton.Yes:
            # Etkin oturumdaki kullanıcı logind üzerinden yeniden başlatabilir (şifre gerekmez)
            QProcess.startDetached("systemctl", ["reboot"])

    def _hibernate_now(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Hibernate now"),
            tr(
                "Save your work first. The computer turns off; press the power button to "
                "continue where you left off. Hibernate now?"
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            QProcess.startDetached("systemctl", ["hibernate"])

    # --- Doldurma ---

    def _fill_all(self) -> None:
        self._filling = True
        try:
            self._fill_plans()
            self._fill_plan_combos()
            self._fill_tree()
            self._fill_quick()
            self._fill_automation()
        finally:
            self._filling = False
        self._update_dirty()

    def _fill_plans(self) -> None:
        for btn in self._plan_group.buttons():
            self._plan_group.removeButton(btn)
        for tile in self._plan_tiles:
            tile.deleteLater()
        self._plan_tiles = []
        self._plan_ids = [p.id for p in self._draft.plans]
        for i, plan in enumerate(self._draft.plans):
            tile = OptionTile(
                texts.plan_name(plan),
                texts.plan_description(plan),
                parent=self._plan_card,
                icon=_PLAN_ICONS.get(plan.id, "settings") if plan.builtin else "settings",
            )
            tile.button.setChecked(plan.id == self._draft.active)
            self._plan_group.addButton(tile.button, i)
            self._plan_box.addWidget(tile, i // _PLAN_COLUMNS, i % _PLAN_COLUMNS)
            self._plan_tiles.append(tile)

    def _fill_plan_combos(self) -> None:
        for combo in (self._edit_combo, self._saver_plan, self._sched_plan):
            combo.blockSignals(True)
            combo.clear()
            for plan in self._draft.plans:
                combo.addItem(texts.plan_name(plan), plan.id)
            combo.blockSignals(False)
        self._edit_combo.setCurrentIndex(max(0, self._edit_combo.findData(self._edit_plan)))
        plan = self._draft.plan(self._edit_plan)
        custom = bool(plan and not plan.builtin)
        self._rename_btn.setEnabled(custom)
        self._delete_btn.setEnabled(custom)

    def _choices(self, sid: str, current: str) -> list[str]:
        spec = SPECS[sid]
        values = list(spec.values)
        support = self._support
        if support and sid in support.values:
            values = [v for v in values if v in support.values[sid]]
        if support and not support.hibernate.available:
            values = [v for v in values if v not in _HIBERNATE_VALUES]
        if current != AUTO and current not in values:
            values.append(current)
        return [AUTO, *values]

    def _fill_combo(self, combo: QComboBox, sid: str, value: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        for v in self._choices(sid, value):
            combo.addItem(texts.value_text(sid, v), v)
        combo.setCurrentIndex(max(0, combo.findData(value)))
        combo.blockSignals(False)

    def _visible(self, sid: str) -> bool:
        spec = SPECS[sid]
        return not (spec.laptop_only and not self._laptop)

    def _clear_layout(self, layout: QVBoxLayout | QGridLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def _fill_tree(self) -> None:
        """Gelişmiş ayarlar: bölüm başlığı (aç/kapat) + her ayar için bir satır."""
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        self._clear_layout(self._adv_list)
        self._tree_combos.clear()
        self._reset_btns.clear()
        split_cols = self._laptop
        unsupported = self._support.unsupported if self._support else {}
        card = self._advanced_card

        # Sütun başlıkları (sık ayarlar kartıyla aynı)
        head = QGridLayout()
        head.setHorizontalSpacing(12)
        head.setColumnStretch(0, 1)
        head.setContentsMargins(24, 0, 0, 0)
        head.setColumnMinimumWidth(0, _ADV_TEXT_MIN)
        titles = [(tr("Plugged in"), "plug"), (tr("On battery"), "battery")]
        if not split_cols:
            titles = [(tr("Value"), "power")]
        for col, (text, icon_name) in enumerate(titles, start=1):
            cell = QWidget(card)
            cell.setObjectName("CardRow")
            cell.setMinimumWidth(_ADV_COMBO_MIN)
            cell.setMaximumWidth(_ADV_COMBO_MAX)
            row = QHBoxLayout(cell)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            glyph = QLabel(cell)
            icons.bind(glyph, icon_name, "secondary", 16)
            row.addWidget(glyph)
            lbl = QLabel(text, cell)
            lbl.setObjectName("Secondary")
            row.addWidget(lbl, 1)
            head.addWidget(cell, 0, col)
        spacer = QWidget(card)
        spacer.setObjectName("CardRow")
        spacer.setFixedWidth(_ADV_RESET_WIDTH)
        head.addWidget(spacer, 0, len(titles) + 1)
        self._adv_list.addLayout(head)

        for section in SECTIONS:
            specs = [s for s in SETTINGS if s.section == section and self._visible(s.id)]
            if not specs:
                continue
            toggle = QToolButton(card)
            toggle.setObjectName("SectionToggle")
            toggle.setText(texts.section_name(section))
            toggle.setCheckable(True)
            toggle.setChecked(section in self._section_open)
            toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            toggle.setArrowType(
                Qt.ArrowType.DownArrow if toggle.isChecked() else Qt.ArrowType.RightArrow
            )
            self._adv_list.addWidget(toggle)
            box = QWidget(card)
            box.setObjectName("CardRow")
            grid = QGridLayout(box)
            grid.setContentsMargins(24, 0, 0, 8)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(8)
            grid.setColumnStretch(0, 1)
            line = 0
            for i, spec in enumerate(specs):
                if i:
                    sep = QFrame(box)
                    sep.setObjectName("Separator")
                    sep.setFixedHeight(1)
                    grid.addWidget(sep, line, 0, 1, 4)
                    line += 1
                reason = unsupported.get(spec.id, "")
                name = texts.setting_name(spec.id)
                if reason:
                    name = f"{name} ({texts.reason_text(reason)})"
                info_box = QWidget(box)
                info_box.setObjectName("CardRow")
                info_box.setMinimumWidth(_ADV_TEXT_MIN)
                info = QVBoxLayout(info_box)
                info.setContentsMargins(0, 0, 0, 0)
                info.setSpacing(2)
                info.addWidget(_title_label(name, box))
                help_text = texts.setting_help(spec.id)
                if help_text:
                    info.addWidget(self._secondary(help_text, box))
                grid.addWidget(info_box, line, 0)
                sources = powerplan.SOURCES if (spec.split and split_cols) else ("ac",)
                for col, src in enumerate(sources, start=1):
                    combo = QComboBox(box)
                    combo.setMinimumWidth(_ADV_COMBO_MIN)
                    combo.setMaximumWidth(_ADV_COMBO_MAX)
                    self._fill_combo(combo, spec.id, self._draft.value(plan, spec.id, src))
                    combo.setEnabled(not reason)
                    combo.currentIndexChanged.connect(
                        lambda _i, s=spec.id, so=src, c=combo: self._on_combo(s, so, c)
                    )
                    grid.addWidget(combo, line, col, Qt.AlignmentFlag.AlignVCenter)
                    self._tree_combos[(spec.id, src)] = combo
                if len(sources) == 1 and split_cols:
                    # Tek değerli ayar (ör. düğmeler): iki sütunu kaplasın
                    note = QLabel(tr("Same when plugged in and on battery"), box)
                    note.setObjectName("Secondary")
                    note.setMinimumWidth(_ADV_COMBO_MIN)
                    note.setMaximumWidth(_ADV_COMBO_MAX)
                    note.setWordWrap(True)
                    grid.addWidget(note, line, 2, Qt.AlignmentFlag.AlignVCenter)
                reset = QToolButton(box)
                reset.setObjectName("SettingLink")
                reset.setText(tr("Default"))
                reset.setToolTip(tr("Restore the default value of this setting"))
                reset.setFixedWidth(_ADV_RESET_WIDTH)
                reset.clicked.connect(lambda _c=False, s=spec.id: self._reset_setting(s))
                grid.addWidget(reset, line, 3, Qt.AlignmentFlag.AlignVCenter)
                self._reset_btns[spec.id] = reset
                line += 1
            box.setVisible(toggle.isChecked())
            toggle.toggled.connect(
                lambda on, b=box, t=toggle, sec=section: self._on_section_toggled(sec, on, b, t)
            )
            self._adv_list.addWidget(box)
        self._update_reset_buttons()

    def _on_section_toggled(
        self, section: str, on: bool, box: QWidget, toggle: QToolButton
    ) -> None:
        box.setVisible(on)
        toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        (self._section_open.add if on else self._section_open.discard)(section)

    def _fill_quick(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        self._quick_title.setText(
            tr("Common settings for {plan}").format(plan=texts.plan_name(plan))
        )
        unsupported = self._support.unsupported if self._support else {}
        for lbl in self._quick_heads:
            lbl.setVisible(self._laptop)
        for (sid, src), combo in self._quick_combos.items():
            self._fill_combo(combo, sid, self._draft.value(plan, sid, src))
            combo.setEnabled(sid not in unsupported)
            combo.setVisible(src == "ac" or self._laptop)

    def _fill_automation(self) -> None:
        saver = self._draft.battery_saver
        sched = self._draft.schedule
        self._saver_chk.setChecked(saver.enabled)
        self._saver_pct.setValue(saver.threshold)
        self._saver_plan.setCurrentIndex(max(0, self._saver_plan.findData(saver.plan)))
        self._sched_chk.setChecked(sched.enabled)
        self._sched_start.setTime(QTime.fromString(sched.start, "HH:mm"))
        self._sched_end.setTime(QTime.fromString(sched.end, "HH:mm"))
        self._sched_plan.setCurrentIndex(max(0, self._sched_plan.findData(sched.plan)))

    # --- Düzenleme ---

    def _dirty(self) -> bool:
        return powerplan.dumps(self._draft) != powerplan.dumps(self._saved)

    def _update_dirty(self) -> None:
        self._save_bar.setVisible(self._service_ok and self._dirty())

    def _on_combo(self, sid: str, src: str, combo: QComboBox) -> None:
        if self._filling:
            return
        value = combo.currentData()
        spec = SPECS[sid]
        # Tek değerli ayar ya da masaüstü bilgisayar: prizde ve pilde aynı değer
        sources = powerplan.SOURCES if not (spec.split and self._laptop) else (src,)
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        target = plan.values if spec.per_plan else self._draft.globals
        pair = target.setdefault(sid, {"ac": AUTO, "bat": AUTO})
        for s in sources:
            pair[s] = value
        if pair == {"ac": AUTO, "bat": AUTO}:
            target.pop(sid, None)
        # Aynı ayar hem hızlı kartta hem ağaçta: diğerini eşitle
        self._filling = True
        try:
            for combos in (self._quick_combos, self._tree_combos):
                for s in sources:
                    other = combos.get((sid, s))
                    if other is not None and other is not combo:
                        other.setCurrentIndex(max(0, other.findData(value)))
        finally:
            self._filling = False
        self._update_reset_buttons()
        self._update_dirty()

    def _on_edit_plan_changed(self, index: int) -> None:
        if self._filling or index < 0:
            return
        self._edit_plan = self._edit_combo.itemData(index)
        self._filling = True
        try:
            self._fill_plan_combos()
            self._fill_tree()
            self._fill_quick()
        finally:
            self._filling = False

    def _on_automation(self, *_args: object) -> None:
        if self._filling:
            return
        saver = self._draft.battery_saver
        saver.enabled = self._saver_chk.isChecked()
        saver.threshold = self._saver_pct.value()
        saver.plan = self._saver_plan.currentData() or saver.plan
        sched = self._draft.schedule
        sched.enabled = self._sched_chk.isChecked()
        sched.start = self._sched_start.time().toString("HH:mm")
        sched.end = self._sched_end.time().toString("HH:mm")
        sched.plan = self._sched_plan.currentData() or sched.plan
        self._update_dirty()

    def _validate(self) -> str:
        for plan in self._draft.plans:
            for src in powerplan.SOURCES:
                lo, hi = plan.get("cpu_min", src), plan.get("cpu_max", src)
                if AUTO not in (lo, hi) and int(lo) > int(hi):
                    return tr(
                        "In {plan}, the minimum processor state is higher than the maximum."
                    ).format(plan=texts.plan_name(plan))
        g = self._draft.globals
        levels = [
            g.get(k, {}).get("ac", AUTO)
            for k in ("battery_low", "battery_critical", "battery_action_level")
        ]
        known = [int(v) for v in levels if v != AUTO]
        if known != sorted(known, reverse=True) or len(set(known)) != len(known):
            return tr("Battery levels must be: low > critical > action level.")
        sched = self._draft.schedule
        if sched.enabled and sched.start == sched.end:
            return tr("The schedule start and end times are the same.")
        return ""

    def _save(self) -> None:
        error = self._validate()
        if error:
            QMessageBox.warning(self, tr("Power plan"), error)
            return
        self._pending_save = True
        self.task_run_now.emit(
            Task(
                label=tr("Save power plan settings"),
                steps=[
                    TaskStep(
                        op_id="power.save_config",
                        params={"config": powerplan.dumps(self._draft)},
                    )
                ],
            )
        )

    def _discard(self) -> None:
        self._draft = copy.deepcopy(self._saved)
        if self._draft.plan(self._edit_plan) is None:
            self._edit_plan = self._draft.active
        self._fill_all()

    # --- Plan işlemleri ---

    def _on_plan_clicked(self, index: int) -> None:
        if not 0 <= index < len(self._plan_ids):
            return
        plan_id = self._plan_ids[index]
        if plan_id == self._draft.active:
            return
        other_changes = self._dirty_except_active()
        self._draft.active = plan_id
        if other_changes or self._saved.plan(plan_id) is None:
            self._update_dirty()  # diğer değişikliklerle birlikte kaydedilir
            return
        if power.can_switch_plan_directly():
            worker = _SwitchWorker(plan_id)
            worker.done.connect(self._on_switched)
            self._keep(worker)
        else:
            self._save()  # kaynak koddan çalışırken: root helper (şifre)

    def _dirty_except_active(self) -> bool:
        a = copy.deepcopy(self._draft)
        a.active = self._saved.active
        return powerplan.dumps(a) != powerplan.dumps(self._saved)

    def _on_switched(self, ok: bool) -> None:
        if not ok:
            QMessageBox.warning(self, tr("Power plan"), tr("The power plan could not be changed."))
        self._reload(force=True)

    def _reapply(self) -> None:
        plan_id = self._saved.active
        if power.can_switch_plan_directly():
            worker = _SwitchWorker(plan_id)
            worker.done.connect(self._on_switched)
            self._keep(worker)
        else:
            self._save()

    def _ask_name(self, title: str, text: str = "") -> str:
        name, ok = QInputDialog.getText(self, title, tr("Plan name:"), text=text)
        name = " ".join(name.split())
        if not ok or not name:
            return ""
        return name[: powerplan.MAX_NAME_LEN]

    def _new_plan(self) -> None:
        name = self._ask_name(tr("New power plan"))
        if not name:
            return
        try:
            plan = powerplan.new_custom_plan(self._draft, name, based_on=self._edit_plan)
        except powerplan.PowerConfigError:
            QMessageBox.warning(
                self,
                tr("Power plan"),
                tr("You can have at most {n} custom plans.").format(n=powerplan.MAX_CUSTOM_PLANS),
            )
            return
        self._edit_plan = plan.id
        self._fill_all()

    def _rename_plan(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None or plan.builtin:
            return
        name = self._ask_name(tr("Rename power plan"), plan.name)
        if name:
            plan.name = name
            self._fill_all()

    def _delete_plan(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None or plan.builtin:
            return
        answer = QMessageBox.question(
            self, tr("Power plan"), tr('Delete the plan "{name}"?').format(name=plan.name)
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        powerplan.delete_plan(self._draft, plan.id)
        self._edit_plan = self._draft.active
        self._fill_all()

    def _reset_plan(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        answer = QMessageBox.question(
            self,
            tr("Power plan"),
            tr('Restore the default settings of "{name}"?').format(name=texts.plan_name(plan)),
        )
        if answer == QMessageBox.StandardButton.Yes:
            powerplan.reset_plan(self._draft, plan.id)
            self._fill_all()

    def _reset_all(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("Power plan"),
            tr(
                "Restore all power settings to their defaults? Custom plans and automatic "
                "switching are removed."
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._draft = powerplan.default_config()
            self._edit_plan = self._draft.active
            self._fill_all()

    def _export_plan(self) -> None:
        plan = self._draft.plan(self._edit_plan)
        if plan is None:
            return
        name = texts.plan_name(plan)
        path, _ = QFileDialog.getSaveFileName(
            self,
            tr("Export power plan"),
            str(Path.home() / f"{name}.json"),
            tr("Power plan (*.json)"),
        )
        if not path:
            return
        try:
            Path(path).write_text(powerplan.export_plan(self._draft, plan.id, name), "utf-8")
        except OSError as exc:
            QMessageBox.warning(self, tr("Power plan"), str(exc))

    def _import_plan(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Import power plan"), str(Path.home()), tr("Power plan (*.json)")
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            plan = powerplan.import_plan(self._draft, text, default_name=tr("Imported plan"))
        except (OSError, UnicodeDecodeError, powerplan.PowerConfigError):
            QMessageBox.warning(
                self, tr("Power plan"), tr("This file is not a valid Linwas power plan.")
            )
            return
        self._edit_plan = plan.id
        self._fill_all()

    # --- Diğer işlemler ---

    def _on_report_action(self, action: str) -> None:
        target = {
            "charge_limit": self._battery_card,
            "automation": self._automation_card,
            "advanced": self._advanced_card,
        }.get(action)
        if target is self._advanced_card:
            self._adv_toggle.setChecked(True)
        if target is not None:
            self._scroll.ensureWidgetVisible(target, 0, 40)

    def _apply_limit(self) -> None:
        if not self._battery_name:
            return
        pct = self._limit.currentData()
        self.task_run_now.emit(
            Task(
                label=tr("Battery charge limit: {n}%").format(n=pct),
                steps=[
                    TaskStep(
                        op_id="battery.set_charge_limit",
                        params={"battery": self._battery_name, "percent": str(pct)},
                    )
                ],
            )
        )
