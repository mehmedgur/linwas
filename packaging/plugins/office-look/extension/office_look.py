# Linwas Office görünümü: LibreOffice eklentisi.
#
# Kullanıcının ayarları ~/.config/linwas-office-look/settings.json dosyasında
# (Linwas'ın "Office görünümü" sayfası ve linwas-office-look aracı yazar):
#   file_menu: true/false        pencere içi Dosya menüsü, Dosya düğmesi ve sekmesi
#   autosave_minutes: 0/1/2/5/10 otomatik kaydetme aralığı (0 = kapalı)
# Aynı klasördeki "disabled" dosyası varsa eklenti hiçbir şey kurmaz.
#
# Kaydet, Farklı kaydet, Aç, Yeni, Dışa aktar ve Belge bilgisi işlemlerini
# ayrı bir iletişim penceresi açmadan, belge penceresinin içinde, belge
# alanının yerini alan tam sayfa bir katmanda yapar. Görünüm "Writer Sade
# Arayüz Taslağı" tasarımının Dosya menüsü ekranını izler.
#
# - Job: her belge görünümü açıldığında çerçeveye bir dispatch yakalayıcı kurar.
# - Yakalayıcı: .uno:SaveAs, açma komutları ve konumu olmayan belgede .uno:Save
#   komutlarını Dosya menüsüne yönlendirir; diğer komutlar olduğu gibi geçer.
# - FileMenu: çerçevenin belge penceresini gizler ve aynı alana kendi
#   pencerelerini yerleştirir. Şerit ve durum çubuğu yerinde kalır. Esc ya da
#   "Belgeye dön" belgeye döner.
# - SaveBadge: konumu olan belgeyi değişiklik varsa ayarlanan aralıkta kaydeder
#   ve pencere başlığına kayıt durumunu yazar ("Kaydedildi", "Kaydedilmemiş
#   değişiklikler"). LibreOffice'in UserAutoSaveEnabled ayarı 7.4'te belgeyi
#   kaydetmediği için kayıt burada yapılır.
# - FileTabController: sade şeritte Dosya sekmesi açılınca Dosya menüsünü gösterir,
#   başka sekmeye geçilince kapatır (ayrıntı sınıfın belgesinde).

import base64
import contextlib
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import traceback
import zipfile

import uno
import unohelper
from com.sun.star.accessibility.AccessibleRole import PAGE_TAB, PAGE_TAB_LIST
from com.sun.star.accessibility.AccessibleStateType import SELECTED
from com.sun.star.awt import (
    XActionListener,
    XCallback,
    XItemListener,
    XKeyListener,
    XMouseListener,
    XWindowListener,
)
from com.sun.star.awt.Key import ESCAPE, RETURN, TAB
from com.sun.star.awt.KeyModifier import SHIFT
from com.sun.star.awt.PosSize import POSSIZE
from com.sun.star.awt.WindowClass import CONTAINER
from com.sun.star.beans import PropertyValue
from com.sun.star.document import XDocumentEventListener
from com.sun.star.frame import (
    XDispatch,
    XDispatchProviderInterceptor,
    XStatusListener,
    XToolbarController,
)
from com.sun.star.lang import XComponent, XInitialization, XServiceInfo
from com.sun.star.style.VerticalAlignment import MIDDLE
from com.sun.star.task import XJob
from com.sun.star.util import XUpdatable

# Şeridin sol üstündeki hızlı erişim çubuğuna eklenen Dosya düğmesinin komutu.
# LibreOffice bu komutu tanımaz; yakalayıcı karşılar ve Dosya menüsünü açar.
FILE_MENU_COMMAND = ".uno:LinwasFileMenu"
SHORTCUTS_TOOLBAR = "private:resource/toolbar/notebookbarshortcuts"
# Sade şeritteki "Daha fazla araç" düğmesi: tüm araçların olduğu tam şeride geçer.
MORE_TOOLS_COMMAND = ".uno:LinwasMoreTools"
# Sade şeridin Dosya sekmesindeki öğe.
FILE_TAB_COMMAND = ".uno:LinwasFileTab"
FULL_RIBBON_COMMAND = ".uno:ToolbarMode?Mode:string=notebookbar.ui"
SIMPLE_RIBBON_UI = "linwas_simple.ui"
APP_NAMES = {
    "com.sun.star.text.TextDocument": "Writer",
    "com.sun.star.sheet.SpreadsheetDocument": "Calc",
    "com.sun.star.presentation.PresentationDocument": "Impress",
}
EXTENSION_ID = "org.linwas.officelook"

# Writer ve Calc kısayolları kendi Open varyantlarını kullanır.
OPEN_COMMANDS = (".uno:Open", ".uno:OpenFromWriter", ".uno:OpenFromCalc")
INTERCEPTED = (".uno:SaveAs", ".uno:Save") + OPEN_COMMANDS

# (ad, ne zaman seçilir, süzgeç, uzantı, dışa aktarım mı, önerilen mi)
FORMATS = {
    "com.sun.star.text.TextDocument": [
        (
            "Word belgesi (.docx)",
            "Başkasına göndereceksen bunu seç. Word kullananlar sorunsuz açar.",
            "MS Word 2007 XML",
            "docx",
            False,
            True,
        ),
        (
            "PDF (.pdf)",
            "Yalnızca okunur, kimse değiştiremez. Göndermek ve yazdırmak için ideal.",
            "writer_pdf_Export",
            "pdf",
            True,
            False,
        ),
        (
            "LibreOffice'in kendi biçimi (.odt)",
            "Yalnızca kendin kullanacaksan. Word'de bazı biçimler değişebilir.",
            "writer8",
            "odt",
            False,
            False,
        ),
        (
            "Düz yazı (.txt)",
            "Yalnızca yazı kalır; biçim, tablo ve resimler kaybolur.",
            "Text",
            "txt",
            False,
            False,
        ),
    ],
    "com.sun.star.sheet.SpreadsheetDocument": [
        (
            "Excel çalışma kitabı (.xlsx)",
            "Başkasına göndereceksen bunu seç. Excel kullananlar sorunsuz açar.",
            "Calc MS Excel 2007 XML",
            "xlsx",
            False,
            True,
        ),
        (
            "PDF (.pdf)",
            "Yalnızca okunur, kimse değiştiremez. Göndermek ve yazdırmak için ideal.",
            "calc_pdf_Export",
            "pdf",
            True,
            False,
        ),
        (
            "LibreOffice'in kendi biçimi (.ods)",
            "Yalnızca kendin kullanacaksan. Excel'de bazı biçimler değişebilir.",
            "calc8",
            "ods",
            False,
            False,
        ),
        (
            "Virgülle ayrılmış değerler (.csv)",
            "Yalnızca bu sayfadaki değerler kalır; formüller, biçim ve diğer sayfalar kaybolur.",
            "Text - txt - csv (StarCalc)",
            "csv",
            False,
            False,
        ),
    ],
    "com.sun.star.presentation.PresentationDocument": [
        (
            "PowerPoint sunusu (.pptx)",
            "Başkasına göndereceksen bunu seç. PowerPoint kullananlar sorunsuz açar.",
            "Impress MS PowerPoint 2007 XML",
            "pptx",
            False,
            True,
        ),
        (
            "PDF (.pdf)",
            "Yalnızca okunur, kimse değiştiremez. Göndermek ve yazdırmak için ideal.",
            "impress_pdf_Export",
            "pdf",
            True,
            False,
        ),
        (
            "LibreOffice'in kendi biçimi (.odp)",
            "Yalnızca kendin kullanacaksan. PowerPoint'te bazı biçimler değişebilir.",
            "impress8",
            "odp",
            False,
            False,
        ),
    ],
    "com.sun.star.drawing.DrawingDocument": [
        (
            "LibreOffice'in kendi biçimi (.odg)",
            "Çizimi daha sonra düzenlemek için.",
            "draw8",
            "odg",
            False,
            True,
        ),
        (
            "PDF (.pdf)",
            "Yalnızca okunur, kimse değiştiremez. Göndermek ve yazdırmak için ideal.",
            "draw_pdf_Export",
            "pdf",
            True,
            False,
        ),
    ],
}
OPENABLE_EXTENSIONS = {
    "odt",
    "ott",
    "ods",
    "ots",
    "odp",
    "otp",
    "odg",
    "otg",
    "docx",
    "doc",
    "dotx",
    "rtf",
    "txt",
    "xlsx",
    "xls",
    "xltx",
    "csv",
    "pptx",
    "ppt",
    "potx",
    "pdf",
}
NEW_DOCUMENTS = [
    ("Boş belge", "private:factory/swriter"),
    ("Boş hesap tablosu", "private:factory/scalc"),
    ("Boş sunum", "private:factory/simpress"),
]
# Sol menü: (anahtar, etiket). Görünüm açanlar BASLIK'ta, diğerleri komut çalıştırır.
MENU = [
    ("new", "Yeni"),
    ("open", "Aç"),
    ("save", "Kaydet"),
    ("save_as", "Farklı kaydet"),
    ("print_view", "Yazdır"),
    ("export", "Dışa aktar"),
    ("share_doc", "Paylaş"),
    ("info", "Belge bilgisi"),
]
BOTTOM_MENU = [
    ("ribbon", "Tam şeride geç"),
    ("settings", "Ayarlar"),
    ("look_settings", "Office görünümü ayarları"),
    ("close", "Belgeyi kapat"),
]
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "linwas-office-look")
DISABLED_FLAG = os.path.join(CONFIG_DIR, "disabled")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
DEFAULT_SETTINGS = {"file_menu": True, "autosave_minutes": 2}
# Ayarlar Linwas'ın "Office görünümü" sayfasında; Linwas yoksa paketin kendi aracı açılır.
SETTINGS_COMMANDS = (["linwas", "--page", "office_look"], ["linwas-office-look", "dialog"])
TITLES = {
    "save_as": "Farklı kaydet",
    "export": "Dışa aktar",
    "open": "Aç",
    "new": "Yeni",
    "info": "Belge bilgisi",
    "print_view": "Yazdır",
}
COMMANDS = {
    "share_doc": ".uno:SendMail",
    "settings": ".uno:OptionsTreeDialog",
    "close": ".uno:CloseDoc",
}

