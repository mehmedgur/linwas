# Linwas — Yapılacaklar ve Bekleyen Fikirler

> **Kural:** Her kodlama aşamasına geçmeden önce Claude bu listeyi okur ve bekleyen fikirleri
> kullanıcıya hatırlatır.

Son güncelleme: 17 Ekim 2026

## Notlar
- Kullanıcının Pardus 23 bilgisayarında hem **GNOME** hem **KDE Plasma** oturumu var. Testler
  **GNOME oturumunda** yapılıyor; KDE desteği planlandığı gibi sonraki sürümde.
- Geliştirme .deb'i Pardus 23'te (GNOME ve KDE oturumlarında) kuruldu ve açıldı: Python 3.12.15,
  Qt 6.11.2, Türkçe arayüz, dağıtım/masaüstü/oturum algılama doğru.
- Kodlama 5 Ekim 2026'dan itibaren kullanıcının Pardus 23 bilgisayarında **Claude Code** ile
  sürüyor; kararlar ve tasarım için claude.ai sohbeti de kullanılabilir. Belgelerin tek doğru
  kaynağı bu `docs/` klasörü.

## Karar bekleyenler
- (yok)

## İnceleme bekleyenler
- [ ] **PR #1 — Eski sistem desteğinin kaldırılması:** CI yeşil, Pardus 23'te "Destekleniyor"
  doğrulandı. Birleştirilmesi bekleniyor.
- [ ] **PR #2 — Proje belgelerinin depoya taşınması** (bu klasör) + program kaldırma kararı.

## Sıradaki aşama
- **Kullanıcı "kodlamaya hazırız" deyince başlanacak (8 Ekim 2026, ayrıntı kararlar.md):**
  1. [x] **Ayarlar › Hakkında › Geliştirici kartı** (kodlandı 10 Ekim 2026, kullanıcının denemesi bekleniyor; kararlar.md › Ayarlar › Uygulama aşama 4–5).
  2. [x] **Tüm Ayarlar sayfası yeniden tasarım** (kodlandı 8 Ekim 2026, kullanıcının denemesi bekleniyor): klasik Denetim Masası kategori görünümü
     (kararlar.md › Sistem ayarlarına yönlendirme). Yeni metinlerin Türkçeleri `linwas_tr.ts`'e.
  1. [ ] Donanım denetimi ve öneri ekranı (KVM, bellek, disk) + web Office'i uygulama olarak ekleme.
  2. [ ] Kurulum (root işlemleri: Podman/Docker, FreeRDP; Windows'un gözetimsiz kurulumu, ilerleme).
  3. [ ] Office kurulumu, RemoteApp kısayolları, dosya ilişkilendirmesi, paylaşılan klasör.
  4. [ ] Yaşam döngüsü: gerektiğinde başlat, boştayken durdur; bellek ayarı; kaldırma.
- **Gelişmiş güç seçenekleri** (kararlar.md › Yeni özellikler › Güç ve pil, 10 Ekim 2026), aşamalar —
  her biri ayrı commit, kullanıcının denemesi bekleniyor:
  1. [x] Plan modeli, sistem servisi (`linwas-power.service`), GNOME ajanı, `power.save_config`.
  2. [x] Sayfa: plan seçimi, sık ayarlar, ağaç liste, otomatik geçiş, çakışma/güç modu/hazırda bekletme.
  3. [x] Tanılama raporu (uygulama içi + HTML, powertop).
- **Görev çubuğu ve masaüstü gruplama** (kararlar.md › Yeni özellikler › 9, 10 Ekim 2026), kullanıcı
  "kodlamaya geçelim" deyince; sıra:
  1. [x] C. Klasörler (masaüstü + görev çubuğu, açılır pencere, DING kurulum önerisi). 10 Ekim 2026, deneme bekliyor.
  2. [x] A. Çalışma grupları (GNOME, XFCE, Cinnamon). 10 Ekim 2026, deneme bekliyor.
  3. [x] B. Pencere gruplama eklentisi — GNOME 42–48 kodlandı (10 Ekim 2026), deneme bekliyor; KDE, XFCE sonra.
  4. [ ] D. Görev çubuğu ayarları: hazır düzen, saydam/mat/bulanık, konum/boyut/gizleme/önizleme, Windows 10/11
     hizalama, birleştirme, öğeler, saat/tarih, sabitlenmiş programlar, macOS dock'u — kodlandı (18 Ekim 2026),
     deneme bekliyor. **Kalan: sağ tıkta son açılan dosyalar.**
  5. [ ] E. Klasör renkleri (12 Ekim 2026; tanım 18 Ekim 2026):
     - **Ne:** Dosyalar'da bir klasöre sağ tıklayınca "Klasör rengi" alt menüsü: 8–10 renk + "Varsayılan".
       Seçilen klasörün simgesi o renkte görünür (macOS etiketleri / Windows'taki renkli klasör
       uygulamaları gibi). Birden çok klasör seçilince hepsine uygulanır.
     - **Nasıl:** renk dosya sisteminde değil, klasörün GIO özniteliğinde saklanır:
       `gio set <klasör> metadata::custom-icon file:///…/folder-<renk>.svg` (kaldırma: `-t unset`).
       Nautilus 43 ve Nemo bu özniteliği gösterir. Simgeler Linwas'la gelir (`resources/folder-colors/`,
       tema renklerine yakın, açık/koyu temada okunur SVG; kendimiz çizeriz, lisans sorunu yok).
       Kullanıcı yetkisi yeter, root yok; klasör taşınırsa öznitelik GIO ile birlikte gider.
     - **Sağ tık menüsü:** Nautilus için `python3-nautilus` (Pardus 23/Debian 12'de 4.0, depoda
       doğrulandı) eklentisi `~/.local/share/nautilus-python/extensions/linwas_folder_color.py`;
       Nemo için `nemo-python` (5.6, depoda var) ile aynı eklenti; XFCE Thunar için `thunarx-python`
       (0.5.2, depoda var) — Thunar'ın `metadata::custom-icon`'u gösterip göstermediği kodlarken
       doğrulanacak (göstermiyorsa XFCE'de yalnız Linwas sayfasından ve Thunar'ın kendi "simge" eki).
       Paket yoksa Linwas kurmayı önerir (kuyruk + `package.install`); eklenti dosyasını kendisi yazar,
       Dosyalar yeniden başlatılınca (`nautilus -q`) menü gelir.
     - **Linwas sayfası:** Düzenle › Program klasörleri'nin yanında ya da Kişiselleştirme altında "Klasör
       renkleri": eklentiyi kur/kaldır, son renklendirilen klasörler listesi, "Bütün renkleri temizle".
     - **Kararlar (kullanıcı, 18 Ekim 2026):** macOS etiketleri gibi 7 renk — kırmızı, turuncu, sarı,
       yeşil, mavi, mor, gri (+ Varsayılan); sayfa Kişiselleştirme altında ("Klasör renkleri").
  6. [x] F. Linwas görev çubuğu eklentisi (Dash to Panel üstüne; D buraya katılır) + medya widget'ı
     (görev çubuğu küçük kontrol + takvim menüsü kartı; tema/kapak rengi; saydam/mat/bulanık) —
     kodlandı 13 Ekim 2026, deneme bekliyor. Kalan: sağ tıkta son açılan dosyalar.
  7. [x] G. Tema (vurgu) rengi seçimi — yalnızca Linwas ve eklentileri; kodlandı 13 Ekim 2026, deneme bekliyor.
