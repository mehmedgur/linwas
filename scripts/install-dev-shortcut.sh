#!/bin/sh
# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
# Kaynak koddaki Linwas'ı açan geliştirici kısayolunu kurar (uygulama menüsü + masaüstü).
# Kurulu .deb paketinin kısayolundan ayrıdır; adı "Linwas (Geliştirici)".
# Kaldırmak için: ./scripts/install-dev-shortcut.sh --remove
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")
NAME=linwas-dev.desktop

if [ "${1:-}" = "--remove" ]; then
    rm -f "$APPS_DIR/$NAME" "$DESKTOP_DIR/$NAME"
    echo "Geliştirici kısayolu kaldırıldı."
    exit 0
fi

if [ ! -x "$ROOT/.venv/bin/python" ]; then
    echo "Önce kurulum gerekli: ./scripts/dev-setup.sh" >&2
    exit 1
fi

mkdir -p "$APPS_DIR"
cat >"$APPS_DIR/$NAME" <<EOF
[Desktop Entry]
Type=Application
Name=Linwas (Dev)
Name[tr]=Linwas (Geliştirici)
Comment=Run Linwas from source code
Comment[tr]=Linwas'ı kaynak koddan çalıştırır
Exec="$ROOT/scripts/run-dev.sh"
Path=$ROOT
Icon=$ROOT/linwas/resources/linwas.svg
Terminal=false
Categories=Development;
StartupWMClass=linwas
EOF
chmod +x "$APPS_DIR/$NAME"

if [ -d "$DESKTOP_DIR" ]; then
    cp "$APPS_DIR/$NAME" "$DESKTOP_DIR/$NAME"
    chmod +x "$DESKTOP_DIR/$NAME"
    # GNOME masaüstünde kısayolun "güvenilir" sayılması için (yoksa çalıştırmadan önce sorar)
    gio set "$DESKTOP_DIR/$NAME" metadata::trusted true 2>/dev/null || true
fi

echo "Kısayol kuruldu: uygulama menüsünde ve masaüstünde \"Linwas (Geliştirici)\"."
