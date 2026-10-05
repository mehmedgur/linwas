# Linwas 2.0 — Claude için proje notları

Kararların tamamı claude.ai'deki "linwas" projesinde:
- `claude/linwas-v1.1-kararlar.md` (karar belgesi, başlığı "Linwas 2.0")
- `claude/linwas-yapilacaklar.md` (yapılacaklar ve bekleyen fikirler)
- `claude/linwas-dogrulama-raporu.md`

## Çalışma kuralları
- Kullanıcıya Türkçe, kısa cevap ver.
- Görev alınca "Anladım" de, "kodlamaya geçelim" komutunu bekle.
- Her kodlama aşamasından önce yapılacaklar listesini oku ve bekleyen fikirleri kullanıcıya hatırlat.
- Doğrulanmamış API/komut/paket adı kullanma; resmi belgeden doğrula.

## Kod kuralları
- Kod (adlar) İngilizce, yorumlar Türkçe.
- Arayüz metinleri `QCoreApplication.translate(context, text)` ile İngilizce yazılır;
  Türkçe karşılığı aynı değişiklikte `linwas/i18n/linwas_tr.ts` dosyasına eklenir.
- `linwas/backend`, `linwas/core` Qt'ye bağımlı olmamalı (testler PySide6 olmadan çalışır).
- Kabuk (shell) ile komut çalıştırma yok. Root işlemleri yalnızca tanımlı işlem adı + doğrulanmış
  parametreyle root helper üzerinden.
- Python 3.10 uyumlu yaz (geliştirme makinesi Ubuntu 22.04); paket Python 3.12 gömer.
- `ruff check .`, `ruff format --check .` ve `pytest` temiz geçmeli.

## Ortam kısıtı
- Claude'un bulut ortamında PyPI engelli: PySide6 yok. Arayüz testleri kullanıcının Pardus 23 /
  Ubuntu 22.04 makinelerinde yapılır. .deb GitHub Actions'ta derlenir.
