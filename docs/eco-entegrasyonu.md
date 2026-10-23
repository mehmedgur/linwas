# Linwas — Eco entegrasyonu

Karar (kullanıcı, 23 Ekim 2026): **Linwas, eco (Linux Ekosistemi) içinde modül olacak.**
Kod `linwas/eco/` altında başlar. Eco deposu: github.com/mehmedgur/eco (özel).

## Eco'dan bilinenler (eco `docs/DEVIR.md`, `docs/KARARLAR.md`)
- Rust bağlam servisi `baglamd` (D-Bus), C++/QML kabuk (plasmashell yerine), KWin; hedef Pardus 25.
- Servis ile arayüz D-Bus üzerinden konuşur; eylemler "yetenek kaydı"nda ad, girdi, risk seviyesi ve
  geri alma yöntemiyle tanımlanır (Karar 14: model önerir, yerel politika motoru karar verir).
- Bellek hedefi: temel Plasma + en fazla 200 MB (Python/PySide6 isteğe bağlı başlatılmalı).
- Eco kuralı: kodda ve commit'lerde model adı geçmez, `Co-Authored-By` eklenmez (eco Karar 22).

## Kararlar (kullanıcı, 23 Ekim 2026)
- **linwas2 sabit kalır.** Eco sürümü linwas2 içinde yeni bir sürüm/profil olarak yapılır
  (`linwas/eco/`); ayrı depo ya da eco'ya taşıma yok.
- **Masaüstü kapsamı eco ile aynı** (şimdi KWin/Plasma; ileride eco'nun kendi masaüstü katmanı).
- Eco kendi masaüstü katmanına geçeceği için Linwas masaüstüne bağımlı kod **tek bir
  "masaüstü bağdaştırıcısı" arayüzünün arkasında** durur (eco'nun compositor bağdaştırıcısı ile
  aynı fikir). Değişen masaüstüne göre yalnızca bağdaştırıcı yazılır.

- **Eco sürümünde Linwas tam bir ayarlar uygulamasıdır** (kullanıcı, 23 Ekim 2026). Eco'da
  `systemsettings` olmadığı için "Sistem ayarlarında aç" bu sürümde yoktur; her ayar Linwas'ta
  gösterilir ve uygulanır. Normal Linwas'ta (GNOME/XFCE/Cinnamon) o buton kalır.
- Bağdaştırıcı bir **ayar arka ucudur**: ayar şeması (ad, tür, aralık, risk, geri alma) ortaktır;
  arka uçlar `oku` / `yaz` / `izle` sağlar. Sırayla: Plasma arka ucu (prototip), eco arka ucu
  (eco kendi masaüstüne geçince). Qt/QML kabuk eco'da kalır, değişen compositor ve ayar katmanıdır.
- Her ayar değişikliği mevcut kurallardan geçer: kuyruk, izin listesi, yedek/geri alma, geçmiş.

- **Ayarların sahibi eco'dur** (kullanıcı, 23 Ekim 2026): ayarları eco servisleri tutar ve uygular;
  Linwas şemayı gösteren arayüzdür ve eco servisine D-Bus ile yazar.
- **Eco teması:** pencere düğmeleri Linwas ile aynı (Windows tarzı, sağ üstte). Eco görsel dili
  `tokens-eco.json` olarak ayrı token dosyasında tutulur (normal Linwas Microsoft temasında kalır).
  Kaynaklar: eco masaüstü mockup v5 (koyu palet, Figtree) + "Hakkında" ayar sayfası görseli (açık
  tema, teal vurgu). Ayrıntı ve çelişkiler açık sorularda.

## Açık sorular (cevap bekliyor)
- [ ] Eco ayar kapsamı: hangi sayfalar ilk sürümde (ekran, ses, ağ, klavye, tema, güç...)?
- [ ] Entegrasyon yolu: (1) ayrı süreç + D-Bus, (2) eco yetenek kaydına eylem olarak kaydolma,
  (3) arayüzü eco kabuğuna gömme. Öneri: 1, sonra 2.
- [ ] Linwas'ın izin modeli (root helper, polkit) ile eco politika motorunun ilişkisi.
- [ ] Bağdaştırıcı arayüzünün kapsamı (ayar okuma/yazma, "ayarlarda aç", tema/ölçek) ve ilk
  bağdaştırıcılar: KDE/Plasma + mevcut GNOME/XFCE/Cinnamon.
