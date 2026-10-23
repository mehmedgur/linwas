# Linwas — Eco entegrasyonu

Karar (kullanıcı, 23 Ekim 2026): **Linwas, eco (Linux Ekosistemi) içinde modül olacak.**
Kod `linwas/eco/` altında başlar. Eco deposu: github.com/mehmedgur/eco (özel).

## Eco'dan bilinenler (eco `docs/DEVIR.md`, `docs/KARARLAR.md`)
- Rust bağlam servisi `baglamd` (D-Bus), C++/QML kabuk (plasmashell yerine), KWin; hedef Pardus 25.
- Servis ile arayüz D-Bus üzerinden konuşur; eylemler "yetenek kaydı"nda ad, girdi, risk seviyesi ve
  geri alma yöntemiyle tanımlanır (Karar 14: model önerir, yerel politika motoru karar verir).
- Bellek hedefi: temel Plasma + en fazla 200 MB (Python/PySide6 isteğe bağlı başlatılmalı).
- Eco kuralı: kodda ve commit'lerde model adı geçmez, `Co-Authored-By` eklenmez (eco Karar 22).

## Açık sorular (cevap bekliyor)
- [ ] Entegrasyon yolu: (1) ayrı süreç + D-Bus, (2) eco yetenek kaydına eylem olarak kaydolma,
  (3) arayüzü eco kabuğuna gömme. Öneri: 1, sonra 2.
- [ ] Linwas kodu `linwas2`'de mi kalacak, eco'ya mı taşınacak?
- [ ] Linwas'ın izin modeli (root helper, polkit) ile eco politika motorunun ilişkisi.
- [ ] Masaüstü kapsamı: eco KWin/Plasma odaklı; Linwas GNOME/XFCE/Cinnamon hedefliyor.
