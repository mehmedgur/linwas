# Linwas 2.0 — Karar Belgesi

(Önceki çalışma adı: v1.1. Kod sıfırdan yazıldığı için sürüm adı **Linwas 2.0** oldu.)

Son güncelleme: 7 Ekim 2026
Depo (2.0): github.com/mehmedgur/linwas2 (geliştirme süresince private; kod düz dosyalar halinde)
Eski depo (v1.0, yalnızca referans): github.com/mehmedgur/linwas
Arayüz taslağı: claude.ai/artifact/GmBq4uSWwSsfwgJvW6u9BB (ana pencere + kuyruk senaryosu)
İlgili belgeler: [yapilacaklar.md](yapilacaklar.md), [dogrulama-raporu.md](dogrulama-raporu.md)

## Çalışma kuralları
- Kullanıcıya Türkçe ve kısa cevap; detay istenirse verilir.
- Görev alınca "Anladım" denir, "kodlamaya geçelim" komutu beklenir.
- **Her kodlama aşamasına geçmeden önce `docs/yapilacaklar.md` okunur ve bekleyen fikirler kullanıcıya hatırlatılır.**
- Doğrulanmamış API/komut/paket adı önerilmez. Her dış servis resmi belgeden doğrulanır.
- Yeni karar alındığında aynı değişiklikte bu belge güncellenir.

## Geliştirme
- Kod linwas2'de sıfırdan yazılır; v1.0 koduna bakılmaz.
- Git: aşama 0 (iskelet) doğrudan ana dala; sonraki her aşama ayrı dalda, küçük ve tek konulu PR'lar. Her PR'da "Pardus'ta / Ubuntu'da şunları dene" test listesi.
- Kod İngilizce (değişken/fonksiyon adları), yorumlar Türkçe.
- **Arayüz metinleri kodda İngilizce** (`QCoreApplication.translate`), **Türkçe çeviri dosyası ilk günden** birlikte yazılır; uygulama varsayılan Türkçe görünür. Çevirisi eksik metin kalırsa test başarısız olur.
- Araçlar: ruff, tip ipuçları, pytest. Arayüz dışı her parçanın birim testi yazılır.
- **Derleme: GitHub Actions.** Her push/PR'da: lint + test → gömülü Python + PySide6 ile .deb → Ubuntu 22.04/24.04 ve Debian 12/13 kapsayıcılarında kurulum ve `--self-check` testi.
- **Geliştirme sırasında çalıştırma: ikisi de.**
  - Geliştirme .deb'i: her çalıştırmada Actions › Artifacts › linwas-deb.
  - Kaynak koddan: `scripts/dev-setup.sh` (bir kerelik) + `scripts/run-dev.sh`.
- **Kodlama ortamı:** kullanıcının Pardus 23 bilgisayarında **Claude Code** (uygulamayı gerçekten çalıştırabildiği için). claude.ai sohbeti kararlar ve tasarım tuvali için kullanılabilir.
  - Claude Code `sudo`/`pkexec` gerektiren komutları kendi başına çalıştırmaz; kullanıcıya ne çalışacağını söyleyip onayını alır.
  - claude.ai bulut ortamında PyPI engelli (PySide6 kurulamaz); orada yalnızca arayüz dışı testler çalışır. Claude oradan Actions sonuçlarını ve hata notlarını (annotation) okuyabilir, ham günlükleri okuyamaz — bu yüzden CI betikleri hataları not olarak yazar.
- Root helper geliştirme modu: kaynak koddan çalışırken Linwas'a özel polkit kuralı kurulu olmadığı için şifre penceresi genel mesaj gösterir; kurulu pakette Linwas'a özel mesaj.
- Test ortamları: kullanıcının bilgisayarı (Pardus 23, **GNOME oturumu**) + sanal makine (Ubuntu 22.04) + CI kapsayıcıları. İlk yayından önce Mint ve Pardus 25 için de sanal makine testi.

## Güvenlik ilkesi (komut çalıştırma)
- AI, eklentiler ve arayüz **ham komut göndermez**; yalnızca tanımlı işlem adı + parametre gönderir (ör. `package.install` + `vlc`).
- Komutu root helper kendisi kurar; her parametreyi doğrular (ör. paket adı biçimi). Kabuk (shell) hiç kullanılmaz → komut enjeksiyonu baştan kapalı.
- Helper, işlem planındaki her adımı izin listesine karşı yeniden doğrular, çalıştırır ve ilerlemeyi satır satır bildirir.

## Yayın öncesi yapılacaklar
- Depo geliştirme süresince private. İlk yayından önce: ya depo herkese açılır ya da herkese açık ayrı bir "linwas-releases" deposu açılır (APT deposu + GitHub Issues orada).
- Lisans kararı (GPL-3.0 önerildi).
- Tüm hedef dağıtımlarda sanal makine testleri.
- Paketteki Maintainer bilgisinin gözden geçirilmesi.

