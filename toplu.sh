#!/bin/bash
# Linwas: birikmiş değişiklikleri konulara göre ayrı commit'lere böler.
# Kullanım: bash toplu.sh   (terminale yapıştırma, dosya olarak çalıştır)
# Hata olursa betik durur; terminal kapanmaz. Tekrar çalıştırılabilir.

cd ~/linwas || { echo "~/linwas bulunamadı"; exit 1; }

DAL=toplu-gelistirme-20261023

dur() { echo; echo "HATA: $1"; echo "Betik durdu. Yukarıdaki çıktıyı Claude'a gönder."; exit 1; }

# Commit: ileti + dosyalar. Var olmayan yolları atlar, değişiklik yoksa geçer.
grupla() {
  local ileti="$1"; shift
  local yollar=()
  for y in "$@"; do
    [ -e "$y" ] && yollar+=("$y")
  done
  [ ${#yollar[@]} -eq 0 ] && { echo "- atlandı (dosya yok): $ileti"; return; }
  git add -- "${yollar[@]}" || dur "git add: $ileti"
  if git diff --cached --quiet; then
    echo "- atlandı (değişiklik yok): $ileti"
  else
    git commit -q -m "$ileti" || dur "git commit: $ileti"
    echo "+ commit: $ileti"
  fi
}

echo "== 1) Commit edilmeyecek dosyalar taşınıyor =="
mkdir -p ~/linwas-ekran
for f in ./*.png ./*.jpg ma.txt 2026-10-23-*.txt; do
  [ -e "$f" ] && mv -v "$f" ~/linwas-ekran/
done
grep -qx '\*.run' .gitignore 2>/dev/null || printf '\n# Üretilen kurulum dosyaları\n*.run\n' >> .gitignore

echo; echo "== 2) Kontroller =="
ruff check . || dur "ruff check kırmızı"
ruff format --check . || dur "ruff format kırmızı (ruff format . ile düzeltilebilir)"
python3 -m pytest -q || dur "pytest kırmızı"

echo; echo "== 3) Dal =="
if git rev-parse --verify -q "$DAL" >/dev/null; then
  git switch "$DAL" || dur "dala geçilemedi"
else
  git switch -c "$DAL" || dur "dal açılamadı"
fi

echo; echo "== 4) Commit'ler =="
grupla "gitignore: *.run kurulum dosyaları" .gitignore

grupla "Eklenti sistemi: katalog, bildirimsel eklentiler, izin ekranı" \
  linwas/core/plugins linwas/ui/dialogs/plugin_permissions.py \
  linwas/ui/pages/settings_plugins.py linwas/ui/plugin_actions.py \
  linwas/plugins/hardware_info/__init__.py \
  packaging/build-plugin-catalog.sh packaging/build_plugin_catalog.py \
  packaging/plugin-catalog \
  tests/test_plugins.py tests/test_plugin_declarative.py

grupla "Office görünümü eklentisi güncellemeleri" \
  linwas/backend/office_look.py linwas/ui/pages/office_look.py \
  packaging/plugins/office-look

grupla "Güç: hazırda bekletme kurulumu, saat ve uyku desteği" \
  linwas/backend/hibernate_setup.py linwas/core/hibernate.py \
  linwas/core/clock.py linwas/core/power_apply.py \
  linwas/backend/power_support.py linwas/ui/pages/power.py \
  linwas/ui/pages/power_texts.py packaging/linwas-clock-sleep.sh \
  tests/test_hibernate.py

grupla "Dokunmatik yüzey ayarları ve dosya türü eşleştirme" \
  linwas/backend/touchpad.py linwas/backend/file_handlers.py \
  tests/test_touchpad.py tests/test_file_handlers.py

grupla "Görev çubuğu düzeni güncellemeleri" \
  linwas/backend/taskbar.py linwas/resources/gnome-taskbar/core.js \
  linwas/ui/pages/taskbar.py tests/test_taskbar_layout.py

grupla "Sorun giderme kontrolleri" \
  linwas/backend/troubleshoot.py linwas/ui/pages/troubleshoot.py \
  tests/test_troubleshoot_checks.py

grupla "Ortak arayüz: yeni bileşenler, tema ve sayfa düzeltmeleri" \
  linwas/ui/widgets/fit.py linwas/ui/widgets/option_tile.py \
  linwas/ui/theme linwas/ui/icons.py linwas/ui/main_window.py \
  linwas/ui/status_bar.py linwas/ui/pages/overview.py \
  linwas/ui/pages/settings.py linwas/ui/pages/guide.py \
  linwas/ui/pages/cleanup.py linwas/ui/pages/network.py \
  linwas/ui/pages/taskmgr.py linwas/ui/dialogs/onboarding.py

grupla "Paketleme: release akışı, .deb betiği ve tek dosyalık kurulum betiği" \
  .github/workflows/release.yml packaging/build-deb.sh scripts/build-setup.sh

grupla "Belgeler ve Türkçe çeviriler" docs linwas/i18n/linwas_tr.ts

echo; echo "== 5) Gruplara girmeyen dosyalar =="
git status --short
echo
echo "Yukarıda dosya varsa 'git diff <dosya>' ile bak, sonra:"
echo "  git add -u && git commit -m \"Diğer değişiklikler\""
echo "Liste boşsa:"
echo "  git push -u origin $DAL"
