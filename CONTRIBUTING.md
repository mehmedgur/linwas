# Katkı rehberi

Linwas'a katkı verdiğin için teşekkürler. Hata bildirimi, çeviri, belge ve kod katkılarının hepsi değerli.

## Hata ve öneri
- Önce [açık konulara](https://github.com/mehmedgur/linwas/issues) bak; aynısı varsa 👍 ekle.
- Yeni konu açarken şablonu doldur: dağıtım ve sürümü, masaüstü (GNOME, Cinnamon…), Linwas sürümü
  (`linwas --version`) ve adımlar.
- Güvenlik açıklarını herkese açık konu olarak değil, [SECURITY.md](SECURITY.md)'deki yolla bildir.

## Geliştirme ortamı
```sh
./scripts/dev-setup.sh   # bir kerelik: sanal ortam + PySide6 + çeviriler
./scripts/run-dev.sh     # uygulamayı çalıştır
```
Göndermeden önce şunlar temiz geçmeli:
```sh
ruff check . && ruff format --check . && pytest
```

## Kod kuralları
- Adlar İngilizce, yorumlar Türkçe. Python 3.10 uyumlu yaz.
- Arayüz metinleri `QCoreApplication.translate(context, text)` ile İngilizce yazılır; Türkçesi aynı
  değişiklikte `linwas/i18n/linwas_tr.ts` dosyasına eklenir (`tests/test_translations.py` denetler).
- `linwas/backend` ve `linwas/core` Qt'ye bağımlı olmaz; arayüz dışı her parçanın birim testi olur.
- Kabukla komut çalıştırma yok (`shell=True` yasak). Root gerektiren işlemler yalnızca root helper'daki
  tanımlı işlemlerle yapılır.
- Ayrıntılı kararlar: [docs/kararlar.md](docs/kararlar.md).

## Pull request
- Küçük ve tek konulu tut; `main`'den dal aç.
- Açıklamaya "Pardus'ta / Ubuntu'da şunları dene" şeklinde kısa bir deneme listesi ekle.
- Commit iletileri Türkçe olabilir.
- İlk katkında [CLA.md](CLA.md)'yi kabul ettiğini PR açıklamasında belirt.

## Davranış kuralları
Herkese saygılı ol. [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/)
geçerlidir; uygunsuz davranışı [SECURITY.md](SECURITY.md)'deki iletişim yoluyla bildir.
