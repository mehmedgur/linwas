# Linwas 2.0 — Kodlama Öncesi Doğrulama Raporu

Tarih: 5 Ekim 2026
Kapsam: Python/PySide6 uyumu, dağıtım sürümleri, AI sağlayıcı API'leri, çalışma ortamı kısıtları.

> **Sonradan güncelleme (aşama 0):** CI testleri PySide6 6.11.2'nin `manylinux_2_34` olduğunu
> (glibc ≥ 2.34, libstdc++ ≥ 11) ve Ubuntu 20.04 / Debian 11'de açılamadığını gösterdi.
> Karar: bu sistemler destekten çıkarıldı (bkz. `kararlar.md` › Dağıtımlar ve paketleme).

## 1. Dağıtımlar ve Python sürümleri

| Dağıtım | Taban | Python | Not |
|---|---|---|---|
| Ubuntu 20.04 / Mint 20 | — | 3.8 | Standart destek bitti — **Linwas desteklemiyor** |
| Debian 11 | — | 3.9 | LTS 31 Ağustos 2026'da bitti — **Linwas desteklemiyor** |
| Ubuntu 22.04 / Mint 21 | — | 3.10 | Kullanıcının sanal makinesi |
| Debian 12 / **Pardus 23** | Debian 12 | 3.11 | Kullanıcının bilgisayarı |
| Ubuntu 24.04 / Mint 22 | — | 3.12 | |
| **Pardus 25** | Debian 13 | 3.13 | Kasım 2025'te çıktı; GNOME ve XFCE |

Linwas kendi Python 3.12'sini gömdüğü için sistemin Python sürümü uygulamayı etkilemez; yalnızca
geliştirici kurulumunda (`scripts/dev-setup.sh`) sistem Python'u kullanılır (en az 3.10).

## 2. PySide6 ve Python uyumu
- PySide6'nın en düşük Python sürümü 3.8'den 3.9'a yükseltildi; 6.11 serisi Python 3.10 istiyor.
- Güncel sürüm: 6.11.2 (Ağustos 2026), Linux paket etiketi `manylinux_2_34`.
- Sonuç: Gömülü çalışma ortamı (Python 3.12 + PySide6) seçildi; glibc gömülemediği için en düşük
  sistem gereksinimi glibc 2.34.

## 3. AI sağlayıcıları

| | Model listesi | Kimlik doğrulama | Görsel bilgisi |
|---|---|---|---|
| **ChatGPT (OpenAI)** | `GET https://api.openai.com/v1/models` | `Authorization: Bearer <anahtar>` | Listede yok |
| **Gemini** | `GET https://generativelanguage.googleapis.com/v1beta/models` | `?key=` parametresi | Listede `supportedGenerationMethods` var |
| **DeepSeek** | `GET https://api.deepseek.com/models` | OpenAI uyumlu | Listede `input_modalities` var |

- DeepSeek OpenAI uyumlu biçim kullanıyor (temel adres `https://api.deepseek.com`) → ChatGPT ile ortak istemci.
- DeepSeek model adları değişti (`deepseek-flash`, `deepseek-v4-pro`); model adları koda sabit yazılmaz.
- Anahtar testi üç sağlayıcıda da model listesi çekilerek, token harcamadan yapılabilir.

## 4. Çalışma ortamı kısıtları
- claude.ai bulut ortamından PyPI erişimi engelli: PySide6 orada kurulamaz.
- Claude Code kullanıcının kendi makinesinde çalışırken bu kısıt yoktur.

## Kaynaklar
- Python 3.8 desteğinin kaldırılması (pyside-setup commit aynası): https://git.omada.cafe/Nova/pyside-setup/commit/262e2a6c2742eb9bb0887ae5cb7c2fb0a975f373
- PySide6 6.11'in Python 3.10 istemesi: https://github.com/popovantondev/MegaProg/pull/16
- PySide6 sürüm listesi: https://www.piwheels.org/project/pyside6-essentials/
- Debian 11 LTS sonu: https://www.debian.org/News/2026/20260831.en.html
- Pardus 25.0: https://fossforce.com/2025/12/is-pardus-25-0-turkeys-perfect-gift-to-linux-users/
- OpenAI model listesi: https://developers.openai.com/api/reference/resources/models/methods/list
- Gemini model listesi: https://ai.google.dev/api/models
- DeepSeek API: https://api-docs.deepseek.com/ ve https://api-docs.deepseek.com/api/list-models
