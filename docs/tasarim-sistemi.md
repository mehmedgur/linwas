# Linwas 2.0 — Tasarım sistemi

> **Kural:** Tasarımda Microsoft Windows tasarım rehberi ne diyorsa o uygulanır
> (https://learn.microsoft.com/windows/apps/design/). Bu belge rehberin Linwas'a uygulanmış hâlidir.
> Arayüz kodu yazarken **tek kaynak bu belge + [`tasarim/tokens.json`](tasarim/tokens.json)**.
> Yeni bir bileşen yazarken buradaki değerler kullanılır; yeni ölçü, renk ya da süre icat edilmez.

- Onaylı görsel taslak (v4): claude.ai tasarım tuvali — https://claude.ai/artifact/GmBq4uSWwSsfwgJvW6u9BB
  (satır "v4 · Microsoft Windows tasarım rehberine göre"; v1–v3 yalnızca geçmiş için).
- Taslakların kaynak dosyaları: [`tasarim/taslaklar/`](tasarim/taslaklar/) — HTML olarak okunabilir;
  tuval çalışma ortamına (`support.js`) bağlı oldukları için tarayıcıda tek başına açılmaz, ama yerleşim,
  ölçü ve renk kullanımı birebir buradan okunabilir.

## 1. İlkeler (Windows 11)
| İlke | Linwas'ta |
|---|---|
| Zahmetsiz | Her iş az adımda: kuyruk → tek onay. Arama Windows terimlerini anlar. |
| Sakin | Vurgu rengi yalnızca etkileşim/durum ve varsayılan eylem için. Sade dil. |
| Kişisel | Açık / Koyu / Yüksek kontrast, yazı boyutu, sistem vurgu rengi. |
| Tanıdık | Windows yerleşimi, terimleri ve kısayolları. |
| Bütün ve tutarlı | Her ekranda aynı değerler. |

## 2. Temel değerler
Tüm sayılar `tasarim/tokens.json` içinde. Özet:

- **Yazı:** Açıklama 12/16 · Gövde 14/20 · Gövde vurgulu 14/20 (600) · Alt başlık 20/28 (600) ·
  Başlık 28/36 (600). Yalnızca 400 ve 600; kalın/italik yok. Cümle düzeni büyük harf.
  Yazı tipi: Segoe UI Variable → Linux'ta **Noto Sans**.
- **Köşe:** kontroller ve sayfa içi kartlar/listeler 4 · pencere, menü (flyout), iletişim kutusu 8 ·
  birbirine değen düz kenarlar ve büyütülmüş pencere 0.
- **Boşluk (8 tabanlı):** düğmeler arası 8 · başlık–kontrol 8 · etiket–kontrol 12 · içerik alanları 12 ·
  yüzey iç boşluğu 16 · ayar kartları arası 4 · sayfa yatay iç boşluğu 40.
- **Simgeler:** tek renk, **1 px çizgi**, sade geometrik (Segoe Fluent Icons tarzı, **kendi SVG'lerimiz** —
  Segoe Fluent Icons lisans gereği gömülmez). 16 px; ayar kartlarında 20 px (çizgi yine 1 px görünür).
  Renk `metin` (durum simgelerinde durum rengi).
- **Renk:** WinUI tema değerleri, açık ve koyu (bkz. tokens.json). Vurgu = sistem/Windows varsayılanı
  açık `#005FB8`, koyu `#60CDFF`.
- **Malzemeler:** pencere zemini Mica → Linux'ta düz `mica_zemin`; menüler Acrylic → `menu_yuzey_acrylic_yedek`;
  modal arkası Smoke `rgba(0,0,0,0.3)`. Qt arka plan bulanıklaştıramadığı için gerçek Mica/Acrylic yok.

## 3. Pencere düzeni (v4 ana pencere)
```
┌──────────────────────────────────────────────────────────────────────────────┐
│ [←] [▣] Linwas            [ Ara (ör. Denetim Masası) 400px ]        – □ ×    │ 48  başlık çubuğu
├───────────────────────┬──────────────────────────────────────────────────────┤
│ ▌Giriş                │ Sistem › Güncellemeler              [⟳ Tara][▥ Yardımcı] │ 52  sayfa başlığı
│  AI Soru              │ ┌ içerik (yatay iç boşluk 40) ────────────────────────┐ │
│  Sistem         (12)  │ │ durum kartları (3 sütun, aralık 12)                 │ │
│  Arayüz               │ │ ayar kartları (en az 68, aralık 4)  ›               │ │
│  Program              │ │ …                                                   │ │
│  Sorun Giderme   •    │ └─────────────────────────────────────────────────────┘ │
│  …                    │                                         [Yardımcı 320] │
│  Ayarlar              │                                                         │
├───────────────────────┴──────────────────────────────────────────────────────┤
│ 2 işlem kuyrukta · Güncellemeler indiriliyor %45 ▬▬▬        Pardus 23 · GNOME │ 24  durum çubuğu
└──────────────────────────────────────────────────────────────────────────────┘
  320 gezinme bölmesi
```
- **Başlık çubuğu (48):** geri düğmesi (40×48 zemin, 16 px simge, soldan 4), 12 px sonra 16 px uygulama
  simgesi, 16 px sonra başlık (Açıklama 12/16). Arama kutusu ortada, 400×32. Pencere düğmeleri 46×32
  sağ üstte.
- **Gezinme (NavigationView, Left):** 320 px, öğe 36 px, aralık 4, iç boşluk sol 16 / sağ 12, simge 16,
  simge–metin 16. Seçili öğe: `sade_uzerinde` zemin + solda 3×16 vurgu çubuğu (öğeler arasında kayar).
  Ayarlar en altta. Rozet: 16 px yükseklik, vurgu zemin, Açıklama yazısı. Pencere <1008 px'de yalnız
  simge, ≤640 px'de gizli (hamburger).
- **Sayfa başlığı (52):** Başlık 28/36. Alt sayfada breadcrumb: üst sayfa `metin_ikincil` renkli ve
  tıklanabilir, `›` (16 px), mevcut sayfa `metin`. Sayfa komutları sağda sade düğmeler.
- **Menü çubuğu yok.** Sık kullanılan komutlar doğrudan ekranda.
- **Sistem sayfası** Windows Ayarlar düzeninde: üstte durum kartları, altta ayar kartları. Kartın tamamı
  tıklanabilir (sağda `›`) → alt sayfa; ya da sağda kontrol (anahtar, düğme).
- **Durum çubuğu (24):** Açıklama yazısı, sol: kuyruk/ilerleme, sağ: dağıtım · masaüstü · sürüm.

## 4. Bileşenler ve durumlar
Her etkileşimli bileşen: Normal · Üzerinde · Basılı · Odak · Devre dışı (+ uygunsa Seçili, Hata).
Görsel karşılıkları `tasarim/taslaklar/V4States.dc.html`.

| Bileşen | Ölçü | Normal | Üzerinde | Basılı | Devre dışı | Diğer |
|---|---|---|---|---|---|---|
| Düğme | 32 yük., yatay iç 11, köşe 4 | `kontrol`, kenar `kontrol_kenar` + alt `kontrol_kenar_alt` | `kontrol_uzerinde` | `kontrol_basili`, metin ikincil | `kontrol_pasif`, metin pasif | — |
| Vurgu düğmesi | aynı | `vurgu`, metin `vurgu_ustu_metin` | `vurgu_uzerinde` | `vurgu_basili`, metin `vurgu_ustu_metin_basili` | `vurgu_pasif` | Varsayılan eylem; Enter'a yanıt verir |
| Sade düğme | 32 yük. (simgeli 40×32) | saydam | `sade_uzerinde` | `sade_basili` | metin pasif | Açık/basılı durumda `sade_uzerinde` |
| Metin kutusu | 32 yük., iç sol 11 | `kontrol`, alt kenar `metin_ikincil` | `kontrol_uzerinde` | — | `kontrol_pasif` | **Odak:** `kontrol_odak` + alt 2 px vurgu · **Hata:** alt 2 px `hata` + altında satır içi hata metni (12/16, `hata`) |
| Gezinme öğesi | 36 | saydam | `sade_uzerinde` | `sade_basili` | metin pasif | **Seçili:** `sade_uzerinde` + 3×16 vurgu çubuğu |
| Liste öğesi | en az 40 | saydam | `sade_uzerinde` | — | — | **Seçili:** `sade_uzerinde` + 3×16 vurgu çubuğu (üstten 12) |
| Ayar kartı | en az 68, iç 0 16, köşe 4 | `kart`, kenar `kart_kenar` | `kart_uzerinde` (tıklanabilirse) | `kart_basili` | — | simge 20, simge–metin 16 |
| Anahtar | 40×20, topuz 12 | kenar `metin_ikincil`, zemin `kontrol_alternatif` | topuz 14 | — | kenar ve topuz `metin_pasif` | **Açık:** zemin/kenar `vurgu`, topuz `vurgu_ustu_metin`, sağda |
| Onay kutusu | 20 | sistem | | | | vurgu rengi |
| Bilgi çubuğu | en az 48, iç 16, köşe 4 | 4 düzey: bilgi / başarılı / uyarı / hata | | | | 16 px dolu daire simge + yarı kalın başlık + mesaj |
| İletişim kutusu | 320–548 gen., iç 24, köşe 8 | yüzey `iletisim_yuzey`, gölge | | | | aşağıya bakın |

**Odak görseli (klavye):** 2 px dış halka `odak_dis` + 1 px iç halka `odak_ic`, kontrolden 1 px dışarıda.

**İletişim kutusu:** Başlık 20/28 (600), gövde 14/20, aralık 12. Altta komut alanı: zemin
`iletisim_komut_alani`, iç 24, üstte `ayirici` çizgisi, düğmeler **eşit genişlikte**, aralık 8.
**Ana eylem solda (vurgu), güvenli eylem "İptal" en sağda.** Düğme metinleri özel ("Yedek al ve başlat",
"Yükle"; "Evet/Hayır" değil). Esc = İptal. Arkada Smoke. Satır içi doğrulama hataları iletişim kutusuyla
değil, ilgili kontrolün altında gösterilir.

## 5. Hareket
| Ne | Süre | Eğri | Nasıl |
|---|---|---|---|
| Renk/durum geçişi (üzerinde, basılı) | 83 ms | doğrusal | zemin/metin rengi |
| Sayfa girişi | 250 ms | (0,0,0,1) | 28 px aşağıdan yukarı + opaklık 0→1 |
| Alt sayfaya iniş | 250 ms | (0,0,0,1) | ölçek 0,94→1 + opaklık 0→1 |
| Gezinme seçim çubuğu | 250 ms | (0,0,0,1) | çubuk yeni öğeye kayar |
| İletişim kutusu açılışı | Smoke 167 ms doğrusal; kutu 250 ms (0,0,0,1) | | Smoke opaklık 0→1; kutu ölçek 1,05→1 + opaklık |
| Bilgi çubuğu girişi | 167 ms | (0,0,0,1) | 8 px yukarıdan + opaklık |
| Anahtar topuzu | 167 ms | (0,0,0,1) | sola/sağa kayma; üzerinde 12→14 px |
| Çıkışlar | 167 ms | (0,0,0,1) | her zaman opaklıkla birlikte |

Sistemde "hareketi azalt" açıksa tüm animasyonlar kapatılır (GNOME: `org.gnome.desktop.interface
enable-animations`; doğrulanacak).

## 6. Qt Widgets'a aktarım notları
- **Değerler:** `ui/theme/tokens.py` `tokens.json`'u okur (ya da aynı değerleri sabit olarak içerir);
  QSS buradan üretilir. Tema değişince QSS yeniden uygulanır.
- **QSS'in yapabildiği:** `rgba()` renkler, `border-radius`, ayrı alt kenar rengi (`border-bottom`),
  `:hover` / `:pressed` / `:disabled` / `:focus` / `:checked` sözde durumları, iç boşluk ve en küçük
  yükseklikler.
- **QSS'in yapamadığı → özel boyama (`paintEvent`) veya animasyon gerekir:**
  - Geçiş süreleri (CSS `transition` yok) → `QVariantAnimation` / `QPropertyAnimation` ile renk ve konum.
  - Çift halkalı odak görseli → özel boyama.
  - Gezinmedeki kayan seçim çubuğu → gezinme listesinin üzerine çizilen ayrı bir widget + `QPropertyAnimation`.
  - Anahtar (ToggleSwitch) → Qt'de yok; `QAbstractButton` tabanlı özel widget.
  - Bilgi çubuğu (InfoBar), ayar kartı, breadcrumb → özel widget'lar.
  - Sayfa girişi/alt sayfa iniş → `QStackedWidget` geçişinde `QGraphicsOpacityEffect` + konum/ölçek animasyonu.
  - Smoke → pencere üstünde yarı saydam katman widget'ı; iletişim kutusu çerçevesiz (`Qt.FramelessWindowHint`) ve bu katmanın içinde.
- **Özel başlık çubuğu (48 px, ortada arama):** çerçevesiz pencere + `QWindow.startSystemMove()` /
  `startSystemResize()`. GNOME/Wayland ve XFCE/X11'de davranışı **doğrulanmalı** (kenar gölgesi, sürükleme,
  çift tıkla büyütme, pencere düğmeleri). Sorun çıkarsa geri dönüş: sistem başlık çubuğu + arama kutusu
  sayfa başlığı satırına.
- **Yazı tipi:** `QFont("Noto Sans")`, piksel boyutlarıyla (`setPixelSize`). QSS `line-height`
  desteklemez; satır yükseklikleri düzen (layout) aralıkları ve gerekirse `setFixedHeight` ile sağlanır.
- **Simgeler:** `linwas/resources/icons/*.svg`, `stroke="currentColor"`; tema rengiyle yeniden
  renklendirilerek `QIcon` üretilir. HiDPI için SVG.
- **Erişilebilirlik:** her özel widget `setAccessibleName` ve klavye odağı (`Qt.StrongFocus`) almalı;
  sekme sırası taslaktaki görsel sırayla aynı.

## 7. Henüz tasarlanmamış olanlar
- Yüksek kontrast tema (sistem `QPalette` renkleriyle).
- Kuyruk ekranları (Kuyruk / Çalışıyor / Sonuç) v4 sistemine göre yeniden çizilecek.
- Diğer sayfalar (Giriş, AI Soru, Arayüz, Program, Sorun Giderme, Ayarlar) — sayfa sayfa taslak → onay.
- Gezinmenin dar pencere kipleri (yalnız simge / gizli).
