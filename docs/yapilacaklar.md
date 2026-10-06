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
- **Aşama 1 — Altyapı:** kuyruk, izin listesi ve parametre doğrulama, root helper, pkexec/polkit,
  yedek/geri alma kaydı, maskeleme, işlem geçmişi, eklenti yükleyici ve kapılar.

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

## Kodlama sırasında doğrulanacaklar
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

## Tasarımda bekleyenler
- [ ] Kuyruk ekranlarını (Kuyruk / Çalışıyor / Sonuç) v4 sistemine göre yeniden çiz.
- [ ] Yüksek kontrast tema taslağı.
- [ ] Diğer sayfaların taslakları (Giriş, AI Soru, Arayüz, Program, Sorun Giderme, Ayarlar).
- [ ] Doğrula: özel 48 px başlık çubuğu (çerçevesiz pencere) GNOME/Wayland ve XFCE/X11'de düzgün çalışıyor mu.
- [ ] Doğrula: "hareketi azalt" ayarının GNOME/Cinnamon/XFCE'de nereden okunacağı.

## Tamamlananlar
- [x] Aşama 0: iskelet, çeviri altyapısı, geliştirici betikleri, Actions ile .deb + kapsayıcı
  kurulum testi. Pardus 23'te doğrulandı.
- [x] PySide6'nın istediği glibc ve sistem kütüphaneleri → PySide6 6.11.2: manylinux_2_34
  (glibc ≥ 2.34, libstdc++ ≥ 11). Bağımlılık listesi Ubuntu 22.04/24.04 ve Debian 12/13'te CI ile
  doğrulandı.
- [x] Tasarım sistemi: Microsoft Windows tasarım rehberi esas (v4); `docs/tasarim-sistemi.md` + `tokens.json`.
- [x] Ubuntu 20.04 / Debian 11 kararı → seçenek A: destekten çıkarıldı (PR #1).
