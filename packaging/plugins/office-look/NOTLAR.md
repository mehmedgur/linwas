# Office görünümü — teknik notlar ve deney kayıtları

> Bu notlar paket `pardus-ofis-deneyimi` adıyla ayrı bir klasörde (officepack) geliştirilirken
> tutuldu; adlar o dönemin adlarıdır (`pardus_dosya.py` → `extension/office_look.py`,
> `sade_serit.py` → `tools/ribbon.py`, `kontrol.py` → `tools/check.py`).

Tarih: 2026-10-17

## Ortam

| Öğe | Değer |
|---|---|
| Dağıtım | Pardus GNU/Linux 23.5 (yirmiuc), Debian 12 tabanlı |
| LibreOffice | 7.4.7.2 (paket `4:7.4.7-1+deb12u14`, Debian deposu) |
| Çalıştırıcı | `/usr/bin/soffice`; `/usr/local/bin/libreoffice` Pardus sarmalayıcısı (`LC_CTYPE=$LANG` ayarlayıp `/usr/bin/libreoffice` çalıştırıyor) |
| Kullanıcı profili | `~/.config/libreoffice/4/user` |
| Sistem .ui klasörü (Writer) | `/usr/lib/libreoffice/share/config/soffice.cfg/modules/swriter/ui/` |
| Kullanıcı .ui klasörü (Writer) | `~/.config/libreoffice/4/user/config/soffice.cfg/modules/swriter/ui/` (varsayılan olarak yok) |
| Hazır Writer şeritleri | `notebookbar.ui`, `notebookbar_compact.ui`, `notebookbar_groupedbar_compact.ui`, `notebookbar_groupedbar_full.ui`, `notebookbar_groups.ui`, `notebookbar_online.ui`, `notebookbar_single.ui` |

## İlgili yapılandırma (`org.openoffice.Office.UI.ToolbarMode`)

- `ActiveWriter`: hangi şerit `.ui` dosyasının yükleneceğini belirler. Varsayılan değer `notebookbar.ui`.
- `Applications/Writer/Active`: etkin arayüz modu. Değer, mod adıyla değil modun **`CommandArg`** değeriyle karşılaştırılır. Örneğin "Sekmeli" için `notebookbar.ui` yazılır, `Tabbed` yazılmaz. Şerit yalnızca eşleşen modda `HasNotebookbar=true` ise gösterilir.
- `Applications/Writer/Modes/<ad>`: Görünüm › Kullanıcı Arayüzü menüsündeki modlar (`Label`, `CommandArg`, `MenuPosition`, `HasNotebookbar`, `IsExperimental`, `HasMenubar`, `Toolbars`, `UserToolbars`, `UIItemProperties`, `Sidebar`).

## Yöntem

- Her test ayrı, geçici bir profille çalıştırıldı (`-env:UserInstallation=file://…`). Gerçek kullanıcı profiline dokunulmadı.
- Test `.ui` dosyası sistemdeki `notebookbar.ui` dosyasının kopyası. Yalnızca "Giriş" (`~Home`) sekmesinin etiketi benzersiz bir metinle değiştirildi (örneğin `PARDUS_USER`).
- Ayarlar, profildeki `registrymodifications.xcu` dosyasına önceden yazıldı. Ardından Writer açıldı, pencerenin ekran görüntüsü alındı ve sekme etiketine bakıldı.

## Sonuçlar

