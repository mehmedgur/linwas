# Linwas 2.0

Windows'tan Linux'a geçenler için, terminal kullanmadan Linux'u yönetmeyi sağlayan masaüstü yardımcısı.
Debian/Ubuntu tabanlı dağıtımlara odaklanır: Ubuntu 20.04+, Debian 11+, Linux Mint, Pardus 23 ve 25.

> **Durum:** Geliştirme aşamasında (aşama 0 — iskelet). Henüz son kullanıcıya uygun değildir.

## Geliştirme sürümünü denemek

### Yol 1 — Geliştirme .deb'i (terminal gerekmez)
1. GitHub'da **Actions** sekmesini aç, en son başarılı çalıştırmayı seç.
2. Sayfanın altındaki **Artifacts** bölümünden `linwas-deb` dosyasını indir.
3. İndirilen zip'i aç, içindeki `.deb` dosyasına çift tıkla ve **Kur**'a bas.
4. Uygulama menüsünden **Linwas**'ı aç.

### Yol 2 — Kaynak koddan (geliştiriciler için, terminal gerekir)
```sh
./scripts/dev-setup.sh   # bir kerelik: sanal ortam + PySide6 + çeviriler
./scripts/run-dev.sh     # uygulamayı çalıştır
```

## Klasör yapısı
```
linwas/            Uygulama kodu
  backend/         Sistem servisleri (dağıtım, masaüstü algılama…)
  core/            Kuyruk, izinler, geri alma, eklenti altyapısı (aşama 1)
  ai/              AI sağlayıcıları (aşama 3)
  plugins/         Yerleşik eklentiler (aşama 4)
  ui/              Arayüz
  i18n/            Çeviriler (kaynak metin İngilizce, Türkçe çeviri)
  resources/       Simgeler
tests/             Birim testleri
scripts/           Geliştirici betikleri
packaging/         .deb paketleme
```

## Geliştirme kuralları
- Kod İngilizce, yorumlar Türkçe.
- Arayüz metinleri kodda İngilizce yazılır; Türkçe çeviri `linwas/i18n/linwas_tr.ts` dosyasında.
- `ruff check .` ve `pytest` her değişiklikte temiz geçmeli.

## Lisans
Linwas özgür yazılımdır: **GNU GPL 3 ve sonrası** ([LICENSE](LICENSE)), GPL'nin 7. bölümünün izin verdiği
ek şartlarla ([NOTICE.md](NOTICE.md)). Herkes kullanabilir, kaynak kodunu değiştirebilir ve dağıtabilir;
her kopyada şunlar korunur:
- kaynak dosyalardaki telif satırları ve "Based on Linwas — Copyright (C) 2026 Mehmed Gürbüz" atfı
  (Hakkında ekranı, `--version`, paket telif dosyası);
- değiştirilmiş sürümler kendilerini "değiştirilmiş sürüm" olarak belirtir;
- "Linwas" adı ve logosu başka ürünün adı olamaz ([TRADEMARKS.md](TRADEMARKS.md)).

Katkılar [CLA.md](CLA.md) ile kabul edilir (taslak; hukuk incelemesinden sonra yürürlüğe girer).
