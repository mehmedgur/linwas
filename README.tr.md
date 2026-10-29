# Linwas

[![CI](https://github.com/mehmedgur/linwas/actions/workflows/ci.yml/badge.svg)](https://github.com/mehmedgur/linwas/actions/workflows/ci.yml)
[![Lisans: GPL-3.0-or-later](https://img.shields.io/badge/lisans-GPL--3.0--or--later-blue)](LICENSE)
[![Son sürüm](https://img.shields.io/github/v/release/mehmedgur/linwas)](https://github.com/mehmedgur/linwas/releases/latest)

**English:** [README.md](README.md)

Windows'tan Linux'a geçenler için masaüstü yardımcısı. Terminal açmadan Linux'u yönetirsin:
program kur, sürücüleri ayarla, Wi-Fi sorununu çöz, güç ayarlarını yap, yedek al, sistemi güncel tut.

> **Durum:** Önizleme sürümü. Hata bulursan [bildir](https://github.com/mehmedgur/linwas/issues/new/choose).

## İndir ve kur
1. [Son sürüm](https://github.com/mehmedgur/linwas/releases/latest) sayfasından `Linwas-Kurulum.deb` dosyasını indir.
2. Dosyaya çift tıkla, açılan yazılım merkezinde **Kur**'a bas.
3. Uygulama menüsünden **Linwas**'ı aç.

Çift tıklayınca kurulum açılmıyorsa `Linwas-Kurulum.run` dosyasını indir, sağ tıklayıp
**Özellikler › İzinler › Çalıştırılabilir** yap ve çift tıkla; pencereli kurulum başlar.

## Desteklenen sistemler (64 bit)
| Dağıtım | Sürüm |
|---|---|
| Ubuntu | 22.04 ve üstü |
| Debian | 12 ve üstü |
| Linux Mint | 21 ve üstü |
| Pardus | 23 ve 25 |

Masaüstü: GNOME, Cinnamon, XFCE (diğerlerinde sınırlı destek).

**Eski sistemler (Ubuntu 20.04, Debian 11, Linux Mint 20):** Linwas bu sistemlerde çalışmaz; güncel
Qt daha yeni bir sistem kütüphanesi (glibc 2.34) gerektirir. Bu sürümlerin güvenlik güncellemeleri de
sona erdi; dağıtımının **resmi yükseltme rehberiyle** yükseltmeni öneririz. Önce kişisel dosyalarını
yedekle.

## Neler yapar
- **Program kur ve kaldır:** uygulama mağazası, Flatpak, kurulu programlar; Windows programları (Bottles).
- **Sürücü ve donanım:** eksik sürücü/ürün yazılımı, NVIDIA/hibrit ekran kartı, donanım bilgisi.
- **Ağ:** Wi-Fi, Bluetooth, erişim noktası, bağlantı kalitesi ve sorun giderme.
- **Güç:** güç planları, pil raporu, hazırda bekletme.
- **Windows'tan taşıma:** dosya ve ayarları aktarma, Windows'a benzeyen görev çubuğu ve Office görünümü.
- **Bakım:** güncelleme merkezi, disk temizliği, yedekleme, görev yöneticisi, kaynak izleyici.
- **Yapay zekâ yardımcısı (isteğe bağlı):** kendi API anahtarınla sorulara cevap ve görev önerisi.

## Kaynak kodu herkesin
Linwas özgür yazılımdır. İsteyen kodunu okur, istediği gibi değiştirir ve kendi sürümünü paylaşır.

**Kaynak kodunu indir**
```sh
git clone https://github.com/mehmedgur/linwas.git
cd linwas
```
(ya da bu sayfada **Code › Download ZIP**).

**Kaynak koddan çalıştır**
```sh
./scripts/dev-setup.sh   # bir kerelik: sanal ortam, PySide6, çeviriler
./scripts/run-dev.sh     # Linwas'ı başlat
```

**Kendi .deb paketini derle**
```sh
./scripts/build-local-deb.sh   # masaüstüne linwasnew.deb yazar
```

**Kendine göre uyarla:** depoyu çatalla (fork), istediğini değiştir, kendi sürümünü yayınla.
[Lisans](#lisans) yalnızca özgür kalmasını ve emeğe atıf yapılmasını ister.

## Klasör yapısı
```
linwas/
  backend/     Sistem servisleri (dağıtım, masaüstü, sürücü, ağ…), Qt'siz
  core/        Görev kuyruğu, izinler, geri alma, eklenti altyapısı, Qt'siz
  ai/          Yapay zekâ sağlayıcıları
  plugins/     Yerleşik eklentiler
  ui/          Qt (PySide6) arayüzü
  i18n/        Çeviriler (kaynak metin İngilizce, Türkçe çeviri)
tests/         Birim testleri
scripts/       Geliştirici betikleri
packaging/     .deb paketleme, root yardımcısı, polkit kuralı
docs/          Tasarım kararları
```

## Katkı
Hata bildirimi, çeviri, belge ve kod katkılarının hepsi değerli: [CONTRIBUTING.md](CONTRIBUTING.md).
Başlamak için [`good first issue`](https://github.com/mehmedgur/linwas/labels/good%20first%20issue)
etiketli konulara bak. Güvenlik açıklarını [SECURITY.md](SECURITY.md)'deki yolla gizli bildir.

PR göndermeden önce:
```sh
ruff check . && ruff format --check . && pytest
```

## Lisans
Linwas **GNU GPL 3 ve sonrası** ([LICENSE](LICENSE)) ile, GPL'nin 7. bölümünün izin verdiği ek
şartlarla ([NOTICE.md](NOTICE.md)) lisanslıdır.

Herkes kullanabilir, inceleyebilir, değiştirebilir ve dağıtabilir; ticari olarak da. Bir kopyayı ya da
değiştirilmiş sürümü paylaşırken:
- aynı lisansla paylaş ve kaynak kodunu da ver;
- telif satırlarını ve "Based on Linwas — Copyright (C) 2026 Mehmed Gürbüz" atfını koru;
- değiştirilmiş sürümü "değiştirilmiş sürüm" olarak belirt;
- "Linwas" adını ve logosunu kendi ürününün adı olarak kullanma ([TRADEMARKS.md](TRADEMARKS.md)).

Katkılar [CLA.md](CLA.md) ile kabul edilir (taslak).
