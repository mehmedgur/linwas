// SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.

// --- Ortak çekirdek (GNOME Shell 42–48) ---
// Kullanıcının seçtiği programların pencerelerini paneldeki tek bir düğmede toplar; düğmeye
// tıklayınca önizlemeli pencere listesi açılır. Gruplar Linwas'ın yazdığı
// ~/.local/share/linwas/window-groups.json dosyasından okunur ve dosya değişince yenilenir.
// Dash to Panel açıksa gruba alınmış programlar onun görev çubuğundan gizlenir
// (Taskbar.getAppInfos süzülür; sabitlenmiş programlar yerinde kalır).

const DTP_UUID = 'dash-to-panel@jderose9.github.com';
const ORIGINAL = Symbol('linwasOriginalGetAppInfos');
const THUMB_W = 160;
const THUMB_H = 100;

class LinwasWindowGroups {
    enable() {
        this._groups = [];
        this._strings = {};
        this._entries = [];
        this._groupedIds = new Set();
        this._signals = [];
        this._patched = [];
        this._dtp = null;
        this._dtpSignal = 0;
        this._updateId = 0;
        this._reloadId = 0;

        const path = GLib.build_filenamev([GLib.get_user_data_dir(), 'linwas', 'window-groups.json']);
        this._file = Gio.File.new_for_path(path);
        this._monitor = this._file.monitor_file(Gio.FileMonitorFlags.NONE, null);
        this._monitor.connect('changed', () => this._queueReload());

        this._connect(Shell.WindowTracker.get_default(), 'tracked-windows-changed', () =>
            this._queueUpdate());
        this._connect(Shell.AppSystem.get_default(), 'app-state-changed', () =>
            this._queueUpdate());
        this._connect(global.settings, 'changed::favorite-apps', () => this._redisplayDtp());
        this._connect(Main.extensionManager, 'extension-state-changed', (_mgr, ext) => {
            if (ext && ext.uuid === DTP_UUID)
                this._connectDtp();
        });

        this._load();
        this._connectDtp();
    }

    disable() {
        for (const id of [this._updateId, this._reloadId]) {
            if (id)
                GLib.source_remove(id);
        }
        this._updateId = this._reloadId = 0;
        for (const [obj, id] of this._signals)
            obj.disconnect(id);
        this._signals = [];
        if (this._monitor) {
            this._monitor.cancel();
            this._monitor = null;
        }
        this._disconnectDtp();
        for (const proto of this._patched) {
            if (proto[ORIGINAL]) {
                proto.getAppInfos = proto[ORIGINAL];
                delete proto[ORIGINAL];
            }
        }
        this._patched = [];
        this._groupedIds = new Set();
        this._redisplayDtp();
        this._destroyButtons();
    }

    _connect(obj, signal, callback) {
        this._signals.push([obj, obj.connect(signal, callback)]);
    }

    // --- Ayar dosyası ---

