# v4 taslak kaynakları

claude.ai tasarım tuvalindeki v4 taslaklarının kaynak dosyaları (Design Component biçimi).

| Dosya | İçerik |
|---|---|
| `V4Main.dc.html` | Ana pencere 1200×760: başlık çubuğu, gezinme, Sistem sayfası, Güncellemeler alt sayfası (breadcrumb, liste), Yardımcı bölmesi, durum çubuğu, onay iletişim kutusu, animasyonlar |
| `V4Dialog.dc.html` | Onay iletişim kutusu (yedek seçimi, ana eylem solda) |
| `V4States.dc.html` | Tüm bileşenlerin durumları + temel değerler |

Bu dosyalar tuvalin çalışma ortamına (`support.js`) bağlıdır; tarayıcıda tek başına açılmaz.
Görsel hâli için tuvali açın: https://claude.ai/artifact/GmBq4uSWwSsfwgJvW6u9BB

Okurken: `{{t.xxx}}` → `tokens.json` renkleri (dosyanın altındaki `renderVals` içinde açık/koyu değerler),
`<helmet><style>` içindeki sınıflar → bileşen durumları ve animasyonlar.
**Uygulamada değerlerin tek kaynağı `../tokens.json` ve `../../tasarim-sistemi.md`'dir.**
