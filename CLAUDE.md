# Linwas 2.0 — Claude için proje notları

**Önce oku:** `docs/kararlar.md` (bütün kararlar) ve `docs/yapilacaklar.md` (bekleyenler).
Bu belgeler projenin tek doğru kaynağıdır. Yeni bir karar alındığında aynı değişiklikte güncelle.

## Çalışma kuralları
- Kullanıcıya Türkçe, kısa cevap ver; detay istenirse ver.
- Görev alınca "Anladım" de, "kodlamaya geçelim" komutunu bekle.
- Her kodlama aşamasından önce `docs/yapilacaklar.md`'yi oku ve bekleyen fikirleri kullanıcıya
  hatırlat.
- Doğrulanmamış API/komut/paket adı kullanma; resmi belgeden doğrula.
- Kullanıcı geliştiricidir ama Linux'ta yeni sayılır: terminal adımlarını açıkça yaz.

## Git
- Her aşama ayrı dalda, küçük ve tek konulu PR. PR açıklamasında "Pardus'ta / Ubuntu'da şunları
  dene" test listesi olsun. Ana dala doğrudan push yok.
- Commit iletileri Türkçe.

## Kod kuralları
- Kod (adlar) İngilizce, yorumlar Türkçe.
- Arayüz metinleri `QCoreApplication.translate(context, text)` ile İngilizce yazılır;
  Türkçe karşılığı aynı değişiklikte `linwas/i18n/linwas_tr.ts` dosyasına eklenir
  (`tests/test_translations.py` eksik/fazla çeviriyi yakalar).
- `linwas/backend`, `linwas/core` Qt'ye bağımlı olmamalı (testler PySide6 olmadan çalışır).
- Kabuk (shell) ile komut çalıştırma yok (`shell=True` yasak). Root işlemleri yalnızca tanımlı işlem
  adı + doğrulanmış parametreyle root helper üzerinden.
- Python 3.10 uyumlu yaz (geliştirme makinesi Ubuntu 22.04); paket Python 3.12 gömer.
- `ruff check .`, `ruff format --check .` ve `pytest` temiz geçmeli.

## Ortam
- **Kullanıcının makinesi (Claude Code burada çalışır):** Pardus 23, testler **GNOME oturumunda**
  (KDE oturumu da var; KDE desteği sonraki sürümde).
  - Kaynak koddan çalıştırma: `./scripts/dev-setup.sh` (bir kerelik) → `./scripts/run-dev.sh`.
  - `sudo`, `pkexec`, `apt install` gibi sistemi değiştiren komutları kendin çalıştırma; ne
    yapacağını açıkla ve kullanıcının onayını al ya da kullanıcıya çalıştırt.
- **Sanal makine:** Ubuntu 22.04.
- **CI (GitHub Actions):** lint + test → gömülü Python 3.12 + PySide6 ile .deb →
  Ubuntu 22.04/24.04, Debian 12/13 kapsayıcılarında kurulum ve `linwas --self-check`.
  Geliştirme .deb'i: Actions › çalıştırma › Artifacts › linwas-deb.
- claude.ai bulut oturumlarında PyPI engelli (PySide6 yok); orada yalnızca arayüz dışı testler
  çalışır.
