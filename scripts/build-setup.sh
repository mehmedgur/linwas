#!/bin/sh
# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
# Kullanıcıya verilecek kurulum dosyalarını üretir ve masaüstüne kopyalar:
#   Linwas-Kurulum.deb  Çift tıklanınca sistemin grafik kurucusu açılır (Pardus Paket Yükleyici,
#                       GNOME Yazılım, Discover, GDebi). Önerilen yol: her masaüstünde çalışır.
#   Linwas-Kurulum.run  Pencereli kurulum programı (zenity/kdialog + pkexec). KDE, Cinnamon, XFCE
#                       dosya yöneticileri çalıştırılabilir dosyaya çift tıklayınca "Çalıştır" sorar;
#                       GNOME'da sağ tık › "Program olarak çalıştır". İndirilince çalıştırma izni
#                       düşerse: Özellikler › "Program olarak çalıştırılabilir".
# Önce scripts/build-local-deb.sh ile paketi derler.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# --no-build: son derlenen paketi kullan (yalnızca kurulum programı değiştiyse)
[ "${1:-}" = "--no-build" ] || sh scripts/build-local-deb.sh
DEB=$(ls -t build/linwas_*_amd64.deb | head -n 1)
VERSION=$(dpkg-deb -f "$DEB" Version)
SHA=$(sha256sum "$DEB" | cut -d' ' -f1)
OUT_DEB="$ROOT/build/Linwas-Kurulum.deb"
OUT_RUN="$ROOT/build/Linwas-Kurulum.run"
cp "$DEB" "$OUT_DEB"

# Kurulum programının başlığı; gömülü paket __PAYLOAD__ satırından sonra başlar.
# @VERSION@ ve @SHA256@ aşağıda doldurulur (indirme bozulduysa kurulmadan söylenir).
cat >"$OUT_RUN" <<'HEADER'
#!/bin/sh
# Linwas kurulumu: gömülü .deb paketini çıkarır, doğrular ve apt ile kurar (bağımlılıkları apt
# çözer). Masaüstünde pencerelerle (zenity/kdialog), terminalde yazıyla sorar.
#   --check         yalnızca gömülü paketi doğrular, kurmaz
#   --extract DIZIN paketi dizine çıkarır, kurmaz
set -u

VERSION="@VERSION@"
SHA256="@SHA256@"
SELF=$0

case "${LANG:-}${LC_ALL:-}${LC_MESSAGES:-}" in
    *tr_*|*tr.*|tr) TR=1 ;;
    *) TR=0 ;;
esac
# t "Türkçe" "English"
t() { if [ "$TR" = 1 ]; then printf '%s' "$1"; else printf '%s' "$2"; fi; }
TITLE=$(t "Linwas Kurulumu" "Linwas Setup")

# Pencere aracı: KDE'de kdialog, diğerlerinde zenity; terminalden çalışıyorsa yazıyla sorulur
UI=text
if [ ! -t 0 ] || [ ! -t 1 ]; then
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
        case "${XDG_CURRENT_DESKTOP:-}" in
            *KDE*) command -v kdialog >/dev/null 2>&1 && UI=kdialog ;;
        esac
        [ "$UI" = text ] && command -v zenity >/dev/null 2>&1 && UI=zenity
        [ "$UI" = text ] && command -v kdialog >/dev/null 2>&1 && UI=kdialog
        [ "$UI" = text ] && UI=none
    else
        UI=none
    fi
fi

info() {
    case $UI in
        zenity) zenity --info --title="$TITLE" --width=420 --text="$1" 2>/dev/null ;;
        kdialog) kdialog --title "$TITLE" --msgbox "$1" 2>/dev/null ;;
        *) printf '%s\n' "$1" ;;
    esac
}
fail() {
    case $UI in
        zenity) zenity --error --title="$TITLE" --width=420 --text="$1" 2>/dev/null ;;
        kdialog) kdialog --title "$TITLE" --error "$1" 2>/dev/null ;;
        *) printf '%s\n' "$1" >&2 ;;
    esac
    exit 1
}
ask() {
    case $UI in
        zenity) zenity --question --title="$TITLE" --width=420 --text="$1" \
            --ok-label="$2" --cancel-label="$(t "Vazgeç" "Cancel")" 2>/dev/null ;;
        kdialog) kdialog --title "$TITLE" --yes-label "$2" --no-label "$(t "Vazgeç" "Cancel")" \
            --yesno "$1" 2>/dev/null ;;
        *)
            printf '%s [%s] ' "$1" "$(t "E/h" "Y/n")"
            read -r answer || return 1
            case $answer in [nNhH]*) return 1 ;; esac ;;
    esac
}
show_log() {
    case $UI in
        zenity) zenity --text-info --title="$TITLE" --width=640 --height=420 --filename="$1" 2>/dev/null ;;
        kdialog) kdialog --title "$TITLE" --textbox "$1" 640 420 2>/dev/null ;;
        *) tail -n 30 "$1" >&2 ;;
    esac
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
trap 'exit 130' INT TERM
DEB="$TMP/linwas_${VERSION}_amd64.deb"
LINE=$(awk '/^__PAYLOAD__$/ { print NR + 1; exit }' "$SELF")
tail -n +"$LINE" "$SELF" >"$DEB"