| # | .ui konumu ve adı | `ActiveWriter` | `Writer/Active` | Sonuç |
|---|---|---|---|---|
| T1 | Kullanıcı profili, yeni ad `pardus_test.ui` | `pardus_test.ui` | `notebookbar.ui` | ✅ Özel şerit yüklendi (`PARDUS_USER` sekmesi görüldü). Diğer etiketler Türkçe çevrildi. |
| T2 | Kullanıcı profili, aynı ad `notebookbar.ui` | `notebookbar.ui` | `notebookbar.ui` | ✅ Kullanıcı kopyası sistem dosyasının yerine geçti (`PARDUS_OVR`). |
| T3 | Dosya yok | `pardus_test.ui` | `notebookbar.ui` | ❌ Writer penceresi açılıyor ama hiç çizilmiyor (askıda). Sonlandırınca çıkış kodu 255 ve "Unspecified Application Error / Signal 6" alındı. |
| T4 | Kullanıcı profili `pardus_test.ui`, mod girdisi yok | `pardus_test.ui` | `pardus_test.ui` | ⚠️ Şerit gösterilmedi, standart araç çubuğu geldi. `Active` değeri hiçbir modun `CommandArg` değeriyle eşleşmiyor. |
| T5 | T4 ile aynı, eksik alanlı `Modes/Pardus` girdisi | `pardus_test.ui` | `pardus_test.ui` | ⚠️ Standart araç çubuğu geldi. LO girdiyi kabul etmedi ve profile `oor:op="remove"` olarak geri yazdı. `UIItemProperties` ve `HasMenubar` eksikti. |
| T5b | T5 ile aynı, tüm alanları dolu `Modes/Pardus` girdisi | `pardus_test.ui` | `pardus_test.ui` | ✅ Özel şerit yüklendi (`PARDUS_T5`). |
| T6 | Sistem klasörü, yeni ad `pardus_sys_test.ui` (root, `pkexec install`) ve profilde .ui yok | `pardus_sys_test.ui` | `notebookbar.ui` | ✅ Sistemdeki dosya yüklendi (`PARDUS_SYS`). |
| T7 | Aynı ad (`pardus_sys_test.ui`) hem sistemde hem kullanıcı profilinde | `pardus_sys_test.ui` | `notebookbar.ui` | ✅ Kullanıcı profilindeki kopya kazandı (`PARDUS_USRWIN`). Öncelik sırası: kullanıcı, sonra sistem. |

T6 ve T7'den sonra test dosyası sistemden silindi (`pkexec rm`). Sistem klasörü ilk hâline döndü.

## Değerlendirme (yol 2)

- **Kullanıcı profili: evet.** Tek bir Writer şerit `.ui` dosyası `user/config/soffice.cfg/modules/swriter/ui/` altına konup `ActiveWriter` ile seçilebiliyor. Dosyanın yeni bir adı olabilir, mevcut bir adı da geçersiz kılabilir.
- Şeridin görünmesi için `Writer/Active` değeri, `HasNotebookbar=true` olan bir modun `CommandArg` değerine eşit olmalı. İki yol var:
  - **En basiti:** `Active=notebookbar.ui` ve `ActiveWriter=<özel>.ui`. Menüde "Sekmeli" seçili görünür.
  - **Temiz yol:** Tüm zorunlu alanlarıyla eksiksiz bir `Modes/<Ad>` girdisi eklenir ve `CommandArg=<özel>.ui` yapılır. Eksik alan varsa LO girdiyi sessizce siler.
- **Risk:** `ActiveWriter` var olmayan bir dosyayı gösterirse Writer askıda kalıyor. Paketleme yapılırken `.ui` dosyası ile yapılandırma birlikte kurulmalı ve birlikte kaldırılmalı.
- Çeviri: Değiştirilmemiş `translatable` etiketler sistem çevirisini kullanmaya devam ediyor. Değiştirilen etiketler ham metin olarak görünüyor.
- **Sistem klasörü: evet (T6).** `/usr/lib/libreoffice/share/config/soffice.cfg/modules/swriter/ui/` altına yeni adla konan dosya `ActiveWriter` ile seçilebiliyor. Bu yöntem bir `.deb` paketiyle dağıtıma uygun.
- **Öncelik (T7):** Kullanıcı profilinde aynı adda bir dosya varsa sistemdeki dosyanın yerine o yükleniyor. Sistemdeki şeridi güncellerken eski kullanıcı kopyaları güncellemeyi gizleyebilir.

## Örnek ayar (kullanıcı profili, en basit yol)

```xml
<item oor:path="/org.openoffice.Office.UI.ToolbarMode"><prop oor:name="ActiveWriter" oor:op="fuse"><value>pardus_test.ui</value></prop></item>
<item oor:path="/org.openoffice.Office.UI.ToolbarMode/Applications/org.openoffice.Office.UI.ToolbarMode:Application['Writer']"><prop oor:name="Active" oor:op="fuse"><value>notebookbar.ui</value></prop></item>
```

## Uygulama: `pardus-libreoffice-writer-sade` paketi

