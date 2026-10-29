// SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
// Linwas görev çubuğu — GNOME Shell 45+ (ES modülü).
// Bu dosyayı Linwas üretir; elle düzenlemeyin.
import Clutter from 'gi://Clutter';
import GdkPixbuf from 'gi://GdkPixbuf';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
