# Linwas — Eco entegrasyonu

Karar (kullanıcı, 23 Ekim 2026): **Linwas, eco (Linux Ekosistemi) içinde modül olacak; linwas2 sabit
kalır**, eco sürümü linwas2 içinde yapılır. Eco deposu: github.com/mehmedgur/eco (özel).

## Karar verilenler
- **Görünüm:** eco, Linwas'ın mevcut tema sistemine yeni bir **düzen** olarak eklendi (`UiStyle.ECO`);
  ayrı bir tema motoru yok. Ayrıntı: kararlar.md › Arayüz tasarımı › Eco düzeni.
- Eco'da Linwas **tam bir ayarlar uygulaması** olacak (eco'da `systemsettings` yok); ayarların sahibi eco
  servisleridir, Linwas arayüzdür ve eco servisine yazar.
- Masaüstü kapsamı eco ile aynı (şimdi KWin/Plasma, ileride eco'nun kendi masaüstü katmanı). Qt/QML
  kabuk eco'da kalır; değişen compositor ve ayar katmanıdır. Masaüstüne bağımlı kod ileride tek bir
  bağdaştırıcı arayüzünün arkasında toplanır.
- Eco kuralı: kodda ve commit'lerde model adı geçmez, `Co-Authored-By` eklenmez (eco Karar 22).

## Eco'dan bilinenler (eco `docs/DEVIR.md`, `docs/KARARLAR.md`)
- Rust bağlam servisi `baglamd` (D-Bus), C++/QML kabuk (plasmashell yerine), KWin; hedef Pardus 25.
- Eylemler "yetenek kaydı"nda ad, girdi, risk seviyesi ve geri alma yöntemiyle tanımlanır (Karar 14).
- Bellek hedefi: temel Plasma + en fazla 200 MB (Python/PySide6 isteğe bağlı başlatılmalı).

## Açık sorular
- [ ] Entegrasyon yolu: (1) ayrı süreç + D-Bus, (2) yetenek kaydına eylem olarak kaydolma,
  (3) arayüzü eco kabuğuna gömme. Öneri: 1, sonra 2.
- [ ] Linwas'ın izin modeli (root helper, polkit) ile eco politika motorunun ilişkisi.
- [ ] Eco ayar şeması / servis arayüzü (eco tarafında henüz tanımlı değil).