# Tasarımın renkleri.
MENU_BACKGROUND = 0x0B5D57
MENU_SELECTED = 0x0F7A72
MENU_TEXT = 0xE6F4F1
WHITE = 0xFFFFFF
TEXT = 0x1F2933
SECONDARY_TEXT = 0x52606D
BORDER = 0xBCC4CC
PLACE_SELECTED = 0xD6ECE9
CARD_SELECTED = 0xEEF7F6
ACCENT = 0x0B5D57

MENU_WIDTH = 240
LEFT_COLUMN = 280
PLACE_COUNT = 10
CARD_COUNT = 4
TILE_COUNT = 12
TILE_WIDTH = 150
TILE_HEIGHT = 196

TEMPLATE_ROOT = "/usr/lib/libreoffice/share/template"
TEMPLATE_EXTENSIONS = {
    "com.sun.star.text.TextDocument": "ott",
    "com.sun.star.sheet.SpreadsheetDocument": "ots",
    "com.sun.star.presentation.PresentationDocument": "otp",
    "com.sun.star.drawing.DrawingDocument": "otg",
}
# Parolayla şifreli kaydedilebilen biçimler; PDF parolası süzgeç verisiyle verilir.
PASSWORD_FORMATS = {"docx", "odt", "xlsx", "ods", "pptx", "odp", "odg", "pdf"}
OOXML = {"docx", "xlsx", "pptx"}
# Yazdır önizlemesi: belge PDF'e aktarılır, sayfalar pdftoppm ile resme çevrilir.
PREVIEW_FILTERS = {
    "com.sun.star.text.TextDocument": "writer_pdf_Export",
    "com.sun.star.sheet.SpreadsheetDocument": "calc_pdf_Export",
    "com.sun.star.presentation.PresentationDocument": "impress_pdf_Export",
    "com.sun.star.drawing.DrawingDocument": "draw_pdf_Export",
}
PAGE_CHOICES = ["Tüm sayfalar", "Yalnız bu sayfa", "Belirli sayfalar"]
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "linwas-office-look")

# Çerçeve -> yakalayıcı, çerçeve -> menü ve belge -> rozet eşlemeleri. pyuno nesneleri
# karşılaştırılabilir ama sözlük anahtarı olamaz; bu yüzden listeler.
_interceptors = []
_menus = []
_badges = []


def user_settings():
    """Kullanıcının ayarları; dosya yoksa ya da bozuksa varsayılanlar."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return settings
    if isinstance(data.get("file_menu"), bool):
        settings["file_menu"] = data["file_menu"]
    if isinstance(data.get("autosave_minutes"), int) and 0 <= data["autosave_minutes"] <= 60:
        settings["autosave_minutes"] = data["autosave_minutes"]
    return settings


def _find(pairs, key):
    """(anahtar, nesne) çiftlerinde anahtarı arar; pyuno nesneleri sözlük anahtarı olamıyor."""
    return next((o for k, o in pairs if k == key), None)


def _prop(name, value):
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


def _xdg_dir(kind, fallbacks):
    try:
        path = subprocess.run(
            ["xdg-user-dir", kind], capture_output=True, text=True, timeout=2
        ).stdout.strip()
        if path and os.path.isdir(path):
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    home = os.path.expanduser("~")
    return next(
        (os.path.join(home, y) for y in fallbacks if os.path.isdir(os.path.join(home, y))), home
    )


def _usb_drives():
    user = os.path.basename(os.path.expanduser("~"))
    return sorted(
        y
        for y in glob.glob(f"/media/{user}/*") + glob.glob(f"/run/media/{user}/*")
        if os.path.isdir(y)
    )


def _network_and_cloud():
    """Bağlı ağ paylaşımları (gvfs) ve eşitlenen bulut klasörleri: (etiket, yol)."""
    places = []
    for path in sorted(glob.glob(f"/run/user/{os.getuid()}/gvfs/*")):
        name = os.path.basename(path)
        fields = dict(p.split("=", 1) for p in name.split(":", 1)[-1].split(",") if "=" in p)
        label = fields.get("share") or fields.get("host") or fields.get("server") or name
        places.append((f"Ağ: {label}", path))
    home = os.path.expanduser("~")
    for name in ("Nextcloud", "ownCloud", "Dropbox", "pCloudDrive"):
        if os.path.isdir(os.path.join(home, name)):
            places.append((f"Bulut: {name}", os.path.join(home, name)))
    return places


def _cache_file(key, data):
    """Küçük resmi önbelleğe yazar, dosya URL'sini döndürür."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.sha1(key.encode()).hexdigest() + ".png")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    return uno.systemPathToFileUrl(path)


def _templates(kind):
    """Belge türüne uyan şablonlar: (başlık, dosya yolu, küçük resim URL'si ya da None)."""
    extension = TEMPLATE_EXTENSIONS.get(kind)
    if extension is None:
        return []
    result = []
    for path in sorted(glob.glob(f"{TEMPLATE_ROOT}/*/**/*.{extension}", recursive=True)):
        if "/wizard/" in path:
            continue
        title = os.path.splitext(os.path.basename(path))[0].replace("_", " ").replace("-", " ")
        image = None
        try:
            with zipfile.ZipFile(path) as z:
                match = re.search(
                    r"<dc:title>([^<]+)</dc:title>", z.read("meta.xml").decode("utf-8", "replace")
                )
                if match:
                    title = match.group(1)
                if "Thumbnails/thumbnail.png" in z.namelist():
                    image = _cache_file(
                        f"{path}:{os.path.getmtime(path)}", z.read("Thumbnails/thumbnail.png")
                    )
        except (OSError, KeyError, zipfile.BadZipFile):
            pass
        result.append((title, path, image))
    return result


def _document_name(model):
    """Başlıkta ve önerilen dosya adında kullanılan ad ("Adsız 1", "rapor.docx")."""
    if model.hasLocation():
        return os.path.basename(uno.fileUrlToSystemPath(model.getLocation()))
    return model.getTitle()


def _document_type(model):
    return next((s for s in FORMATS if model.supportsService(s)), None)


def _add_file_button(ctx, frame):
    """Uygulamanın hızlı erişim çubuğunun başına Dosya düğmesini ve simgesini ekler.

    Değişiklik yalnız bellekte yapılır (store() çağrılmaz); her açılışta yeniden eklenir.
    """
    smgr = ctx.ServiceManager
    module = smgr.createInstanceWithContext("com.sun.star.frame.ModuleManager", ctx).identify(frame)
    manager = smgr.createInstanceWithContext(
        "com.sun.star.ui.ModuleUIConfigurationManagerSupplier", ctx
    ).getUIConfigurationManager(module)
    if not manager.hasSettings(SHORTCUTS_TOOLBAR):
        return False

    images = manager.getImageManager()
    place = ctx.getValueByName(
        "/singletons/com.sun.star.deployment.PackageInformationProvider"
    ).getPackageLocation(EXTENSION_ID)
    provider = smgr.createInstanceWithContext("com.sun.star.graphic.GraphicProvider", ctx)
    for command, name in ((FILE_MENU_COMMAND, "file_menu"), (MORE_TOOLS_COMMAND, "more_tools")):
        if images.hasImage(0, command):
            continue
        for kind, size in ((0, 16), (1, 26)):
            image = provider.queryGraphic((_prop("URL", f"{place}/icons/{name}_{size}.png"),))
            uno.invoke(
                images,
                "insertImages",
                (
                    kind,
                    uno.Any("[]string", (command,)),
                    uno.Any("[]com.sun.star.graphic.XGraphic", (image,)),
                ),
            )

    settings = manager.getSettings(SHORTCUTS_TOOLBAR, True)
    for i in range(settings.getCount()):
        if any(
            p.Name == "CommandURL" and p.Value == FILE_MENU_COMMAND for p in settings.getByIndex(i)
        ):
            return False
    item = (
        _prop("CommandURL", FILE_MENU_COMMAND),
        _prop("Label", "Dosya"),
        _prop("Type", uno.Any("short", 0)),
        _prop("IsVisible", True),
    )
    uno.invoke(settings, "insertByIndex", (0, uno.Any("[]com.sun.star.beans.PropertyValue", item)))
    manager.replaceSettings(SHORTCUTS_TOOLBAR, settings)
    return True


def _show_menu(frame, view):
    menu = _find(_menus, frame)
    if menu is None or not menu.is_current():
        if menu is not None:
            menu.destroy()
        menu = FileMenu(uno.getComponentContext(), frame)
        _menus[:] = [(c, m) for c, m in _menus if c != frame] + [(frame, menu)]
    menu.show(view)


def _later(ctx, action):
    """İşlemi olay döngüsüne erteler.

    Belgeyi değiştiren işlemler (yükleme, kapatma, başka pencere) menünün kendi
    olay işleyicisinin içinden çalışırsa LibreOffice kilitlenir.
    """
    async_callback = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.awt.AsyncCallback", ctx
    )
    async_callback.addCallback(_Deferred(action), None)


class _Deferred(unohelper.Base, XCallback):
    def __init__(self, action):
        self.action = action

    def notify(self, data):
        try:
            self.action()
        except Exception:
            traceback.print_exc(file=sys.stderr)


class _RedirectDispatch(unohelper.Base, XDispatch):
    """Durum bilgisini asıl dispatch'e bırakır, yalnız çalıştırmayı menüye yönlendirir."""

    def __init__(self, frame, command, original):
        self.frame = frame
        self.command = command
        self.original = original

    def dispatch(self, url, args):
        model = self.frame.getController().getModel()
        if self.command == ".uno:Save" and model is not None and model.hasLocation():
            self.original.dispatch(url, args)
            return
        try:
            _show_menu(self.frame, "open" if self.command in OPEN_COMMANDS else "save_as")
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self.original.dispatch(url, args)

    def addStatusListener(self, listener, url):
        self.original.addStatusListener(listener, url)

    def removeStatusListener(self, listener, url):
        self.original.removeStatusListener(listener, url)