if [ "$(sha256sum "$DEB" | cut -d' ' -f1)" != "$SHA256" ]; then
    fail "$(t "Kurulum dosyası eksik ya da bozuk indirilmiş. Lütfen yeniden indir." \
        "The setup file is incomplete or damaged. Please download it again.")"
fi
case "${1:-}" in
    --check) echo "OK linwas $VERSION"; exit 0 ;;
    --extract)
        mkdir -p "${2:?}" && cp "$DEB" "$2/" && echo "$2/$(basename "$DEB")"; exit 0 ;;
esac

if ! command -v apt-get >/dev/null 2>&1; then
    fail "$(t "Linwas yalnızca Pardus, Debian, Ubuntu ve Linux Mint gibi sistemlere kurulabilir." \
        "Linwas can only be installed on Debian-based systems such as Pardus, Ubuntu and Linux Mint.")"
fi
if [ "$(dpkg --print-architecture)" != "amd64" ]; then
    fail "$(t "Linwas yalnızca 64 bit (amd64) bilgisayarlarda çalışır." \
        "Linwas only runs on 64-bit (amd64) computers.")"
fi

# Pencere aracı yoksa (ör. sade masaüstü): paket sistemin kendi kurucusuyla açılır
if [ "$UI" = none ]; then
    KEEP="${XDG_DOWNLOAD_DIR:-$HOME}/Linwas-Kurulum.deb"
    cp "$DEB" "$KEEP" && xdg-open "$KEEP"
    exit $?
fi

INSTALLED=$(dpkg-query -W -f '${Status} ${Version}' linwas 2>/dev/null || true)
case $INSTALLED in
    "install ok installed $VERSION") TEXT=$(t "Linwas $VERSION zaten kurulu. Yeniden kurulsun mu?" \
        "Linwas $VERSION is already installed. Reinstall it?") ;;
    "install ok installed "*) TEXT=$(t "Linwas $VERSION sürümüne güncellenecek." \
        "Linwas will be updated to version $VERSION.") ;;
    *) TEXT=$(t "Linwas $VERSION bu bilgisayara kurulacak. Gereken ek paketler internetten indirilir; yönetici şifren sorulacak." \
        "Linwas $VERSION will be installed on this computer. Required packages are downloaded from the internet; your administrator password will be asked.") ;;
esac
ask "$TEXT" "$(t "Kur" "Install")" || exit 0

# apt paketi _apt kullanıcısıyla okur; okunabilir olmazsa uyarı verir
chmod 755 "$TMP"
chmod 644 "$DEB"
LOG="$TMP/install.log"
# Arka planda otomatik güncelleme sürüyorsa apt kilidi 5 dakikaya kadar beklenir
APT="apt-get -y -o DPkg::Lock::Timeout=300 install $DEB"
# sudo şifreyi aynı pencere aracıyla sorar (pkexec yoksa ya da şifre penceresi gösteremediyse).
# Pencere kapatılırsa iz bırakılır: sudo yanlış şifre sanıp 3 kez sorar, iz varsa pencere bir daha açılmaz
# ve aşağıda "iptal edildi" denir.
use_sudo_askpass() {
    ASKPASS="$TMP/askpass"
    PROMPT=$(t "Linwas'ı kurmak için şifreni gir:" "Enter your password to install Linwas:")
    case $UI in
        zenity) printf '#!/bin/sh\n[ -e "%s" ] && exit 1\nzenity --password --title="%s" 2>/dev/null || { touch "%s"; exit 1; }\n' \
            "$TMP/cancelled" "$TITLE" "$TMP/cancelled" >"$ASKPASS" ;;
        kdialog) printf '#!/bin/sh\n[ -e "%s" ] && exit 1\nkdialog --title "%s" --password "%s" 2>/dev/null || { touch "%s"; exit 1; }\n' \
            "$TMP/cancelled" "$TITLE" "$PROMPT" "$TMP/cancelled" >"$ASKPASS" ;;
    esac
    chmod 700 "$ASKPASS"
    RUN="env SUDO_ASKPASS=$ASKPASS sudo -A env DEBIAN_FRONTEND=noninteractive $APT"
}