## Eklenti mimarisi
- Linwas = sabit çekirdek + eklentiler. Kullanıcı için tek uygulama; eklenti kurulunca menüye/sayfalara kendi parçasını ekler.
- Eklenti kapıları:
  - Sayfa ekleme (menüye sayfa veya mevcut sayfaya kart)
  - Görev türü (kuyruğa kendi işleri; onay/ilerleme/sonuç ekranları otomatik)
  - İzin listesi önerisi (son karar root helper'da; eklenti root ile doğrudan bir şey çalıştıramaz)
  - Sistem taraması kontrolleri
  - Sorun Giderme belirti kartları ve çözüm reçeteleri
  - Rehber/arama girdileri ve ayar eşleşmeleri
  - AI bağlamı ve AI'ın önerebileceği görevler
  - İlk açılış sihirbazı adımı
- **Yerleşik özellikler de eklenti olarak yazılır** (Oyun, Yazıcı, Yedekleme, Windows'tan taşıma, Görev Yöneticisi, Disk temizliği, Güç ve pil, Wine vb.).
- **Sürümlü arayüz:** eklenti desteklediği arayüz sürümünü bildirir; uyumsuz eklenti kapatılır ve kullanıcıya söylenir.
- **Resmi eklentiler** imzalı APT deposundan .deb olarak gelir (Python kodlu, entry point); APT imzası yeterli.
- **Üçüncü taraf eklentiler (17 Ekim 2026, kullanıcı kararı):**
  - **Kodsuz (bildirimsel):** tek `manifest.json`; Python kodu çalıştıramaz. Yapabilecekleri: sorun giderme
    belirti kartları ve reçeteleri, tarama denetimleri (hazır denetim türleriyle: komut/dosya/servis/paket/
    çekirdek modülü/boş alan), rehber ve arama girdileri, görevler (yalnızca izin listesindeki işlemler ve
    sabit, kurulumda doğrulanan parametreler), Linwas sayfasına ya da sistem ayarına gitme, https bağlantısı.
    Eklentilere kapalı işlemler (ör. `deb.install`, `file.write_text`, `apt.add_source`/`add_key`,
    Timeshift geri yükleme) ayrı bir izin listesinde tutulur. Python kodlu üçüncü taraf eklenti sonraki
    sürümde ayrı süreçte çalışma koşuluyla değerlendirilir.
  - **Güven:** Linwas'ın incelediği, Linwas anahtarıyla imzalı **katalog** (imzalı `index.json` +
    eklenti dosyalarının SHA-256'sı; doğrulama sistemde zaten olan `gpgv` ile, yeni bağımlılık yok).
    Katalog bir eklentiyi geri çekerse Linwas onu kapatır. **Geliştirici kipi** (Ayarlar'da, varsayılan
    kapalı): imzasız yerel dosya büyük uyarıyla kurulabilir; bu eklentiler "Geliştirici" rozeti taşır.
  - **İzin ekranı:** kurulumdan önce eklentinin kullanacağı her işlem (risk düzeyiyle), açacağı sayfalar ve
    bağlantılar tek tek gösterilir; güncelleme yeni izin isterse yeniden onay alınır.
  - **Önce altyapı:** boştaki kapılar (tarama, sorun giderme, rehber, AI bağlamı) bağlanır, Ayarlar ›
    Eklentiler kartlı sayfa olur (aç/kapat, sürüm, yayıncı, rozet, izinler, hata). Aşamalar: yapilacaklar.md.
- Gelecekte olası eklentiler: bkz. `yapilacaklar.md`.

## Hedef kullanıcı ve genel UX
- Tamamen yeni Linux kullanıcısı. Sade dil, teknik terim olursa yanında açıklama.
- Terminal hiç kullanılmaz; kurulum dahil her şey GUI.
- Komutlar varsayılan gizli, "Detay" ile görülür.
- **Süzülmüş veri (23 Ekim 2026, kullanıcı kararı):** kullanıcıya ham veri değil, süzülmüş ve yorumlanmış bilgi
  gösterilir. Önce sade özet ya da hüküm ("Bağlantı son 24 saatte kararlıydı"); sayılar, adresler ve teknik alanlar
  "Ayrıntılar" / "Gelişmiş ayrıntılar" arkasındadır (varsayılan kapalı; `widgets/details_toggle.py`, kart
  içinde `QToolButton#DetailsToggle`). Gürültülü kayıtlar (çok zayıf Wi-Fi ağları, adsız Bluetooth cihazları,
  tekrarlar) varsayılan gizli, "N … göster" ile açılır; bağlı ve kayıtlı olanlar her zaman görünür. Destek
  eylemleri ("Tümünü kopyala", "Asistana sor") ham veriyi içerir.
- İlk açılış: kısa tanıtım turu → kurulum sihirbazı (sistem taraması, Windows'tan taşıma, Timeshift önerisi ve ilk tam yedek, isteğe bağlı AI anahtarı).
- Tema: Windows benzeri tasarım; Açık / Koyu / Sistem (Ayarlar'dan).
- Dil: Türkçe + İngilizce (Qt Linguist altyapısı).
- **Pencere kapatma (8 Ekim 2026 kararı):** varsayılan her kapatmada sorulur: "Arka plana küçült" / "Tamamen kapat" / "Vazgeç" + "Seçimimi hatırla" (işaretlenirse Ayarlar › Genel › "Pencereyi kapattığımda"ya yazılır; oradan "Her seferinde sor"a dönülür). Eski ayar dosyalarındaki "auto" da sorar.
- ~~Pencere kapatma varsayılanı~~ → aşağıdaki **Ayarlar (7 Ekim 2026)** kararına bakın (tepside arka planda çalışma). Pencere kapatma: Ayarlar'dan seçilir. Varsayılan: sistem tepsisi destekleniyorsa tepsiye küçülür; desteklenmiyorsa (ör. Debian/Pardus GNOME) uygulama kapanır, arka planda iş varsa bildirimle devam eder.
- Erişilebilirlik: yazı boyutu, yüksek kontrast, tam klavye kullanımı, ekran okuyucu (Orca) uyumu.
- Telemetri yok.

## Arayüz tasarımı ve teknolojisi
- Teknoloji: **Qt Widgets + QSS** (PySide6). QML seçilmedi: animasyon yok, erişilebilirlik Widgets'ta daha güçlü.
- Tasarım değerleri (renk, yazı, boşluk, köşe) tek dosyada: `ui/theme/tokens.py`. Açık / Koyu / Yüksek kontrast setleri; QSS bu değerlerden üretilir.
- Ortak bileşen kütüphanesi (kart, menü öğesi, rozet, ana buton, durum çubuğu, görev kartı); sayfalar bunlardan kurulur.
- Simgeler: kendi SVG simge setimiz (Windows benzeri çizgi stil), HiDPI uyumlu. Çizimler `ui/theme/icon_data.py`'de (masaüstü simge temasına bağlı değil); renk temadan gelir, tema değişince `ui/icons.py` bağlı simgeleri yeniler. QSS'teki onay işareti/ok simgeleri `~/.cache/linwas/icons` altına yazılır.
- Animasyon: yok.
- Erişilebilirlik her bileşene baştan eklenir.
- Tasarım akışı: sayfa sayfa — tuvalde taslak → onay → Qt'ye aktarım → sıradaki sayfa.
- Onaylı taslaklar: ana pencere (Sistem › Genel bakış) ve kuyruk senaryosu (Kuyruk → Onay → Çalışıyor → Sonuç).
  - Ana pencere: üstte başlık çubuğu; solda daraltılabilir menü (arama kutusu, rozetler, açılır alt menüler, altta sistem durumu kartı, Yardımcı paneli düğmesi, Ayarlar); ortada içerik (Genel bakış: Timeshift rozeti, 4 hızlı işlem kutusu, Güncellemeler/Sürücüler/Wi-Fi/Bluetooth kartları); sağda AI yardımcı paneli (sağlayıcı seçimi, sohbet, önerilen görev kartı + "Kuyruğa ekle", ekran görüntüsü/log ekleme, "Sistem bilgimi ekle", token çubuğu); altta durum çubuğu (kuyruk sayısı, ilerleme, Detay, "Uygula (tek onay)").
  - Vurgu rengi `#0067c0`, yazı tipi Noto Sans, açık tema zemin `#f3f3f3`, kartlar beyaz, kenarlık `#e0e3e7`, köşe 8 px (kartlar 10 px).
  - ~~Windows görünümü~~ → **macOS havası (12 Ekim 2026, kullanıcı onayı):** tuval "Linwas macOS Görünümü"
    (claude.ai artifact AYgNY1TjwxLtui1ERsfg1D: Güç ve pil, Wi-Fi, Giriş, Bileşenler). Kenar çubuğu
    System Settings gibi: her öğenin simgesi renkli yuvarlak kare içinde, seçili öğe vurgu zeminli beyaz
    yazı, üstte beyaz kullanıcı kartı, gri yuvarlak arama. İçerik zemini `#f5f5f7`, kenar çubuğu `#ebebef`,
    kartlar beyaz + köşe 12 px + hafif gölge; iç satır ayırıcısı metin hizasından başlar; bölüm başlıkları
    kartın dışında küçük gri. macOS tipi anahtar (beyaz yuvarlak düğme); düğme köşesi 8 px; vurgu `#0066d6`;
    yazı `#1d1d1f`, ikincil `#6e6e73`. Pencere düğmeleri (trafik ışıkları) yok, başlığı masaüstü çizer.
  - **Eco düzeni (23 Ekim 2026, kullanıcı kararı):** Linwas, eco (Linux Ekosistemi) projesinin ayarlar
    uygulaması olacak; macOS/Windows yanında üçüncü bir **düzen** (`UiStyle.ECO`, Ayarlar › Görünüm ›
    Düzen › "Eco düzeni"). Açık ve koyu tema birlikte; vurgu teal (`#2f6f73` / koyu `#5cb7bc`); yazı tipi
    **Figtree** (pakete gömülü, SIL OFL 1.1; ağırlıklar 400/500/700); cam/bulanıklık yok; köşe 7 px
    (kartlar 10 px); pencere düğmeleri Linwas ile aynı. Değerler `docs/tasarim/tokens-eco.json`, kodda
    `ui/theme/tokens.py` (`ECO_LIGHT`, `ECO_DARK`, `METRICS[UiStyle.ECO]`); `tests/test_eco_style.py`
    ikisinin uyumunu ve WCAG AA kontrastını denetler. Türetilen renkler (koyu vurgu, ikincil metin) belgede
    "turetilmis" diye işaretli. Ayrıntı: [eco-entegrasyonu.md](eco-entegrasyonu.md).
  - **Seçim kartları ve Wi-Fi/Bluetooth (17 Ekim 2026):** birkaç seçenekten biri yuvarlak köşeli seçim
    kartlarıyla seçilir (`widgets/option_tile.py`: başlık + gri açıklama, seçili kart vurgu kenarlıklı ve
    açık vurgu zeminli; seçim düğmesi içi beyaz noktalı dolu daire). Wi-Fi ve Bluetooth sekmeleri: üstte
    durum kartı (simge kutusu, durum, aç/kapat; aygıt yoksa sürücü yönlendirmesi), altında kart içinde
    liste (Wi-Fi: Kayıtlı/Şifreli/Açık, gizli ağ, IP; Bluetooth: Aygıtlarım / Diğer aygıtlar), unutmada
    onay, altta "Diğer … ayarları". nmcli/bluetoothctl çağrıları arka planda.
  - **Güç ve pil sayfası (17 Ekim 2026):** pil özeti (pil biçimli gösterge, büyük yüzde, durum/kalan
    süre; Pil sağlığı / Şarj döngüsü / Güç kaynağı kutuları; pil yıpranmış ya da azsa yapıcı öneri), plan
    seçim kartları (simgeli, 3 sütun), sık ayarlar satır tablosu (ad + açıklama, Prizde / Pilde), otomasyon
    kutuları (Pil tasarrufu, Zamanlama); kaydet çubuğu sayfanın altında sabit. Gelişmiş güç ayarları
    (ağaç liste) sık ayarların hemen altında ve **açık başlar** (kullanıcı: "her şeyi kontrol
    edebiliyordum, görünür olsun"); sık ayarlar kartında "Bu planın tüm ayarları" bağlantısı.
  - **Sorun giderme genişletildi (17 Ekim 2026):** taramaya DNS, saat eşitleme, salt okunur sistem diski,
    /home ve ayrı /boot doluluğu, bellek, sıcaklık (termal bölgeler, ≥ 90 °C), DKMS modülleri, yazılımla
    çizim (ekran kartı sürücüsü yok), eski APT listesi (> 14 gün), açılış süresi (> 90 sn), pil sağlığı
    (< %60) eklendi; her sorunda "Yardımcıya sor". Yeni belirti kartları: Bluetooth, mikrofon/kamera, pil
    çabuk bitiyor, tarih/saat, güncellemeler başarısız, yavaş açılış. Yeni root işlemi `package.autoremove`
    (`apt-get autoremove --purge`: eski çekirdekler, dolu /boot). Sabit genişlikli düğmeler (Disk temizliği,
    durum çubuğu, Görev Yöneticisi) yazıya göre genişliyor (`widgets/fit.py`).
  - **Dokunmatik yüzeyde sağ tık (18 Ekim 2026):** GNOME varsayılanı `click-method='fingers'` (sağ alt
    köşe sol tık sayılır) Windows'tan gelenlerde "sağ tık çalışmıyor" diye görülüyor. İlk açılış
    sihirbazında (dokunmatik yüzey varsa ve köşe tıklaması kapalıysa) "sağ alt köşeyle sağ tık" kutusu
    işaretli gelir (`'areas'`); Sorun giderme'de "Sağ tık çalışmıyor" kartı aynı düzeltmeyi ve fare
    ayarlarını sunar. `backend/touchpad.py`; şimdilik yalnız GNOME (Cinnamon/XFCE anahtarı doğrulanmadı).
  - **Görev çubuğu eklentisi ve "Temizle" (18 Ekim 2026, hata):** takvim menüsüne eklenen medya kartında
    `clear()` olmadığı için GNOME'un bildirim "Temizle" düğmesi ilk öğede hata verip bildirimleri
    silmiyordu (`s.clear is not a function`, calendar.js:976). Karta boş `clear()` ve `canClear=false`
    eklendi; eklenti dosyası görev çubuğu sayfası açılınca yenilenir, oturum yeniden açılınca geçerli.
  - **Klasör renkleri (18 Ekim 2026, kullanıcı):** Dosyalar'da sağ tık › "Klasör rengi" (7 renk: kırmızı,
    turuncu, sarı, yeşil, mavi, mor, gri + Varsayılan); `metadata::custom-icon` + Linwas'ın SVG simgeleri;
    Nautilus (`python3-nautilus`), Nemo (`nemo-python`), Thunar (`thunarx-python`, gösterimi doğrulanacak).
    Linwas sayfası Kişiselleştirme › Klasör renkleri. Ayrıntı: yapilacaklar.md › E.
  - **macOS düzeni (18 Ekim 2026, kullanıcı kararları):** düzen seçilince pencere düğmeleri solda
    (`close,minimize,maximize:`; Windows/GNOME düzenine geçince sağa döner), dock hep görünür, çöp kutusu
    ve sürücüler dock'ta. Claude'un seçtikleri: çalışan programda nokta (`DOTS`), tıklayınca öne getir /
    önizleme (`focus-or-previews`), bütün programlar düğmesi başta (`show-apps-at-top`), dinamik
    saydamlık. "Dock" bölümü: konum (alt/sol/sağ), simge boyutu 24–64, görünürlük (hep görünür / pencere
    gelince gizle / hep gizli), çöp kutusu, sürücüler, nokta, bildirim sayısı, programlar düğmesi başta,
    her ekranda dock. "Önceki düzene dön" düğme yerleşimini ve dock ayarlarını da geri getirir. macOS'taki
    büyüme (magnification) Dash to Dock'ta yok.
  - **Görev çubuğu özelleştirme (18 Ekim 2026, kullanıcı seçimi):** Windows düzeninde (Dash to Panel)
    Davranış: simgelerin yeri "Windows 11 gibi (ortada)" / "Windows 10 gibi (solda)" (Başlat ve görev
    listesi `panel-element-positions` içinde `centerMonitor` / `stackedTL`), düğmeleri birleştirme
    (`group-apps`), her ekranda (`multi-monitors`), simgede sayı ve ilerleme (`progress-show-count`,
    `progress-show-bar`). Öğeler: Başlat, Etkinlikler, saat, sistem simgeleri, masaüstünü göster köşesi
    (görünürlük `panel-element-positions`), köşede masaüstüne göz at (`show-showdesktop-hover`). Saat
    ve tarih (her GNOME düzeninde): `clock-show-date/weekday/seconds`, `clock-format`; saatin yeri
    sağda/ortada. Sabitlenmiş programlar: `org.gnome.shell favorite-apps` (sırala, çıkar, ekle). Anahtar
    ve öğe adları Pardus 23'teki Dash to Panel şemasından/kaynağından doğrulandı.
  - **Güç yönetimini tek tuşla devralma (17 Ekim 2026, kullanıcı):** sayfanın en üstünde "Güç yönetimi"
    kartı (eski "başka güç aracı" ve "servis durdu" kartlarının yerine): durum başlığı + denetim listesi
    (güç servisi, başka güç aracı, masaüstü ajanı). "Güç yönetimini Linwas'a ver" → root işlemi
    `power.take_over`: TLP/auto-cpufreq/laptop-mode-tools servislerini `systemctl disable --now` ile
    kapatır (paket silinmez), kapatılanları `/etc/linwas/power-takeover.json`'a yazar, `linwas-power.service`'i
    açıp yeniden başlatır; sonra ajan çalışmıyorsa başlatılır. "Yönetimi geri ver" → `power.give_back`:
    Linwas servisini kapatır, kayıttaki (yalnızca bilinen) araçları yeniden açar.
  - **Hazırda bekletme kurulumu (17 Ekim 2026):** eksik yalnızca swap/resume ise Linwas `/swapfile`
    (varsayılan RAM kadar, en az yarısı) oluşturur, fstab'a ve `/etc/default/grub.d/linwas-hibernate.cfg`
    ile çekirdek satırına `resume=UUID=… resume_offset=…` ekler; Secure Boot kilidi, GRUB/initramfs-tools
    olmaması, desteklenmeyen dosya sistemi, yer yokluğu ya da elle kurulmuş /swapfile'da kurmaz ve nedeni
    yazar. Ayrıntı: yapilacaklar.md › Hazırda bekletme kurulumu.
  - **Ölçek ve okunabilirlik (12 Ekim 2026, kullanıcı):** yazı küçük kalmasın. Qt'ye aktarımda gövde
    16 px, başlık 32 px, ayar satırı en az 64 px, tıklama alanı en az 40 px. Her ekranda Windows / macOS /
    Linux'taki karşılığı karşılaştırılır, en anlaşılır çözüm seçilir.
  - **Düzen seçimi (12 Ekim 2026, kullanıcı):** Linwas'ın içinde düzen seçilir: Ayarlar › Görünüm › Düzen
    = **macOS düzeni** (varsayılan, yukarıdaki) / **Windows düzeni** (önceki görünüm: vurgu `#0067c0`,
    köşe 6/8 px, düz simgeler, seçili öğede solda vurgu çizgisi, altı çizili sekmeler; yazı 15 px).
    Tema (açık/koyu/yüksek kontrast) düzenden bağımsız. Kod: `tokens.UiStyle`, `tokens.METRICS`,
    `tokens.colors(theme, style)`, `stylesheet.build(theme, style)`, ayar `ui_style`. Windows düzeninin
    ayrıntılı tasarımı sonra konuşulacak.
  - **macOS düzeni ilkeleri (12 Ekim 2026, kullanıcı; dış görüş):** birebir kopya değil. Tek tip simgeler
    (aynı çizgi kalınlığı 1.8, aynı boyut); kenar çubuğu simgeleri 13 Ekim'de yeniden
    renkli yapıldı (aşağıya bakın); kartlarda tek köşe/kenarlık/boşluk sistemi; pencere
    başlığını masaüstü çizer (çift başlık çubuğu yok); Genel bakış'ta gerçek **sistem sağlığı** özeti
    (sistem diski, ayrıysa kişisel dosyalar diski, bellek, pil sağlığı; durum rozeti İyi / Göz atın /
    İlgilenin; `backend/health.py`).
  - **Ana ekran düzeltmeleri (13 Ekim 2026, dış görüş üzerine):** Genel bakış: bilgisayar kartı (ad ›
    model › dağıtım · masaüstü › işlemci · RAM · ekran kartları; "Donanım ayrıntıları"), aynı hizada üç
    durum kartı (Güncellemeler, Sürücüler, Wi-Fi ve Bluetooth; durumlar: denetleniyor / güncel /
    işlem gerekiyor / desteklenmiyor / hata + "Yeniden dene" — önceden hiç doldurulmuyordu),
    **Öneriler** ayrı ve yalnızca doğrulanmış olanlar (APT'de güncelleme var, Timeshift kurulu değil,
    fwupd'nin bildirdiği firmware güncellemesi, pil sağlığı < %80; yoksa "Şu an ilgilenmeniz gereken
    bir şey yok"), Hızlı işlemler (kişisel yedeğin sistem geri yükleme olmadığı yazılı), en altta
    Sistem sağlığı. Kartlar klavyeyle açılır (Enter/Boşluk). Yapay zekâ paneli kapalıyken yer kaplamaz
    (dar şerit kaldırıldı); kenar çubuğunun altındaki "Yardımcı" ya da F1 açar/kapatır (yapay zekâ
    ayarlı değilse AI sayfası açılır). Alt durum çubuğu yalnızca bekleyen ya da çalışan görev varken
    görünür.
  - **Kenar çubuğu (13 Ekim 2026, kullanıcı):** macOS Sistem Ayarları gibi kategoriler, aç/kapa yok:
    başlıksız üst grup (Genel bakış, Yapay zekâ sorusu) · Sistem (Güncelleme merkezi, Programlar, Görev
    yöneticisi, Disk temizliği, Güç) · Bağlantılar ve aygıtlar (Wi-Fi/Bluetooth, Donanım ve yazıcılar,
    Ekran) · Kişiselleştirme (Tema, Görev çubuğu, Yazı tipleri) · Düzenleme (Program klasörleri, Çalışma
    grupları, Pencere grupları) · Yedekleme ve taşıma · Yardım (Sorun giderme, Windows'ta nasıldı?, Tüm
    ayarlar) · eklenti sayfaları "Eklentiler" altında. Basit tek renkli simge yok: macOS düzeninde her
    öğenin kendi renkli, üstten alta degradeli kutusu + beyaz kalın simge (seçiliyken de renk korunur);
    Windows düzeninde düz simge. Kategori başlığı 14 px yarı kalın ikincil renk; tüm öğeleri gizliyse
    başlık da gizlenir.
  - Kenar çubuğu (eski): üstte logo + ad, her öğede simge. Genel bakış kartlarında vurgu renkli simge kutusu, tıklanabilir kartlarda üzerine gelince vurgu kenarlık; durum kartları ilgili sayfayı açar.

## Menü yapısı
- **AI Soru** (geniş sohbet ekranı; ayrıca her sayfada yardımcı panel)
- **Sistem:** Genel bakış, Güncellemeler, Sürücüler, Wi-Fi ve Bluetooth, **Yedekler ve geri alma**, Donanım ve yazıcı, Görev Yöneticisi, Disk temizliği, Yedekleme (kişisel dosyalar), Güç ve pil (masaüstü bilgisayarda adı "Güç", pil bölümleri gizli), Windows'tan taşıma, Tüm ayarlar (Denetim Masası)
- **Arayüz:** Windows görünümü, tema/duvar kağıdı, yazı tipleri, ekran/ölçekleme
- **Program:** Üstte arama, altta "Windows'ta ne kullanıyordun?" bölümü; **Kurulu programlar** sekmesi; Oyun sekmesi
- **Sorun Giderme:** Üstte tek tıkla tam tarama, altta belirti kartları
- **Ayarlar:** Linwas'ın kendi ayarları (işlem geçmişi ve eklenti listesi burada)
- **Ayarlar (7 Ekim 2026 kararı):**
  - **Düzen:** sayfa içinde solda kategori listesi, sağda seçilen bölüm; üstte "Ayarlarda ara". Bölümler: Genel, Görünüm, Yapay zekâ, Bildirimler ve başlangıç, Gizlilik ve veriler, Yedekleme ve sıfırlama, Eklentiler, Hakkında.
  - **Kaydetme:** değişiklik anında kaydedilir ve uygulanır ("Kaydet" düğmesi yok); root gerektirenler yine şifre sorar.
  - **Teknik ayarlar ayrı yerde (Denetim Masası gibi):** basit Ayarlar sayfasında teknik ayar yok; teknik ayarların hepsi ayrı bir "Gelişmiş" sayfasında (ör. komut çıktılarını ve paket adlarını gösterme, ayrıntılı günlük, tanılama).
  - **Yapay zekâ:** AI ayarları penceresi bu bölüme taşınır (sağlayıcı, API anahtarı, model); aylık token sınırı (yaklaşınca uyarı, aşılınca durdurma); sohbet geçmişi saklama süresi (hiç / 7 gün / 30 gün / her zaman) + tümünü sil; asistanın erişim izinleri (sistem bilgisi, ekran görüntüsü, log ekleme).
  - **Bildirimler ve başlangıç:** Linwas oturum açılınca tepside sessizce başlar (varsayılan açık, kapatılabilir); masaüstü bildirimleri (güncelleme, yeniden başlatma, yedek, sorun), sessiz saatler.
  - **Gizlilik ve veriler:** Linwas'ın tuttuğu veriler (işlem geçmişi, AI sohbetleri, geri alma kayıtları) görülür ve tek tıkla silinir; hata raporu izni.
  - **Uygulama (aşama 1–3, 7 Ekim 2026):** `ui/pages/settings.py` (bölümler: Genel, Görünüm, Yapay zekâ, Bildirimler ve başlangıç, Gizlilik ve veriler, Eklentiler; arama bölüm metinlerinde arar). AI ayarları penceresi `ui/pages/settings_ai.py` bölümüne taşındı (anahtar düzenleme bitince, sınır değişince kaydedilir; karşılama sihirbazı aynı bölümü pencerede açar); ⚙ düğmesi Ayarlar › Yapay zekâ'yı açar; sınırın %80'inde panelde uyarı. Sohbet saklama `ai_retention` (açılışta ve değişince eski sohbetler silinir; "Saklama" seçiliyse hiç kaydedilmez); `ai_allow_system_info` kapalıysa sistem bilgisi eklenemez. **Arka plan:** Pardus GNOME'da tepsi yok (AppIndicator eklentisi kurulu değil), bu yüzden tepsiye bağlı değil: pencere kapatılınca Linwas gizlenip çalışmaya devam eder (tepsi varsa simge de gösterilir), ilk seferde "çalışmaya devam ediyor" bildirimi; tamamen kapatma Ayarlar › Genel'de. Oturumla başlatma `~/.config/autostart/linwas.desktop` (`linwas --background`, penceresiz). Tek kopya: `QLocalServer` (`linwas-<uid>`); ikinci başlatma pencereyi öne getirir, .deb/.exe yolunu iletir. Bildirimler `gdbus call … Notify` (bildirimdeki "Aç" `gdbus monitor` ile dinlenir); saatte bir: güncelleme sayısı, yeniden başlatma (açılış başına bir kez), otomatik güncelleme sonucu, sürücüsüz aygıt; aynı durum bir kez bildirilir (`~/.local/share/linwas/notify_state.json`); sessiz saatlerde gönderilmez.
  - **Uygulama (aşama 4–5, 7 Ekim 2026):** Gizlilik ve veriler: tutulan veriler boyutlarıyla (`core/user_data.py`: işlem geçmişi, AI sohbetleri, AI kullanım sayaçları, bildirim durumu, sürücü değişikliği geçmişi, günlükler) tek tek ya da toplu silinir; ayarlar ve API anahtarları korunur; geri alma kayıtları root'a ait olduğundan yalnızca sayısı gösterilir (Yedekler ve geri alma'ya bağlantı). Yedekleme ve sıfırlama: ayarlar + AI tercihleri + aylık sınırlar JSON'a dışa/içe aktarılır (`"format": "linwas-settings"`; API anahtarları ve bu bilgisayara ait ilk açılış bilgileri taşınmaz); sıfırlama ilk açılış bilgilerini korur; sonrasında tema/başlangıç/AI hemen uygulanır, sayfa yeniden kurulur. Hakkında: sürüm, sistem, masaüstü, Python, Qt/PySide6; **geliştirici kartı (8 Ekim 2026 kararı, kodlandı 10 Ekim 2026 — deneme bekliyor):** Lisanslar kartının üstünde geliştirici (mehmedgur; gerçek ad kullanıcı isterse), e-posta (mehmedgrbz11@gmail.com, .deb Maintainer satırıyla aynı), proje sayfası (github.com/mehmedgur/linwas2), "Sorun bildir" düğmesi buraya taşınır, lisans (yayın öncesi karar; o zamana dek "karar verilmedi"); bilgiler tek yerde (`linwas/__init__.py`); sistem bilgisini kopyala; sorun bildir (GitHub Issues); lisanslar (Linwas lisansı yayın öncesi karar). **Gelişmiş sayfası** (`ui/pages/advanced.py`, menüde yok; Ayarlar'ın sol altındaki bağlantıyla): teknik ayrıntıları göster (`show_details`, görev penceresinde komut çıktısı baştan açık), ayrıntılı günlük (`debug_log`, `~/.local/state/linwas/linwas.log`, 1 MB × 3), ayar/veri/günlük klasörlerini aç, tanılama (`backend/diagnostics.py`: pkexec, polkit kuralı, sistem yardımcısı, zamanlayıcı, gdbus, anahtarlık, 2 GB boş alan, internet, Flatpak, fwupd, Timeshift; sonuçlar kopyalanabilir), otomatik güncellemeyi şimdi çalıştır (`service.restart linwas-autoupdate.service`), paket sistemi bakımı (paket listesini yenile, bozuk paketleri onar, önbelleği temizle).
  - **Yedekleme ve sıfırlama:** Linwas ayarlarını dosyaya dışa/içe aktarma (yeni bilgisayara taşıma), varsayılanlara sıfırlama. **Hakkında:** sürüm, sistem bilgisini kopyala, lisanslar.
- Menü özellikleri: daraltma, arama kutusu (Windows terimlerini de arar), açılır alt menüler, bildirim rozetleri, sistem durumu kartı, yardımcı paneli düğmesi.
- Genel bakışta hızlı işlemler: Görev Yöneticisi, Disk temizliği, Dosyalarımı yedekle, Windows'tan taşı.

## Yedekler ve geri alma
- Riskli işlemden önce kullanıcıya **iki seçenek** sunulur (onay penceresinde):
  1. **Tam yedek (Timeshift):** tüm sistemin anlık görüntüsü; uzun sürebilir ve yer kaplar, en güvenli yol.
  2. **Hızlı geri alma (değişiklik yedeği):** Linwas, değiştireceği dosyaların işlem öncesi kopyasını ve kurulan/kaldırılan paketlerin listesini kaydeder. İşlem sonrası **"Değişiklikleri geri al"** butonu.
- Hızlı geri almanın sınırı kullanıcıya sade dille söylenir: ayar dosyaları ve kurulan/kaldırılan paketler geri alınabilir; sistem güncellemeleriyle yükseltilen paketlerin eski sürümüne dönüş her zaman mümkün değildir — bunun için tam yedek gerekir.
- Önerilen seçenek işlem türüne göre önceden seçili gelir (ör. sürücü/çekirdek → tam yedek; ayar değişikliği → hızlı geri alma).
- Son tam yedek 24 saatten yeniyse bu bilgi gösterilir, yeni tam yedek almadan devam edilebilir.
- Disk alanı yetersizse tam yedek öncesi uyarı.
- İlk tam yedek, ilk açılış sihirbazında (kullanıcı beklemeye hazırken) önerilir.
- Timeshift yoksa: sihirbazda kurulum önerisi; riskli işlemde uyarı + hızlı geri alma seçeneği.
- **"Yedekler ve geri alma" sayfası (Sistem altında):** Timeshift anlık görüntüleri ve Linwas değişiklik yedekleri tek listede; tarih, hangi işlem için alındığı, kapladığı alan. Kullanıcı her yedeği görebilir, geri yükleyebilir ve silebilir; toplam yedek boyutu gösterilir.
- Değişiklik yedekleri root'a ait güvenli bir sistem klasöründe tutulur; geri yükleme ve silme kuyruk + toplu onay üzerinden yapılır.

## Sistem ayarlarına yönlendirme
- Linwas'ın yaptığı işler Linwas içinde kalır (**Linwas öncelikli**); aynı ayarı sistem de yapabiliyorsa sistem ayarı ikincil link olarak verilir.
- Linwas'ın yapmadığı ayarlar için **"Sistem ayarlarında aç"** butonu: masaüstüne göre doğru ayar uygulaması, mümkünse doğru bölümde açılır (GNOME: Ayarlar bölüm adıyla; Cinnamon: Sistem Ayarları modül adıyla; XFCE: ilgili ayrı ayar uygulaması).
- Butonun yerleri: ilgili Linwas sayfaları, arama sonuçları ("Linux'ta burada: Ayarlar › Fare"), "Tüm ayarlar (Denetim Masası)" sayfası, AI cevapları.
- "Tüm ayarlar (Denetim Masası)": Windows'taki gibi kategoriler. **Görünüm (8 Ekim 2026 kararı, kodlandı — `ui/pages/all_settings.py`, denenmedi):** klasik Denetim Masası "Kategori görünümü": her kategori bir satır; solda büyük simge (kendi SVG setimiz, gerekirse yeni simge), sağda kalın başlık ve altında "Tarih ve saat · Dil ve bölge · …" biçiminde tıklanabilir bağlantılar. Linwas'ın kendi sayfası olan ayarlarda küçük "Linwas" etiketi; sistemdeki karşılığı sağ tık menüsündeki "Sistem ayarlarında aç" ile açılır (satırdaki ayrı "Sistem" düğmesi kalkar). Sağ üstte arama kutusu + "Sistem ayarlarını aç". Kategoriler: Sistem; Donanım ve ses; Ağ ve İnternet; Görünüm ve kişiselleştirme; Gizlilik ve bildirimler; Erişim kolaylığı (iki sütun). Arama kategori adında ve bağlantı metinlerinde arar (Türkçe İ/ı duyarsız). Görsel düzen (8 Ekim 2026 düzeltmesi): her kategori ayrı kart (vurgu renkli 52 px simge kutusu, başlık + kısa açıklama, ince çizgi); altında her ayar kendi simgesiyle düğme (iki sütun), Linwas etiketi açık mavi küçük rozet. Sağ tık ve klavyedeki menü tuşu aynı menüyü açar. Sistem karşılığı da Linwas sayfası da olmayan ayar soluk (devre dışı) gösterilir.
- Yardım: yan panelde adım adım rehber; önce metin, en sık 10–15 ayar için ekran görüntüsü.
- Eşleşmeler `data/settings_map.json` içinde, masaüstü ve sürüme göre; Pardus 23 ve Ubuntu 22.04'te tek tek doğrulanır. Bölüm bulunamazsa ayar uygulamasının ana ekranı açılır.
- Güvenlik: kullanıcı yetkisiyle açılır, şifre istemez, kuyruğa girmez; yalnızca bilinen ayar uygulamaları açılabilir.

## İzinler ve görevler
- İşlemler kuyruğa girer; "Uygula" ile tek polkit onayı (toplu onay).
- Riskli işlem kuyruktaysa Linwas başa yedek adımı ekler (bkz. Yedekler ve geri alma).
- Onay penceresi: adımlar, yedek seçeneği, tahmini süre, yeniden başlatma gereği, "yalnızca izin listesindeki işlemler" notu, "Çalışacak komutları göster".
- Root helper her komutu whitelist'e karşı yeniden doğrular (bkz. Güvenlik ilkesi).
- Görev ilerlemesi alt durum çubuğunda; pencere arka plana alınabilir.
- Sonuç ekranı: başarılı/başarısız adımlar, "Yeniden dene" + "Yardımcıya sor", "Değişiklikleri geri al" (hızlı geri alma seçildiyse), gerekirse "Yeniden başlatma gerekli" kartı.
- İşlem geçmişi tutulur ve görüntülenebilir.

## Hata akışı
- Hata çıktısı maskelenip otomatik AI paneline gider.
- AI kapalıysa Sorun Giderme'deki hazır adımlara düşer.
- İlk seferde "hata kayıtlarını AI'a göndereyim mi?" onayı.
- "Sorun bildir": maskeli rapor hazırlar; "GitHub'da aç" (doldurulmuş issue sayfası) + "Raporu kopyala / kaydet" (GitHub hesabı olmayanlar için).

## Program kurulumu ve kaldırma
- **Arama:** Program sayfasının üstündeki arama kutusuyla kullanıcı istediği uygulamayı arayıp "Kur" ile kuyruğa ekler.
  - Yalnızca kullanıcıya yönelik masaüstü uygulamaları listelenir (AppStream kataloğu); Türkçe ad, simge, açıklama, ekran görüntüsü. Kütüphane/teknik paketler gösterilmez.
  - Windows adıyla arama: "Photoshop" → GIMP, Krita önerisi (rehber üzerinden).
- **Kaynaklar:**
  - APT ve Flatpak (Flathub). Aynı uygulama ikisinde de varsa her zaman sorulur, farklar sade dille açıklanır.
  - **Seçilmiş üçüncü taraf listesi:** depolarda bulunmayan popüler uygulamalar (ör. Chrome, Zoom) için üreticilerin resmi depoları. Depo ekleme kuyrukta ayrı bir adım olarak gösterilir. Liste resmi eklenti mantığıyla güncellenir; depo adresleri ve imza anahtarları üreticinin resmi belgesinden doğrulanır.
  - **Herhangi bir .deb dosyası:** kullanıcı indirdiği .deb'i Linwas ile açar; Linwas risk analizini (kaynak, imza, bağımlılıklar, ne değiştireceği) gösterir, onayla kuyruğa ekler.
- Ubuntu'da Flatpak gerekirse Linwas onu da kurar (kuyruk üzerinden).
- **Snap:** Snap ile kurulu uygulamalar listede gösterilir ve güncellenebilir; yeni kurulum kaynağı olarak sunulmaz. Mint'te gösterilmez.
- ~~Güncellemeler: bildirilir, kullanıcı başlatır.~~ → **Güncelleme merkezi** (7 Ekim 2026 kararı, aşağıda).
- Sürücüler: önerilen tek tıkla + "Diğer seçenekler" (Güncelleme merkezi › Sürücüler altında).
- **Güncelleme merkezi (7 Ekim 2026 kararı; Windows Update benzeri, daha gelişmiş):**
  - **Tek sayfa:** Güncellemeler + Sürücüler + Firmware birleşir. Üstte durum ("Güncelsiniz" / "N güncelleme"), "Denetle" düğmesi, son denetim zamanı; altında bölümler: Sistem güncellemeleri, Sürücüler, Firmware, Güncelleme geçmişi, Gelişmiş seçenekler.
  - **Otomatik kurulum:** güvenlik + sistem güncellemeleri (dağıtım deposu) kendiliğinden kurulur. Sürücü değişikliği, yeni çekirdek serisi ve firmware her zaman kullanıcı onayıyla. **Linwas'ın kendi systemd zamanlayıcısı** + root helper (unattended-upgrades değil); geri alma kaydı tutulur, hata AI'a sorulabilir.
  - **Duraklatma:** Windows gibi "1 hafta duraklat", açılır listeden 5 haftaya kadar; süre dolunca kendiliğinden devam eder. Gelişmiş seçeneklerde tamamen kapatma.
  - **Koşullar:** pilde çalışırken ve ölçülü bağlantıda (NetworkManager) bekler; Timeshift varsa kurulumdan önce anlık görüntü (sınırlı sayıda tutulur).
  - **Yeniden başlatma:** bildirim + rozet; "Şimdi yeniden başlat" ya da "Bu gece şu saatte". Linwas kendiliğinden yeniden başlatmaz.
  - **Sürücüler:** sürüm seçimi (ör. NVIDIA 535/550, önerilen işaretli), önceki sürücüye dönme (değişiklikten önce yedek), Secure Boot açıksa MOK kaydı adımları sade dille, kurulum sonrası sorunlar (siyah ekran, çözünürlük) için hazır çözümler + AI.
  - **Kapsam:** yazıcı/tarayıcı sürücüleri (takılan aygıta göre paket önerisi), firmware (fwupd; sürüm notları, geçmiş, yeniden başlatma gereksinimi), yeni donanım için yeni çekirdek (Ubuntu HWE, Debian/Pardus backports; tam yedekle).
  - **Uygulama (aşama 1–2, 7 Ekim 2026):** sayfa `ui/pages/update_center.py` (kenar çubuğunda "Güncelleme merkezi"; eski "drivers" sayfa kimliği Sürücüler bölümüne yönlenir). Geçmiş `/var/log/apt/history.log` (+ .gz) dosyasından okunur (herkes okuyabilir); otomatik kurulum apt'ye `-o Linwas::Auto=1` verir, geçmişte "Otomatik" rozeti böyle bulunur. Otomatik kurulum `core/autoupdate.py`: `linwas-autoupdate.timer` (günlük, açılıştan 15 dk sonra, `Persistent=true`) → `linwas-autoupdate.service` (oneshot, root, parametresiz) → `apt-get update` + `apt-get upgrade` (yeni paket kurmaz/kaldırmaz). Ayar `/etc/linwas/autoupdate.json` (varsayılan: açık, yedek açık), yalnızca root helper işlemi `autoupdate.configure` (enabled, snapshot, pause_weeks −1…5) yazar. Durum `/var/lib/linwas-autoupdate/state.json`. Pil: prize/USB-C güç kaynağı takılı değilse ya da pil şarj olmadan %30'un altındaysa beklenir; ölçülü: NetworkManager `Metered` özelliği 1 ya da 3. Yedek: Timeshift, açıklama "Linwas otomatik güncelleme", son 3 tanesi tutulur. Yeniden başlatma gerekli: `/run/reboot-required` ya da çalışandan yeni kurulu çekirdek; "Şimdi" `systemctl reboot` (kullanıcı, logind), "Bu saatte" root işlemi `power.schedule_reboot` (`shutdown -r SS:DD`), iptal `power.cancel_reboot`.
  - **Uygulama (aşama 3–4, 7 Ekim 2026):** NVIDIA seçenekleri depodan okunur (`backend/driver_options.py`; Ubuntu `nvidia-driver-<n>[-open]`, Debian/Pardus `nvidia-driver`, `nvidia-tesla-<n>-driver`, `nvidia-legacy-<n>xx-driver`); önerilen `ubuntu-drivers devices` ya da `nvidia-detect`, yoksa Debian'da `nvidia-driver`, Ubuntu'da en yeni seri; legacy sürümler "yalnızca eski kartlar için" işaretli. Sürücü değişikliği görevi: Timeshift yedeği (kuruluysa) → `package.install` ya da açık kaynağa dönüş için yeni root işlemi `driver.remove_nvidia` (`apt-get purge '.*nvidia.*'` + autoremove) → Secure Boot açık ve anahtar kayıtlı değilse yeni root işlemi `secureboot.enroll_mok` (8 haneli tek kullanımlık şifre Linwas'ta üretilip gösterilir, `mokutil --import`'a standart girdiden verilir; anahtar Ubuntu `/var/lib/shim-signed/mok/MOK.der`, Debian `/var/lib/dkms/mok.pub`). Başarılı değişiklik `~/.local/share/linwas/driver_changes.json`'a yazılır; "Önceki sürücüye dön" buradan. Sorun giderme kartı + "Asistana sor" (aygıt/sürücü/Secure Boot bilgisi). Aygıt Yöneticisi: `backend/devices.py` (PCI `lspci -vmmnnk`, USB sysfs + `lsusb` adları); sürücüsüz ekran/ağ/Bluetooth/ses/kamera/depolama aygıtları "sorunlu". Yazıcı/tarayıcı: USB üretici kimliğine göre paket (HP `hplip`, Epson `printer-driver-escpr`, Brother `printer-driver-brlaser`, Canon `printer-driver-gutenprint`, Samsung `printer-driver-splix`; IPP-over-USB aygıtlarda `ipp-usb`); Sürücüler bölümünde "Yazıcılar ve tarayıcılar" ve Donanım sayfasında önerilir.
  - **Donanımdan bağımsızlık (7 Ekim 2026):** öneriler yalnızca o makinenin deposunda gerçekten bulunan paketlerden gösterilir (Ubuntu'da `firmware-*` yok, `linux-firmware` içinde gelir). AMD: `firmware-amd-graphics`, `mesa-vulkan-drivers`, `mesa-va-drivers`; Intel: `intel-media-va-driver`, `mesa-vulkan-drivers`; işlemci mikrokodu `intel-microcode` / `amd64-microcode` (/proc/cpuinfo üreticisine göre).
  - **Görünüm (7 Ekim 2026 düzeltmesi):** Windows'taki "durum + alt alta satırlar" düzeni yerine Linwas'ın kendi düzeni: başlıkta tek satır durum + Denetle / Tümünü kur; büyük sayılı üç kutucuk (Sistem, Sürücüler, Firmware); altta yan yana "Son değişiklikler" (son 3 işlem) ve "Otomatik güncellemeler" (durum, son çalışma, Duraklat/Devam et, Ayarlar).
  - **Uygulama (aşama 5, 7 Ekim 2026):** Firmware bölümü `ui/pages/firmware_view.py` + `backend/firmware.py`: `fwupdmgr get-devices|get-updates|get-history --json` (kullanıcı yetkisiyle); aygıt başına güncelleme, sürüm notları (HTML → düz metin), "Önemli" (urgency high/critical), "prize takılı olmalı" (require-ac; pilde düğme kapalı), yeniden başlatmada tamamlanır (needs-reboot); işlemci mikrokodu kartı. Eski metin sayımı (• sayma) hatalıydı, JSON'a geçildi. Yeni root işlemleri: `firmware.refresh` (`fwupdmgr refresh --force`), `firmware.update_device` (40 haneli aygıt kimliği). Yeni çekirdek (`backend/kernel.py`, Sürücüler bölümünde kart): Ubuntu HWE (`linux-generic-hwe-<sürüm>`, `package.install`); Debian türevlerinde depoda tanımlı `*-backports` varsa yeni root işlemi `kernel.install_backports` (`apt-get install -t <suite> linux-image-<mimari>`); saf Debian'da backports yoksa `apt.add_source` ile resmi `deb.debian.org` backports satırı (`linwas-backports.list`). Pardus gibi türevlere Debian deposu eklenmez. Kurulumdan önce Timeshift yedeği.
  - **Sürücüler geliştirmesi (8 Ekim 2026 kararı):**
    - **Görünüm — donanım kartları:** her donanım (ekran kartı, Wi-Fi/ağ, ses, Bluetooth, kamera, yazıcı/tarayıcı) büyük simgeli kart: model adı, kullanılan sürücü, durum rozeti (Çalışıyor / Önerilen var / Sorunlu), işlem düğmesi. Sade metin; "Ayrıntılar" açılınca paket adı, sürüm, çekirdek modülü, PCI/USB kimliği.
    - **Uygulama (aşama 1, 8 Ekim 2026):** `backend/hardware_cards.py` aygıtları (`devices.list_devices`) ve sürücü önerilerini birleştirir; öneri üretici kimliğine göre (10de NVIDIA, 1002 AMD, 8086 Intel, 14e4 Broadcom, 10ec Realtek, 14c3 MediaTek) aygıta bağlanır, eşleşmezse gruptaki ilk aygıta, aygıt yoksa aygıtsız karta. Ekran kartlarının HDMI ses denetleyicisi ayrı kart olmaz. Sürücü sürümü `/sys/module/<sürücü>/version`. USB sınıf 06 (Still Imaging: telefon, fotoğraf makinesi) artık yazıcı sayılmaz.
    - **Sürücü sağlık kontrolü:** kurulu sürücü gerçekten çalışıyor mu — yüklü çekirdek modülü, çizimi hangi kartın yaptığı, kurulu paket ile yüklü modül sürüm uyuşmazlığı (yeniden başlatma gerekir), DKMS derleme hatası; sonuç sade dille + tek tık düzeltme (kuyruk üzerinden).
    - **Uygulama (aşama 2, 8 Ekim 2026):** `backend/driver_health.py`; Sürücüler sayfasının üstünde "Sürücü sağlık kontrolü" kartı, "Denetle" ile. Denetimler: NVIDIA (paket kurulu + modül yüklü mü; `/sys/module/nvidia/version` ile `modinfo -F version nvidia|nvidia-current` farklıysa yeniden başlatma; Secure Boot anahtarı; nouveau hâlâ yüklü), DKMS (`dkms status`: her modül çalışan çekirdek için "installed" mı; değilse eksikse `linux-headers-<uname -r>` + yeni root işlemi `driver.rebuild_modules` = `dkms autoinstall -k <çalışan çekirdek>`), çizim (`glxinfo -B` renderer; llvmpipe/softpipe = hızlandırma yok → asistana sor). Düzeltmeler: Şimdi yeniden başlat (`systemctl reboot`, onaylı), Sürücüleri yeniden hazırla, Anahtarı kaydet. `dkms`/`modinfo` /usr/sbin'de aranır.
    - **Eksik firmware tespiti:** çekirdek günlüğündeki "firmware yüklenemedi" kayıtları; gereken paket depoda doğrulanıp önerilir.
    - Sağlık kontrolü ve firmware tespiti **yalnızca elle** ("Denetle" düğmesi); arka planda çalışmaz, bildirim göndermez.
    - **Uygulama (aşama 3, 8 Ekim 2026):** `backend/firmware_missing.py`, sağlık kontrolünün parçası. Kaynaklar: (1) `journalctl -k -b` "Direct firmware load for … failed" / "firmware: failed to load …" (normal kullanıcı çoğunlukla okuyamaz: Pardus'ta `dmesg_restrict=1`, journal grubu yok → atlanır); aygıtı çalışan sürücülerin satırları sayılmaz (iwlwifi önce yeni sürümü dener); (2) bağlı sürücüsü olmayan önemli aygıtta modülün `modinfo -F firmware` dosyalarının hiçbiri /lib/firmware'de (.xz/.zst dahil) yoksa. Dosya ön eki → paket (Pardus 23'te doğrulandı: firmware-iwlwifi, -realtek, -atheros, -brcm80211, -misc-nonfree (MediaTek de burada; firmware-mediatek yok), -amd-graphics, -sof-signed, -intel-sound, -libertas, -ti-connectivity; Ubuntu linux-firmware); ilk depoda bulunan önerilir. Paket kurulu ama dosya günlükte eksikse "yeniden başlat".
    - **Hibrit grafik (PRIME):** varsayılan Dengeli (tümleşik kart çizer, güçlü kart gerektiğinde); programı güçlü kartla açma listesi + menü kısayolu; Ubuntu'da (`prime-select` varsa) ayrıca Tasarruf / Performans modu. Komutlar ve ortam değişkenleri resmi belgeden doğrulanacak.
    - **Uygulama (aşama 4, 8 Ekim 2026):** `backend/hybrid_gpu.py` + `ui/pages/hybrid_view.py`; Sürücüler sayfasında iki ekran kartı varsa "Hibrit grafik" kartı. Tümleşik kart = Intel varsa o, yoksa ilk. Program seçilince menü kısayolu `~/.local/share/applications/<aynı ad>.desktop` olarak kopyalanır: `PrefersNonDefaultGPU=true` + her `Exec=` başına `env` (NVIDIA kapalı kaynak: `__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia __VK_LAYER_NV_optimus=NVIDIA_only`; diğerleri `DRI_PRIME=1`) + `X-Linwas-GPU=true` işareti; yalnızca işaretli dosyalar silinir, kullanıcının kendi kısayolu `.linwas-orig` olarak saklanıp geri konur. Ubuntu'da `prime-select` varsa kip seçimi (yeni root işlemi `prime.select`: intel / on-demand / nvidia).
    - **Yeni sürüm bildirimi:** depoda kart için daha yeni NVIDIA serisi çıkınca bildirim + sürüm notu; kurulum yine onayla.
    - **Uygulama (aşama 5, 8 Ekim 2026):** saatlik bildirim döngüsü (`ui/notifier.py`) NVIDIA ekran kartı varsa günde en çok bir kez `driver_options.nvidia_options()` okur; `newer_series()` kurulu seri numaralı paketten (`nvidia-driver-<n>`) daha yeni seriyi bulur (açık çekirdek -open, legacy, tesla hariç). Her yeni seri için bir kez bildirim ("Güncellemeler" bildirim ayarına bağlı), "Aç" Sürücüler bölümünü açar. Debian/Pardus `nvidia-driver` tek paket olduğundan bildirim çıkmaz (yeni sürüm normal güncellemeyle gelir). Sürüm notu bağlantısı eklenmedi (NVIDIA sayfa adresi doğrulanmadı).
    - Sıra (her biri ayrı commit, aralarda kullanıcı dener): görünüm → sağlık → firmware → PRIME → bildirim.
  - **Aygıt Yöneticisi:** Donanım ve yazıcı altında ayrı görünüm; bütün PCI/USB aygıtları, kullandığı sürücü, durumu; sürücüsüz/sorunlu aygıtlar en üstte uyarıyla. Güncelleme merkezi ile karşılıklı bağlantı.
- EXE: risk analizi; Linux alternatifi varsa önerilir, yoksa Wine ile açılır. (6 Ekim 2026 ayrıntıları:)
  - **Açma:** Programlar › "Windows programı aç (.exe)…" ve "Windows programları" sekmesi; .exe/.msi çift tıklanınca Linwas açılır (kurulu pakette ilk açılışta `xdg-mime default`, kullanıcı düzeyinde).
  - **.deb dosyaları (18 Ekim 2026, kullanıcı):** çift tıklanan .deb Linwas'ta açılır (risk analizi →
    kurulum). Kurulu pakette ilk açılışta `xdg-mime default linwas.desktop` (asıl tür ve eski adları,
    kullanıcı düzeyinde); önceki uygulama (ör. Arşiv Yöneticisi) ayarlara yazılır. Ayarlar › Genel ›
    "Dosyaları açma" kutusu kapatılınca ona dönülür (yoksa kullanıcının mimeapps.list'inden Linwas
    satırı silinir). `backend/file_handlers.py`.
  - **Analiz** (`backend/exe_inspect.py`, salt okunur): PE başlığı (mimari, konsol/pencere, imza tablosu var mı — Linux'ta doğrulanamaz, .NET), sürüm bilgisi (şirket/ürün), kurulum türü (Inno/NSIS/MSI/InstallShield/WiX), çift uzantı hilesi, tarayıcının yazdığı indirme adresi (xattr), SHA256. Risk: yüksek = geçersiz PE / çift uzantı / ARM; orta = imzasız veya yapımcı yok.
  - **Virüs taraması:** yalnızca "VirusTotal'da denetle" düğmesi (tarayıcıda, yalnızca SHA256 ile; dosya gönderilmez). ClamAV yok.
  - **Wine:** dağıtım deposundan; yeni root işlemi `wine.setup` (i386 mimarisi + `wine wine64 wine32:i386`).
  - **Ortam (WINEPREFIX) — karma:** varsayılan tek ortak ortam (`~/.local/share/linwas/wine/shared`); yüksek riskli dosya her zaman ayrı ortamda; kullanıcı "Ayrı ortamda aç" seçebilir; ortak ortamda 60 sn içinde hata koduyla kapanan program için "ayrı ortamda yeniden dene" önerilir. Ayrı ortam silinince kısayolları da silinir; ortak ortamdaki program Wine'ın "Program Ekle/Kaldır" penceresiyle kaldırılır.
  - **Bottles'a geçiş (7 Ekim 2026 kararı, kodlandı):** Windows programları Bottles üzerinden çalıştırılacak; Linwas Bottles'ı arka planda resmi komut satırı aracıyla (`bottles-cli`, Flatpak'ta `flatpak run --command=bottles-cli com.usebottles.bottles …`) yönetir, kullanıcı Bottles penceresini görmez. Akış: Bottles yoksa Flatpak olarak kurulur (kuyrukta adım) → programa özel şişe (uygulama/oyun profili, 64 bit + 32 bit desteği) → kurulum dosyası şişede çalışır → program şişeye kaydedilir, menüye kısayol eklenir → çıktı JSON olarak okunur, hata AI'a iletilip sade dille gösterilir. Kabuk yok, sabit komutlar, kullanıcı yetkisiyle (şifre yok); Bottles kendi Wine sürümünü getirir. Bottles beğenilmezse yukarıdaki dağıtım Wine'ı yoluna geri dönülür (mevcut kod şimdilik korunur).
    - **Uygulama ayrıntıları:** `backend/bottles.py` (`ENABLED = False` → Wine yoluna dönüş). Her programa ayrı şişe (ad: programın sadeleştirilmiş adı); Linwas'ın şişeleri `~/.local/share/linwas/bottles.json` kaydında. Flatpak Bottles ev klasörünü göremediği için kurulum dosyasının klasörü yalnızca o çalıştırmada salt okunur açılır (`flatpak run --filesystem=<klasör>:ro`). Kurulumdan sonra `--json programs` okunur, her programa `~/.local/share/applications/linwas-bottle-<şişe>--<program>.desktop` kısayolu yazılır (`bottles-cli run -b … -p …`). Kurulum dosyası olmayan EXE `bottles-cli add` ile eklenir, kendi klasöründen açılır. Şişe silme CLI'da yok: Linwas kaydındaki şişenin klasörü (`~/.var/app/com.usebottles.bottles/data/bottles/bottles/<ad>`) ve kısayolları silinir. Bottles yoksa görev: (Flatpak yoksa yeni root işlemi `flatpak.setup`: `flatpak` paketi + Flathub deposu) → `flatpak.install com.usebottles.bottles`. "Bu bir oyun" seçilirse `gaming` profili. Hata penceresinde "Asistana sor".
  - **Windows sanal makinesi (7 Ekim 2026; aynı gün askıya alındı → yapilacaklar.md › Bekleyen fikirler; Wine/Bottles'ta çalışmayan büyük programlar için, ilk hedef Microsoft 365):** Bottles'ta Microsoft 365 kurulumu `30088-45` ve `0-2031 (17002)` hatalarıyla başarısız oldu (CrossOver da "kuruluyor ama çalışmıyor" diyor). Yol: QEMU/KVM içinde Windows + FreeRDP RemoteApp; Office pencereleri Linux masaüstünde yerel uygulama gibi görünür, menüye kısayol ve dosya ilişkilendirmesi eklenir, ev klasörü paylaşılır. Sıfırdan yazılmaz: altyapı olarak bakımı süren hazır parçalar (dockur/windows konteyneri; LinOffice/WinApps incelenir), Linwas yönetici ve Türkçe arayüz olur (donanım denetimi, kurulum, bellek ayarı, gerektiğinde başlat/durdur). **Windows sürümü:** Windows 11 Pro varsayılanı kullanılmaz; varsayılan **Windows 11 IoT Enterprise LTSC 2024** (en az 2 GB bellek, TPM isteğe bağlı, güvenlik desteği 11 Ekim 2034'e kadar, Microsoft 365 destekli); sürüm seçilebilir (perakende lisanslı Windows 11 Pro / 10 Pro). **Lisans:** geliştirme ve denemede lisanssız, Microsoft'un deneme (Evaluation) sürümüyle; lisans kararı en sona bırakıldı. Kurulum ekranında "Kendi Windows lisansınız ve Microsoft 365 aboneliğiniz gerekir; yoksa deneme süresiyle sınırlıdır" yazılır; Linwas etkinleştirmeyi atlatan yöntem önermez. **Donanıma göre öneri:** KVM yoksa ya da bellek 8 GB'tan azsa yalnızca web Office (+ LibreOffice/ONLYOFFICE); 8–16 GB "sınırda" uyarısıyla (sanal makineye 3–4 GB, yalnızca Office açıkken çalışır); 16 GB ve üstü rahat. Bottles küçük programlar için kalır.
  - **Microsoft Office:** Wine/Bottles'ta çalışması garanti değil (Office 2016 gibi kurulum dosyalı sürümler kısmen/tamamen çalışabilir; Microsoft 365 genellikle kurulum/etkinleştirmede sorun çıkarır). Linwas kurmayı **dener**, söz "deneyebilirsin" düzeyindedir; çalışmazsa Office web sürümü ve LibreOffice önerilir.
- **Program kaldırma** (6 Ekim 2026 kararı):
  - **İki yerden:** Program › **Kurulu programlar** sekmesi (Windows'taki "Programlar ve Özellikler" gibi) ve arama sonuçları (kurulu programda "Kur" yerine "Kaldır" butonu).
  - **Kurulu programlar listesi:** yalnızca kullanıcıya yönelik uygulamalar (AppStream); arama ve sıralama. Sütunlar: ad + simge, **kapladığı alan**, **kaynak rozeti** (APT / Flatpak / Snap / üçüncü taraf), **güncelleme var mı** (programa özel "Güncelle" butonu), **kurulma tarihi**.
  - **Ayarlar:** onay penceresinde "Ayarlarımı da sil" kutucuğu, **varsayılan: işaretsiz (ayarlar saklanır)** — program yeniden kurulursa ayarlar geri gelir. Kutucuğun neyi sileceği kaynağa göre sade dille yazılır (Flatpak'te kişisel veriler dahil; APT'de sistem ayar dosyaları — ev klasöründeki kişisel ayarların her zaman güvenilir şekilde bulunamayacağı söylenir).
  - **Gereksiz bağımlılıklar:** aynı işlemde temizlenir; onay penceresinde "bunlar da kaldırılacak" diye ayrı listelenir.
  - **Güvenlik:** kaldırma kuyruk + toplu onay üzerinden. Onaydan önce paket yöneticisinin kaldıracağı **tüm paketler** gösterilir. Bu liste masaüstü ortamını, oturum açma ekranını, ağ yöneticisini, ses sistemini, Linwas'ın kendisini ya da sistemin temel paketlerini içeriyorsa işlem **engellenir** ve nedeni sade dille açıklanır. Sistemle gelen ön kurulu uygulamalar (ör. tarayıcı) kaldırılabilir ama ek uyarı gösterilir.
  - **Geri alma:** kaldırma "hızlı geri alma" kapsamındadır (kaldırılan paket listesi kaydedilir; "Değişiklikleri geri al" yeniden kurar). Ayarlar da silindiyse bunların geri gelmeyeceği onay penceresinde söylenir.
  - Snap uygulamaları da listede gösterilir ve kaldırılabilir.

## Arayüz sayfası
- Desteklenen masaüstleri: Cinnamon, GNOME, XFCE (eklenti yapısında; KDE sonraki sürüme). Desteklenmeyen ortamda yalnızca ortak ayarlar.
- GNOME'da Windows tarzı görev çubuğu için eklenti GUI'den kurulur. (Not: Pardus 25 GNOME'un kendi "Win 11 Style" düzen seçicisi var; Pardus'ta önce onun kullanımı değerlendirilecek.)
- Fontlar: varsayılan Carlito, Caladea, Liberation (tek tık). İsteğe bağlı orijinal Microsoft fontları; lisans onayı Linwas penceresinde, gerekli depo Linwas tarafından açılır.

## Yeni özellikler (hepsi 2.0'da, yerleşik eklenti olarak)
1. **Windows'tan taşıma**
   - Kaynak: aynı bilgisayardaki Windows bölümü (çift açılış) veya Windows kullanıcı klasörünün kopyalandığı harici disk/USB. Hızlı Başlangıç / BitLocker durumları sade dille anlatılır.
   - **Otomatik taşınanlar:** kişisel klasörler; Chrome/Edge yer imleri ve geçmişi; Firefox profilinin tamamı (yer imleri, kayıtlı şifreler, geçmiş, eklentiler — ana parola yoksa); Thunderbird profili; program listesi → Linux karşılık önerisi; sistem tercihleri (klavye düzeni Q/F, dil ve bölge, saat dilimi, açık/koyu tema, sol el fare, ekran ölçeği); kullanıcının kendi kurduğu fontlar (Windows sistem fontları hariç); yazıcı listesi.
   - Yer imleri/profiller otomatik aktarılır. Hedef tarayıcı açıksa uyarı ve "Tarayıcıyı kapat" butonu. Kapatılmazsa aktarım beklemeye alınır.
   - **Sadece rehberle:** Chrome/Edge kayıtlı şifreleri (Windows'ta CSV dışa aktar → Linwas aktarır), Wi-Fi şifreleri, Outlook (.pst) e-postaları.
   - **Taşınmaz:** Windows programlarının kendisi, duvar kağıdı, oyunlar.
   - **Başka Linux'a taşıma (12 Ekim 2026, kullanıcı kararı):** Windows'tan taşıma ile tek sayfada birleşir
     (menü adı "Taşıma"; kaynak: Windows ya da Linux). Linux'ta iki yön: **Dışa aktar** (bu sistemden paket
     oluştur) ve **İçe aktar** (paketi ya da eski bölümü yeni sisteme al); yeni sistemde ilk açılış sihirbazı
     bulduğu paketi önerir.
     - **Yol:** harici disk / USB (paket dosyası); aynı bilgisayardaki diğer bölüm (çift açılış ya da yeniden
       kurulumda eski `/home`); bulut (GNOME Çevrimiçi Hesaplar ile bağlı Google Drive vb.; büyük veride
       yavaşlık uyarısı).
     - **Kapsam:** kişisel dosyalar; program listesi (yeni dağıtımda karşılığı kurulur, adı depoda
       doğrulanır); program ayarları (tarayıcı profilleri, Thunderbird, LibreOffice, `~/.config`);
       masaüstü düzeni (tema, duvar kağıdı, yazı tipleri, kısayollar, görev çubuğu, Linwas klasör/grupları);
       sistem bilgileri (Wi-Fi şifreleri, yazıcılar, SSH/GPG anahtarları).
     - **Hedef:** Linwas'ın desteklediği aileler (Ubuntu, Debian, Pardus, Mint); yeni sistemde de Linwas
       kurulu olmalı.
     - **Masaüstü farklıysa** (ör. GNOME → XFCE): ortak ayarlar karşılığına çevrilir (tema rengi, açık/koyu,
       duvar kağıdı, yazı tipi, klavye düzeni); masaüstüne özel olanlar atlanır ve sonuçta listelenir.
     - **Depo paketi mi Flatpak mı:** ikisi de varsa kullanıcıya sorulur (eski sistemdeki kuruluş biçimi
       önerilen olarak işaretlenir).
     - **Seçim:** hazır işaretli liste, her satırda boyut; hedef diskte yer yetiyor mu gösterilir.
     - **Şifreleme:** isteğe bağlı; paket şifre/anahtar (Wi-Fi, tarayıcı şifreleri, SSH/GPG) içeriyorsa
       zorunlu (parola sorulur; unutulursa açılamayacağı söylenir).
     - **Uygulama (12 Ekim 2026):** `backend/linux_transfer.py`, arayüz `ui/pages/linux_transfer.py`
       (Taşıma sayfasının başlangıç ekranında üç yol: Windows'tan getir / Başka Linux'tan getir / Bu
       bilgisayarı başka Linux'a taşı). Paket klasörü `Linwas-Tasima-<bilgisayar>-<tarih>/`:
       `linwas-transfer.json` + öğe başına `tar.gz` (şifreliyse `.tar.gz.gpg`, GnuPG simetrik AES256,
       parola boruyla verilir, diske yazılmaz) + parola denetimi için `check.gpg`. Önbellek, kilit ve
       soket dosyaları alınmaz. İçe aktarmada kişisel klasörler var olan dosyaların üstüne yazmaz ve
       yeni sistemdeki klasör adına çevrilir (ör. Belgeler → Documents); program/masaüstü ayar
       klasörlerinin var olan hâli silinmez, `<ad>.linwas-onceki-<tarih>` olarak kenara alınır. Aynı
       masaüstünde dconf dalları (GNOME/Cinnamon) ya da xfconf dosyaları (XFCE) birebir; farklı
       masaüstünde tema, simge teması, yazı tipi, açık/koyu, duvar kağıdı çevrilir (kurulu olmayan tema
       atlanır ve listelenir). Wi-Fi: `nmcli -s -g` ile dışa, `nmcli connection add` ile içe (aynı adlı
       ağ atlanır; 802.1X atlanır). Programlar: APT kökenliyse depoda aday + Flathub'da aynı ad;
       Flatpak kökenliyse Flathub + depoda tahmini paket adı; ikisi varsa tabloda seçim (eskisi gibi
       önerilir), kurulum tek görevle (gerekirse önce `flatpak.setup`). Bulut: gvfs bağlantıları
       (`/run/user/<uid>/gvfs`). Diğer bölüm: `/proc/mounts`'taki `/media`, `/run/media`, `/mnt`
       altında ev klasörü aranır; program listesi ve masaüstü/Wi-Fi bu yolla gelmez. Menü adı
       "Windows'tan taşı" → "Taşıma".
2. **Görev Yöneticisi:** "Kapat" doğrudan zorla kapatır; masaüstü ve sistem süreçleri kapatılamaz. CPU/RAM, başlangıç programları.
3. **Disk temizliği:** yalnızca elle; kazanılacak alan önceden gösterilir.
4. **Yazıcı ve tarayıcı:** otomatik bulma; bulunamazsa AI çözüm üretir, görevleri kuyruğa hazır koyar, kullanıcı tek onayla uygular.
5. **Oyun:** Steam + Proton, Lutris / Heroic, GameMode, uyumluluk kontrolü (AI değerlendirmesi + "tahmindir" uyarısı + ProtonDB linki; AI kapalıysa ProtonDB araması tarayıcıda açılır).
6. **Kişisel dosya yedeği:** harici disk / USB.
7. **"Windows'ta nasıl?" rehberi:** ayarlar + programlar + klavye kısayolları + kavramlar (`data/windows_map.json`); sistem ayarı karşılıkları `data/settings_map.json` ile bağlantılı.
8. **Güç ve pil:** enerji modu, pil sağlığı, kapak kapanınca davranışı, pil koruma (%80, destekleyen cihazlarda).
   - **Gelişmiş güç seçenekleri (10 Ekim 2026, kullanıcı kararı):** Windows'taki gibi.
     - **Planlar:** Linwas planları Tasarruf / Dengeli / Performans + kullanıcının özel planları. Her ayarın
       Prizde ve Pilde ayrı değeri var; prize takınca/çıkarınca otomatik uygulanır. Plan sistem genelidir
       (`/etc/linwas/`, yalnızca root helper yazar); ekran/uyku süreleri Linwas'ı açan kullanıcıya uygulanır.
       Planda "Sistem güç profili" (power-profiles-daemon) ayarı da var; GNOME menüsünden değiştirilirse
       Linwas görür ve uyarır.
     - **Bölümler:** Ekran ve uyku (karartma/kapatma, uyku, hazırda bekletme, karma uyku, uyanma
       zamanlayıcıları); Düğmeler ve kapak (güç/uyku düğmesi, kapak: prizde/pilde/harici ekran bağlıyken);
       İşlemci (turbo, EPP, en düşük/en yüksek işlemci durumu, governor); Pil (şarj sınırı, düşük/kritik
       seviye ve eylemi, bildirim); USB/PCIe/disk (USB seçici askıya alma, ASPM, SATA ALPM, disk kapanma);
       Kablosuz (Wi-Fi güç tasarrufu, pilde Bluetooth kapatma); Ekran kartı ve parlaklık (AMD/Intel/NVIDIA
       güç modu, pilde parlaklık, uyarlanabilir parlaklık); Tanılama raporu.
     - **Arayüz:** üstte plan seçimi + sık ayarlar kartlarla; altta "Gelişmiş güç seçenekleri" ağaç listesi,
       her satırda Prizde / Pilde değeri. Desteklenmeyen ayar gizlenmez, nedeniyle birlikte devre dışı gösterilir.
     - **Masaüstü bilgisayar:** sayfa görünür (adı "Güç"), pil/kapak/priz-pil ayrımı gizli.
     - **Uygulayıcı:** ek paket yok; root helper + sysfs/logind/udev ve priz/pil değişiminde uygulayan Linwas
       systemd servisi. TLP / auto-cpufreq gibi araç kuruluysa uyarılır, düşük seviye bölümler (işlemci,
       USB/PCIe/disk, kablosuz) salt okunur olur ve aracı kaldırma önerilir (kuyruğa eklenir).
     - **Hazırda bekletme:** sistem destekliyorsa seçenek olarak sunulur, desteklemiyorsa nedeni yazılır
       (swap/resume yok, Secure Boot kilidi vb.); Linwas kurulum yapmaz (kurulum bekleyen fikir).
     - **Tanılama raporu:** uygulama içi özet (hata/uyarı/öneri, tek tıkla düzelt) + istenirse HTML rapor;
       powertop varsa ayrıntı eklenir, yoksa kurulumu önerilir.
     - **Ekler:** varsayılana sıfırla (plan / tümü), plan içe/dışa aktarma (dosya), zamanlı plan (belirli
       saatlerde başka plan), pil seviyesine göre geçiş (%X altında Tasarruf).
     - Komutlar, sysfs yolları ve gsettings anahtarları kodlarken resmi belgeden doğrulanır; donanımdan
       bağımsız (AMD/Intel/NVIDIA, tüm desteklenen dağıtımlar).
     - **Uygulama (10 Ekim 2026):** `core/powerplan.py` (katalog, model, doğrulama, etkin plan:
       pil tasarrufu > zamanlı plan > seçili plan), `core/power_apply.py` (`linwas-power.service`, root;
       20 sn'de bir priz/pil/saat/ayar değişimini denetler, değişince uygular, düşük seviye ayarları
       10 dk'da bir yeniler; Linwas'ın değiştirdiği değerlerin eskisi `/run/linwas-power/state.json`'da,
       "Sistem varsayılanı" seçilince geri yüklenir; parlaklık ve sistem güç profili yalnızca plan/kaynak
       değişiminde), `core/power_agent.py` (GNOME gsettings; XDG autostart). Plan değiştirme şifresiz:
       polkit eylemi `org.linwas.power.switch` (allow_active=yes) → `/usr/lib/linwas/linwas-power-switch`;
       kaynak koddan çalışırken root helper. Ayarı kaydetmek root helper `power.save_config` (şifre;
       `/etc/linwas/power.json`, logind `90-linwas-power.conf`, `UPower.conf`; yedekli). Düğmeler/kapak ve
       Pil seviyeleri tüm planlar için ortak (logind/UPower genel ayar); kapak ayarı açılışta geçerli.
       Güç düğmesinde "kapat" yok (GNOME bunu sunmuyor). USB askıya almada fare/klavye (HID) ve Bluetooth
       hariç. Tanılama: `backend/power_report.py` + root işlemi `power.powertop_report`
       (`/var/lib/linwas-power/powertop.csv`).
     - **Geri bildirim düzeltmeleri (13 Ekim 2026):** servis durumu `power_apply.service_state()`
       ("missing" kurulu değil / "stopped" / "running"). Çalışmıyorsa sayfanın üstünde neden kartı;
       plan, sık ayarlar, gelişmiş ayarlar ve otomatik geçiş kartları kilitli (uygulanamayan ayar
       değiştirilemez); durmuşsa "Servisi başlat" (`service.enable` + `service.restart`). Pil: yüzde
       çubuğun sağında; altında durum · kalan süre (yalnızca çekirdek enerji/akım verirse,
       `Battery.minutes_left`) ve ayrı satırda sağlık · döngü. Gelişmiş ayarlar varsayılan kapalı
       ("Gelişmiş ayarları göster"); her satırda ad + kısa açıklama, değiştirilmiş satırda "Varsayılan"
       düğmesi (yerleşik planda fabrika değeri, özel planda Sistem varsayılanı).

9. **Görev çubuğu Linwas temasını izler (13 Ekim 2026):** Linwas'ta Açık/Koyu seçiliyse paletin
   `mode` alanıyla görev çubuğu ve menüler de o temada çizilir (uygulama ile panel arasında keskin
   geçiş olmasın); "Sistem" seçiliyse masaüstünün açık/koyu ayarı izlenir.
10. **Görev çubuğu ve masaüstü gruplama (10 Ekim 2026, kullanıcı kararı):** amaç, çok pencereyle
   çalışırken görev çubuğunu sade tutmak. Üç ayrı, isteğe bağlı eklenti; kullanıcı istediğini açar
   (çizimli karşılaştırma: claude.ai artifact "Görev Çubuğu Gruplama Seçenekleri").
   - **Ortak:** aynı programın pencereleri varsayılan olarak tek düğmede toplanır (GNOME: Dash to Panel,
     KDE: Görev Yöneticisi gruplama, XFCE: Pencere Düğmeleri gruplama). Tasarım masaüstü bağımsız; ilk
     teslim GNOME, sonra KDE ve XFCE.
   - **C. Klasörler (ilk):** Android ana ekran klasörü gibi; masaüstüne ve görev çubuğuna sabitlenen klasör
     simgesi, tıklayınca Linwas'ın açılır penceresinde program ızgarası. Düzenleme açılır pencereden ("+" ile
     ekle, çıkar, yeniden adlandır, sırala) ve masaüstünde simgeyi klasörün üstüne sürükle-bırak (DING'in
     bunu ilettiği kodlarken doğrulanacak). Masaüstü simgeleri kapalıysa (Pardus GNOME'da Desktop Icons NG
     kurulu değil) ilk klasörde kurulumu önerilir.
     - **Uygulama (10 Ekim 2026):** `backend/app_folders.py` (kayıt `~/.local/share/linwas/app-folders.json`,
       kısayol `~/.local/share/applications/linwas-folder-<kimlik>.desktop` + masaüstünde güvenilir kopya:
       0755 + `gio set … metadata::trusted true`), `ui/app_folder_popup.py` (`linwas --app-folder <kimlik>
       %U`; ana pencereden bağımsız süreç), sayfa Arayüz › Program klasörleri (`ui/pages/app_folders.py`).
       Sürükle-bırak DING kaynağından doğrulandı (fileItem.js: güvenilir kısayola bırakılan dosyalar
       argüman olarak verilir). Masaüstündeki kısayol klasöre taşınır (`folder-items/<klasör>/`), çıkarılınca
       geri döner. Görev çubuğu: GNOME `favorite-apps` (Dash to Panel de kullanır). Klasör simgesi 2×2
       program simgesinden üretilir, her değişimde yeni adla yazılır (önbellek). Masaüstü simgeleri
       kapalıysa: kurulu ama kapalı → `gnome-extensions enable`; kurulu değil → `package.install`
       (`gnome-shell-extension-desktop-icons-ng`, UUID `ding@rastersoft.com`), sonra `enabled-extensions`'a
       yazılır, oturum yeniden açılınca görünür.
     - **Masaüstünde sağ tık (13 Ekim 2026, kullanıcı):** seçili program simgelerinde "Klasörde grupla
       (Linwas)" (ad sorulur, simgeler klasöre taşınır), "Klasöre ekle (Linwas)" (var olan klasör seçilir),
       klasör simgesinde "Klasörü çöz (Linwas)" (programlar masaüstüne döner). XFCE: Thunar özel eylemleri
       `~/.config/Thunar/uca.xml` (xfdesktop thunar-uca'yı yükler; Linwas eylemleri `unique-id`
       "linwas-folder-…", kullanıcınınkilere dokunulmaz; `%F`). GNOME (DING) ve Nautilus: Betikler alt
       menüsü `~/.local/share/nautilus/scripts` (seçili dosyalar argüman). Komut `linwas --folder-action
       <group|add|ungroup> <dosyalar>` (`backend/folder_menu.py`, `ui/folder_actions.py`); Linwas açılışında
       ve klasör sayfasında geçerli dilde yazılır. XFCE güveni: kısayola `metadata::xfce-exe-checksum` =
       içeriğin SHA-256'sı (libxfce4util), GNOME'un `metadata::trusted`'ı ile birlikte. Görev çubuğuna
       sabitleme XFCE'de henüz yok.
   - **Masaüstü kapsamı (10 Ekim 2026, kullanıcı kararı):** çalışma grupları GNOME, XFCE ve Cinnamon için
     birlikte yazılır (kullanıcı üçünü de kullanıyor); KDE sonraki sürümde. Ortak: X11'de `wmctrl` ile geçiş,
     pencere taşıma ve "program hep kendi grubunda açılsın" ajanı; masaüstüne özel: masaüstü sayısı/adları,
     görev çubuğu yalnızca geçerli masaüstü, grup değiştirici (GNOME: Dash to Panel/Dash to Dock
     `isolate-workspaces`, Workspace Indicator, auto-move-windows; XFCE: xfconf xfwm4 + Pencere Düğmeleri +
     Çalışma Alanı Değiştirici; Cinnamon: org.cinnamon gsettings + pencere listesi + çalışma alanı
     değiştirici). GNOME Wayland'de geçiş/taşıma dışarıdan yapılamaz; GNOME kısayolları gösterilir.
   - **A. Çalışma grupları (ikinci):** kullanıcının grupları ("Proje", "E-posta" …), her grup bir sanal
     masaüstü; görev çubuğu yalnızca o grubun pencerelerini gösterir; grup değiştirici; grup açılınca
     programları birlikte başlatma (grubun klasörüyle). X11'de dışarıdan pencere taşıma; Wayland'de
     masaüstüne özel yol (doğrulanacak).
     - **Uygulama (10 Ekim 2026):** `backend/workgroups.py` (kayıt `~/.local/share/linwas/workgroups.json`,
       gruplar açılmadan önceki masaüstü ayarı `workgroups-before.json`; son grup silinince geri yüklenir),
       sayfa Arayüz › Çalışma grupları (`ui/pages/workgroups.py`). Grup sırası = masaüstü sırası; sıra
       değişince/grup silinince pencereler X11'de yeni sıraya taşınır (silinenin pencereleri ilk gruba).
       Her grup için menü kısayolu `linwas-group-<kimlik>.desktop` (`linwas --open-group`): her masaüstünde
       panele/favorilere sabitlenebilir; gruba geçer, o grupta penceresi olmayan programları başlatır.
       XFCE/Cinnamon kural ajanı `linwas --workgroups-agent` (XDG autostart `linwas-workgroups.desktop`,
       1 sn'de bir `wmctrl -lx`; pencere sınıfı StartupWMClass / masaüstü kimliği / Exec'ten eşleşir).
       Hazırlık satırları: görev çubuğu yalnızca geçerli grup, grup değiştirici (GNOME eksikse
       `gnome-shell-extensions` paketi), X11'de `wmctrl` (yoksa kurulum önerisi).
   - **B. Pencere gruplama eklentisi (üçüncü):** farklı programların pencerelerini kullanıcının seçtiği tek
     düğmede birleştirir, önizlemeli açılır liste. Her masaüstüne ayrı eklenti (GNOME Shell JS, KDE
     Plasmoid QML, XFCE paneli C); önce GNOME. GNOME sürümleri arası bakım gerektirir.
     - **Kararlar (10 Ekim 2026, kullanıcı):** grup düğmesi panelde ayrı düğme (Dash to Panel kendi
       program düğmelerine dışarıdan ekleme yapılmasına izin vermiyor); gruba alınan programlar Dash to
       Panel görev çubuğundan gizlenir; GNOME 42–48 desteklenir.
     - **Uygulama (10 Ekim 2026):** `backend/window_groups.py` (kayıt `~/.local/share/linwas/window-groups.json`,
       eklentinin göstereceği çevrilmiş metinler de bu dosyada), sayfa Arayüz › Pencere grupları
       (`ui/pages/window_groups.py`). Eklenti `linwas-window-groups@linwas`, kullanıcı klasörüne
       (`~/.local/share/gnome-shell/extensions/`) kurulur; kaynağı `resources/gnome-extension/`: ortak
       `core.js` + GNOME 42–44 için eski içe aktarma, 45+ için ES modülü başı/sonu, kurulumda kabuk sürümüne
       göre birleştirilir. Linwas güncellenince sayfa açılışında eklenti dosyaları yenilenir. Eklenti JSON'u
       izler (Gio.FileMonitor); grubun penceresi yoksa düğme gizlenir; düğme simgesi grubun ilk programı,
       yanında pencere sayısı; açılır listede Clutter.Clone önizleme, başlık, kapat düğmesi. Bir program
       yalnızca bir grupta olabilir. Dash to Panel gizleme: `global.dashToPanel.panels[].taskbar`
       prototipinde `getAppInfos` süzülür (eski ve yeni ESM sürümünde resmi kaynaktan doğrulandı);
       sabitlenmiş (favorite-apps) programlar yerinde kalır; hata olursa süzme bırakılır. Ubuntu Dock'ta
       gizleme yok (yalnızca düğme). Durum: `org.gnome.Shell.Extensions.GetExtensionInfo` (`state` 1 =
       çalışıyor; boş = oturum yeniden açılmalı).
   - **D. Görev çubuğu ayarları (12 Ekim 2026, kullanıcı kararı):** Arayüz › Görev çubuğu sayfası; ilk
     teslim GNOME (Dash to Panel), sonra XFCE/Cinnamon. Linux'ta bugün olmayan ya da dağınık olanlar:
     - **Hazır düzen:** "Windows gibi" (altta tek panel: Dash to Panel) / "macOS gibi" (üstte ince çubuk +
       altta ortalanmış dock: Dash to Panel kapatılır, Dash to Dock açılır; Pardus 23 deposunda
       `gnome-shell-extension-dashtodock` 436.84.1 var). Geçişten önce mevcut ayarlar saklanır, "Önceki
       düzene dön" düğmesi.
     - **Sağ tıkta son açılan dosyalar:** program simgesinin menüsünde o programla son açılan dosyalar
       (`~/.local/share/recently-used.xbel`, GTK; `remember-recent-files` kapalıysa bölüm gizlenir ve
       nedeni sayfada yazar). Linwas GNOME eklentisine eklenir; Dash to Panel menüsüne ekleme yolu
       kodlarken resmi kaynaktan doğrulanacak.
     - **Görünüm:** Saydam / Mat / Bulanık (blur) + saydamlık kaydırıcısı. Saydam ve mat Dash to Panel
       ayarlarıyla (`trans-use-custom-opacity`, `trans-panel-opacity`, `trans-use-custom-bg`,
       `trans-bg-color`, `trans-use-dynamic-opacity`). Bulanık: Pardus deposunda Blur my Shell yok; Linwas
       GNOME eklentisi panelin arkasına `Shell.BlurEffect` uygular (GNOME 43'te varlığı kodlarken
       doğrulanacak). Desteklenmeyen masaüstünde seçenek gizlenir.
     - Ayrıca (Linux'ta dağınık, tek sayfada): konum (alt/üst/sol/sağ: `panel-positions`), boyut
       (`panel-sizes`), otomatik gizleme (`intellihide`), pencere önizlemesi (`show-window-previews`).
   - **F. Linwas görev çubuğu eklentisi + medya widget'ı (13 Ekim 2026, kullanıcı kararı):** D maddesi bu
     eklentiye katılır. Görev çubuğunu Dash to Panel çizer; **Linwas'ın GNOME Shell eklentisi** onu
     yönetir ve üstüne ekler (pencere grupları eklentisi gibi Linwas tarafından kurulur, sürümle
     güncellenir; ayrı Linwas eklentisi olarak açılıp kapatılır).
     - **Medya widget'ı** (MPRIS: Spotify, tarayıcıda YouTube Music, son çalan oynatıcı): (1) görev
       çubuğunda küçük kontrol (şarkı adı + oynat/duraklat; tıklayınca büyük kart), (2) bildirim/takvim
       menüsünde GNOME'un medya kartının yerine Linwas'ın modern kartı (kapak resmi, sanatçı, ilerleme,
       önceki/oynat/sonraki, oynatıcı değiştirme). Hızlı ayarlar menüsüne konmaz.
     - **Arka plan:** varsayılan temaya göre (açık/koyu + Linwas vurgu rengi); seçenek "kapak resminin
       rengini al". Görev çubuğu ve widget için ayrı ayrı Saydam / Mat / Bulanık + saydamlık kaydırıcısı.
     - GNOME 42–48 desteklenir (pencere grupları eklentisiyle aynı yapı).
     - **Uygulama (13 Ekim 2026):** eklenti `linwas-taskbar@linwas`, kaynağı
       `linwas/resources/gnome-taskbar/` (ortak `core.js` + eski/ESM başı-sonu), Python
       `backend/taskbar.py`, sayfa Arayüz › Görev çubuğu (`ui/pages/taskbar.py`, yerleşik eklenti
       `linwas.taskbar`). Ayar dosyası `~/.local/share/linwas/taskbar.json` (eklenti izler; Linwas'ın
       açık/koyu renkleri ve vurgu rengi `palette`, çevrilmiş metinler `strings`). GNOME 43 kaynağından
       (libgnome-shell.so gresource) doğrulandı: `Main.panel.statusArea.dateMenu._messageList`
       `._sectionList` ve `._mediaSection` (MessageListSection, görünürlüğü `_sync` ile), MPRIS istemcisi
       GNOME'unkine benzer `Gio.DBusProxy.makeProxyWrapper` ile (satır içi arayüz XML'i; `...Remote`
       çağrıları tüm sürümlerde var), `Shell.BlurEffect` GNOME 43'te `sigma` (46+ `radius`; ikisi de
       denenir). Dash to Panel açıksa arka plan onun `trans-use-custom-bg`, `trans-bg-color`,
       `trans-use-custom-opacity`, `trans-panel-opacity` anahtarlarıyla, bulanıklık
       `global.dashToPanel.panels[].panelBox`'a efekt olarak; kapalıysa `Main.panel` doğrudan boyanır.
       Kapak resmi `~/.cache/linwas/covers/` altına önbelleklenir (http adresleri gvfs ile), ortalama
       rengi GdkPixbuf ile. Oynatıcı seçimi: çalan > en son etkin; kapanan oynatıcı "son çalınan" olarak
       kartta kalır ("%1 aç"). Yerleşim yalnızca Windows düzeninde (Dash to Panel): `panel-position`,
       `panel-size`, `intellihide`, `show-window-previews`. macOS düzeni Dash to Dock'u (kimliği kurulu
       klasörden bulunur, `dash-to-dock@…`) açar; kurulu değilse `package.install` görevi istenir;
       Dash to Dock anahtarları (`dock-position`, `extend-height`, `dock-fixed`) yoksa yok sayılır
       (kurulunca doğrulanacak). Henüz yok: sağ tıkta son dosyalar (D) — sonraki adım.
     - **Düzeltme ve birleştirme (13 Ekim 2026, kullanıcı denemesi):** "Windows görünümü" sayfası
       menüden kalktı, Görev çubuğu sayfasına katıldı (Windows tarzı görev çubuğu = "Windows gibi"
       düzeni; pencere düğmeleri bölümü taşındı; `appearance` bağlantıları `taskbar`'ı açar). Sayfa
       iki kısım: eklentisiz çalışanlar (hazır düzen, pencere düğmeleri, yerleşim) ve Linwas eklentisi
       isteyenler (görünüm, medya). Dash to Panel yalnızca `panel-positions` / `panel-sizes`
       (ekran başına JSON, ör. `{"0":"BOTTOM"}`) değişimini dinliyor (panelManager.js); konum/boyut
       artık bu anahtarlara her ekran için yazılıyor (ekranlar `available-monitors`). Yeni GNOME
       eklentisi kabuk yeniden başlayınca yüklenir: sayfada "oturumu kapatıp açın; X11'de Alt+F2 › r".
       Kart saydamlığı: kart GNOME menüsünün opak zemini üstünde durduğu için fark görünmüyordu;
       görev çubuğundaki medya menüsünde saydam/bulanık seçilince menü zemini kaldırılır (görünen yüzey
       kart). Takvim menüsündeki kart menünün içinde kalır; orada saydamlık yalnızca menü rengine göre.
       **Menüler ve kartlar (13 Ekim 2026, kullanıcı):** Saydam / Mat / Bulanık seçimi görev çubuğundaki
       bütün açılır menülere uygulanır (`Main.panel.statusArea[*].menu.box`: hızlı ayarlar, takvim, ses,
       ağ, diğer eklentilerin simgeleri; başka eklenti açılıp kapanınca yeniden taranır). Renk Linwas'ın
       kart rengi (açık/koyu), saydamlık görev çubuğuyla aynı; mat = opak Linwas rengi. Eklenti
       kapanınca menüler GNOME'un kendi görünümüne döner. Ayar sayfada Görünüm › "Menüler ve kartlar".
   - **G. Tema (vurgu) rengi seçimi (13 Ekim 2026, kullanıcı kararı):** yalnızca **Linwas** penceresi ve
     Linwas eklentileri (görev çubuğu, medya widget'ı) renk alır; masaüstünün sistem rengi değişmez.
     Ayarlar › Görünüm'de hazır renkler + özel renk; seçilen renk açık ve koyu temada okunur kontrastta
     tutulur (gerekirse otomatik koyulaştırılır).
     - **Uygulama (13 Ekim 2026):** ayar `accent_color` (boş = düzenin rengi), `tokens.with_accent` /
       `readable_accent` (yazıyla en az 4.5:1 kontrast), 8 hazır renk (`ACCENT_PRESETS`) + özel renk
       (QColorDialog); seçilen renk görev çubuğu eklentisine `palette` ile gider.
   - **E. Klasör renkleri (12 Ekim 2026, kullanıcı kararı):** Dosyalar'da (Nautilus) klasöre renk verme;
     Windows'ta yok, macOS'ta etiket rengi gibi. `gio set <klasör> metadata::custom-icon-name folder-<renk>`
     (kullanıcı makinesinde çalıştığı doğrulandı; Nautilus 43.2, simge teması breeze: folder-red/blue/
     green/orange/yellow/violet/grey/brown/black/magenta/cyan var). Simge temasında renkli klasör yoksa
     Linwas kendi renkli SVG'lerini `~/.local/share/icons/hicolor` altına kurar. Sağ tık menüsüne "Klasör
     rengi" için `python3-nautilus` (Pardus deposunda 4.0-1+b1) + Linwas Nautilus eklentisi; kurulu değilse
     yalnızca Linwas sayfasından (klasör seç → renk). "Varsayılana dön" metadata'yı siler.

## Office görünümü (17 Ekim 2026, kullanıcı onayı)

- **Amaç:** LibreOffice'i Microsoft Office benzeri yapmak, tek tıkla kurulum ve geri dönüş.
  Tasarım "Writer Sade Arayüz Taslağı" (claude.ai Design tuvali).
- **Paket:** `linwas-office-look` (Architecture: all, Linwas APT deposundan resmi eklenti),
  kaynak `packaging/plugins/office-look/`. LibreOffice'e (writer, calc, impress) bağımlıdır,
  bu yüzden kurulum LibreOffice'i de kurar. Önceki deneme paketi `pardus-ofis-deneyimi`'nin
  yerine geçer (`Conflicts`/`Replaces`/`Provides`). Teknik bulgular: `packaging/plugins/office-look/NOTLAR.md`.
- **İçerik:** LibreOffice eklentisi (Python UNO): pencere içi Dosya menüsü (Kaydet, Farklı
  kaydet biçim kartları, Aç, son dosyalar, şablonlar, Yazdır önizlemesi, parola, ağ/bulut
  konumları), şeridin sol üstünde Dosya düğmesi, Dosya sekmesine tıklayınca menü, kayıt
  durumu rozeti ve otomatik kaydetme; varsayılanlar xcd (OOXML, Carlito, Impress şablon
  penceresi kapalı); sade şerit (Writer: Dosya, Yaz, Ekle, Sayfa, Gözden geçir, Görünüm;
  Calc: Dosya, Tablo, Ekle, Veri, Görünüm).
- **Sade şerit kurulumda üretilir:** postinst, kurulu `notebookbar.ui` dosyasından
  `linwas_simple.ui` ve onu etkinleştiren `linwas-office-look-ribbon.xcd` dosyasını üretir;
  dpkg tetikleyicisi LibreOffice güncellenince yeniden üretir. Üretim başarısız olan uygulama
  tam şeritte kalır (var olmayan .ui'ye işaret eden ayar LibreOffice'i askıda bırakır).
- **Ayarlar kullanıcı başına:** şerit (sade/tam/klasik), Dosya menüsü, otomatik kaydetme,
  kayıt biçimi, yazı tipi; "Yalnız benim için kapat" parola istemez. Hepsi paketteki
  `linwas-office-look` aracında (LibreOffice kapalıyken kullanıcının profilini yazar);
  Linwas `backend/office_look.py` ile bu aracı çağırır. Kurma/kaldırma kuyrukta
  `package.install`/`package.remove`; yeni root işlemi yok.
- **Linwas sayfası:** kenar çubuğunda yeni "Office" grubu › "Office görünümü"
  (`ui/pages/office_look.py`). LibreOffice'teki "Office görünümü ayarları" öğesi
  `linwas --page office_look` ile bu sayfayı açar; Linwas yoksa aracın zenity penceresi açılır.

## Donanım ve yazıcılar yenilemesi (13 Ekim 2026, kullanıcı onayı)
- Taslak: tuval "Linwas macOS Görünümü" › "Donanım ve yazıcılar · Genel bakış" ve "· Yazıcılar"
  (claude.ai artifact AYgNY1TjwxLtui1ERsfg1D).
- Sayfada sekmeler: **Genel bakış / Aygıtlar / Yazıcılar ve tarayıcılar**.
  - Genel bakış: bilgisayar kartı (DMI: üretici, model, aile, anakart, BIOS sürümü/tarihi, kasa türü;
    dağıtım ve masaüstü; "Her şey çalışıyor · N aygıt" özeti), bileşen kartları (işlemci, bellek, ekran
    kartları, depolama, ekran, pil, ağ ve Bluetooth, ses ve kamera) durum rozeti ve "Ayrıntılar" ile;
    üstte "Sistem raporu" (HTML) ve "Bilgileri kopyala".
  - Aygıtlar: Aygıt Yöneticisi; arama, "Tümü / Sorunlu / Sürücüsüz" süzgeci, açılır kategoriler.
  - Yazıcılar: yazıcı kartı (durum, varsayılan, mürekkep/toner düzeyi varsa, Test sayfası / Kuyruk /
    Seçenekler / Kaldır), bulunan ama kurulmamış yazıcı için tek "Kur", boş durum, tarayıcılar, sorun
    giderme.
- **Ayrıntılar ayrı pencerede** açılır.
- **İşlemci yükü ve sıcaklık sayfa açıkken 2 saniyede bir** güncellenir.
- **Bellek ayrıntısı** (tür, hız, yuva) görünür; "Göster" denince yönetici parolası sorulur (root helper
  işlemi, `dmidecode -t memory`; seri numaraları yazılmaz).
- **Donanım bilgisi ayrı bir eklenti olarak yazılır** (kullanıcı kararı): okuma işlevleri ve bileşen
  kartları/ayrıntı pencereleri Donanım eklentisinin parçası; sayfa ve başka eklentiler (Genel bakış'ın
  sistem sağlığı, AI bağlamı, sistem raporu) bu eklentinin sağladığı arayüzden okur.
- **Uygulama (13 Ekim 2026):** yerleşik eklenti `linwas.hardware_info` (`linwas/plugins/hardware_info/`):
  `probe.py` (Qt'siz okuma: DMI, lscpu, /proc/stat yükü, hwmon sıcaklığı, /proc/meminfo, lsblk +
  NVMe sıcaklığı, xrandr, pil), `widgets.py` (bilgisayar kartı, bileşen kartları, 2 sn zamanlayıcı —
  yalnızca sekme görünürken, ayrıntı penceresi, HTML sistem raporu `~/.cache/linwas/system-report.html`,
  panoya özet), `ai_context()` donanım özeti. Sayfasız eklentiler `BUILTIN_PLUGINS`'te sayfa denetimine
  takılmaz. Root işlemi `hardware.memory_report`: `dmidecode -t memory` çıktısı ilerleme olarak
  gönderilmez; seri numarasız özet `/var/lib/linwas/memory-modules.json` (0644). Yazıcılar: `lpstat -v`
  (bağlantı türü), `lpoptions -p` (model, konum, `marker-*` düzeyleri), `lpstat -o` (kuyruk), test sayfası
  `lp`, varsayılan `lpoptions -d` (kullanıcı düzeyi), kendi işlerini iptal `cancel -a`; kaldırma ve
  seçenekler sistem yazıcı ayarlarında (root gerektirir). Taslaktaki ayrı "Seçenekler" ve "Kaldır"
  düğmeleri tek "Seçenekler ve kaldırma…" düğmesinde birleşti.

## Wi-Fi ve Bluetooth geliştirmeleri (23 Ekim 2026, kullanıcı onayı)
Kapsam (kullanıcı seçti): Wi-Fi — bağlantı ayrıntıları, ağ ayarları, şifre göster + QR, bağlantı testi +
hotspot; Bluetooth — yeniden adlandır + otomatik bağlan, bilgisayarın görünürlüğü, ses çıkışı + dosya
gönderme (tür simgesi ve pil yüzdesi sayfada zaten vardı). Fikir: durum fotoğrafı yerine **ölçülmüş
deneyim** (son günlerde nasıldı, neden koptu). Her aşama ayrı commit; ayrıntı ve kalanlar `yapilacaklar.md`.
- **Bağlantı ayrıntıları (aşama 1):** varsayılan görünen (süzülmüş): hız + bant, IP adresi, güvenlik (sade dille).
  "Gelişmiş ayrıntılar" arkasında: ağ geçidi, DNS, kanal, MAC, BSSID. "IP adresini kopyala" / "Tümünü kopyala"
  (hepsini kopyalar). Bant `FREQ`'ten türetilir (nmcli'nin `BAND` alanı eski sürümlerde yok). Alan adları
  NetworkManager kaynağından doğrulandı.
- **Ağ listesi:** çok zayıf (< %30) ve ne bağlı ne kayıtlı ağlar gizli, "N zayıf ağı göster" ile açılır.
  Bluetooth'ta adsız (adı yalnızca adresinden ibaret) yeni cihazlar gizli, "N adsız cihazı göster" ile açılır.
- **Ölçüm ve kalite çizelgesi (aşama 2):**
  - **Açık rıza, varsayılan kapalı:** Wi-Fi sekmesindeki "Bağlantı kalitemi ölç" kutusu (`net_measure`).
  - **Ne ölçülür:** Linwas çalışırken (arka plan kipi dahil) dakikada bir: bağlı mı, sinyal, bant ve **yalnızca
    yerel ağ geçidine** 3 ping (gecikme, kayıp). Dışarıya hiçbir şey gönderilmez. Wi-Fi kapalı/kart yoksa örnek
    yazılmaz (çizelgede "veri yok"). Linwas kapalıyken de ölçülmez.
  - **Saklama:** `~/.local/share/linwas/net_quality.jsonl`, 7 gün; ağ adı + sayılar (site/trafik yok).
    Ayarlar › Kullanıcı verileri'nde görünür ve silinir.
  - **Kopma sayımı:** bağlıyken bağlantı kopması; kullanıcının Linwas'tan yaptığı "Bağlantıyı kes / Kapat /
    Unut" `user` işaretiyle yazılır, sayılmaz. Büyük zaman boşlukları (uyku, Linwas kapalı) sayılmaz.
  - **Çizelge ve hüküm:** üstte tek cümlelik hüküm (kararlıydı / genel olarak kararlıydı / kararsızdı; kopmalar
    ve kötü dilimlerin payından), altında yalnızca işe yarayan not (kopma sayısı, en yavaş saat); sayılar
    (ölçüm sayısı, ortalama gecikme) hükmün üzerine gelince ipucunda. Çizelge: son 24 saat, 15 dakikalık
    dilimler; dilimin durumu en kötü örneğe göre (iyi / yavaş / kötü / bağlantı yok [içi boş çubuk] /
    gecikme verisi yok / veri yok). Eşikler sezgiseldir: geçide gecikme ≤ 30 ms iyi, ≤ 100 ms yavaş, üstü
    kötü; kayıp ≤ %2 iyi, ≤ %10 yavaş.
  - **Bağlantı testi** (yalnız düğmeyle): ağ geçidine ping → `nmcli networking connectivity check` → ad
    çözümleme ve TCP 443 (`example.com`, IANA belge alan adı) → tanı kodu (ok, no_address, gateway_down,
    gateway_lossy, portal, dns_failed, internet_down, slow). Sonuç sade dille üç satır (router, adlar,
    internet) + hüküm; adresler ve süreler "Ayrıntılar" arkasında; sorun varsa "Asistana sor".
  - **Doğrulanan komutlar:** `ping -n -c N -i 0.4 -W 1.0 <IP>` (iputils belgesi; çıktı biçimine değil cevap
    satırlarındaki `time=` değerine bakılır), `nmcli networking connectivity [check]` (full / limited / portal /
    none / unknown). Yalnızca IP adresi ping'lenir (seçenek enjeksiyonuna karşı).

## AI
- Sağlayıcılar: Gemini, ChatGPT, DeepSeek. AI isteğe bağlı; anahtar yoksa gizlenir.
- AI yalnızca görev önerir (tanımlı işlem adı + parametre); "Kuyruğa ekle"ye kullanıcı basar.
- AI cevaplarında Linwas sayfa kısayolu yok; ancak sistem ayarlarını açan butonlar önerebilir.
- Anahtar: adım adım rehber + anahtar testi (model listesi çekilerek, token harcamadan).
- **Anahtar saklama:** sistem anahtar kasası (keyring). Kasa yoksa Linwas bunu sade dille söyler ve kurulumunu kuyruğa önerir; kurulmazsa anahtar yalnızca o oturum için hatırlanır. Anahtarlar asla düz metin olarak kaydedilmez; loglarda ve hata raporlarında maskelenir.
- Model seçimi: tam liste, sağlayıcının model listeleme servisinden canlı çekilir; model adları koda sabit yazılmaz.
  - **Değişiklik (6 Ekim 2026):** Gemini'de yalnızca seçilmiş modeller gösterilir (`data/ai_models.json`):
    3.8 Flash (ana), 3.7 Flash (hızlı/ucuz), 3.1 Pro (zor problemler, ücretli) + ücretsiz katmandaki
    1M bağlamlı modeller. Her açılışta canlı listeyle karşılaştırılır; canlı listede olmayan gösterilmez,
    hiçbiri yoksa tam liste gösterilir. Diğer sağlayıcılarda tam liste.
  - Sohbet sırasında sağlayıcı/model değiştirilebilir; geçmiş korunur. AI sayfasında sohbet geçmişi
    ve AI ayarları (anahtar, test, aylık sınır). Yan panel sürüklenerek genişletilir, şeride daraltılır.
- Doğrulanan uç noktalar (bkz. `dogrulama-raporu.md`):
  - ChatGPT: `GET https://api.openai.com/v1/models`, `Authorization: Bearer`
  - Gemini: `GET https://generativelanguage.googleapis.com/v1beta/models`, anahtar `?key=` parametresi (URL'ler loglanırken anahtar maskelenmeli)
  - DeepSeek: `GET https://api.deepseek.com/models`; OpenAI uyumlu → ChatGPT ile ortak istemci
- Görsel desteği: DeepSeek'te `input_modalities` alanından; ChatGPT ve Gemini'de gönderilir, reddedilirse sade uyarı.
- Sistem bilgisi: her seferinde "Sistem bilgimi ekle" onayı; maskelenir.
- Sohbet geçmişi: yerel SQLite; "Tüm geçmişi sil".
- Sağlayıcı hata/limit: uyarı, kullanıcı başka sağlayıcı seçer.
- Token limiti: sağlayıcı başına aylık, kullanıcı belirler; kullanım gösterilir.
- Üslup: detaylı ve öğretici; cevap dili uygulama diliyle aynı.
- Ekler: ekran görüntüsü (önizleme + "kişisel bilgi içerebilir" uyarısı) ve maskeli log dosyası.
- Proaktif: yalnızca sistem taramasını yorumlar.

## Dağıtımlar ve paketleme
- **Desteklenen: Ubuntu 22.04+, Debian 12+, Linux Mint 21+, Pardus 23 ve Pardus 25.**
- **Desteklenmeyen: Ubuntu 20.04, Debian 11, Linux Mint 20** (karar: seçenek A). Gerekçe: gömülü PySide6 6.11 (manylinux_2_34) glibc ≥ 2.34 ve libstdc++ ≥ 11 istiyor; bu sistemlerde glibc 2.31 var ve güvenlik destekleri bitmiş. Eski Qt gömmek güvenlik ve bakım açısından kabul edilmedi.
  - .deb bu sistemlerde kurulumda açık bir bağımlılık hatası verir (`libc6 (>= 2.34)`, `libstdc++6 (>= 11)`).
  - Yükseltme notu uygulama içinde değil, README'de ve ileride yayın sayfasında.
- Linwas içindeki "güvenlik desteği bitti" uyarı mekanizması korunur (ör. Ubuntu 22.04'ün desteği bittiğinde kullanılmak üzere).
- **Çalışma ortamı: gömülü.** .deb paketi kendi Python 3.12'sini (python-build-standalone, sürüm ve SHA256 sabitlenmiş) ve PySide6-Essentials 6.x'i içerir (paket ~77 MB). Gömülü bileşenlerin güvenlik güncellemeleri Linwas güncellemesiyle gelir.
- Paket xz ile sıkıştırılır (eski dpkg'ler zstd açamıyor).
- Derleme GitHub Actions'ta (bkz. Geliştirme).
- Dağıtım: .deb paketi; çift tıkla kurulum, postinst kendi APT deposunu ve imza anahtarını ekler. Güncellemeler sistem güncellemesiyle gelir. Resmi eklentiler aynı depodan ayrı .deb paketleri olarak.
- Çift tıklama davranışı her dağıtımda test edilecek.
- **APT deposu (aşama 5):** `stable` dağıtımı, `main` bileşeni, amd64; `packaging/build-apt-repo.sh` (apt-ftparchive + gpg) `pool/` ve `dists/stable/` üretir, `InRelease` ve `Release.gpg` ile imzalar. postinst kaynağı deb822 biçiminde `/etc/apt/sources.list.d/linwas.sources` olarak ekler (`Signed-By: /usr/share/keyrings/linwas-archive-keyring.gpg`); kullanıcı dosyayı `.disabled` yaptıysa yeniden eklemez; purge ikisini de siler.
- **İmza anahtarı:** ed25519, 5 yıl geçerli, parolasız (CI imzalar); `packaging/create-signing-key.sh` ile ayrı bir klasörde (`~/.linwas-signing`) bir kez üretilir. Gizli anahtar GitHub gizli değeri `LINWAS_SIGNING_KEY`, depo adresi değişken `LINWAS_APT_URL`. Süre dolmadan uzatılıp açık anahtar bir Linwas güncellemesiyle dağıtılır.
- **Yayın iş akışı:** `.github/workflows/release.yml` (`v*` etiketi veya elle): imzalı .deb + APT deposu → artifact. Yükleme adımı yayın yeri kararından sonra.
- **CI APT testi:** Ubuntu 22.04 ve Debian 12 kapsayıcılarında geçici anahtarla imzalı yerel depo → postinst kaynağı → `apt-get update` imza kabulü → depodan güncelleme → purge.

## Test
- Birim testleri: dağıtım/masaüstü algılama, çeviri eksiksizliği, whitelist ve parametre doğrulama, maskeleme, kuyruk, yedek/geri alma kaydı, ayar eşleşmeleri, eklenti yükleyici ve sürüm uyumu, .deb risk analizi.
- CI kurulum testi: desteklenen dağıtım kapsayıcılarında `linwas --self-check` (Türkçe ve İngilizce).

## Açık konular
- Lisans (GPL-3.0 önerildi; yayından önce karar).
- Herkese açık yayın yeri (depoyu açmak mı, ayrı "linwas-releases" mı; yayından önce karar).
- Üçüncü taraf eklentiler (şimdilik yok).

## Dosya şeması
```
linwas2/
├── pyproject.toml, README.md, CLAUDE.md
├── docs/                      # kararlar, yapılacaklar, doğrulama raporu (tek doğru kaynak)
├── .github/workflows/ci.yml   # lint+test → .deb → kapsayıcılarda kurulum testi
├── scripts/                   # dev-setup.sh, run-dev.sh, compile-translations.sh
├── packaging/                 # build-deb.sh, ci-install-test.sh, linwas-launcher.sh, linwas.desktop,
│   └── debian/control.in      # (ileride: postinst, polkit policy, APT deposu)
├── tests/
└── linwas/                    # Python paketi
    ├── __main__.py, app.py, translations.py
    ├── i18n/                  # linwas_tr.ts (.qm derlenir)
    ├── resources/             # linwas.svg
    ├── backend/               # distro, desktop (+ ileride packages, deb_inspect, third_party_repos,
    │                          #   drivers, network, snapshot, settings_launcher)
    ├── core/                  # (aşama 1) tasks, privilege, helper, whitelist, error_router,
    │                          #   sanitizer, history, rollback, plugins/
    ├── ai/                    # (aşama 3) base, gemini, openai_compat, keystore, usage, chat_history, context
    ├── plugins/               # (aşama 4) migrate, taskmgr, cleanup, printers, gaming, backup, power, wine
    ├── data/                  # (ileride) windows_map.json, settings_map.json, third_party_apps.json
    └── ui/                    # main_window (+ ileride pages, widgets, onboarding, theme, icons, tray)
```

## Kodlama sırası
0. ✅ İskelet: klasör yapısı, pyproject.toml, README, karşılama penceresi, Türkçe çeviri altyapısı, geliştirici betikleri, GitHub Actions ile geliştirme .deb'i ve kurulum testi.
1. Altyapı: kuyruk, izin listesi ve parametre doğrulama, root helper, pkexec/polkit, yedek/geri alma kaydı, maskeleme, işlem geçmişi, eklenti yükleyici ve kapılar.
2. Arayüz temeli: tema değerleri, ortak bileşenler, ana pencere, menü, durum çubuğu, kuyruk/onay/çalışıyor/sonuç pencereleri.
3. AI: üç sağlayıcı, anahtar kasası, kullanım sayacı, yardımcı paneli.
4. Sayfalar ve yerleşik eklentiler, sırayla.
5. ✅ Son paketleme: APT deposu, imza anahtarı, postinst, Linwas'a özel polkit kuralı.