- `tools/sadelestir.py`: sistemdeki `notebookbar.ui` dosyasından Düzen, Kaynaklar, Gözden Geçir, Eklenti ve Araçlar sekmelerini siler. Bağlamsal sekmeler korunur. Silinen widget'lara işaret eden `GtkSizeGroup` girdileri de temizlenir.
- `paket/usr/lib/libreoffice/share/registry/pardus-writer-sade.xcd`: tüm zorunlu alanlarıyla `Modes/PardusSade` girdisini ekler. `ActiveWriter` ve `Writer/Active` varsayılanını `pardus_sade.ui` yapar.
- `build.sh`: `.ui` dosyasını üretir ve `dist/pardus-libreoffice-writer-sade_0.1.0_all.deb` paketini derler.
- Doğrulama: Paket kuruldu ve boş bir profille Writer açıldı. Varsayılan olarak sade şerit geldi (Dosya, Başlangıç, Ekle, Görünüm).
- Not: Paket kaldırılınca `Modes/PardusSade` girdisi de kaybolur. Bu modu seçmiş kullanıcıların `Active` değeri hiçbir modla eşleşmez ve standart araç çubuğuna düşerler (T4 davranışı). T3'teki askıda kalma riski yalnızca `Active=notebookbar.ui` ve `ActiveWriter=pardus_sade.ui` birlikte kalırsa ortaya çıkar.
- `tools/kontrol.py`: `build.sh` tarafından çağrılan statik denetim. Şunları yakalar: `Modes` girdisinde eksik zorunlu alan (zorunlu alan listesi `main.xcd` şemasından okunur), paket içinde olmayan `ActiveWriter`/`CommandArg` dosyası, hiçbir modla eşleşmeyen `Writer/Active`, kalması gereken veya kaldırılması gereken sekmeler, yinelenen id ve sahipsiz `GtkSizeGroup` girdisi. Olumsuz testlerle (eksik alan, olmayan dosya) doğrulandı.
- `build.sh`: kurulu `libreoffice-writer` 7.4 serisinde değilse durur. Şerit dosyası kaynak sürüme bağlı olduğu için bu kontrol gerekli.
- Kaynak paket: `debian/` (`control`, `changelog`, `rules`, `copyright`, `source/format` = 3.0 native). `debian/rules` debhelper kullanmıyor, yalnızca dpkg-dev gerekiyor. `dpkg-buildpackage -us -uc -b` ile derlenebiliyor. `build.sh` aynı kuralları çalıştırır ve çıktıyı `dist/` altına koyar. Eski `paket/DEBIAN/control` kaldırıldı. Pakete `usr/share/doc/<paket>/` altında `copyright` ve `changelog.gz` eklendi.
- Açık konu: `debian/copyright` içinde proje kodunun lisansı `TODO` olarak bırakıldı. Üretilen `.ui` dosyası LibreOffice'ten türetildiği için MPL-2.0 lisanslı.

## Sürüm 0.2.0: `pardus-ofis-deneyimi`

Paket adı `pardus-libreoffice-writer-sade` yerine `pardus-ofis-deneyimi` oldu (`Conflicts`/`Replaces` ile). Sade şerit kaldırıldı.

### Varsayılanlar (`pardus-ofis-deneyimi.xcd`)
- Writer, Calc ve Impress sekmeli tam şeritle açılır (`Active<Uyg>` ve `Applications/<Uyg>/Active` = `notebookbar.ui`).
- Varsayılan kayıt biçimi OOXML. Kullanılan süzgeçler: `MS Word 2007 XML`, `Calc MS Excel 2007 XML`, `Impress MS PowerPoint 2007 XML`. `WarnAlienFormat=false`.
- Writer temel yazı tipi Carlito 11 pt (`StandardHeight=388`, birim 1/100 mm).
- Impress açılışta şablon seçme penceresi göstermez (`Impress/Misc/NewDoc/AutoPilot=false`).
- `writer/calc/impress.xcd` kendi Factories varsayılanlarını yazdığı için `<dependency>` ile onlardan sonra yüklenir. Bağımlılık dosyası yoksa LibreOffice xcd dosyasını hiç yüklemez.