    _queueReload() {
        if (this._reloadId)
            return;
        this._reloadId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 300, () => {
            this._reloadId = 0;
            this._load();
            return GLib.SOURCE_REMOVE;
        });
    }

    _load() {
        let data = {};
        try {
            const [, bytes] = this._file.load_contents(null);
            data = JSON.parse(new TextDecoder().decode(bytes));
        } catch (e) {
            data = {};
        }
        const groups = Array.isArray(data.groups) ? data.groups : [];
        this._groups = groups
            .filter(g => g && typeof g.id === 'string' && typeof g.name === 'string')
            .map(g => ({
                id: g.id,
                name: g.name,
                apps: Array.isArray(g.apps) ? g.apps.filter(a => typeof a === 'string') : [],
            }));
        this._strings = data.strings && typeof data.strings === 'object' ? data.strings : {};
        this._groupedIds = new Set(this._groups.flatMap(g => g.apps));
        this._rebuildButtons();
        this._redisplayDtp();
    }

    // --- Panel düğmeleri ---

    _destroyButtons() {
        for (const entry of this._entries)
            entry.button.destroy();
        this._entries = [];
    }

    _rebuildButtons() {
        this._destroyButtons();
        this._groups.forEach((group, i) => {
            const button = new PanelMenu.Button(0.0, group.name, false);
            const box = new St.BoxLayout({style_class: 'panel-status-menu-box linwas-group-button-box'});
            const icon = new St.Icon({style_class: 'system-status-icon', gicon: this._groupIcon(group)});
            const label = new St.Label({text: group.name, y_align: Clutter.ActorAlign.CENTER});
            const count = new St.Label({style_class: 'linwas-group-count', y_align: Clutter.ActorAlign.CENTER});
            box.add_child(icon);
            box.add_child(label);
            box.add_child(count);
            button.add_child(box);
            const entry = {group, button, count};
            button.menu.connect('open-state-changed', (_menu, open) => {
                if (open)
                    this._fillMenu(entry);
            });
            Main.panel.addToStatusArea(`linwas-group-${group.id}`, button, 100 + i, 'left');
            this._entries.push(entry);
        });
        this._update();
    }

    _groupIcon(group) {
        const appSystem = Shell.AppSystem.get_default();
        for (const id of group.apps) {
            const app = appSystem.lookup_app(id);
            if (app)
                return app.get_icon();
        }
        return Gio.ThemedIcon.new('view-grid-symbolic');
    }

    _queueUpdate() {
        if (this._updateId)
            return;
        this._updateId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 150, () => {
            this._updateId = 0;
            this._update();
            return GLib.SOURCE_REMOVE;
        });
    }

    _update() {
        // Penceresi olmayan grup panelde yer kaplamaz
        for (const entry of this._entries) {
            const n = this._groupWindows(entry.group).length;
            entry.count.text = n > 1 ? `${n}` : '';
            entry.button.visible = n > 0;
        }
    }

    _groupWindows(group) {
        const ids = new Set(group.apps);
        const tracker = Shell.WindowTracker.get_default();
        return global.display.get_tab_list(Meta.TabList.NORMAL_ALL, null).filter(win => {
            if (win.skip_taskbar)
                return false;
            const app = tracker.get_window_app(win);
            return app !== null && ids.has(app.get_id());
        });
    }

    // --- Açılır pencere listesi ---

    _fillMenu(entry) {
        const menu = entry.button.menu;
        menu.removeAll();
        const windows = this._groupWindows(entry.group);
        if (!windows.length) {
            menu.addMenuItem(new PopupMenu.PopupMenuItem(
                this._strings.noWindows || 'No open windows', {reactive: false}));
            return;
        }
        const tracker = Shell.WindowTracker.get_default();
        for (const win of windows) {
            const app = tracker.get_window_app(win);
            const item = new PopupMenu.PopupBaseMenuItem({style_class: 'linwas-group-item'});
            item.add_child(this._thumbnail(win, app));

            const text = new St.BoxLayout({vertical: true, x_expand: true, y_align: Clutter.ActorAlign.CENTER});
            text.add_child(new St.Label({style_class: 'linwas-group-title', text: win.get_title() || ''}));
            if (app) {
                const sub = new St.Label({text: app.get_name(), style_class: 'linwas-group-count'});
                text.add_child(sub);
            }
            item.add_child(text);

            const close = new St.Button({
                style_class: 'linwas-group-close',
                child: new St.Icon({icon_name: 'window-close-symbolic', icon_size: 16}),
                y_align: Clutter.ActorAlign.CENTER,
            });
            if (this._strings.close)
                close.accessible_name = this._strings.close;
            close.connect('clicked', () => {
                win.delete(global.get_current_time());
                menu.close();
            });
            item.add_child(close);

            item.connect('activate', () => Main.activateWindow(win));
            menu.addMenuItem(item);
        }
    }

    _thumbnail(win, app) {
        const actor = win.get_compositor_private();
        if (actor) {
            const [w, h] = actor.get_size();
            if (w > 0 && h > 0) {
                const scale = Math.min(THUMB_W / w, THUMB_H / h, 1);
                const clone = new Clutter.Clone({source: actor, width: w * scale, height: h * scale});
                return new St.Bin({style_class: 'linwas-group-thumb', child: clone});
            }
        }
        return new St.Icon({
            gicon: app ? app.get_icon() : Gio.ThemedIcon.new('application-x-executable'),
            icon_size: 48,
        });
    }

    // --- Dash to Panel ---

    _connectDtp() {
        this._disconnectDtp();
        const dtp = global.dashToPanel;
        if (!dtp)
            return;
        this._dtp = dtp;
        this._dtpSignal = dtp.connect('panels-created', () => this._patchDtp());
        this._patchDtp();
    }

    _disconnectDtp() {
        if (this._dtp && this._dtpSignal) {
            try {
                this._dtp.disconnect(this._dtpSignal);
            } catch (e) {
                // Dash to Panel kapanırken nesnesini silmiş olabilir
            }
        }
        this._dtp = null;
        this._dtpSignal = 0;
    }

    _patchDtp() {
        const panels = global.dashToPanel && global.dashToPanel.panels;
        if (!Array.isArray(panels))
            return;
        for (const panel of panels) {
            const taskbar = panel && panel.taskbar;
            if (!taskbar)
                continue;
            const proto = Object.getPrototypeOf(taskbar);
            if (typeof proto.getAppInfos !== 'function' || proto[ORIGINAL])
                continue;
            const original = proto.getAppInfos;
            const self = this;
            proto[ORIGINAL] = original;
            proto.getAppInfos = function (...args) {
                return self._filterAppInfos(original.apply(this, args));
            };
            this._patched.push(proto);
        }
        this._redisplayDtp();
    }

    _filterAppInfos(infos) {
        // Dash to Panel'in iç yapısı değişirse gizlemeyi bırak: pencereler yine görünür
        try {
            if (!this._groupedIds.size || !Array.isArray(infos))
                return infos;
            const favorites = new Set(global.settings.get_strv('favorite-apps'));
            return infos.filter(info => {
                const id = info && info.app ? info.app.get_id() : null;
                return !id || !this._groupedIds.has(id) || favorites.has(id);
            });
        } catch (e) {
            logError(e, 'Linwas window groups');
            return infos;
        }
    }

    _redisplayDtp() {
        const panels = global.dashToPanel && global.dashToPanel.panels;
        if (!Array.isArray(panels))
            return;
        for (const panel of panels) {
            try {
                panel.taskbar._queueRedisplay();
            } catch (e) {
                // Görev çubuğu yoksa ya da yöntem adı değiştiyse yok say
            }
        }
    }
}
