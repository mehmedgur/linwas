# Linwas — Yapılacaklar ve Bekleyen Fikirler

> **Kural:** Her kodlama aşamasına geçmeden önce Claude bu listeyi okur ve bekleyen fikirleri
> kullanıcıya hatırlatır.

Son güncelleme: 6 Ekim 2026

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
- Oyun sekmesi. (Testler kullanıcı yeni emir verene kadar yazılmıyor.)

## Aşama 4'ün en sonunda yapılacaklar (kullanıcı kararı, 6 Ekim 2026)
- [ ] **Oyun sekmesi** (Program › Oyun): Steam + Proton, Lutris / Heroic, GameMode, uyumluluk
  kontrolü (AI + ProtonDB).
- [x] **EXE ve Wine:** kodlandı (feat/asama-5-paketleme), kullanıcının denemesi bekleniyor.

## Aşama 5 sonuna ertelenenler (token tasarrufu, 6 Ekim 2026)
- [ ] Yeni yazılan modüllerin birim testleri (ör. settings_launcher, appearance, troubleshoot,
  error_report, app_settings, onboarding akışı, geri yükleme, dosya yedeği/geri alma) ve
  sayfaların görsel kontrolü. Commit öncesi mevcut `ruff` + `pytest` çalışmaya devam ediyor.

## Bekleyen fikirler (sonraki sürümler)
- [ ] **"Linwas Hazırlık" Windows aracı:** Geçişten önce Windows'ta çalışan küçük bir araç.
  Chrome/Edge şifrelerini, Wi-Fi şifrelerini ve Outlook verisini güvenli bir pakete aktarır; Linwas
  bu paketi içeri alır. (Ayrı Windows uygulaması gerektirir.)
- [ ] **Windows Uygulamaları eklentisi:** Wine tabanlı ayrı alan. Bottles gibi mevcut açık kaynak
  araçlarla entegrasyon araştırılacak. Mevcut EXE/Wine desteği buraya taşınabilir.
- [ ] **KDE desteği** (masaüstü eklentisi). Kullanıcının bilgisayarında KDE oturumu olduğu için
  test kolay.
- [ ] **Yeni AI sağlayıcıları:** Claude, internetsiz yerel model.
- [ ] **Başka dağıtım aileleri:** Fedora (dnf), Arch (pacman) için paket yöneticisi eklentileri.
- [ ] **Okul / kurum paketi** (ör. Pardus kullanan okul laboratuvarları için toplu ayar ve kısıtlama).
- [ ] **Topluluk sorun giderme reçeteleri** (eklenti olarak).
- [ ] **Üçüncü taraf eklentiler:** kendi imza sistemi + izin ekranı.

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