- [x] **Başka Linux'a taşıma** (kararlar.md › Yeni özellikler › 1, 12 Ekim 2026): Windows'tan taşıma ile
  tek "Taşıma" sayfası; dışa/içe aktarma, USB / diğer bölüm / bulut, şifreli paket. Kodlandı 12 Ekim
  2026, deneme bekliyor (Pardus → Ubuntu sanal makinesi: USB ile paket; şifreli/şifresiz).
- [x] **Donanım ve yazıcılar yenilemesi** (kararlar.md › Donanım ve yazıcılar yenilemesi, 13 Ekim 2026):
  kodlandı 13 Ekim 2026 (donanım bilgisi eklentisi + sayfa), deneme bekliyor. Kodlamada doğrulananlar: DMI `/sys/class/dmi/id` (product_family "103C_5335M7 HP
  Victus" → baştaki kod atılır), sıcaklık hwmon `coretemp` temp1 = "Package id 0" (AMD: `k10temp`),
  NVMe sıcaklığı hwmon `nvme` (device → .../nvme/nvme0), `/usr/sbin/dmidecode` kurulu (3.4), CUPS
  test sayfası `/usr/share/cups/data/default-testpage.pdf`, `simple-scan` kurulu.
- [x] **macOS düzeni ilkeleri** (sakin kenar çubuğu, Genel bakış'ta sistem sağlığı) — 12 Ekim 2026, deneme bekliyor.
- [x] **Arayüz yenileme — macOS havası** (kararlar.md › Arayüz tasarımı, 12 Ekim 2026): `tokens.py` + QSS +
  kenar çubuğu renkli simge kutuları; yazı 16 px, başlık 32 px. Kodlandı 12 Ekim 2026, deneme bekliyor
  (sayfalarda taşan/sıkışan yerler denemede düzeltilecek).
- **Sürücüler geliştirmesi** (kararlar.md › Güncelleme merkezi › Sürücüler geliştirmesi, 8 Ekim 2026),
  aşamalar — her biri ayrı commit, aralarda kullanıcı dener:
  1. [x] Donanım kartları görünümü (durum rozeti, sade metin + "Ayrıntılar") — 8 Ekim 2026, deneme bekliyor.
  2. [x] Sürücü sağlık kontrolü (modül, çizen kart, sürüm uyuşmazlığı, DKMS) — elle "Denetle". 8 Ekim 2026, deneme bekliyor.
  3. [x] Eksik firmware tespiti (çekirdek günlüğü → depoda doğrulanmış paket). 8 Ekim 2026, deneme bekliyor.
  4. [x] Hibrit grafik (PRIME): Dengeli + programı güçlü kartla açma; Ubuntu'da prime-select modları. 8 Ekim 2026, deneme bekliyor.
  5. [x] Yeni NVIDIA sürümü bildirimi. 8 Ekim 2026, deneme bekliyor (Ubuntu sanal makinesinde: daha yeni `nvidia-driver-<n>` serisi varken bildirim).
- **Ayarlar** (kararlar.md › Ayarlar, 7 Ekim 2026), aşamalar:
  1. [x] İskelet: solda kategoriler + arama, anında kaydetme; mevcut Genel/tema/eklentiler/geçmiş taşınır.
  2. [x] Yapay zekâ bölümü (AI penceresi taşınır, token sınırı, sohbet saklama süresi, erişim izinleri).
  3. [x] Bildirimler ve başlangıç (oturumla tepside başlama, masaüstü bildirimleri, sessiz saatler).
  4. [x] Gizlilik ve veriler, Yedekleme ve sıfırlama, Hakkında.
  5. [x] Ayrı "Gelişmiş" sayfası (teknik ayarlar).
- **Güncelleme merkezi** (kararlar.md › Güncelleme merkezi), aşamalar — her biri ayrı commit, aralarda
  kullanıcı dener:
  1. [x] Güncelleme merkezi arayüzü (Güncellemeler + Sürücüler + Firmware tek sayfa) + güncelleme geçmişi.
  2. [x] Otomatik kurulum (Linwas systemd zamanlayıcısı), duraklatma (1–5 hafta), pil/ölçülü bağlantı
     koşulları, kurulum öncesi Timeshift, yeniden başlatma bildirimi.
  3. [x] Sürücü sürüm seçimi, önceki sürücüye dönme, Secure Boot (MOK), sorun giderme + AI.
  4. [x] Aygıt Yöneticisi (Donanım altında) + yazıcı/tarayıcı sürücüleri.
  5. [x] Firmware ayrıntıları (fwupd) + yeni donanım için yeni çekirdek (HWE / backports).
- **Bottles'a geçiş** (kararlar.md › EXE): kodlandı (7 Ekim 2026), kullanıcının denemesi bekleniyor;
  beğenilmezse `bottles.ENABLED = False` ile dağıtım Wine'ına dönülür.
- Kodlama özellikleri tamam; kalanlar: kullanıcı denemeleri, yayın öncesi kararlar,
  doğrulanacaklar. (Testler kullanıcı yeni emir verene kadar yazılmıyor.)

- **Hazırda bekletme kurulumu** (fikir 10 Ekim 2026, plan 17 Ekim 2026; kullanıcı "kodlamaya geçelim"
  deyince). Linux'ta hazırda bekletme yalnızca swap'a yazılır; Windows'taki `hiberfil.sys` gibi Linwas
  swap dosyasını kendisi kurar. Kullanıcının Pardus'unda durum: swap yok, RAM 23 GB, çekirdek `disk`
  destekliyor, lockdown `none`, `resume=` yok → eksik yalnızca swap + resume.
  - **Kapsam:** Güç ve pil › Hazırda bekletme kartında "Hazırda bekletmeyi kur" (destek yoksa ve neden
    `swap`/`resume` ise). `kernel` ya da `lockdown` (Secure Boot) nedeninde kurulum sunulmaz, neden yazılır.
    Kurulduktan sonra "Hazırda bekletmeyi kaldır".
  - **Ön koşul denetimi (backend/hibernate_setup.py, Qt'siz, test edilebilir):** RAM (`MemTotal`), kök
    dosya sistemi türü (`findmnt -no FSTYPE,UUID /`), boş alan (RAM + 2 GB pay, ayrıca işlemden sonra en az
    %10 boş kalmalı), mevcut swap (`swapon --show --bytes`; zram ayrı sayılır), lockdown, `CanHibernate`,
    LUKS (kök şifreliyse initramfs'de cryptsetup var mı), önyükleyici GRUB mu (`/etc/default/grub` var mı;
    systemd-boot ise şimdilik desteklenmez). Sonuç: `ok` ya da kullanıcıya gösterilecek neden listesi.
  - **Boyut:** varsayılan RAM kadar (yuvarlanmış GB); kullanıcı en az RAM'in yarısına indirebilir (uyarıyla).
    Mevcut disk swap'ı yeterliyse dosya oluşturulmaz, yalnızca resume ayarlanır.
  - **Dosya sistemi:** ext4/xfs: `dd if=/dev/zero` (mkswap(8): bu dosya sistemlerinde fallocate
    önerilmez) + `chmod 600` + `mkswap`; `resume_offset` = `filefrag -v`
    çıktısındaki ilk fiziksel blok. btrfs: `btrfs filesystem mkswapfile` ve
    `btrfs inspect-internal map-swapfile -r` (btrfs-progs ≥ 6.1; Ubuntu 22.04'te 5.16 → desteklenmez,
    nedeni yazılır). Diğer dosya sistemleri: desteklenmez.
  - **Kalıcılık:** `/etc/fstab`'a `/swapfile none swap sw 0 0 # linwas-hibernate` (öncelik verilmez:
    çekirdek eksi öncelik atar, zram (100) önce kullanılır);
    çekirdek satırı için `/etc/default/grub.d/linwas-hibernate.cfg`
    (`GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT resume=UUID=<kök UUID> resume_offset=<n>"`);
    sonra `update-initramfs -u` ve `update-grub`. **Doğrulandı (Pardus 23, initramfs-tools 0.142):** init
    çekirdek satırındaki `resume=`'i `RESUME`'a, `resume_offset=`'i değişkene alır ve conf.d'deki
    `RESUME`'u ezer; bu yüzden `/etc/initramfs-tools/conf.d/resume`'a dokunulmaz (kullanıcının
    makinesinde orada 1 GB'lık etkin olmayan swap LV'si yazılı).
  - **Root işlemleri (whitelist + helper, `shell=True` yok):** `hibernate.setup` (parametre: `size_gb`, yeni
    ParamKind tamsayı aralığı 1–256; dosya yolu sabit `/swapfile`, kullanıcıdan alınmaz) ve
    `hibernate.remove`. Geri alma kaydı yerine işlem içinde geri alma: yarıda hata olursa fstab eski
    hâline döner, grub.d dosyası ve swap dosyası silinir (fstab geri alma önekleri dışında kalır).
    Görev sırası: Timeshift kuruluysa `snapshot.timeshift_create` → `hibernate.setup`. Risk: orta (tek onay
    penceresinde "bilgisayar yeniden başlatılmalı" ve kullanılacak disk alanı yazılır).
  - **Masaüstü:** GNOME kapatma menüsünde hazırda bekletme düğmesi yok; Güç sayfası seçeneklerinde (uyku
    yerine, kapak, güç düğmesi, "bir süre uyuduktan sonra hazırda beklet") zaten sunuluyor. Ubuntu'da
    polkit hazırda bekletmeyi kapatıyorsa (`CanHibernate` = `no`/`challenge`) gerekli polkit kuralı da
    kurulumun parçası olur — kodlarken doğrulanacak.
  - **Sonrası:** "Yeniden başlat" düğmesi (`power.schedule_reboot`); yeniden başlayınca kart "Kullanılabilir"
    der ve "Şimdi dene" düğmesi sunar (açık işlerin kaydedilmesi uyarısıyla `systemctl hibernate`).
  - **Doğrulanacaklar (resmi belgelerden):** initramfs-tools'un `RESUME` ile birlikte çekirdek satırındaki
    `resume_offset`'i okuması (Debian 12/13, Ubuntu 22.04/24.04, Pardus 23); Ubuntu polkit varsayılanı;
    systemd ≥ 255'in EFI `HibernateLocation` ile `resume=` gerektirmemesi (yalnızca bilgi; biz yine yazarız);
    LUKS'lu kökte uyanma; Secure Boot açık Ubuntu'da lockdown nedeninin doğru gösterilmesi.
  - **Aşamalar (her biri ayrı commit):**
    1. [x] `core/hibernate.py` (saf parçalar) + `backend/hibernate_setup.py` (denetim) +
       `tests/test_hibernate.py` (kodlandı 17 Ekim 2026; testler kullanıcıda çalıştırılacak).
    2. [x] Root helper: `hibernate.setup` / `hibernate.remove`, işlem içi geri alma, whitelist
       `SWAP_SIZE_GB` (kodlandı 17 Ekim 2026).
    3. [x] Arayüz: Hazırda bekletme kartında boyut seçimi, onay, Timeshift adımı, "Şimdi yeniden başlat",
       "Şimdi hazırda beklet", "Hazırda bekletmeyi kaldır", çeviriler (kodlandı 17 Ekim 2026).
    4. [ ] Pardus 23 (ext4, GNOME) ve Ubuntu 22.04 sanal makinede deneme; CI kapsayıcılarında `--self-check`.
- **Eklentiler ve üçüncü taraf eklentiler** (karar 17 Ekim 2026; kararlar.md › Eklenti mimarisi).
  Aşamalar (her biri ayrı commit):
  1. [x] **Altyapıyı tamamla** (kodlandı 17 Ekim 2026, deneme bekliyor; ilk açılış kapısı ertelendi, aşağıda): eklenti aç/kapat (ayar dosyasında kapalı eklenti kimlikleri; yerleşik sayfa
     eklentileri de kapatılabilir, çekirdek sayfalar kapatılamaz); boştaki kapıları bağla: `scan_checks` +
     `troubleshooting_cards` → Sorun giderme, `guide_entries` → Rehber/arama, `ai_context` → yardımcıya
     gönderilen sistem bilgisi. Kapı veri yapıları eylem taşıyacak biçimde genişler (sayfaya git, sistem
     ayarı, görev, bağlantı). Ayarlar › Eklentiler: kart listesi (simge, ad, sürüm, yayıncı, rozet:
     Yerleşik / Resmi / Katalog / Geliştirici, aç/kapat, hata satırı, "Ayrıntılar"da kapılar ve izinler).
  2. [x] **Kodsuz eklenti biçimi** (kodlandı 17 Ekim 2026, deneme bekliyor): `core/plugins/declarative.py` (Qt'siz): `manifest.json` şeması (sürüm 1;
     kimlik, çok dilli ad/açıklama, sürüm, yayıncı, en düşük Linwas sürümü, kapılar), katı doğrulayıcı,
     eklentilere açık işlemler listesi, izin özeti çıkarma, `DeclarativePlugin` uyarlayıcısı. Kurulum yeri
     `~/.local/share/linwas/plugins/<kimlik>/`. Geliştirici kipinde yerel dosyadan kurma + izin ekranı.
     Testler: şema, reddedilen işlem/parametre, izin özeti. İlk örnek: "Topluluk sorun giderme
     reçeteleri" (yazıcı, ses, Wi-Fi reçeteleri).
  3. [x] **Katalog ve imza** (kodlandı 17 Ekim 2026, deneme bekliyor; katalog adresi paket derlenirken
     `LINWAS_APT_URL`'den `/usr/share/linwas/plugin-catalog.json`'a yazılır, imza APT anahtarıyla): imzalı `index.json` (`gpgv --keyring <Linwas eklenti anahtarı>`), dosya
     SHA-256 denetimi, Ayarlar › Eklentiler › "Eklenti kataloğu" (göz at, kur, güncelle, kaldır), geri
     çekilen eklentinin kapatılması, yeni izin isteyen güncellemede yeniden onay.
  4. [ ] **Yayın akışı:** yapılanlar: `packaging/build-plugin-catalog.sh` (+ `build_plugin_catalog.py`),
     `release.yml` adımı, örnek `packaging/plugin-catalog/plugins/org.linwas.recipes.json`. Kalan: eklenti
     yazma kılavuzu (`docs/eklenti-yazma.md`), katalog için inceleme süreci, daha çok örnek.
  5. [ ] **İlk açılış sihirbazı kapısı:** `OnboardingStep` yalnız kimlik/ad taşıyor; içerik biçimi (ör. tek
     sayfalık bilgi + eylemler) kararlaştırılınca bağlanacak.
## Aşama 4'ün en sonunda yapılacaklar (kullanıcı kararı, 6 Ekim 2026)
- Oyun sekmesi sonraki sürüme ertelendi (kullanıcı kararı, 7 Ekim 2026; bkz. Bekleyen fikirler).
- [x] **EXE ve Wine:** kodlandı (feat/asama-5-paketleme), kullanıcının denemesi bekleniyor.
- [x] **Programlar › Keşfet:** kategorili öne çıkan programlar (kart ızgarası) ve kartlı arama
  sonuçları kodlandı (7 Ekim 2026), kullanıcının denemesi bekleniyor.

## Aşama 5 sonuna ertelenenler (token tasarrufu, 6 Ekim 2026)
- [ ] Yeni yazılan modüllerin birim testleri (ör. settings_launcher, appearance, troubleshoot,
  error_report, app_settings, onboarding akışı, geri yükleme, dosya yedeği/geri alma) ve
  sayfaların görsel kontrolü. Commit öncesi mevcut `ruff` + `pytest` çalışmaya devam ediyor.

## Bekleyen fikirler (sonraki sürümler)
- [ ] **Windows sanal makinesi (Microsoft 365)** — 7 Ekim 2026'da askıya alındı (kullanıcı kararı); araştırma
  bitti, sıradaki adım 0b (elle prototip). Ayrıntı: kararlar.md › EXE › Windows sanal makinesi. Başlarken
  lisans kararı da verilecek (IoT LTSC lisansının bireysel kullanıma uygunluğu, perakende seçenek,
  kurulum ekranındaki lisans metni). Aşamalar:
  0. [x] Araştırma (7 Ekim 2026) — sonuçlar:
     - **dockur/windows (MIT):** `VERSION=11i` → `win11x64-enterprise-iot-eval` (Windows 11 IoT Enterprise
       LTSC deneme sürümü), `11l` → Enterprise LTSC (IoT değil). ISO Microsoft'un kendi sunucusundan
       (software-static.download.prss.microsoft.com) iner. Varsayılan 4 GB / 2 çekirdek / 64 GB; `RAM_SIZE`,
       `CPU_CORES`, `DISK_SIZE`, `LANGUAGE`, `REGION`, `KEYBOARD`; `/dev/kvm`, `/dev/net/tun`, `NET_ADMIN`;
       RDP 3389, kurulum izleme 8006 (tarayıcı); paylaşılan klasör `/shared` → Windows'ta Z:; kapatırken
       `--stop-timeout 120`. Docker ve Podman destekli; compose şart değil (`docker run` örneği var).
     - **WinApps ve LinOffice: AGPLv3** (WinApps'in eski bazı dosyaları "tüm hakları saklı"). Kodları
       kopyalanmaz; Linwas kendi uygulamasını yazar, dockur'u (MIT) arka uç olarak kullanır.
     - **RemoteApp için Windows içi ayarlar** (Microsoft'un belgelenmiş ayarları): `fDenyTSConnections=0`,
       `TSAppAllowList\fDisabledAllowList=1`, `fAllowUnlistedRemotePrograms=1`, NLA, güvenlik duvarında
       "Remote Desktop" kuralı.
     - **FreeRDP 3:** Ubuntu 24.04 (3.32) ve Debian 13 (3.15) depolarında var; Debian 12/Pardus 23 yalnızca
       bookworm-backports (3.10), Ubuntu 22.04'te yok → bu sistemlerde Flathub `com.freerdp.FreeRDP` (3.32;
       varsayılan komut `sdl-freerdp`, yalnızca İndirilenler'e erişir → ev klasörü için çalıştırırken
       `--filesystem`). RemoteApp argümanları: `/app:program:…,cmd:"dosya"`, `/drive:`, `/wm-class:`.
     - **Kapsayıcı:** Pardus 23'te docker.io 20.10 var ama compose yok; Podman 4.3.1 + podman-compose 1.0.3
       depoda. Linwas compose kullanmadan `podman/docker run` argümanlarını kendisi kurar.
     - **Bellek:** kapsayıcıyı duraklatmak (pause) belleği boşaltmaz; 8 GB'lık makinede boşta Windows'u
       kapatmak gerekir (yeniden açılış yarım dakikayı bulabilir).
  0b. [ ] Kendi makinende deneme (prototip, kod yazmadan önce): root'suz Podman + /dev/kvm + /dev/net/tun
     ile dockur `11i` kurulumu; Flatpak FreeRDP'nin RemoteApp (`/app:`) ile tek pencere açması ve ev klasörü
     paylaşımı; Microsoft 365'in bu Windows'a kurulması; dockur'un kurulum sonrası betik desteği
     (RemoteApp ayarlarını otomatik yapmak için); şifrenin komut satırında görünmemesi (FreeRDP
     `/from-stdin`).
- [ ] **Oyun sekmesi** (Program › Oyun): Steam + Proton, Lutris / Heroic, GameMode, uyumluluk
  kontrolü (AI + ProtonDB). 7 Ekim 2026: ilk yayından sonraki sürüme ertelendi.
- [ ] **"Linwas Hazırlık" Windows aracı:** Geçişten önce Windows'ta çalışan küçük bir araç.
  Chrome/Edge şifrelerini, Wi-Fi şifrelerini ve Outlook verisini güvenli bir pakete aktarır; Linwas
  bu paketi içeri alır. (Ayrı Windows uygulaması gerektirir.)
- [x] **LibreOffice'i Microsoft Office gibi göstermek:** `linwas-office-look` paketi ve
  Office › Office görünümü sayfası (kararlar.md › Office görünümü). Kodlandı 17 Ekim 2026,
  deneme bekliyor. Kalanlar:
  - [x] Paket Linwas APT deposunun yayın iş akışında (`release.yml`; sürüm
    `packaging/plugins/office-look/VERSION`). 17 Ekim 2026: yerel imzalı depoyla denendi
    (apt imzayı kabul ediyor, paket listede). Pardus 23'e .deb ile kuruldu.
  - **Kalanların tanımı (18 Ekim 2026; kullanıcı kararı: 1–6 sırayla, her biri ayrı commit):**
    1. **İlk açılışta Dosya sekmesi:** "Daha fazla araç"taki hatanın aynısı olması muhtemel — şerit Dosya
       sekmesinin denetçisini eklentinin yakalayıcısı kurulmadan alıyor. Plan: Xephyr + geçici profille
       ilk açılışı yeniden üret (bu oturumda kurulan yöntem), XTest ile Dosya sekmesine tıkla; neden
       doğrulanınca ya sekme komutunu LibreOffice'in kendi komutuna bağla ya da eklenti ilk görünümde
       şeridi yeniden yükletsin (`.uno:ToolbarMode` aynı moda). Kabul: temiz profilde ilk açılışta
       Dosya sekmesi menüyü açar.
    2. **Ubuntu 22.04/24.04 ve Debian 13:** `ribbon.build()` her LibreOffice sürümünün notebookbar.ui'ı
       ile çalışmalı (7.3 / 24.2 / 24.8 / 25.x). Plan: CI'ya kapsayıcı adımı — ilgili dağıtımda
       `libreoffice-writer/calc/impress` kurup `build()` + `dangling_size_groups()` + yinelenen kimlik
       denetimi; bir komut kaynakta yoksa düz düğme yazılır (zaten öyle), sekme kimliği yoksa o
       uygulama tam şeritte kalır (zaten öyle). Görsel deneme Ubuntu 22.04 sanal makinesinde.
    3. **Eklenti metinleri yalnız Türkçe:** eklentideki (Dosya menüsü paneli, düğmeler, başlık rozeti)
       metinler `_t("…")` ile iki dilli tabloya taşınır; dil LibreOffice'in arayüz dilinden
       (`org.openoffice.Setup/L10N/ooLocale`) okunur, `tr` dışı her dil İngilizce. Şerit etiketleri
       (`ribbon.py`'deki "Yaz", "Daha fazla araç") da aynı tabloyla, üretim sırasında sistem diline göre.
    4. **Calc "İşlevler" sekmesi (Excel'deki Formüller):** Ekle sekmesinden sonra yeni sekme; gruplar
       (komutların hepsi 7.4.7 Calc arayüz dosyalarında doğrulandı): İşlev ekle `.uno:FunctionDialog`,
       Otomatik toplam `.uno:AutoSum` · Adlar: `.uno:DefineName`, `.uno:AddName`, `.uno:InsertName` ·
       Formül denetimi: `.uno:ShowPrecedents`, `.uno:ShowDependents`, `.uno:ClearArrows`,
       `.uno:ShowErrors`, `.uno:ToggleFormula` (formülleri göster) · Hesapla: `.uno:Calculate`,
       `.uno:CalculateHard`. Excel'deki kategori düğmeleri (Mali, Mantıksal, Metin…) LibreOffice'te tek
       komut olarak yok; "İşlev ekle" penceresi kategoriyle açılır.
    5. **İlk açılış ipucu paneli:** sade şeritle ilk açılışta (kullanıcı başına bir kez) küçük bir
       pencere: "Şerit Word/Excel'deki gibi; tüm araçlar için Daha fazla araç; eski menüler için
       Görünüm › Kullanıcı Arayüzü". "Bir daha gösterme" ayar dosyasına yazılır.
       **Karar (kullanıcı):** evet, kullanıcı başına bir kez.
    6. **Impress "Giriş" sekmesi ONLYOFFICE düzeninde:** Pano · Slayt (`.uno:InsertSlide`,
       `.uno:DuplicateSlide`, `.uno:DeleteSlide`, `.uno:AssignLayout`) · Yazı (yazı tipi, boyut, Büyüt,
       Küçült / K, T, A, üstü çizili, gölge `.uno:Shadowed`, renk, vurgu) · Paragraf (madde, numara /
       hizalamalar, satır aralığı) · Ekle (`.uno:Text`, `.uno:BasicShapes`, `.uno:InsertGraphic`,
       `.uno:InsertTable`) · Gösteri (`.uno:Presentation`, `.uno:PresentationCurrentSlide`) · Bul ·
       Daha fazla araç. Komutlar 7.4.7 Impress notebookbar.ui'da doğrulandı.
  - [ ] Bilinen sınır: paket kurulduktan sonra LibreOffice'in **ilk** açılışında (paket eklentisi
    o sırada kullanıcıya kaydediliyor) Dosya sekmesi menüyü açmıyor; ikinci açılıştan itibaren
    açıyor. Dosya düğmesi ve kısayollar ilk açılışta da çalışıyor.
  - [ ] Ubuntu 22.04/24.04 ve Debian 13'te (LibreOffice 7.3 / 24.x) sade şerit üretimini denemek.
  - [ ] LibreOffice eklentisinin arayüz metinleri yalnız Türkçe; İngilizce karşılıklar.
  - [ ] Calc tasarımındaki "İşlevler" sekmesi ve ilk açılış ipucu paneli.
  - [ ] Writer "Yaz" sekmesi ONLYOFFICE düzeninde (0.5.0, 18 Ekim 2026; grup adsız, ayırıcılı, iki sıra
    simge) — kodlandı. Calc "Tablo" da aynı düzende (Xephyr'de görüldü); Impress "Giriş" sırada.
  - [x] Calc'ta "Daha fazla araç" çalışmıyordu → düğme doğrudan tam şeride geçme komutunu çalıştırıyor.
  - [x] Excel uyumu: Calc formül yazımı Excel A1 (`Sayfa1!A1`).
  - [x] Uygulama adlarında Office karşılığı: menü, arama ve pencere başlığında "LibreOffice Writer (Word)"
    (kullanıcıya özel .desktop kopyası; Office görünümü sayfasında aç/kapat). Görsel deneme bekliyor.
- [ ] **Windows Uygulamaları eklentisi:** Wine tabanlı ayrı alan. Bottles gibi mevcut açık kaynak
  araçlarla entegrasyon araştırılacak. Mevcut EXE/Wine desteği buraya taşınabilir.
- [ ] **KDE desteği** (masaüstü eklentisi). Kullanıcının bilgisayarında KDE oturumu olduğu için
  test kolay.
- [ ] **Yeni AI sağlayıcıları:** Claude, internetsiz yerel model.
- [ ] **Başka dağıtım aileleri:** Fedora (dnf), Arch (pacman) için paket yöneticisi eklentileri.
- [ ] **Okul / kurum paketi** (ör. Pardus kullanan okul laboratuvarları için toplu ayar ve kısıtlama).

## Yayın öncesi yapılacaklar (2.0)
- [ ] Lisans kararı (GPL-3.0 önerildi).
- [ ] Herkese açık yayın yeri: depoyu açmak mı, ayrı "linwas-releases" deposu mu (APT deposu +
  GitHub Issues).
- [ ] Mint ve Pardus 25 için sanal makine testleri (Ubuntu 22.04/24.04 ve Debian 12/13 kurulumu CI'da
  kapsayıcılarda otomatik test ediliyor).
- [ ] Çift tıkla .deb kurulumunun her dağıtımda testi.
- [ ] Paket içindeki Maintainer bilgisi (şu an kullanıcının e-postası) yayından önce gözden geçirilecek.
- [ ] İmza anahtarını üret (`packaging/create-signing-key.sh`), yedeğini çevrim dışı al; GitHub'a
  `LINWAS_SIGNING_KEY` gizli değeri ve `LINWAS_APT_URL` değişkenini ekle.
- [ ] Yayın yeri belli olunca `release.yml`'ye depo yükleme adımı (ör. GitHub Pages).

## Kodlama sırasında doğrulanacaklar
- [ ] **Çalışma grupları (10 Ekim 2026):** GNOME'da masaüstü sayısı/adları, Dash to Panel'de yalnızca geçerli
  grup, Workspace Indicator'da grup adları, auto-move-windows ile programın kendi grubunda açılması (Wayland
  dahil); XFCE'de xfconf adları, Pencere Düğmeleri `include-all-workspaces`, `xfce4-panel --add=pager`
  penceresi, ajanın yeni pencereyi taşıması; Cinnamon'da (sanal makine) adlar, `enabled-applets`'e eklenen
  değiştirici, pencere listesi JSON ayarı; grup sırası değişince/silinince pencerelerin taşınması; son grup
  silinince eski masaüstü ayarlarının geri gelmesi; Flatpak programlarında pencere sınıfı eşleşmesi.
- [ ] **Pencere grupları (10 Ekim 2026):** eklenti kurulup oturum yeniden açılınca panelde grup düğmesi
  (Dash to Panel'de doğru yerde mi); pencere sayısı ve açılır listede önizleme (küçültülmüş pencere dahil);
  tıklayınca pencereye geçiş, kapat düğmesi; gruba alınan programın Dash to Panel'den gizlenmesi ve grup
  silinince geri gelmesi; JSON değişince düğmelerin yenilenmesi; GNOME 46/48'de (Ubuntu 24.04, Debian 13)
  ESM sürümünün açılması; Ubuntu Dock'ta yalnızca düğme.
- [ ] **Program klasörleri (10 Ekim 2026):** DING kurulup oturum yeniden açılınca klasör masaüstünde görünüyor
  mu; masaüstündeki kısayolu klasörün üstüne bırakınca ekleniyor mu (DING "güvenilir" saymazsa sağ tık ›
  "Başlatmaya izin ver"); Dash to Panel'de sabitlenen klasör simgesi ve tıklanınca açılır pencere;
  açılır pencere dışına tıklayınca kapanıyor mu (X11/Wayland); simge değişince masaüstü yeniliyor mu;
  Ubuntu'da (DING hazır kurulu, Ubuntu Dock) aynı adımlar.
- [ ] **Gelişmiş güç seçenekleri (10 Ekim 2026):** .deb kurulunca `linwas-power.service` açık mı;
  plan değiştirirken şifre sorulmuyor mu; prizden çekince/takınca plan ve ekran/uyku süreleri değişiyor mu
  (`gsettings get org.gnome.desktop.session idle-delay`); "Sistem varsayılanı"na dönünce eski değerler geri
  geliyor mu; AMD/Intel/NVIDIA'da ekran kartı güç modu; `iw` ile Wi-Fi tasarrufu; TLP kurulu Ubuntu'da uyarı
  ve salt okunur bölümler; UPower.conf değişince upower yeniden başlıyor mu; powertop CSV ayrıştırma
  (sürüme göre biçim farkı); masaüstü bilgisayarda sayfa adı "Güç".
- [ ] **Ayarlar (aşama 1–3, denenmedi):** `gdbus call … Notify` bildiriminin GNOME/Cinnamon/XFCE'de
  görünmesi ve "Aç" düğmesinin `gdbus monitor` ile yakalanması; oturum açılışında `--background`
  başlatma; tek kopya (menüden ikinci açılışta pencerenin öne gelmesi); KDE/Cinnamon'da tepsi simgesi.
- [ ] **Firmware ve çekirdek (aşama 5, denenmedi):** gerçek bir fwupd güncellemesiyle `get-updates --json`
  alanları (Releases, Urgency) ve `fwupdmgr update <id> -y`; Ubuntu 22.04'te HWE önerisi; saf Debian 12'de
  backports etkinleştirme + `apt-get install -t bookworm-backports linux-image-amd64`.
- [ ] **Sürücü sağlık kontrolü (8 Ekim 2026):** gerçek bir DKMS hatasıyla (ör. çekirdek güncellemesi + başlık paketi yok) "Sürücüleri yeniden hazırla" akışı (`dkms autoinstall -k`); Ubuntu'da `nvidia` modül adı ve `dpkg-query nvidia-*driver*` eşleşmesi; Wayland oturumunda `glxinfo -B`.
- [ ] **Hibrit grafik (8 Ekim 2026):** güçlü kart kısayoluyla açılan programın gerçekten NVIDIA'da çalışması (Pardus'ta `__NV_PRIME_RENDER_OFFLOAD` elle doğrulandı); Flatpak uygulamalarında `env … flatpak run` ile ortam değişkenlerinin geçmesi; Ubuntu'da `prime-select query|nvidia|on-demand|intel` (nvidia-prime) ve AMD+AMD makinede `DRI_PRIME=1`.
- [ ] **Sürücüler (aşama 3–4, denenmedi):** Secure Boot açık bir makinede MOK akışı (mavi ekran,
  `mokutil --test-key`); Ubuntu'da `ubuntu-drivers devices` çıktısı ve `nvidia-driver-<n>` seçenekleri;
  `apt-get purge '.*nvidia.*'` sonrası nouveau ile açılış; yazıcı üretici → paket eşlemesinin gerçek
  aygıtlarla denenmesi (Epson/Brother/Canon modellerinin bir kısmı üreticinin kendi sürücüsünü ister).
- [ ] **Güncelleme merkezi (aşama 1–2, denenmedi):** `.deb` ile kurulunca zamanlayıcının etkin olması
  (`systemctl list-timers linwas-autoupdate.timer`); `sudo systemctl start linwas-autoupdate.service`
  ile elle çalıştırma ve `/var/lib/linwas-autoupdate/state.json`; `timeshift --list` çıktı biçimi
  (eski yedeklerin silinmesi); `shutdown -r SS:DD` sonrası `/run/systemd/shutdown/scheduled` dosyası;
  apt geçmişinde `Linwas::Auto=1` işaretinin görünmesi.
- [ ] **Bottles (bottles-cli):** Flatpak Bottles'ın Pardus 23 ve Ubuntu 22.04'te çalışması; Flatpak
  kum havuzunda dosya erişimi (İndirilenler'deki EXE'ye erişebiliyor mu); `bottles-cli` komutları ve
  JSON çıktısı resmi belgeden (docs.usebottles.com/advanced/cli); Office 2016 ve 365'in gerçek durumu.
  Ayrıca: `bottles-cli run -e` kurulum bitene kadar bekliyor mu (beklemezse menü kısayolları
  "Menüye ekle" düğmesiyle eklenir); şişe klasör adının şişe adıyla aynı olması; `--json programs`
  alan adları; ilk `new` çağrısında Wine/DXVK indirme süresi.
- [ ] Windows NTUSER.DAT değer yolları (klavye Preload, AppsUseLightTheme, SwapMouseButtons,
  LocaleName, LogPixels, Devices) gerçek bir Windows diskiyle denenmeli (`hivexsh` + `lsval`).
- [ ] Ubuntu'da Microsoft font paketinin debconf sorusu (`msttcorefonts/accepted-mscorefonts-eula`)
  — Debian/Pardus 3.8.1 paketinde bu soru yok; Ubuntu sanal makinesinde denenmeli.
- [ ] `data/settings_map.json` GNOME panel adları Ubuntu 22.04'te; Cinnamon modülleri Mint'te.
- [ ] Ubuntu'da AppStream (DEP-11) kataloğuyla aramanın iyileştirilmesi (Pardus depolarında katalog yok;
  şimdilik apt-cache + debtags + Türkçe terim eşlemesi kullanılıyor).
- [ ] Ayar uygulaması bölüm adları (GNOME / Cinnamon / XFCE), Pardus 23 ve Ubuntu 22.04'te.
- [ ] En sık 10–15 ayar için rehber ekran görüntüleri.
- [ ] Pardus 25 GNOME'un kendi "Win 11 Style" düzen seçicisinin Arayüz sayfasında kullanımı.
- [ ] Seçilmiş üçüncü taraf uygulamalar (Chrome, Zoom vb.) için üreticilerin resmi depo adresleri ve
  imza anahtarları — her biri resmi belgeden.
- [ ] Windows ayar kayıtlarından (klavye, bölge, tema, fare, ölçek) okunacak değerlerin yerleri.
- [ ] Program kaldırma: APT, Flatpak ve Snap'te "ayarları da sil" ve "gereksiz bağımlılıkları
  temizle" işlemlerinin tam karşılıkları; kurulma tarihi ve kapladığı alan bilgisinin her kaynakta
  nereden okunacağı; kaldırılması engellenecek kritik paketlerin (masaüstü, oturum açma ekranı, ağ,
  ses, Linwas) dağıtım bazında listesi — her biri resmi belgeden.

## Tamamlananlar
- [x] Aşama 0: iskelet, çeviri altyapısı, geliştirici betikleri, Actions ile .deb + kapsayıcı
  kurulum testi. Pardus 23'te doğrulandı.
- [x] PySide6'nın istediği glibc ve sistem kütüphaneleri → PySide6 6.11.2: manylinux_2_34
  (glibc ≥ 2.34, libstdc++ ≥ 11). Bağımlılık listesi Ubuntu 22.04/24.04 ve Debian 12/13'te CI ile
  doğrulandı.
- [x] Aşama 5 — Son paketleme: kurulu root helper + polkit eylemi (Linwas'a özel mesaj),
  postinst/postrm, imzalı APT deposu betiği, imza anahtarı betiği, yayın iş akışı, CI APT testi
  (debian:12 ve ubuntu:22.04 kapsayıcılarında yerelde de geçti).
- [x] Ubuntu 20.04 / Debian 11 kararı → seçenek A: destekten çıkarıldı (PR #1).

## En sona eklenecekler (kullanıcı kararı, 13 Ekim 2026)
- [ ] **Linwas işlemlerinde şifre sormama:** Linwas'ın kendi işlemleri (root helper) için parola
  istenmesin. Güvenlik etkisi konuşulacak (ör. yalnızca etkin yerel oturum için polkit kuralı,
  yüksek riskli işlemlerde yine sorma seçeneği).