install_now() {
    case $UI in
        zenity)
            # Kurulum bitene dek akan çubuk; çıkış kodu dosyaya yazılır (boru hattı onu yutar)
            ( $RUN >"$LOG" 2>&1; echo $? >"$TMP/rc"; echo 100 ) |
                zenity --progress --pulsate --auto-close --no-cancel --title="$TITLE" --width=420 \
                    --text="$(t "Linwas kuruluyor… Bu birkaç dakika sürebilir." \
                        "Installing Linwas… This can take a few minutes.")" 2>/dev/null
            RC=$(cat "$TMP/rc" 2>/dev/null || echo 1) ;;
        kdialog)
            # En çok değer 0: dönen (belirsiz) çubuk. kdialog D-Bus adresini yazar, iş bitince kapatılır.
            REF=$(kdialog --title "$TITLE" --progressbar "$(t "Linwas kuruluyor… Bu birkaç dakika sürebilir." \
                "Installing Linwas… This can take a few minutes.")" 0 2>/dev/null)
            $RUN >"$LOG" 2>&1
            RC=$?
            if [ -n "$REF" ]; then
                set -- $REF
                dbus-send --session --type=method_call --dest="$1" "$2" \
                    org.kde.kdialog.ProgressDialog.close >/dev/null 2>&1 || true
            fi ;;
        *)
            echo "$(t "Linwas kuruluyor…" "Installing Linwas…")"
            { $RUN; echo $? >"$TMP/rc"; } 2>&1 | tee "$LOG"
            RC=$(cat "$TMP/rc" 2>/dev/null || echo 1) ;;
    esac
}

if [ "$(id -u)" -eq 0 ]; then
    RUN="env DEBIAN_FRONTEND=noninteractive $APT"
elif [ "$UI" = text ]; then
    RUN="sudo env DEBIAN_FRONTEND=noninteractive $APT"
elif command -v pkexec >/dev/null 2>&1; then
    RUN="pkexec env DEBIAN_FRONTEND=noninteractive $APT"
else
    use_sudo_askpass  # ör. yeni kurulmuş Debian KDE'de pkexec yok
fi
install_now
# pkexec 127: şifre penceresi gösterilemedi (polkit aracı yok) ya da yetki verilmedi → sudo ile bir kez daha
case $RUN in
    pkexec*) if [ "$RC" = 127 ]; then use_sudo_askpass; install_now; fi ;;
esac

# pkexec 126: kullanıcı şifre penceresini kapattı
if [ "$RC" = 126 ] || [ -e "$TMP/cancelled" ]; then
    info "$(t "Kurulum iptal edildi; bilgisayarda bir şey değişmedi." "Setup was cancelled; nothing was changed.")"
    exit 0
fi
if [ "$RC" != 0 ]; then
    show_log "$LOG"
    fail "$(t "Linwas kurulamadı. Ayrıntılar az önceki pencerede. İnternet bağlantını denetleyip yeniden dene." \
        "Linwas could not be installed. The details are in the previous window. Check your internet connection and try again.")"
fi

if ask "$(t "Linwas kuruldu. Uygulamalar menüsünde de bulabilirsin. Şimdi açılsın mı?" \
    "Linwas is installed. You can also find it in the applications menu. Open it now?")" "$(t "Aç" "Open")"; then
    setsid linwas >/dev/null 2>&1 &
fi
exit 0
__PAYLOAD__
HEADER
sed -i -e "s/@VERSION@/$VERSION/" -e "s/@SHA256@/$SHA/" "$OUT_RUN"
cat "$DEB" >>"$OUT_RUN"
chmod +x "$OUT_RUN"

DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
if [ -d "$DESKTOP_DIR" ]; then
    cp "$OUT_DEB" "$OUT_RUN" "$DESKTOP_DIR/"
    echo "Masaüstüne kopyalandı: Linwas-Kurulum.deb ve Linwas-Kurulum.run"
fi
echo "Kullanıcıya: Linwas-Kurulum.deb dosyasına çift tıklasın (sistem kurucusu açılır)."
