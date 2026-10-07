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
- **Şimdilik yalnızca resmi eklentiler.** Resmi eklentiler imzalı APT deposundan .deb olarak gelir; ayrı bir eklenti imza sistemi şimdilik yazılmaz (APT imzası yeterli). Üçüncü taraf eklentiler gündeme gelirse kendi imza sistemi ve izin ekranı eklenir.
- Gelecekte olası eklentiler: bkz. `yapilacaklar.md`.

## Hedef kullanıcı ve genel UX
- Tamamen yeni Linux kullanıcısı. Sade dil, teknik terim olursa yanında açıklama.
- Terminal hiç kullanılmaz; kurulum dahil her şey GUI.
- Komutlar varsayılan gizli, "Detay" ile görülür.
- İlk açılış: kısa tanıtım turu → kurulum sihirbazı (sistem taraması, Windows'tan taşıma, Timeshift önerisi ve ilk tam yedek, isteğe bağlı AI anahtarı).
- Tema: Windows benzeri tasarım; Açık / Koyu / Sistem (Ayarlar'dan).
- Dil: Türkçe + İngilizce (Qt Linguist altyapısı).
- Pencere kapatma: Ayarlar'dan seçilir. Varsayılan: sistem tepsisi destekleniyorsa tepsiye küçülür; desteklenmiyorsa (ör. Debian/Pardus GNOME) uygulama kapanır, arka planda iş varsa bildirimle devam eder.
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
  - Kenar çubuğu: üstte logo + ad, her öğede simge, gruplar (Sistem, Arayüz) küçük ikincil renkli başlık + aç/kapa oku. Genel bakış kartlarında vurgu renkli simge kutusu, tıklanabilir kartlarda üzerine gelince vurgu kenarlık; durum kartları ilgili sayfayı açar.

## Menü yapısı
- **AI Soru** (geniş sohbet ekranı; ayrıca her sayfada yardımcı panel)
- **Sistem:** Genel bakış, Güncellemeler, Sürücüler, Wi-Fi ve Bluetooth, **Yedekler ve geri alma**, Donanım ve yazıcı, Görev Yöneticisi, Disk temizliği, Yedekleme (kişisel dosyalar), Güç ve pil (yalnızca dizüstü), Windows'tan taşıma, Tüm ayarlar (Denetim Masası)
- **Arayüz:** Windows görünümü, tema/duvar kağıdı, yazı tipleri, ekran/ölçekleme
- **Program:** Üstte arama, altta "Windows'ta ne kullanıyordun?" bölümü; **Kurulu programlar** sekmesi; Oyun sekmesi
- **Sorun Giderme:** Üstte tek tıkla tam tarama, altta belirti kartları
- **Ayarlar:** Linwas'ın kendi ayarları (işlem geçmişi ve eklenti listesi burada)
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
- "Tüm ayarlar (Denetim Masası)": Windows'taki gibi kategoriler.
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
  - **Aygıt Yöneticisi:** Donanım ve yazıcı altında ayrı görünüm; bütün PCI/USB aygıtları, kullandığı sürücü, durumu; sürücüsüz/sorunlu aygıtlar en üstte uyarıyla. Güncelleme merkezi ile karşılıklı bağlantı.
- EXE: risk analizi; Linux alternatifi varsa önerilir, yoksa Wine ile açılır. (6 Ekim 2026 ayrıntıları:)
  - **Açma:** Programlar › "Windows programı aç (.exe)…" ve "Windows programları" sekmesi; .exe/.msi çift tıklanınca Linwas açılır (kurulu pakette ilk açılışta `xdg-mime default`, kullanıcı düzeyinde).
  - **Analiz** (`backend/exe_inspect.py`, salt okunur): PE başlığı (mimari, konsol/pencere, imza tablosu var mı — Linux'ta doğrulanamaz, .NET), sürüm bilgisi (şirket/ürün), kurulum türü (Inno/NSIS/MSI/InstallShield/WiX), çift uzantı hilesi, tarayıcının yazdığı indirme adresi (xattr), SHA256. Risk: yüksek = geçersiz PE / çift uzantı / ARM; orta = imzasız veya yapımcı yok.
  - **Virüs taraması:** yalnızca "VirusTotal'da denetle" düğmesi (tarayıcıda, yalnızca SHA256 ile; dosya gönderilmez). ClamAV yok.
  - **Wine:** dağıtım deposundan; yeni root işlemi `wine.setup` (i386 mimarisi + `wine wine64 wine32:i386`).
  - **Ortam (WINEPREFIX) — karma:** varsayılan tek ortak ortam (`~/.local/share/linwas/wine/shared`); yüksek riskli dosya her zaman ayrı ortamda; kullanıcı "Ayrı ortamda aç" seçebilir; ortak ortamda 60 sn içinde hata koduyla kapanan program için "ayrı ortamda yeniden dene" önerilir. Ayrı ortam silinince kısayolları da silinir; ortak ortamdaki program Wine'ın "Program Ekle/Kaldır" penceresiyle kaldırılır.
  - **Bottles'a geçiş (7 Ekim 2026 kararı, kodlandı):** Windows programları Bottles üzerinden çalıştırılacak; Linwas Bottles'ı arka planda resmi komut satırı aracıyla (`bottles-cli`, Flatpak'ta `flatpak run --command=bottles-cli com.usebottles.bottles …`) yönetir, kullanıcı Bottles penceresini görmez. Akış: Bottles yoksa Flatpak olarak kurulur (kuyrukta adım) → programa özel şişe (uygulama/oyun profili, 64 bit + 32 bit desteği) → kurulum dosyası şişede çalışır → program şişeye kaydedilir, menüye kısayol eklenir → çıktı JSON olarak okunur, hata AI'a iletilip sade dille gösterilir. Kabuk yok, sabit komutlar, kullanıcı yetkisiyle (şifre yok); Bottles kendi Wine sürümünü getirir. Bottles beğenilmezse yukarıdaki dağıtım Wine'ı yoluna geri dönülür (mevcut kod şimdilik korunur).
    - **Uygulama ayrıntıları:** `backend/bottles.py` (`ENABLED = False` → Wine yoluna dönüş). Her programa ayrı şişe (ad: programın sadeleştirilmiş adı); Linwas'ın şişeleri `~/.local/share/linwas/bottles.json` kaydında. Flatpak Bottles ev klasörünü göremediği için kurulum dosyasının klasörü yalnızca o çalıştırmada salt okunur açılır (`flatpak run --filesystem=<klasör>:ro`). Kurulumdan sonra `--json programs` okunur, her programa `~/.local/share/applications/linwas-bottle-<şişe>--<program>.desktop` kısayolu yazılır (`bottles-cli run -b … -p …`). Kurulum dosyası olmayan EXE `bottles-cli add` ile eklenir, kendi klasöründen açılır. Şişe silme CLI'da yok: Linwas kaydındaki şişenin klasörü (`~/.var/app/com.usebottles.bottles/data/bottles/bottles/<ad>`) ve kısayolları silinir. Bottles yoksa görev: (Flatpak yoksa yeni root işlemi `flatpak.setup`: `flatpak` paketi + Flathub deposu) → `flatpak.install com.usebottles.bottles`. "Bu bir oyun" seçilirse `gaming` profili. Hata penceresinde "Asistana sor".
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
2. **Görev Yöneticisi:** "Kapat" doğrudan zorla kapatır; masaüstü ve sistem süreçleri kapatılamaz. CPU/RAM, başlangıç programları.
3. **Disk temizliği:** yalnızca elle; kazanılacak alan önceden gösterilir.
4. **Yazıcı ve tarayıcı:** otomatik bulma; bulunamazsa AI çözüm üretir, görevleri kuyruğa hazır koyar, kullanıcı tek onayla uygular.
5. **Oyun:** Steam + Proton, Lutris / Heroic, GameMode, uyumluluk kontrolü (AI değerlendirmesi + "tahmindir" uyarısı + ProtonDB linki; AI kapalıysa ProtonDB araması tarayıcıda açılır).
6. **Kişisel dosya yedeği:** harici disk / USB.
7. **"Windows'ta nasıl?" rehberi:** ayarlar + programlar + klavye kısayolları + kavramlar (`data/windows_map.json`); sistem ayarı karşılıkları `data/settings_map.json` ile bağlantılı.
8. **Güç ve pil:** enerji modu, pil sağlığı, kapak kapanınca davranışı, pil koruma (%80, destekleyen cihazlarda).

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