### Dosya menüsü eklentisi (`eklenti/pardus-dosya`, `share/extensions/pardus-dosya` altına paketli)
- `Jobs.xcu`: `OnViewCreated` olayında bir Job çalışır ve çerçeveye dispatch yakalayıcı kurar. Şema düğümünün adı `JobList`; `JoinedJobs` adıyla yazılırsa Job sessizce hiç çalışmaz.
- Yakalanan komutlar: `.uno:SaveAs`, `.uno:Open`, `.uno:OpenFromWriter`, `.uno:OpenFromCalc` ve konumu olmayan belgede `.uno:Save`. Ctrl+O, Writer'da `.uno:OpenFromWriter` komutunu gönderir.
- Menü, ONLYOFFICE tarzı tam sayfa bir katmandır: belge penceresi (`getComponentWindow`) gizlenir ve aynı alana ana pencerenin çocuğu olan iki pencere (sol menü ve içerik) yerleştirilir. Kardeş pencereler belge penceresinin altında kaldığı için gizlemek şart. Konum, `(0,0)`'daki 1×1 ölçü penceresiyle belge penceresinin ekran konumları farkından hesaplanır; `LayoutManager.getCurrentDockingArea()` bu iş için kullanılamaz.
- Görünümler: Kaydet, Farklı kaydet (biçim kutucukları, klasör gezinme, dosya adı, üzerine yazma onayı), Aç, Son dosyalar (`Histories/PickList`), Yeni, Yazdır. Esc ve "Geri" belgeye döner.
- Belgeyi değiştiren işlemler (yükleme, yazdırma) `AsyncCallback` ile ertelenir. Menünün olay işleyicisinin içinden yükleme yapılırsa LibreOffice kilitleniyor.
- Doğrulama: Writer, Calc ve Impress'te Ctrl+S, Ctrl+Shift+S ve Ctrl+O katmanı açtı, sistem penceresi açılmadı. Enter ile `.docx`/`.xlsx` kaydedildi. Liste üzerinden dosya açıldı. Son dosyalar ve Yeni çalıştı. Paket sistem genelinde kurulup boş profille de denendi.
- Sınırlar: Şeritteki "Dosya" sekmesine tıklamak menüyü açmaz; menüyü yalnız kısayollar ve sekmedeki Kaydet/Aç düğmeleri açar. Yazdır hâlâ LibreOffice'in yazdırma penceresini açar.

## Dosya menüsü: "Writer Sade Arayüz Taslağı" tasarımı (Dosya.dc.html)