class _OwnCommandDispatch(unohelper.Base, XDispatch):
    """Eklentinin kendi düğmeleri: her zaman etkin.

    Varsayılan iş Dosya menüsünü açıp kapatmaktır.
    """

    def __init__(self, frame, action=None):
        self.frame = frame
        self.action = action

    def dispatch(self, url, args):
        if self.action is not None:
            _later(uno.getComponentContext(), self.action)
            return
        # Office'teki gibi: menü açıksa düğme belgeye döndürür.
        menu = _find(_menus, self.frame)
        if menu is not None and menu.is_open and menu.is_current():
            menu.close()
        else:
            _show_menu(self.frame, "open")

    def addStatusListener(self, listener, url):
        status = uno.createUnoStruct("com.sun.star.frame.FeatureStateEvent")
        status.FeatureURL = url
        status.IsEnabled = True
        status.Source = self
        listener.statusChanged(status)

    def removeStatusListener(self, listener, url):
        pass


class _Interceptor(unohelper.Base, XDispatchProviderInterceptor):
    def __init__(self, frame):
        self.frame = frame
        self.slave = None
        self.master = None

    def getSlaveDispatchProvider(self):
        return self.slave

    def setSlaveDispatchProvider(self, provider):
        self.slave = provider

    def getMasterDispatchProvider(self):
        return self.master

    def setMasterDispatchProvider(self, provider):
        self.master = provider

    def queryDispatch(self, url, target, flags):
        if url.Complete == FILE_MENU_COMMAND:
            return _OwnCommandDispatch(self.frame)
        if url.Complete == MORE_TOOLS_COMMAND:
            return _OwnCommandDispatch(self.frame, lambda: self.run_original(FULL_RIBBON_COMMAND))
        original = self.slave.queryDispatch(url, target, flags) if self.slave else None
        if original is not None and url.Complete in INTERCEPTED:
            return _RedirectDispatch(self.frame, url.Complete, original)
        return original

    def queryDispatches(self, requests):
        return tuple(self.queryDispatch(i.FeatureURL, i.FrameName, i.SearchFlags) for i in requests)

    def run_original(self, command):
        """Yakalanmamış komutu çalıştırır (sistem penceresi, yazdırma, kapatma)."""
        url = uno.createUnoStruct("com.sun.star.util.URL")
        url.Complete = command
        ctx = uno.getComponentContext()
        transformer = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.util.URLTransformer", ctx
        )
        _, url = transformer.parseStrict(url)
        original = self.slave.queryDispatch(url, "", 0)
        if original is not None:
            original.dispatch(url, ())


class Job(unohelper.Base, XJob, XServiceInfo):
    IMPLEMENTATION = "org.linwas.officelook.Job"

    def __init__(self, ctx):
        self.ctx = ctx

    def execute(self, args):
        try:
            self._install(args)
        except Exception:
            traceback.print_exc(file=sys.stderr)
        return None

    def _install(self, args):
        if os.path.exists(DISABLED_FLAG):
            return  # kullanıcı "Yalnız benim için kapat" dedi
        settings = user_settings()
        environment = next((a.Value for a in args if a.Name == "Environment"), ())
        values = {a.Name: a.Value for a in environment}
        frame = values.get("Frame")
        model = values.get("Model")
        if frame is None and model is not None:
            frame = model.getCurrentController().getFrame()
        if frame is None:
            return
        if settings["file_menu"] and _find(_interceptors, frame) is None:
            interceptor = _Interceptor(frame)
            frame.registerDispatchProviderInterceptor(interceptor)
            _interceptors.append((frame, interceptor))
            try:
                _add_file_button(self.ctx, frame)
            except Exception:
                traceback.print_exc(file=sys.stderr)
            # Çubuktaki denetçiler dispatch'leri yeniden sorsun; Dosya düğmesi etkinleşir.
            frame.contextChanged()
        # Aynı çerçeveye başka belge yüklenebilir; rozet belge başına kurulur.
        if model is not None and _find(_badges, model) is None:
            _badges.append((model, SaveBadge(frame, model, settings["autosave_minutes"])))

    def getImplementationName(self):
        return self.IMPLEMENTATION

    def supportsService(self, name):
        return name == self.IMPLEMENTATION

    def getSupportedServiceNames(self):
        return (self.IMPLEMENTATION,)


class SaveBadge(unohelper.Base, XDocumentEventListener):
    """Pencere başlığını "<ad> — <kayıt durumu> - <uygulama>" biçiminde tutar."""

    EVENTS = {
        "OnModifyChanged",
        "OnSaveDone",
        "OnSaveAsDone",
        "OnSaveToDone",
        "OnTitleChanged",
        "OnLoad",
        "OnNew",
    }

    def __init__(self, frame, model, autosave_minutes):
        self.frame = frame
        self.model = model
        self.interval = autosave_minutes * 60
        self.ctx = uno.getComponentContext()
        # LibreOffice'in kendi başlığının son parçası uygulamanın adıdır.
        self.app = frame.getTitle().rsplit(" - ", 1)[-1]
        self.stop = threading.Event()
        model.addDocumentEventListener(self)
        self.update_title()
        if self.interval > 0:
            threading.Thread(target=self._schedule, daemon=True).start()

    def _schedule(self):
        # Kayıt UNO'yu ana iş parçacığından kullanmalı; bu yüzden yalnız sıraya konur.
        while not self.stop.wait(self.interval):
            _later(self.ctx, self._autosave)

    def _autosave(self):
        if self.stop.is_set():
            return
        m = self.model
        if m.hasLocation() and m.isModified() and not m.isReadonly():
            m.store()

    def update_title(self):
        if self.model.isModified():
            status = "Kaydedilmemiş değişiklikler"
        elif self.model.hasLocation():
            status = "Kaydedildi"
        else:
            status = "Henüz kaydedilmedi"
        self.frame.setTitle(f"{_document_name(self.model)} — {status} - {self.app}")

    def documentEventOccured(self, event):
        if event.EventName in self.EVENTS:
            try:
                self.update_title()
            except Exception:
                traceback.print_exc(file=sys.stderr)

    def disposing(self, event):
        self.stop.set()
        _badges[:] = [(m, r) for m, r in _badges if r is not self]


class _Listener(
    unohelper.Base, XActionListener, XItemListener, XKeyListener, XMouseListener, XWindowListener
):
    """Menü olaylarını tek bir geri çağırmaya toplar."""

    def __init__(self, callback):
        self.callback = callback

    def actionPerformed(self, event):
        self.callback("action", event)

    def itemStateChanged(self, event):
        self.callback("select", event)

    def keyPressed(self, event):
        if event.KeyCode == RETURN:
            self.callback("enter", event)
        elif event.KeyCode == ESCAPE:
            self.callback("escape", event)
        elif event.KeyCode == TAB:
            self.callback("tab", event)

    def keyReleased(self, event):
        pass

    def mousePressed(self, event):
        self.callback("click", event)

    def mouseReleased(self, event):
        pass

    def mouseEntered(self, event):
        pass

    def mouseExited(self, event):
        pass

    def windowResized(self, event):
        self.callback("resize", event)

    def windowMoved(self, event):
        pass

    def windowShown(self, event):
        pass

    def windowHidden(self, event):
        pass

    def disposing(self, event):
        pass


