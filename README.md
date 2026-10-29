# Linwas

[![CI](https://github.com/mehmedgur/linwas/actions/workflows/ci.yml/badge.svg)](https://github.com/mehmedgur/linwas/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)
[![Latest release](https://img.shields.io/github/v/release/mehmedgur/linwas)](https://github.com/mehmedgur/linwas/releases/latest)

**Türkçe:** [README.tr.md](README.tr.md)

A desktop assistant for people moving from Windows to Linux. It lets you manage Linux without
opening a terminal: install apps, set up drivers, fix Wi-Fi, tune power, back up and keep the system
up to date.

> **Status:** preview release. The interface is Turkish by default; switch to English in
> **Settings › Language**. New translations are welcome (see [Contributing](#contributing)).

## Download and install
1. Download `Linwas-Kurulum.deb` from the [latest release](https://github.com/mehmedgur/linwas/releases/latest).
2. Double-click it and press **Install** in the software center.
3. Open **Linwas** from the application menu.

If double-clicking does nothing, download `Linwas-Kurulum.run`, right-click it ›
**Properties › Permissions › Allow executing as program**, then double-click it for a guided install.

**Supported systems (64-bit):** Ubuntu 22.04+, Debian 12+, Linux Mint 21+, Pardus 23/25.
Desktops: GNOME, Cinnamon, XFCE (others work with limited features).

## What it does
- **Apps:** app store, Flatpak, installed apps, Windows programs through Bottles.
- **Drivers and hardware:** missing drivers and firmware, NVIDIA and hybrid graphics, hardware info.
- **Network:** Wi-Fi, Bluetooth, hotspot, connection quality and troubleshooting.
- **Power:** power plans, battery report, hibernation.
- **Coming from Windows:** move files and settings, a Windows-like taskbar and Office look.
- **Maintenance:** update center, disk cleanup, backups, task manager, resource monitor.
- **AI helper (optional):** answers questions and suggests tasks using your own API key.

## The source is yours
Linwas is free software. Anyone can read the code, change it and share their own version.

**Get the source**
```sh
git clone https://github.com/mehmedgur/linwas.git
cd linwas
```
(or use **Code › Download ZIP** on this page).

**Run it from source**
```sh
./scripts/dev-setup.sh   # once: virtual env, PySide6, translations
./scripts/run-dev.sh     # start Linwas
```

**Build your own .deb**
```sh
./scripts/build-local-deb.sh   # writes linwasnew.deb to your desktop
```

**Make it your own:** fork the repository, change anything you like and publish your version.
The [license](#license) only asks you to keep it free and give credit.

## Project layout
```
linwas/
  backend/     System services (distro, desktop, drivers, network…), no Qt
  core/        Task queue, permissions, undo, plugin system, no Qt
  ai/          AI providers
  plugins/     Built-in plugins
  ui/          Qt (PySide6) interface
  i18n/        Translations (source strings in English, Turkish translation)
tests/         Unit tests (run without PySide6 where possible)
scripts/       Developer scripts
packaging/     .deb packaging, root helper, polkit policy
docs/          Design decisions (Turkish)
```

## Contributing
Bug reports, translations, docs and code are all welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md).
Look for issues labelled
[`good first issue`](https://github.com/mehmedgur/linwas/labels/good%20first%20issue).
Report security issues privately as described in [SECURITY.md](SECURITY.md).

Before sending a pull request:
```sh
ruff check . && ruff format --check . && pytest
```

## License
Linwas is licensed under the **GNU GPL, version 3 or later** ([LICENSE](LICENSE)), with additional
terms allowed by GPL section 7 ([NOTICE.md](NOTICE.md)).

You may use, study, modify and redistribute it, also commercially. When you share a copy or
a modified version:
- keep it under the same license and share its source code;
- keep the copyright notices and the line
  "Based on Linwas — Copyright (C) 2026 Mehmed Gürbüz";
- mark modified versions as modified;
- don't use the "Linwas" name or logo as your product's name ([TRADEMARKS.md](TRADEMARKS.md)).

Contributions are accepted under [CLA.md](CLA.md) (draft).