- Sol menü koyu yeşil zeminli (#0B5D57). Seçili öğenin zemini #0F7A72. Öğeler: Belgeye dön, Yeni, Aç, Kaydet, Farklı kaydet, Yazdır, Dışa aktar, Paylaş, Belge bilgisi. En altta Ayarlar ve Belgeyi kapat.
- Farklı kaydet ekranı:
  - Sol sütunda "Nereye kaydedilsin?" başlığı altında konumlar: Belgeler, Masaüstü, İndirilenler, takılı USB bellekler ve "Başka klasör seç…". "Başka klasör seç…" alt klasör listesini açar. Altında "Seçili yer: Belgeler › …" satırı var.
  - Sağ sütunda dosya adı ve açıklamalı biçim kartları. Varsayılan seçenekte "Önerilen" rozeti bulunur. Altta Kaydet ve Vazgeç düğmeleri ile varsayılan biçimin nereden değiştirileceğini söyleyen not yer alır.
- Dışa aktar ekranı aynı düzeni kullanır, yalnız PDF kartını gösterir. Aç ekranı aynı konum sütununu kullanır; sütunun başında "Son kullanılanlar" vardır, sağda dosya listesi bulunur.
- Kartlar iç içe iki pencereyle çiziliyor: çerçeve için dış pencere, zemin için iç pencere. UNO denetimlerinde kenar yuvarlama ve SVG ikon yok; tasarımdaki ikonlar bu yüzden eklenmedi.
- Tasarımdaki "Yazı'nın kendi biçimi" ifadesi "LibreOffice'in kendi biçimi" olarak, "Ayarlar › Kaydetme" ifadesi LibreOffice'teki karşılığı "Ayarlar › Yükle/Kaydet › Genel" olarak yazıldı.

### Dosya sekmesi tıklaması (açık konu)
- Notebookbar sekme değişimi UNO'ya bildirilmiyor. Şerit, erişilebilirlik ağacında da görünmüyor.
- Denenen yol: Dosya sekmesine bir araç kutusu öğesi ekleyip bu öğeyi Python ToolbarController ile çizmek.
  - Öğe yalnız `File Tab` içindeki `sfxlo-PriorityMergedHBox`'ın başına eklenince şerit yükleniyor. Sekmenin özgün bölümleri silinir ya da gizlenirse şerit hiç yüklenmiyor.
  - `vnd.pardus.dosya:` protokolüyle kaydedilen denetçi notebookbar tarafından hiç örneklenmedi. Fabrika (`theToolbarControllerFactory.hasController`) kaydı görüyor.
  - Denetçi var olan bir `.uno:` komutuna kaydedilince LibreOffice açılışta çöküyor.
  - Bu yüzden bu parçalar pakete alınmadı.

## Sürüm 0.3.0

- **Otomatik kaydetme:** Konumu olan ve değişmiş belge iki dakikada bir kaydedilir. Bu iş eklentinin `KayitRozeti` sınıfında yapılıyor, çünkü LibreOffice 7.4'ün `UserAutoSaveEnabled` ayarı belgeyi kaydetmedi. Pencere başlığı belgenin durumunu gösterir: "Kaydedildi", "Kaydedilmemiş değişiklikler" ya da "Henüz kaydedilmedi".
- **Dosya düğmesi:** Şeridin sol üstündeki hızlı erişim çubuğuna (`notebookbarshortcuts`) eklenir. Komutu `.uno:PardusDosyaMenusu`, menüyü açıp kapatır. Düğme ve simgesi `ModuleUIConfigurationManager` üzerinden yalnız bellekte eklenir (`store()` çağrılmaz), bu yüzden kullanıcı profiline bir şey yazılmaz. Komut adları `Komutlar.xcu` dosyasında.
- **Dosya menüsüne eklenenler:**
  - Yazdır: yazıcı, kopya sayısı, sayfa aralığı ve harmanlama. Önizleme için belge PDF'e aktarılır ve sayfalar `pdftoppm` ile resme çevrilir.
  - Yeni: şablon kutucukları (küçük resimler `.ott` dosyasının içinden alınır).
  - Aç › Son kullanılanlar: küçük resimli liste (resimler `Histories/PickList` kaydındaki Thumbnail alanından gelir).
  - Parola ile koruma. OOXML için `EncryptionData` = OOXPassword ve `CryptoType=Standard` gerekiyor; yalnız `Password` verilirse dosya şifrelenmeden kaydediliyor. PDF için `FilterData` içinde EncryptFile ve DocumentOpenPassword kullanılıyor.
  - Ağ (gvfs) ve bulut (Nextcloud, ownCloud, Dropbox) konumları.
- **Sade şerit (`tools/sade_serit.py`, derleme sırasında üretilir):**
  - Writer sekmeleri: Dosya, Yaz, Ekle, Sayfa, Gözden geçir, Görünüm.
  - Calc sekmeleri: Dosya, Tablo, Ekle, Veri, Görünüm.
  - Impress'te yalnız sekmeler sadeleştirildi.
  - Yaz, Ekle ve Calc'ın Tablo sekmesinde tasarımdaki adlı gruplar var. "Daha fazla araç" düğmesi tam şeride geçer. Dosya menüsündeki "Tam şeride geç / Sade şeride dön" öğesi iki şerit arasında geçiş yapar.
  - Önemli bulgu: Silinen öğelere işaret eden `GtkSizeGroup` girdileri temizlenmezse LibreOffice açılışta çöküyor. Dosya sekmesi deneylerindeki çökmelerin nedeni de buydu. `kontrol.py` artık bunu denetliyor.
  - Bağımlılık: Şerit dosyası 7.4'e bağlı olduğu için paket `<< 4:7.5` ile sınırlı.
- **Kaldırma aracı (`pardus-ofis-deneyimi-kaldir`, zenity):**
  - "Yalnız benim için kapat": parola istemez. LibreOffice kapalıyken kullanıcının `registrymodifications.xcu` dosyasına özgün değerleri yazar ve eski değerleri `~/.config/pardus-ofis-deneyimi/yedek.json` dosyasına yedekler. Ayrıca `kapali` işaretini koyar; eklenti bu işareti görünce hiçbir şey kurmaz.
  - "Benim için yeniden aç": yedeği geri yükler.
  - "Tümüyle kaldır": `pkexec apt-get remove` çalıştırır.
  - Kullanıcı ayar dosyasının yazılıp geri yüklenmesinin ayarları değiştirmediği kullanıcının kendi profilinin bir kopyasıyla doğrulandı.
- **Test ortamı:** Arayüz testleri Xephyr (`:7`) sanal ekranında yapıldı; kullanıcının masaüstüne tıklama gönderilmedi.

## Dosya sekmesi (çözüldü)

- Python ToolbarController'ın çökme nedeni: LibreOffice denetçi argümanlarını **yapıcıya da** veriyor. `__init__(self, ctx)` imzası TypeError verip uygulamayı düşürüyordu. Doğru imza `__init__(self, ctx, *argumanlar)`.
- Sekme değişiminin tespiti:
  - Notebookbar sekme değişimini bildirmiyor. Araç kutusunun boyama olayları gelmiyor. SHOWING durumu sekmeyle değişmiyor. Erişilebilirlik olayları açılıştan sonra gelmiyor.
  - Çalışan yol: Dosya sekmesindeki öğenin araç kutusundan erişilebilirlik ağacında yukarı çıkılıp PAGE_TAB (sekme) bulunur ve onun **SELECTED** durumu 0,2 saniyede bir okunur.
  - Dosya sekmesi seçilince menü açılır. Başka sekmeye geçilince, menü sekmeden açılmışsa kapanır.
- Şerit dosyası: Dosya sekmesinin özgün bölümleri **kalmalı**, öğe başa eklenir. İçerik boşaltılırsa (boyut grupları temizlense bile) sekmeye tıklanınca şeridin tamamı kayboluyor.
- Writer ve Calc'ta denendi: Dosya sekmesi menüyü açıyor, Esc ile kapanıyor. Başka sekmeden Dosya'ya dönülünce yeniden açılıyor, Sayfa sekmesine geçince kapanıyor. Sol üstteki düğmeyle açılan menü şeritte gezinince açık kalıyor.
- Linwas entegrasyon planı: `docs/linwas-plani.md`.

## Sistem kurulumu (linwas-office-look 0.4.0, 17 Ekim 2026)

- Pardus 23'e kuruldu. postinst üç uygulamanın sade şeridini üretti:
  `modules/{swriter,scalc,simpress}/ui/linwas_simple.ui` ve `registry/linwas-office-look-ribbon.xcd`.
  Eski `pardus-ofis-deneyimi` paketi `Conflicts`/`Replaces` sayesinde kaldırıldı.
- Boş profille denendi: sade şerit varsayılan geliyor, Ctrl+S Dosya menüsünü açıyor,
  `.docx` olarak kaydediyor, başlıkta "Kaydedildi" yazıyor.
- **İlk açılış sınırı:** Paketle gelen eklenti, profilin ilk açılışında kullanıcıya
  kaydediliyor. Şerit bu kayıttan önce kurulduğu için o oturumda Dosya sekmesinin denetçisi
  çalışmıyor. LibreOffice kapatılıp açılınca sekme menüyü açıyor.

## Sürüm 0.5.0: Writer "Yaz" sekmesi ONLYOFFICE düzeninde (18 Ekim 2026)

Kullanıcı isteği: `libre.png` (0.4.0 şeridi) yerine `onlyoffice.png` örneği. Değişiklik yalnız Writer
"Yaz" (Home) sekmesinde; Ekle sekmesi, Calc ve Impress aynı.
- Grup adları kaldırıldı; gruplar `GtkSeparator` (dikey, LibreOffice'in kendi notebookbar.ui'ındaki
  gibi `VclOptionalBox`'ın ilk çocuğu) ile ayrılıyor. Adsız gruplarda küçük düğmeler hep yalnız simge
  (`toolbar_style=icons`); ad ipucunda.
- Gruplar: Pano (Kopyala, Kes / Yapıştır, Biçim boyacısı) · Yazı (yazı tipi, boyut, Büyüt, Küçült,
  büyük-küçük harf / K, T, A, üstü çizili, üst-alt simge, vurgu `.uno:BackColor`, renk, biçimi temizle
  `.uno:ResetAttributes`) · Paragraf (madde, numara, `.uno:SetOutline`, girinti / hizalamalar) ·
  Paragraf ayarları (`.uno:LineSpacing`, `.uno:ControlCodes` / `.uno:BackgroundColor`,
  `.uno:SetBorderStyle`) · Stil galerisi (grup adı kalkınca şerit yüksekliğini kullanır) · Bul / Tümünü
  seç · Daha fazla araç.
- Komutların hepsi LibreOffice 7.4.7 `swriter/ui/notebookbar.ui`'da var (grep ile doğrulandı); kaynak
  düğme kopyalandığı için açılır menüler korunur.
- Kurulu 7.4.7 dosyasıyla `build()` denendi: sahipsiz boyut grubu yok, yinelenen kimlik yok, 7 grup /
  6 ayırıcı. Görsel deneme kullanıcıda (paket kurulup Writer açılarak).
- **Calc "Tablo" sekmesi** de aynı düzende: Pano · Yazı (yazı tipi, boyut, Büyüt, Küçült / K, T, A,
  üstü çizili, renk, hücre zemini, kenarlık) · Hizalama (üst, orta, alt, kaydır / sol, orta, sağ,
  birleştir) · Sayı · Hücre ekle/sil, biçimi temizle · Otomatik toplam, işlev, sırala, süzgeç, koşullu
  biçim, bul · Daha fazla araç. Xephyr'de geçici profille açılıp görüldü.
- **"Daha fazla araç" Calc'ta çalışmıyordu.** Düğme eklentinin `.uno:LinwasMoreTools` komutunu
  çağırıyordu; Calc şeridi düğmenin hedefini eklentinin yakalayıcısı (OnViewCreated) kurulmadan önce
  alıyor ve `contextChanged()` ile yenilemiyor. Frame üzerinden gönderilen aynı komut çalışıyordu,
  düğmeye tıklamak çalışmıyordu (Xephyr + XTest ile doğrulandı). Çözüm: düğme doğrudan
  `.uno:ToolbarMode?Mode:string=notebookbar.ui` çalıştırır, etiket ve simge (`cmd/lc_toolbarmode.png`)
  .ui içinde. Düzeltmeden sonra tıklayınca `ActiveCalc` `notebookbar.ui` oldu.
- **Excel uyumu:** `org.openoffice.Office.Calc/Formula/Syntax/Grammar` = 1 (Excel A1; başka sayfaya
  başvuru `Sayfa1!A1`). LibreOffice 7.4'ün diğer varsayılanları zaten Excel'e yakın: joker karakter
  açık, düzenli ifade kapalı, `SearchCriteria` açık, OOXML açılışta yeniden hesaplama yok
  (`OOXMLRecalcMode` 1); Calibri/Cambria → Carlito/Caladea fontconfig ile (paket bağımlılığı).

## Uygulama adlarında Office karşılığı (18 Ekim 2026)

- `tools/office_names.py`: `/usr/share/applications/libreoffice-{writer,calc,impress}.desktop`
  kullanıcıya özel kopyası `~/.local/share/applications/` altına yazılır; yalnız `[Desktop Entry]`
  bölümündeki `Name` satırlarına " (Word|Excel|PowerPoint)" eklenir, `Keywords`'e Office adı girer,
  `X-Linwas-OfficeName=true` işareti konur. İşaretsiz (kullanıcının kendi) kopyaya dokunulmaz;
  eylem adları ("Yeni Belge") değişmez; işlem tekrarlanınca aynı sonuç (kurulu 7.4.7 dosyasıyla
  denendi).
- Ayar `office_names` (varsayılan açık): `linwas-office-look set office_names on|off`,
  `refresh-names`. "Yalnız benim için kapat" kopyaları siler, "aç" geri yazar.
- Eklenti: pencere başlığı "… - LibreOffice Writer (Word)"; LibreOffice oturumu başına bir kez
  `linwas-office-look refresh-names` (LibreOffice güncellenince kopya yenilenir).