class FileMenu:
    TOP = 40
    MARGIN = 48
    COLUMN_GAP = 48
    ROW_HEIGHT = 44
    PLACE_HEIGHT = 48
    LABEL_HEIGHT = 20
    CARD_HEIGHT = 70
    # Düz pencerede Tab kendiliğinden ilerlemiyor; Farklı kaydet için odak sırası.
    FOCUS_ORDER = ("name", "password1", "password2", "tamam")

    def __init__(self, ctx, frame):
        self.ctx = ctx
        self.frame = frame
        self.controller = frame.getController()
        self.smgr = ctx.ServiceManager
        self.toolkit = self.smgr.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)
        self.container = frame.getContainerWindow()
        self.listener = _Listener(self._on_event)
        self.k = {}
        self.clickables = []
        self.directory = _xdg_dir("DOCUMENTS", ("Belgeler", "Documents"))
        self.places = []
        self.place = None
        self.folder_browser = False
        self.entries = []
        self.pending_overwrite = None
        self.view = "save_as"
        self.is_open = False

        self.all_formats = FORMATS.get(_document_type(self.controller.getModel()), [])
        self.formats = self.all_formats
        self.format_index = 0

        self.left = self._window(self.container, MENU_BACKGROUND)
        self.right = self._window(self.container, WHITE)
        # Ana pencerenin istemci alanının ekran konumunu ölçmek için (0, 0)'da kalan 1×1 pencere.
        self.probe = self._window(self.container, WHITE)
        self.probe.setPosSize(0, 0, 1, 1, POSSIZE)
        self.probe.setVisible(True)

        self._menu_item("back", "←   Belgeye dön", bold=True, color=WHITE)
        for key, label in MENU + BOTTOM_MENU:
            self._menu_item(key, label)

        s = self.right
        self._add(
            s, "title", "FixedText", font_size=21, bold=True, TextColor=TEXT, BackgroundColor=WHITE
        )
        self._add(
            s,
            "place_label",
            "FixedText",
            font_size=10,
            bold=True,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        for i in range(PLACE_COUNT):
            self._add(
                s,
                f"place{i}",
                "FixedText",
                font_size=11,
                TextColor=TEXT,
                BackgroundColor=WHITE,
                VerticalAlign=MIDDLE,
            )
            self._clickable(self.k[f"place{i}"], lambda i=i: self._select_place(i))
        self._add(
            s,
            "selected_place",
            "FixedText",
            font_size=10,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
            MultiLine=True,
        )
        self._add(s, "folders", "ListBox", Dropdown=False)

        self._add(
            s,
            "name_label",
            "FixedText",
            Label="Dosya adı",
            font_size=10,
            bold=True,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self._add(s, "name", "Edit", font_size=11)
        self._add(
            s,
            "format_label",
            "FixedText",
            Label="Hangi biçimde kaydedilsin?",
            font_size=10,
            bold=True,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self.cards = [self._card(i) for i in range(CARD_COUNT)]

        self._add(
            s,
            "files_label",
            "FixedText",
            font_size=10,
            bold=True,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self._add(s, "files", "ListBox", Dropdown=False, font_size=11)

        self._add(
            s,
            "status",
            "FixedText",
            Label="",
            font_size=10,
            TextColor=TEXT,
            BackgroundColor=WHITE,
            MultiLine=True,
        )
        self._add(
            s,
            "tamam",
            "Button",
            Label="Kaydet",
            font_size=11,
            bold=True,
            DefaultButton=True,
            BackgroundColor=ACCENT,
            TextColor=WHITE,
        )
        self._add(
            s,
            "cancel",
            "Button",
            Label="Vazgeç",
            font_size=11,
            BackgroundColor=WHITE,
            TextColor=TEXT,
        )
        self._add(
            s,
            "hint",
            "FixedText",
            font_size=10,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
            MultiLine=True,
            Align=2,
            Label="Varsayılan biçimi Ayarlar › Yükle/Kaydet › Genel bölümünden değiştirebilirsin.",
        )
        for i, (label, _) in enumerate(NEW_DOCUMENTS):
            self._add(s, f"new{i}", "Button", Label=label, font_size=12)
        self._add(
            s,
            "templates_label",
            "FixedText",
            Label="Şablonlar",
            font_size=10,
            bold=True,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self.tiles = [self._tile(i) for i in range(TILE_COUNT)]
        self.tile_items = []
        self.tile_page = 0
        self._add(s, "prev", "Button", Label="‹  Önceki")
        self._add(s, "next", "Button", Label="Sonraki  ›")
        self._add(
            s,
            "page_label",
            "FixedText",
            font_size=10,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
            Align=1,
            VerticalAlign=MIDDLE,
        )
        self._add(
            s,
            "printer_label",
            "FixedText",
            Label="Yazıcı",
            font_size=10,
            bold=True,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self._add(s, "printer", "ListBox", Dropdown=True, LineCount=10, font_size=11)
        self._add(
            s,
            "copies_label",
            "FixedText",
            Label="Kopya sayısı",
            font_size=10,
            bold=True,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self._add(
            s,
            "copies",
            "NumericField",
            Value=1.0,
            ValueMin=1.0,
            ValueMax=999.0,
            DecimalAccuracy=0,
            Spin=True,
            font_size=11,
        )
        self._add(
            s,
            "pages_label",
            "FixedText",
            Label="Hangi sayfalar?",
            font_size=10,
            bold=True,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self._add(
            s, "pages", "ListBox", Dropdown=True, font_size=11, StringItemList=tuple(PAGE_CHOICES)
        )
        self._add(s, "range", "Edit", font_size=11)
        self._add(
            s,
            "range_label",
            "FixedText",
            Label="Örnek: 1-3, 5",
            font_size=9,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self._add(
            s,
            "collate",
            "CheckBox",
            Label="Kopyaları harmanla",
            font_size=11,
            BackgroundColor=WHITE,
            State=1,
        )
        self._add(s, "advanced", "Button", Label="Gelişmiş yazdırma ayarları…")
        self._add(
            s,
            "preview",
            "ImageControl",
            Border=1,
            ScaleImage=True,
            ScaleMode=1,
            BackgroundColor=0xF6F7F9,
        )
        self._add(s, "preview_prev", "Button", Label="‹")
        self._add(s, "preview_next", "Button", Label="›")
        self._add(
            s,
            "preview_page",
            "FixedText",
            font_size=10,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
            Align=1,
            VerticalAlign=MIDDLE,
        )
        self.preview_page = 1
        self.preview_count = 0
        self._add(
            s,
            "password_check",
            "CheckBox",
            Label="Parola ile koru",
            font_size=11,
            BackgroundColor=WHITE,
        )
        self._add(s, "password1", "Edit", font_size=11, EchoChar=0x2022)
        self._add(s, "password2", "Edit", font_size=11, EchoChar=0x2022)
        self._add(
            s,
            "password1_label",
            "FixedText",
            Label="Parola",
            font_size=10,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        self._add(
            s,
            "password2_label",
            "FixedText",
            Label="Yeniden",
            font_size=10,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        for i in range(6):
            self._add(
                s,
                f"info_key{i}",
                "FixedText",
                font_size=10,
                bold=True,
                TextColor=SECONDARY_TEXT,
                BackgroundColor=WHITE,
            )
            self._add(
                s,
                f"info_value{i}",
                "FixedText",
                font_size=11,
                TextColor=TEXT,
                BackgroundColor=WHITE,
            )

        for control in self.k.values():
            control.addKeyListener(self.listener)
        for name in (
            "tamam",
            "cancel",
            "folders",
            "files",
            "prev",
            "next",
            "advanced",
            "preview_prev",
            "preview_next",
        ) + tuple(f"new{i}" for i in range(len(NEW_DOCUMENTS))):
            self.k[name].addActionListener(self.listener)
        self.k["password_check"].addItemListener(self.listener)
        self.k["pages"].addItemListener(self.listener)
        self.k["files"].addItemListener(self.listener)
        self.container.addWindowListener(self.listener)

    # --- Pencere ve denetimler ---

    def _window(self, parent, color):
        descriptor = uno.createUnoStruct("com.sun.star.awt.WindowDescriptor")
        descriptor.Type = CONTAINER
        descriptor.WindowServiceName = ""
        descriptor.Parent = parent
        descriptor.Bounds = uno.createUnoStruct("com.sun.star.awt.Rectangle", 0, 0, 10, 10)
        descriptor.WindowAttributes = 0
        window = self.toolkit.createWindow(descriptor)
        window.setBackground(color)
        return window

    def _add(self, parent, name, kind, font_size=None, bold=False, **properties):
        model = self.smgr.createInstanceWithContext(
            f"com.sun.star.awt.UnoControl{kind}Model", self.ctx
        )
        if font_size is not None:
            fd = model.FontDescriptor
            fd.Height = font_size
            if bold:
                fd.Weight = 150.0
            model.FontDescriptor = fd
        for key, value in properties.items():
            if isinstance(value, tuple):
                # pyuno demetleri []any olarak geçirir; dize listesi açıkça belirtilmeli.
                uno.invoke(model, "setPropertyValue", (key, uno.Any("[]string", value)))
            else:
                model.setPropertyValue(key, value)
        control = self.smgr.createInstanceWithContext(
            f"com.sun.star.awt.UnoControl{kind}", self.ctx
        )
        control.setModel(model)
        control.createPeer(self.toolkit, parent)
        self.k[name] = control
        return control

    def _clickable(self, target, action):
        target.addMouseListener(self.listener)
        self.clickables.append((target, action))

    def _menu_item(self, key, label, bold=False, color=MENU_TEXT):
        control = self._add(
            self.left,
            "m_" + key,
            "FixedText",
            Label="    " + label,
            font_size=11,
            bold=bold,
            TextColor=color,
            BackgroundColor=MENU_BACKGROUND,
            VerticalAlign=MIDDLE,
        )
        self._clickable(control, lambda: self._menu_selected(key))

    def _card(self, i):
        """Biçim kartı: 1-2 px çerçeve için dış pencere, içinde düğme, ad, rozet ve açıklama."""
        outer = self._window(self.right, BORDER)
        inner = self._window(outer, WHITE)
        outer.setVisible(True)
        inner.setVisible(True)
        card = {"outer": outer, "inner": inner}
        card["radio"] = self._add(
            inner, f"card{i}_r", "RadioButton", Label="", BackgroundColor=WHITE
        )
        card["name"] = self._add(
            inner,
            f"card{i}_a",
            "FixedText",
            font_size=11,
            bold=True,
            TextColor=TEXT,
            BackgroundColor=WHITE,
        )
        card["badge"] = self._add(
            inner,
            f"card{i}_o",
            "FixedText",
            Label="Önerilen",
            font_size=9,
            bold=True,
            TextColor=WHITE,
            BackgroundColor=ACCENT,
            Align=1,
            VerticalAlign=MIDDLE,
        )
        card["description"] = self._add(
            inner,
            f"card{i}_c",
            "FixedText",
            font_size=10.5,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
            MultiLine=True,
        )
        for target in (inner, card["name"], card["description"]):
            self._clickable(target, lambda i=i: self._select_format(i))
        card["radio"].addItemListener(_Listener(lambda kind, event, i=i: self._select_format(i)))
        return card

    def _tile(self, i):
        """Küçük resimli kutucuk: şablon ya da son kullanılan dosya."""
        outer = self._window(self.right, BORDER)
        inner = self._window(outer, WHITE)
        outer.setPosSize(0, 0, TILE_WIDTH, TILE_HEIGHT, POSSIZE)
        inner.setPosSize(1, 1, TILE_WIDTH - 2, TILE_HEIGHT - 2, POSSIZE)
        inner.setVisible(True)
        tile = {"outer": outer, "inner": inner}
        tile["image"] = self._add(
            inner,
            f"tile{i}_r",
            "ImageControl",
            Border=0,
            ScaleImage=True,
            ScaleMode=1,
            BackgroundColor=0xF6F7F9,
        )
        tile["name"] = self._add(
            inner,
            f"tile{i}_a",
            "FixedText",
            font_size=10,
            bold=True,
            TextColor=TEXT,
            BackgroundColor=WHITE,
        )
        tile["subtitle"] = self._add(
            inner,
            f"tile{i}_t",
            "FixedText",
            font_size=9,
            TextColor=SECONDARY_TEXT,
            BackgroundColor=WHITE,
        )
        tile["image"].setPosSize(8, 8, TILE_WIDTH - 18, TILE_HEIGHT - 66, POSSIZE)
        tile["name"].setPosSize(8, TILE_HEIGHT - 54, TILE_WIDTH - 18, 20, POSSIZE)
        tile["subtitle"].setPosSize(8, TILE_HEIGHT - 32, TILE_WIDTH - 18, 20, POSSIZE)
        for target in (inner, tile["image"], tile["name"], tile["subtitle"]):
            self._clickable(target, lambda i=i: self._tile_clicked(i))
        return tile

    def is_current(self):
        """Menü bu çerçevenin şu anki belgesine mi ait? Belge değişince yeniden kurulur."""
        return self.controller == self.frame.getController()

    def destroy(self):
        self.container.removeWindowListener(self.listener)
        for k in self.k.values():
            k.dispose()
        for card in self.cards + self.tiles:
            card["inner"].dispose()
            card["outer"].dispose()
        for p in (self.left, self.right, self.probe):
            p.dispose()

    def _area(self):
        """Belge penceresinin kapladığı alan, ana pencereye göre (şerit ve durum çubuğu hariç).

        Belge penceresinin konumu kendi üst penceresine göre verildiği için ekran
        konumları farkından hesaplanır.
        """
        document = self.frame.getComponentWindow()
        b = document.getPosSize()
        try:
            a = document.getAccessibleContext().getLocationOnScreen()
            k = self.probe.getAccessibleContext().getLocationOnScreen()
            return uno.createUnoStruct(
                "com.sun.star.awt.Rectangle", a.X - k.X, a.Y - k.Y, b.Width, b.Height
            )
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return b

    # --- Gösterme / gizleme ---

    def show(self, view):
        model = self.controller.getModel()
        self.pending_overwrite = None
        self.folder_browser = False
        if model.hasLocation():
            path = uno.fileUrlToSystemPath(model.getLocation())
            self.directory = os.path.dirname(path)
            self.base_name = os.path.splitext(os.path.basename(path))[0]
        else:
            self.base_name = _document_name(model)
        if not self.is_open:
            self.frame.getComponentWindow().setVisible(False)
            self.is_open = True
        self.left.setVisible(True)
        self.right.setVisible(True)
        self._switch_view(view)

    def close(self):
        if not self.is_open:
            return
        self.is_open = False
        self.left.setVisible(False)
        self.right.setVisible(False)
        window = self.frame.getComponentWindow()
        window.setVisible(True)
        window.setFocus()

    def _switch_view(self, view):
        self.view = view
        for key, _ in MENU + BOTTOM_MENU:
            selected = key == view
            model = self.k["m_" + key].getModel()
            model.BackgroundColor = MENU_SELECTED if selected else MENU_BACKGROUND
            model.TextColor = WHITE if selected else MENU_TEXT
            fd = model.FontDescriptor
            fd.Weight = 150.0 if selected else 100.0
            model.FontDescriptor = fd
        self.k["title"].getModel().Label = TITLES[view]
        self.k["m_ribbon"].getModel().Label = "    " + (
            "Tam şeride geç" if self._is_simple() else "Sade şeride dön"
        )
        self._status("")

        if view in ("save_as", "export"):
            self.formats = (
                [b for b in self.all_formats if b[4]] if view == "export" else self.all_formats
            )
            self.format_index = next((i for i, b in enumerate(self.formats) if b[5]), 0)
            self.k["name"].setText(
                self.base_name + ("." + self.formats[self.format_index][3] if self.formats else "")
            )
            self.k["tamam"].getModel().Label = "Dışa aktar" if view == "export" else "Kaydet"
            self.k["password_check"].getModel().State = 0
            self.k["password1"].setText("")
            self.k["password2"].setText("")
            self.k["place_label"].getModel().Label = "Nereye kaydedilsin?"
            self._fill_cards()
            self._fill_places(recent=False)
        elif view == "open":
            self.k["tamam"].getModel().Label = "Aç"
            self.k["place_label"].getModel().Label = "Nereden açılsın?"
            self._fill_places(recent=True)
        elif view == "new":
            kind = _document_type(self.controller.getModel())
            self._fill_tiles(
                [
                    (
                        b,
                        "Şablon",
                        r,
                        (lambda y=y: self._load(uno.systemPathToFileUrl(y), as_template=True)),
                    )
                    for b, y, r in _templates(kind)
                ]
            )
        elif view == "info":
            self._fill_info()
        elif view == "print_view":
            self.k["tamam"].getModel().Label = "Yazdır"
            self._prepare_print()
        self._layout()
        focus = {
            "save_as": "name",
            "export": "tamam",
            "open": "files",
            "new": "new0",
            "info": "m_back",
            "print_view": "tamam",
        }[view]
        self.k[focus].setFocus()

    # --- Yerleşim ---

    def _layout(self):
        area = self._area()
        menu_width = min(MENU_WIDTH, area.Width // 4)
        self.left.setPosSize(area.X, area.Y, menu_width, area.Height, POSSIZE)
        self.right.setPosSize(
            area.X + menu_width, area.Y, area.Width - menu_width, area.Height, POSSIZE
        )

        y = 16
        self.k["m_back"].setPosSize(12, y, menu_width - 24, self.ROW_HEIGHT, POSSIZE)
        y += self.ROW_HEIGHT + 16
        for key, _ in MENU:
            self.k["m_" + key].setPosSize(12, y, menu_width - 24, self.ROW_HEIGHT, POSSIZE)
            y += self.ROW_HEIGHT
        y = area.Height - 16 - len(BOTTOM_MENU) * self.ROW_HEIGHT
        for key, _ in BOTTOM_MENU:
            self.k["m_" + key].setPosSize(12, y, menu_width - 24, self.ROW_HEIGHT, POSSIZE)
            y += self.ROW_HEIGHT

        visible = self._visible = {"title"}
        visible_cards = 0
        content_width = area.Width - menu_width - 2 * self.MARGIN
        x = self.MARGIN

        def put(name, left, parent, width, size):
            self.k[name].setPosSize(left, parent, width, size, POSSIZE)
            visible.add(name)

        put("title", x, self.TOP, content_width, 36)
        y0 = self.TOP + 36 + 20
        v = self.view

        if v in ("save_as", "export", "open"):
            # Sol sütun: konumlar.
            y = y0
            put("place_label", x, y, LEFT_COLUMN, self.LABEL_HEIGHT)
            y += self.LABEL_HEIGHT + 6
            for i in range(len(self.places)):
                put(f"place{i}", x, y, LEFT_COLUMN, self.PLACE_HEIGHT)
                y += self.PLACE_HEIGHT + 6
            y += 8
            put("selected_place", x, y, LEFT_COLUMN, 2 * self.LABEL_HEIGHT)
            y += 2 * self.LABEL_HEIGHT + 8
            if self.folder_browser:
                put("folders", x, y, LEFT_COLUMN, max(120, area.Height - y - self.MARGIN))

            # Sağ sütun.
            rx = x + LEFT_COLUMN + self.COLUMN_GAP
            right_width = max(240, min(content_width - LEFT_COLUMN - self.COLUMN_GAP, 680))
            y = y0
            if v in ("save_as", "export"):
                put("name_label", rx, y, right_width, self.LABEL_HEIGHT)
                y += self.LABEL_HEIGHT + 8
                put("name", rx, y, right_width, self.ROW_HEIGHT)
                y += self.ROW_HEIGHT + 14
                put("format_label", rx, y, right_width, self.LABEL_HEIGHT)
                y += self.LABEL_HEIGHT + 8
                for i, card in enumerate(self.cards[: len(self.formats)]):
                    self._layout_card(card, i, rx, y, right_width)
                    y += self.CARD_HEIGHT + 8
                visible_cards = len(self.formats)
                if self.formats and self.formats[self.format_index][3] in PASSWORD_FORMATS:
                    # Tek satır: [x] Parola ile koru   Parola [....]   Yeniden [....]
                    put("password_check", rx, y + 6, 170, 24)
                    if self.k["password_check"].getModel().State == 1:
                        field_width = (right_width - 170 - 2 * 70 - 24) // 2
                        px = rx + 170
                        put("password1_label", px, y + 8, 64, self.LABEL_HEIGHT)
                        put("password1", px + 66, y, field_width, 36)
                        px += 66 + field_width + 12
                        put("password2_label", px, y + 8, 64, self.LABEL_HEIGHT)
                        put("password2", px + 66, y, field_width, 36)
                    y += 36 + 8
            elif self._recent_selected():
                put("files_label", rx, y, right_width, self.LABEL_HEIGHT)
                y += self.LABEL_HEIGHT + 8
                y = self._layout_tiles(
                    rx, y, content_width - (rx - x), area.Height - y - self.MARGIN - 90, put
                )
            else:
                put("files_label", rx, y, right_width, self.LABEL_HEIGHT)
                y += self.LABEL_HEIGHT + 8
                size = max(
                    160,
                    area.Height - y - self.MARGIN - self.ROW_HEIGHT - 3 * self.LABEL_HEIGHT - 16,
                )
                put("files", rx, y, right_width, size)
                y += size + 10
            put("status", rx, y, right_width, 2 * self.LABEL_HEIGHT)
            y += 2 * self.LABEL_HEIGHT + 4
            if not self._recent_selected():
                put("tamam", rx, y, 140, self.ROW_HEIGHT)
            put("cancel", rx + (0 if self._recent_selected() else 152), y, 110, self.ROW_HEIGHT)
            if v in ("save_as", "export"):
                put("hint", rx + 280, y, right_width - 280, self.ROW_HEIGHT)
        elif v == "new":
            for i in range(len(NEW_DOCUMENTS)):
                put(f"new{i}", x + i * 212, y0, 200, 72)
            y = y0 + 72 + 28
            if self.tile_items:
                put("templates_label", x, y, content_width, self.LABEL_HEIGHT)
                y += self.LABEL_HEIGHT + 8
                self._layout_tiles(x, y, content_width, area.Height - y - self.MARGIN - 40, put)
        elif v == "print_view":
            y = y0
            for name, size in (
                ("printer_label", self.LABEL_HEIGHT),
                ("printer", 36),
                ("copies_label", self.LABEL_HEIGHT),
                ("copies", 36),
                ("pages_label", self.LABEL_HEIGHT),
                ("pages", 36),
            ):
                put(name, x, y, LEFT_COLUMN, size)
                y += size + (6 if size == self.LABEL_HEIGHT else 16)
            if self.k["pages"].getSelectedItemPos() == 2:
                put("range", x, y - 8, LEFT_COLUMN, 36)
                put("range_label", x, y + 30, LEFT_COLUMN, self.LABEL_HEIGHT)
                y += 60
            put("collate", x, y, LEFT_COLUMN, 24)
            y += 40
            put("status", x, y, LEFT_COLUMN, 2 * self.LABEL_HEIGHT)
            y += 2 * self.LABEL_HEIGHT + 4
            put("tamam", x, y, 140, self.ROW_HEIGHT)
            put("cancel", x + 152, y, 110, self.ROW_HEIGHT)
            y += self.ROW_HEIGHT + 16
            put("advanced", x, y, LEFT_COLUMN, self.ROW_HEIGHT)
            # Sağ: önizleme (A4 oranı) ve sayfa düğmeleri.
            rx = x + LEFT_COLUMN + self.COLUMN_GAP
            size = area.Height - y0 - self.MARGIN - self.ROW_HEIGHT - 12
            width = min(content_width - (rx - x), int(size / 1.414))
            put("preview", rx, y0, width, size)
            nav_y = y0 + size + 12
            put("preview_prev", rx + width // 2 - 110, nav_y, 44, self.ROW_HEIGHT)
            put("preview_page", rx + width // 2 - 60, nav_y, 120, self.ROW_HEIGHT)
            put("preview_next", rx + width // 2 + 66, nav_y, 44, self.ROW_HEIGHT)
        elif v == "info":
            y = y0
            for i in range(6):
                if self.k[f"info_key{i}"].getModel().Label:
                    put(f"info_key{i}", x, y, 200, self.LABEL_HEIGHT)
                    put(f"info_value{i}", x + 210, y, content_width - 210, self.LABEL_HEIGHT)
                    y += self.LABEL_HEIGHT + 14

        for name, control in self.k.items():
            if not name.startswith(("m_", "card", "tile")):
                control.setVisible(name in visible)
        for i, card in enumerate(self.cards):
            card["outer"].setVisible(i < visible_cards)
        for i, tile in enumerate(self.tiles):
            tile["outer"].setVisible(f"tile{i}" in visible)

    def _recent_selected(self):
        return self.view == "open" and bool(self.places) and self.places[self.place][0] == "recent"

    def _fill_tiles(self, items):
        """ogeler: (ad, alt yazı, küçük resim URL'si ya da None, tıklanınca çalışacak işlem)."""
        self.tile_items = items
        self.tile_page = 0

    def _layout_tiles(self, x, y, width, size, put):
        """Kutucukları ızgaraya dizer, sayfalar; ızgaranın altındaki y'yi döndürür."""
        columns = max(1, (width + 12) // (TILE_WIDTH + 12))
        row = max(1, (size + 12) // (TILE_HEIGHT + 12))
        per_page = min(TILE_COUNT, columns * row)
        page_count = max(1, -(-len(self.tile_items) // per_page))
        self.tile_page = min(self.tile_page, page_count - 1)
        first = self.tile_page * per_page
        self.visible_tiles = self.tile_items[first : first + per_page]
        for i, (name, subtitle, image, _) in enumerate(self.visible_tiles):
            tile = self.tiles[i]
            row_index, column = divmod(i, columns)
            tile["outer"].setPosSize(
                x + column * (TILE_WIDTH + 12),
                y + row_index * (TILE_HEIGHT + 12),
                TILE_WIDTH,
                TILE_HEIGHT,
                POSSIZE,
            )
            tile["name"].getModel().Label = name
            tile["subtitle"].getModel().Label = subtitle
            tile["image"].getModel().ImageURL = image or ""
            self._visible.add(f"tile{i}")
        y += -(-len(self.visible_tiles) // columns) * (TILE_HEIGHT + 12)
        if page_count > 1:
            put("prev", x, y, 120, self.ROW_HEIGHT)
            put("page_label", x + 128, y, 80, self.ROW_HEIGHT)
            put("next", x + 216, y, 120, self.ROW_HEIGHT)
            self.k["page_label"].getModel().Label = f"{self.tile_page + 1} / {page_count}"
            self.k["prev"].setEnable(self.tile_page > 0)
            self.k["next"].setEnable(self.tile_page < page_count - 1)
            y += self.ROW_HEIGHT + 8
        return y

    def _tile_clicked(self, i):
        if i < len(getattr(self, "visible_tiles", [])):
            self.visible_tiles[i][3]()

    def _layout_card(self, card, i, x, y, width):
        selected = i == self.format_index
        border = 2 if selected else 1
        background = CARD_SELECTED if selected else WHITE
        card["outer"].setPosSize(x, y, width, self.CARD_HEIGHT, POSSIZE)
        card["outer"].setBackground(ACCENT if selected else BORDER)
        card["inner"].setPosSize(
            border, border, width - 2 * border, self.CARD_HEIGHT - 2 * border, POSSIZE
        )
        card["inner"].setBackground(background)
        name, description, _, _, _, recommended = self.formats[i]
        for part in ("radio", "name", "badge", "description"):
            card[part].getModel().BackgroundColor = background if part != "badge" else ACCENT
        card["radio"].getModel().State = 1 if selected else 0
        card["name"].getModel().Label = name
        card["description"].getModel().Label = description
        inner_width = width - 2 * border
        card["radio"].setPosSize(14, 14, 22, 22, POSSIZE)
        name_width = min(inner_width - 160, 9 * len(name) + 16)
        card["name"].setPosSize(44, 12, name_width, 24, POSSIZE)
        card["badge"].setPosSize(44 + name_width + 6, 13, 84, 22, POSSIZE)
        card["badge"].setVisible(recommended)
        card["description"].setPosSize(
            44, 36, inner_width - 60, self.CARD_HEIGHT - 2 * border - 38, POSSIZE
        )

    # --- İçerik doldurma ---

    def _status(self, text):
        self.k["status"].getModel().Label = text

    def _fill_cards(self):
        for i in range(len(self.cards)):
            if i < len(self.formats):
                self.cards[i]["outer"].setVisible(True)

    def _fill_places(self, recent):
        places = [("recent", "Son kullanılanlar", None)] if recent else []
        places += [
            ("documents", "Belgeler", _xdg_dir("DOCUMENTS", ("Belgeler", "Documents"))),
            ("desktop", "Masaüstü", _xdg_dir("DESKTOP", ("Masaüstü", "Desktop"))),
            ("downloads", "İndirilenler", _xdg_dir("DOWNLOAD", ("İndirilenler", "Downloads"))),
        ]
        for path in _usb_drives():
            places.append(("usb", f"USB bellek ({os.path.basename(path)})", path))
        for label, path in _network_and_cloud():
            places.append(("network", label, path))
        places = places[: PLACE_COUNT - 1] + [("other", "Başka klasör seç…", None)]
        self.places = places
        for i, (_, label, _) in enumerate(places):
            self.k[f"place{i}"].getModel().Label = "    " + label
        # Belgenin bulunduğu yere uyan konum seçili gelir; açarken önce son kullanılanlar.
        self.place = (
            0
            if recent
            else next(
                (
                    i
                    for i, (_, _, path) in enumerate(places)
                    if path and self.directory.startswith(path)
                ),
                len(places) - 1,
            )
        )
        if recent:
            self._list_files()
        self._paint_places()
        self._show_selected_place()

    def _paint_places(self):
        for i in range(len(self.places)):
            model = self.k[f"place{i}"].getModel()
            selected = i == self.place
            model.BackgroundColor = PLACE_SELECTED if selected else WHITE
            model.TextColor = ACCENT if selected else TEXT
            fd = model.FontDescriptor
            fd.Weight = 150.0 if selected else 100.0
            model.FontDescriptor = fd

    def _show_selected_place(self):
        if self.places and self.places[self.place][0] == "recent":
            text = "Son açtığın dosyalar"
        else:
            text = self.directory.replace(os.path.expanduser("~"), "~", 1)
            for _, label, path in self.places:
                if path and (self.directory == path or self.directory.startswith(path + os.sep)):
                    parts = [label] + [
                        p for p in os.path.relpath(self.directory, path).split(os.sep) if p != "."
                    ]
                    text = " › ".join(parts)
                    break
        self.k["selected_place"].getModel().Label = "Seçili yer: " + text
        if self.view == "open":
            self._list_files()
        if self.folder_browser:
            self._list_folders()

    def _select_place(self, i):
        key, _, path = self.places[i]
        self.place = i
        self.pending_overwrite = None
        if key == "other":
            self.folder_browser = True
        elif path:
            self.directory = path
            self.folder_browser = False
        self._paint_places()
        self._show_selected_place()
        self._layout()

    def _list_folders(self):
        try:
            names = sorted(
                (
                    a
                    for a in os.listdir(self.directory)
                    if not a.startswith(".") and os.path.isdir(os.path.join(self.directory, a))
                ),
                key=str.lower,
            )
        except OSError:
            names = []
        self.subfolders = [".."] + names
        listbox = self.k["folders"]
        listbox.removeItems(0, listbox.getItemCount())
        listbox.addItems(tuple(["↑  Üst klasör"] + [a + "/" for a in names]), 0)

    def _list_files(self):
        """Aç görünümünde seçili yerdeki klasör ve dosyalar ya da son kullanılanlar."""
        if self._recent_selected():
            home = os.path.expanduser("~")
            recent = self._recent_files()
            self._fill_tiles(
                [
                    (
                        os.path.basename(y),
                        os.path.dirname(y).replace(home, "~", 1),
                        image,
                        (lambda y=y: self._load(uno.systemPathToFileUrl(y))),
                    )
                    for y, image in recent
                ]
            )
            self.k["files_label"].getModel().Label = "Son kullanılanlar"
            if not recent:
                self._status("Son açılan dosya yok.")
            return
        else:
            try:
                names = sorted(os.listdir(self.directory), key=str.lower)
            except OSError as e:
                self._status(f"Klasör okunamadı: {e.strerror}")
                names = []
            folders = [
                a
                for a in names
                if not a.startswith(".") and os.path.isdir(os.path.join(self.directory, a))
            ]
            files = [
                a
                for a in names
                if not a.startswith(".")
                and os.path.isfile(os.path.join(self.directory, a))
                and os.path.splitext(a)[1][1:].lower() in OPENABLE_EXTENSIONS
            ]
            self.entries = [(os.path.join(self.directory, a), True) for a in folders] + [
                (os.path.join(self.directory, a), False) for a in files
            ]
            items = [os.path.basename(y) + ("/" if k else "") for y, k in self.entries]
            self.k["files_label"].getModel().Label = "Dosyalar"
        listbox = self.k["files"]
        listbox.removeItems(0, listbox.getItemCount())
        listbox.addItems(tuple(items), 0)
        if not items:
            self._status("Burada açılabilecek dosya yok.")

    def _recent_files(self):
        recent = []
        try:
            provider = self.smgr.createInstanceWithContext(
                "com.sun.star.configuration.ConfigurationProvider", self.ctx
            )
            node = provider.createInstanceWithArguments(
                "com.sun.star.configuration.ConfigurationAccess",
                (_prop("nodepath", "/org.openoffice.Office.Histories/Histories/PickList"),),
            )
            items = node.getByName("ItemList")
            order = node.getByName("OrderList")
            urls = [
                order.getByName(n).HistoryItemRef for n in sorted(order.getElementNames(), key=int)
            ]
            urls += [u for u in items.getElementNames() if u not in urls]
            for url in urls:
                if url.startswith("file://") and items.hasByName(url):
                    path = uno.fileUrlToSystemPath(url)
                    if os.path.isfile(path):
                        recent.append((path, self._recent_thumbnail(items.getByName(url), path)))
        except Exception:
            traceback.print_exc(file=sys.stderr)
        return recent

    def _recent_thumbnail(self, item, path):
        """Geçmişteki base64 PNG küçük resmi önbelleğe yazar."""
        try:
            data = item.Thumbnail
        except Exception:
            return None
        if not data:
            return None
        try:
            return _cache_file(f"{path}:{os.path.getmtime(path)}", base64.b64decode(data))
        except (ValueError, OSError):
            return None

    def _fill_info(self):
        model = self.controller.getModel()
        rows = []
        if model.hasLocation():
            path = uno.fileUrlToSystemPath(model.getLocation())
            rows.append(("Konum", path.replace(os.path.expanduser("~"), "~", 1)))
            with contextlib.suppress(OSError):
                rows.append(("Boyut", f"{os.path.getsize(path) / 1024:.1f} KB"))
        else:
            rows.append(("Konum", "Henüz kaydedilmedi"))
        try:
            props = model.getDocumentProperties()
            if props.Author:
                rows.append(("Oluşturan", props.Author))
            t = props.ModificationDate
            if t.Year:
                rows.append(
                    (
                        "Son değişiklik",
                        f"{t.Day:02d}.{t.Month:02d}.{t.Year} {t.Hours:02d}:{t.Minutes:02d}",
                    )
                )
            counts = {n.Name: n.Value for n in props.DocumentStatistics}
            if "WordCount" in counts:
                rows.append(
                    (
                        "Sözcük",
                        f"{counts['WordCount']} sözcük, {counts.get('CharacterCount', 0)} karakter",
                    )
                )
            if "PageCount" in counts:
                rows.append(("Sayfa", str(counts["PageCount"])))
        except Exception:
            traceback.print_exc(file=sys.stderr)
        for i in range(6):
            a, d = rows[i] if i < len(rows) else ("", "")
            self.k[f"info_key{i}"].getModel().Label = a
            self.k[f"info_value{i}"].getModel().Label = d

    # --- Yazdır ---

    def _prepare_print(self):
        printers = ()
        try:
            printers = self.smgr.createInstanceWithContext(
                "com.sun.star.awt.PrinterServer", self.ctx
            ).getPrinterNames()
        except Exception:
            traceback.print_exc(file=sys.stderr)
        listbox = self.k["printer"]
        listbox.removeItems(0, listbox.getItemCount())
        listbox.addItems(tuple(printers), 0)
        current = {p.Name: p.Value for p in self.controller.getModel().getPrinter()}.get("Name", "")
        listbox.selectItemPos(printers.index(current) if current in printers else 0, True)
        if not printers:
            self._status("Kurulu yazıcı bulunamadı.")
        self.k["pages"].selectItemPos(0, True)
        self.k["copies"].getModel().Value = 1.0
        self.preview_page = self._current_page()
        self._make_preview()

    def _current_page(self):
        try:
            return self.controller.getViewCursor().getPage()
        except Exception:
            return 1

    def _make_preview(self):
        """Belgeyi geçici PDF'e aktarır; önizleme sayfalarını oradan çizer."""
        model = self.controller.getModel()
        filter_name = PREVIEW_FILTERS.get(_document_type(model))
        self.preview_count = 0
        if filter_name is None:
            return
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.preview_pdf = os.path.join(CACHE_DIR, f"onizleme-{os.getpid()}-{id(self)}.pdf")
        try:
            model.storeToURL(
                uno.systemPathToFileUrl(self.preview_pdf), (_prop("FilterName", filter_name),)
            )
            info = subprocess.run(
                ["pdfinfo", self.preview_pdf], capture_output=True, text=True, timeout=20
            ).stdout
            self.preview_count = int(re.search(r"^Pages:\s+(\d+)", info, re.M).group(1))
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self._status("Önizleme hazırlanamadı.")
            return
        self.preview_page = min(max(1, self.preview_page), self.preview_count)
        self._draw_preview()

    def _draw_preview(self):
        if not self.preview_count:
            return
        n = self.preview_page
        output = os.path.splitext(self.preview_pdf)[0] + f"-{n}"
        try:
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-r",
                    "90",
                    "-f",
                    str(n),
                    "-l",
                    str(n),
                    "-singlefile",
                    self.preview_pdf,
                    output,
                ],
                check=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            traceback.print_exc(file=sys.stderr)
            return
        model = self.k["preview"].getModel()
        model.ImageURL = ""
        model.ImageURL = uno.systemPathToFileUrl(output + ".png")
        self.k["preview_page"].getModel().Label = f"Sayfa {n} / {self.preview_count}"
        self.k["preview_prev"].setEnable(n > 1)
        self.k["preview_next"].setEnable(n < self.preview_count)

    def _print(self):
        model = self.controller.getModel()
        printer = self.k["printer"].getSelectedItem()
        if not printer:
            self._status("Bir yazıcı seç.")
            return
        options = [
            _prop("CopyCount", uno.Any("short", int(self.k["copies"].getModel().Value or 1))),
            _prop("Collate", self.k["collate"].getModel().State == 1),
        ]
        mode = self.k["pages"].getSelectedItemPos()
        if mode == 1:
            options.append(_prop("Pages", str(self._current_page())))
        elif mode == 2:
            page_range = self.k["range"].getText().replace(" ", "")
            if not re.fullmatch(r"\d+(-\d+)?(,\d+(-\d+)?)*", page_range):
                self._status("Sayfaları 1-3, 5 biçiminde yaz.")
                return
            options.append(_prop("Pages", page_range))
        try:
            model.setPrinter((_prop("Name", printer),))
            uno.invoke(model, "print", (tuple(options),))
        except Exception as e:
            self._status(f"Yazdırılamadı: {getattr(e, 'Message', e)}")
            return
        self.close()

    def _select_format(self, i):
        if i >= len(self.formats) or (
            i == self.format_index and self.cards[i]["radio"].getModel().State == 1
        ):
            return
        self.format_index = i
        name = self.k["name"].getText().strip()
        if name:
            self.k["name"].setText(os.path.splitext(name)[0] + "." + self.formats[i][3])
        self.pending_overwrite = None
        self._layout()

    # --- İşlemler ---

    def _menu_selected(self, key):
        if key == "back":
            self.close()
        elif key == "save":
            self._save_in_place()
        elif key == "ribbon":
            target = "notebookbar.ui" if self._is_simple() else SIMPLE_RIBBON_UI
            _later(self.ctx, lambda: self._run_original(f".uno:ToolbarMode?Mode:string={target}"))
        elif key == "look_settings":
            for command in SETTINGS_COMMANDS:
                try:
                    subprocess.Popen(
                        command,
                        start_new_session=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return
                except OSError:
                    continue
            self._status("Office görünümü ayarları açılamadı.")
        elif key in COMMANDS:
            _later(self.ctx, lambda: self._run_original(COMMANDS[key]))
        elif key != self.view:
            self._switch_view(key)

    def _is_simple(self):
        """Bu uygulama şu an sade şeritte mi? (ToolbarMode/Applications/<Uyg>/Active)"""
        app = APP_NAMES.get(_document_type(self.controller.getModel()))
        if app is None:
            return False
        try:
            provider = self.smgr.createInstanceWithContext(
                "com.sun.star.configuration.ConfigurationProvider", self.ctx
            )
            node = provider.createInstanceWithArguments(
                "com.sun.star.configuration.ConfigurationAccess",
                (_prop("nodepath", f"/org.openoffice.Office.UI.ToolbarMode/Applications/{app}"),),
            )
            return node.getByName("Active") == SIMPLE_RIBBON_UI
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return False

    def _save_in_place(self):
        model = self.controller.getModel()
        if not model.hasLocation():
            self._switch_view("save_as")
            return
        try:
            model.store()
        except Exception as e:
            self._switch_view("save_as")
            self._status(f"Kaydedilemedi: {getattr(e, 'Message', e)}")
            return
        self.close()

    def _save_as(self):
        name = self.k["name"].getText().strip()
        if not name or "/" in name:
            self._status("Geçerli bir dosya adı yaz.")
            return
        if not self.formats:
            self._status("Bu belge türü için kayıt biçimi tanımlı değil.")
            return
        _, _, filter_name, extension, is_export, _ = self.formats[self.format_index]
        if os.path.splitext(name)[1][1:].lower() != extension:
            name += "." + extension
        path = os.path.join(self.directory, name)
        if os.path.exists(path) and self.pending_overwrite != path:
            self.pending_overwrite = path
            self._status(
                f"Burada '{name}' adında bir dosya var. Üzerine yazmak için yeniden "
                f"{self.k['tamam'].getModel().Label}'e bas."
            )
            return
        args = [_prop("FilterName", filter_name), _prop("Overwrite", True)]
        if extension in PASSWORD_FORMATS and self.k["password_check"].getModel().State == 1:
            password = self.k["password1"].getText()
            if not password:
                self._status("Parola boş olamaz.")
                return
            if password != self.k["password2"].getText():
                self._status("İki parola aynı değil.")
                return
            if is_export:
                args.append(
                    _prop(
                        "FilterData",
                        uno.Any(
                            "[]com.sun.star.beans.PropertyValue",
                            (_prop("EncryptFile", True), _prop("DocumentOpenPassword", password)),
                        ),
                    )
                )
            elif extension in OOXML:
                # OOXML süzgeci "Password"u yok sayar; LibreOffice'in parola penceresinin
                # verdiği şifreleme verisi (parola + CryptoType) açıkça verilmeli.
                args.append(
                    _prop(
                        "EncryptionData",
                        uno.Any(
                            "[]com.sun.star.beans.NamedValue",
                            (
                                uno.createUnoStruct(
                                    "com.sun.star.beans.NamedValue", "OOXPassword", password
                                ),
                                uno.createUnoStruct(
                                    "com.sun.star.beans.NamedValue", "CryptoType", "Standard"
                                ),
                            ),
                        ),
                    )
                )
            else:
                args.append(_prop("Password", password))
        self.pending_overwrite = None
        url = uno.systemPathToFileUrl(path)
        args = tuple(args)
        model = self.controller.getModel()
        try:
            if is_export:
                model.storeToURL(url, args)
            else:
                model.storeAsURL(url, args)
        except Exception as e:
            self._status(f"Kaydedilemedi: {getattr(e, 'Message', e)}")
            return
        self.close()

    def _load(self, url, as_template=False):
        def load():
            desktop = self.smgr.createInstanceWithContext("com.sun.star.frame.Desktop", self.ctx)
            try:
                desktop.loadComponentFromURL(
                    url, "_default", 0, (_prop("AsTemplate", True),) if as_template else ()
                )
            except Exception as e:
                self._status(f"Açılamadı: {getattr(e, 'Message', e)}")
                return
            if self.is_open and self.is_current():
                self.close()

        _later(self.ctx, load)

    def _open(self):
        i = self.k["files"].getSelectedItemPos()
        if not 0 <= i < len(self.entries):
            self._status("Listeden bir dosya seç.")
            return
        path, is_folder = self.entries[i]
        if is_folder:
            self.directory = path
            self._show_selected_place()
        else:
            self._load(uno.systemPathToFileUrl(path))

    def _open_folder(self):
        i = self.k["folders"].getSelectedItemPos()
        if not 0 <= i < len(self.subfolders):
            return
        self.directory = os.path.abspath(os.path.join(self.directory, self.subfolders[i]))
        self.pending_overwrite = None
        self._show_selected_place()

    def _move_focus(self, source, async_callback):
        order = [name for name in self.FOCUS_ORDER if name in self._visible]
        current = next((i for i, name in enumerate(order) if self.k[name] == source), None)
        if current is not None and order:
            self.k[order[(current + (-1 if async_callback else 1)) % len(order)]].setFocus()

    def _run_original(self, command):
        interceptor = _find(_interceptors, self.frame)
        self.close()
        if interceptor is not None:
            interceptor.run_original(command)

    # --- Olaylar ---

    def _on_event(self, kind, event):
        if kind == "resize":
            if self.is_open:
                self._layout()
            return
        if kind == "escape":
            self.close()
            return
        if kind == "tab":
            self._move_focus(event.Source, async_callback=event.Modifiers & SHIFT)
            return
        k = self.k
        source = event.Source
        if kind == "click":
            action = next((action for target, action in self.clickables if target == source), None)
            if action is not None:
                action()
        elif source == k["cancel"]:
            self.close()
        elif source == k["password1"] and kind == "enter":
            k["password2"].setFocus()
        elif source == k["tamam"] and self.view == "print_view":
            self._print()
        elif source == k["advanced"]:
            _later(self.ctx, lambda: self._run_original(".uno:Print"))
        elif source == k["pages"]:
            self._layout()
            if k["pages"].getSelectedItemPos() == 2:
                k["range"].setFocus()
        elif source == k["preview_prev"] or source == k["preview_next"]:
            self.preview_page += -1 if source == k["preview_prev"] else 1
            self._draw_preview()
        elif source == k["tamam"] or source in (k["name"], k["password2"]) and kind == "enter":
            if self.view == "open":
                self._open()
            else:
                self._save_as()
        elif source == k["folders"] and kind in ("action", "enter"):
            self._open_folder()
        elif source == k["files"] and kind in ("action", "enter"):
            self._open()
        elif source == k["files"] and kind == "select":
            self._status("")
        elif source == k["password_check"]:
            self._layout()
            if k["password_check"].getModel().State == 1:
                k["password1"].setFocus()
        elif source == k["prev"] or source == k["next"]:
            self.tile_page += -1 if source == k["prev"] else 1
            self._layout()
        else:
            for i, (_, url) in enumerate(NEW_DOCUMENTS):
                if source == k[f"new{i}"]:
                    self._load(url)
                    return


class FileTabController(
    unohelper.Base,
    XToolbarController,
    XStatusListener,
    XInitialization,
    XUpdatable,
    XComponent,
    XServiceInfo,
):
    """Sade şeridin Dosya sekmesindeki öğenin denetçisi.

    Notebookbar sekme değişimini UNO'ya bildirmiyor; ama öğenin araç kutusundan
    erişilebilirlik ağacında yukarı çıkınca Dosya sekmesinin kendisine (PAGE_TAB)
    ulaşılıyor. Sekmenin SELECTED durumu doğru, olayları ise güvenilmez (açılıştan
    sonra gelmiyor); bu yüzden durum düzenli aralıkla okunur. Dosya sekmesi seçilince
    menü açılır, başka sekmeye geçilince (sekmeden açılmışsa) kapanır.
    """

    IMPLEMENTATION = "org.linwas.officelook.FileTabController"
    POLL_INTERVAL = 0.2

    def __init__(self, ctx, *args):
        # Denetçi fabrikası argümanları yapıcıya da verir;
        # yalnız ctx alan yapıcı LibreOffice'i çökertir.
        self.ctx = ctx
        self.frame = None
        self.tab = None
        self.selected = False
        self.opened_from_tab = False
        self.stop = threading.Event()
        self.initialize(args)

    def initialize(self, args):
        for a in args:
            name = getattr(a, "Name", None)
            if name == "Frame":
                self.frame = a.Value
            elif name == "ParentWindow" and self.tab is None:
                self._find_tab(a.Value)

    def _find_tab(self, toolbox):
        try:
            context = toolbox.getAccessibleContext()
            for _ in range(20):
                parent = context.getAccessibleParent()
                if parent is None:
                    return
                parent_context = parent.getAccessibleContext()
                if (
                    context.getAccessibleRole() == PAGE_TAB
                    and parent_context.getAccessibleRole() == PAGE_TAB_LIST
                ):
                    self.tab = context
                    self.selected = self._is_selected()
                    threading.Thread(target=self._watch, daemon=True).start()
                    return
                context = parent_context
        except Exception:
            traceback.print_exc(file=sys.stderr)

    def _is_selected(self):
        return self.tab.getAccessibleStateSet().contains(SELECTED)

    def _watch(self):
        # UNO yalnız okunur; menüyü açıp kapatma ana iş parçacığına sıraya konur.
        while not self.stop.wait(self.POLL_INTERVAL):
            try:
                now = self._is_selected()
            except Exception:
                return  # şerit yok edildi
            if now != self.selected:
                self.selected = now
                if self.frame is not None and not os.path.exists(DISABLED_FLAG):
                    _later(self.ctx, self._open_from_tab if now else self._close_from_tab)

    def _open_from_tab(self):
        _show_menu(self.frame, "open")
        self.opened_from_tab = True

    def _close_from_tab(self):
        if not self.opened_from_tab:
            return
        self.opened_from_tab = False
        menu = _find(_menus, self.frame)
        if menu is not None and menu.is_open and menu.is_current():
            menu.close()

    # Öğe "Dosya menüsünü aç" düğmesidir: menü kapatıldıktan sonra sekmede kalan
    # kullanıcı onunla yeniden açabilir.
    def execute(self, modifiers):
        if self.frame is not None:
            _show_menu(self.frame, "open")

    def click(self):
        self.execute(0)

    def doubleClick(self):
        pass

    def createPopupWindow(self):
        return None

    def createItemWindow(self, parent):
        return None

    def statusChanged(self, event):
        pass

    def update(self):
        pass

    def dispose(self):
        self.stop.set()

    def addEventListener(self, listener):
        pass

    def removeEventListener(self, listener):
        pass

    def disposing(self, event):
        self.stop.set()

    def getImplementationName(self):
        return self.IMPLEMENTATION

    def supportsService(self, name):
        return name == "com.sun.star.frame.ToolbarController"

    def getSupportedServiceNames(self):
        return ("com.sun.star.frame.ToolbarController",)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(Job, Job.IMPLEMENTATION, (Job.IMPLEMENTATION,))
g_ImplementationHelper.addImplementation(
    FileTabController, FileTabController.IMPLEMENTATION, ("com.sun.star.frame.ToolbarController",)
)
