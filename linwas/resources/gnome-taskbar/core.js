
// --- Ortak çekirdek (GNOME Shell 42–48) ---
// Linwas'ın yazdığı ~/.local/share/linwas/taskbar.json dosyasını izler:
//  - Görev çubuğu arka planı: saydam / mat / bulanık, renk kaynağı (tema, vurgu, kapak).
//    Dash to Panel açıksa onun saydamlık ayarları yazılır ve paneline bulanıklık eklenir;
//    değilse GNOME üst çubuğu doğrudan boyanır.
//  - Medya (MPRIS: Spotify, tarayıcıda YouTube Music, son çalan oynatıcı): görev çubuğunda küçük
//    kontrol ve takvim menüsünde GNOME'un medya bölümünün yerine Linwas kartı.
// GNOME 43 kaynağında doğrulananlar: dateMenu._messageList._mediaSection / _sectionList,
// Shell.BlurEffect (GNOME 46'dan itibaren "sigma" yerine "radius").

const DTP_UUID = 'dash-to-panel@jderose9.github.com';
const DTP_SCHEMA = 'org.gnome.shell.extensions.dash-to-panel';
const MPRIS_PREFIX = 'org.mpris.MediaPlayer2.';
const MPRIS_PATH = '/org/mpris/MediaPlayer2';
const BLUR_NAME = 'linwas-taskbar-blur';

const DBUS_XML = `<node><interface name="org.freedesktop.DBus">
  <method name="ListNames"><arg type="as" direction="out" name="names"/></method>
  <signal name="NameOwnerChanged"><arg type="s" name="name"/><arg type="s" name="oldOwner"/>
  <arg type="s" name="newOwner"/></signal></interface></node>`;
const MPRIS_XML = `<node><interface name="org.mpris.MediaPlayer2">
  <method name="Raise"/>
  <property name="CanRaise" type="b" access="read"/>
  <property name="Identity" type="s" access="read"/>
  <property name="DesktopEntry" type="s" access="read"/></interface></node>`;
const PLAYER_XML = `<node><interface name="org.mpris.MediaPlayer2.Player">
  <method name="PlayPause"/><method name="Next"/><method name="Previous"/>
  <property name="PlaybackStatus" type="s" access="read"/>
  <property name="Metadata" type="a{sv}" access="read"/>
  <property name="CanGoNext" type="b" access="read"/>
  <property name="CanGoPrevious" type="b" access="read"/></interface></node>`;

const DBusProxy = Gio.DBusProxy.makeProxyWrapper(DBUS_XML);
const MprisProxy = Gio.DBusProxy.makeProxyWrapper(MPRIS_XML);
const PlayerProxy = Gio.DBusProxy.makeProxyWrapper(PLAYER_XML);

// --- Renk yardımcıları ---

function hexToRgb(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m)
        return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mix(a, b, t) {
    return [0, 1, 2].map(i => Math.round(a[i] + (b[i] - a[i]) * t));
}

function luminance(rgb) {
    const lin = c => {
        const v = c / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2]);
}

function rgba(rgb, alpha) {
    return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${alpha.toFixed(2)})`;
}

function toHex(rgb) {
    return `#${rgb.map(c => c.toString(16).padStart(2, '0')).join('')}`;
}

function fgFor(rgb) {
    return luminance(rgb) > 0.45 ? '#1d1d1f' : '#ffffff';
}

function formatTime(us) {
    if (!(us > 0))
        return '0:00';
    const s = Math.floor(us / 1e6);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

// --- MPRIS oynatıcısı ---

class LinwasPlayer {
    constructor(busName, onChange, onClose) {
        this.busName = busName;
        this.title = '';
        this.artists = [];
        this.artUrl = '';
        this.length = 0;
        this.status = 'Stopped';
        this.identity = '';
        this.desktopEntry = '';
        this.canNext = false;
        this.canPrev = false;
        this.lastActive = 0;
        this._onChange = onChange;
        this._onClose = onClose;
        this._closed = false;
        this._mpris = new MprisProxy(Gio.DBus.session, busName, MPRIS_PATH, (proxy, error) => {
            if (error || this._closed)
                return;
            this.identity = this._mpris.Identity || '';
            this.desktopEntry = this._mpris.DesktopEntry || '';
            this._ownerId = this._mpris.connect('notify::g-name-owner', () => {
                if (!this._mpris.g_name_owner)
                    this._close();
            });
            if (!this._mpris.g_name_owner)
                this._close();
            else
                this._onChange();
        });
        this._player = new PlayerProxy(Gio.DBus.session, busName, MPRIS_PATH, (proxy, error) => {
            if (error || this._closed)
                return;
            this._propsId = this._player.connect('g-properties-changed', () => this._update());
            this._update();
        });
    }

    _update() {
        const raw = this._player.Metadata || {};
        const md = {};
        for (const key in raw) {
            try {
                md[key] = raw[key].deepUnpack();
            } catch (e) {
                md[key] = undefined;
            }
        }
        this.title = typeof md['xesam:title'] === 'string' ? md['xesam:title'] : '';
        const artists = md['xesam:artist'];
        this.artists = Array.isArray(artists) ? artists.filter(a => typeof a === 'string') : [];
        this.artUrl = typeof md['mpris:artUrl'] === 'string' ? md['mpris:artUrl'] : '';
        const length = md['mpris:length'];
        this.length = typeof length === 'number' || typeof length === 'bigint' ? Number(length) : 0;
        this.status = this._player.PlaybackStatus || 'Stopped';
        this.canNext = !!this._player.CanGoNext;
        this.canPrev = !!this._player.CanGoPrevious;
        if (this.status === 'Playing' || !this.lastActive)
            this.lastActive = Date.now();
        this._onChange();
    }

    get playing() {
        return this.status === 'Playing';
    }

    playPause() {
        this._player?.PlayPauseRemote(() => {});
    }

    next() {
        this._player?.NextRemote(() => {});
    }

    previous() {
        this._player?.PreviousRemote(() => {});
    }

    app() {
        if (!this.desktopEntry)
            return null;
        return Shell.AppSystem.get_default().lookup_app(`${this.desktopEntry}.desktop`);
    }

    raise() {
        const app = this.app();
        if (app)
            app.activate();
        else if (this._mpris?.CanRaise)
            this._mpris.RaiseRemote(() => {});
    }

    position(callback) {
        Gio.DBus.session.call(this.busName, MPRIS_PATH, 'org.freedesktop.DBus.Properties', 'Get',
            new GLib.Variant('(ss)', ['org.mpris.MediaPlayer2.Player', 'Position']),
            null, Gio.DBusCallFlags.NONE, 1000, null, (conn, res) => {
                try {
                    callback(Number(conn.call_finish(res).recursiveUnpack()[0]));
                } catch (e) {
                    callback(-1);
                }
            });
    }

    snapshot() {
        return {
            title: this.title, artists: this.artists, artUrl: this.artUrl,
            identity: this.identity, desktopEntry: this.desktopEntry,
        };
    }

    _close() {
        if (this._closed)
            return;
        this.destroy();
        this._onClose(this);
    }

    destroy() {
        this._closed = true;
        if (this._ownerId)
            this._mpris.disconnect(this._ownerId);
        if (this._propsId)
            this._player.disconnect(this._propsId);
        this._ownerId = this._propsId = 0;
    }
}

class MediaManager {
    constructor(onChange) {
        this._players = new Map();
        this._onChange = onChange;
        this.last = null; // kapanan son oynatıcının bilgisi ("son çalınan")
        this._dbus = new DBusProxy(Gio.DBus.session, 'org.freedesktop.DBus', '/org/freedesktop/DBus',
            (proxy, error) => {
                if (error)
                    return;
                this._dbus.ListNamesRemote((result, err) => {
                    if (err || !result)
                        return;
                    for (const name of result[0]) {
                        if (name.startsWith(MPRIS_PREFIX))
                            this._add(name);
                    }
                });
                this._sigId = this._dbus.connectSignal('NameOwnerChanged',
                    (p, sender, [name, oldOwner, newOwner]) => {
                        if (name.startsWith(MPRIS_PREFIX) && newOwner && !oldOwner)
                            this._add(name);
                    });
            });
    }

    _add(name) {
        if (this._players.has(name))
            return;
        const player = new LinwasPlayer(name, () => this._onChange(), p => {
            this._players.delete(p.busName);
            if (p.title)
                this.last = p.snapshot();
            this._onChange();
        });
        this._players.set(name, player);
    }

    players() {
        return [...this._players.values()].filter(p => p.title);
    }

    current() {
        const list = this.players().sort((a, b) =>
            (b.playing - a.playing) || (b.lastActive - a.lastActive));
        return list[0] || null;
    }

    destroy() {
        if (this._sigId)
            this._dbus.disconnectSignal(this._sigId);
        for (const p of this._players.values())
            p.destroy();
        this._players.clear();
    }
}

// --- Kapak resmi ---

function coverDir() {
    return GLib.build_filenamev([GLib.get_user_cache_dir(), 'linwas', 'covers']);
}

function coverPath(url, callback) {
    if (!url) {
        callback(null);
        return;
    }
    if (url.startsWith('file://')) {
        callback(Gio.File.new_for_uri(url).get_path());
        return;
    }
    if (!/^https?:\/\//.test(url)) {
        callback(null);
        return;
    }
    const name = GLib.compute_checksum_for_string(GLib.ChecksumType.SHA1, url, -1);
    const path = GLib.build_filenamev([coverDir(), name]);
    if (GLib.file_test(path, GLib.FileTest.EXISTS)) {
        callback(path);
        return;
    }
    Gio.File.new_for_uri(url).load_contents_async(null, (file, res) => {
        try {
            const [, bytes] = file.load_contents_finish(res);
            GLib.mkdir_with_parents(coverDir(), 0o755);
            GLib.file_set_contents(path, bytes);
            callback(path);
        } catch (e) {
            callback(null);
        }
    });
}

function averageColor(path) {
    try {
        const pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 16, 16, false);
        const px = pb.get_pixels();
        const n = pb.get_n_channels();
        const stride = pb.get_rowstride();
        let r = 0, g = 0, b = 0, count = 0;
        for (let y = 0; y < pb.get_height(); y++) {
            for (let x = 0; x < pb.get_width(); x++) {
                const i = y * stride + x * n;
                r += px[i];
                g += px[i + 1];
                b += px[i + 2];
                count++;
            }
        }
        return count ? [r / count, g / count, b / count].map(Math.round) : null;
    } catch (e) {
        return null;
    }
}

function coverStyle(path) {
    if (!path)
        return '';
    const uri = Gio.File.new_for_path(path).get_uri();
    return `background-image: url("${uri}");`;
}

// --- Medya kartı (görev çubuğu menüsü ve takvim menüsü) ---

class MediaCard {
    constructor(ext) {
        this._ext = ext;
        this._open = false;
        this._timer = 0;
        this.actor = new St.BoxLayout({ vertical: true, style_class: 'linwas-media-card', x_expand: true });

        const head = new St.BoxLayout({ style_class: 'linwas-media-head' });
        this._appIcon = new St.Icon({ icon_size: 16, icon_name: 'audio-x-generic-symbolic' });
        this._appName = new St.Label({ style_class: 'linwas-media-app', y_align: Clutter.ActorAlign.CENTER });
        this._switch = new St.Button({ style_class: 'linwas-media-ctl', can_focus: true,
            child: new St.Icon({ icon_name: 'view-more-horizontal-symbolic', icon_size: 14 }) });
        this._switch.connect('clicked', () => this._ext.nextPlayer());
        head.add_child(this._appIcon);
        head.add_child(this._appName);
        head.add_child(new St.Widget({ x_expand: true }));
        head.add_child(this._switch);
        this.actor.add_child(head);

        this._body = new St.BoxLayout({ style_class: 'linwas-media-body' });
        this._cover = new St.Widget({ style_class: 'linwas-media-cover', width: 96, height: 96 });
        const texts = new St.BoxLayout({ vertical: true, style_class: 'linwas-media-texts', x_expand: true,
            y_align: Clutter.ActorAlign.CENTER });
        this._title = new St.Label({ style_class: 'linwas-media-title' });
        this._artist = new St.Label({ style_class: 'linwas-media-artist' });
        this._track = new St.Widget({ style_class: 'linwas-media-track', x_expand: true, height: 4 });
        this._fill = new St.Widget({ style_class: 'linwas-media-fill', height: 4, width: 0 });
        this._track.add_child(this._fill);
        const times = new St.BoxLayout();
        this._pos = new St.Label({ style_class: 'linwas-media-time' });
        this._len = new St.Label({ style_class: 'linwas-media-time' });
        times.add_child(this._pos);
        times.add_child(new St.Widget({ x_expand: true }));
        times.add_child(this._len);
        texts.add_child(this._title);
        texts.add_child(this._artist);
        texts.add_child(this._track);
        texts.add_child(times);
        this._body.add_child(this._cover);
        this._body.add_child(texts);
        this.actor.add_child(this._body);

        this._controls = new St.BoxLayout({ style_class: 'linwas-media-controls',
            x_align: Clutter.ActorAlign.CENTER });
        this._prev = this._button('media-skip-backward-symbolic', () => this._ext.current()?.previous());
        this._play = this._button('media-playback-start-symbolic', () => this._ext.current()?.playPause());
        this._play.add_style_class_name('linwas-media-play');
        this._next = this._button('media-skip-forward-symbolic', () => this._ext.current()?.next());
        this.actor.add_child(this._controls);

        this._empty = new St.BoxLayout({ vertical: true, style_class: 'linwas-media-empty' });
        this._emptyLabel = new St.Label();
        this._openBtn = new St.Button({ style_class: 'button', can_focus: true });
        this._openBtn.connect('clicked', () => this._ext.openLast());
        this._empty.add_child(this._emptyLabel);
        this._empty.add_child(this._openBtn);
        this.actor.add_child(this._empty);
    }

    _button(icon, callback) {
        const b = new St.Button({ style_class: 'linwas-media-ctl', can_focus: true,
            child: new St.Icon({ icon_name: icon, icon_size: 20 }) });
        b.connect('clicked', () => {
            callback();
            return Clutter.EVENT_STOP;
        });
        this._controls.add_child(b);
        return b;
    }

    setOpen(open) {
        this._open = open;
        if (this._timer) {
            GLib.source_remove(this._timer);
            this._timer = 0;
        }
        if (open) {
            this._tick();
            this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
                this._tick();
                return GLib.SOURCE_CONTINUE;
            });
        }
    }

    _tick() {
        const p = this._ext.current();
        if (!p || !p.length) {
            this._fill.width = 0;
            this._pos.text = '';
            this._len.text = '';
            return;
        }
        p.position(pos => {
            if (!this.actor || pos < 0)
                return;
            const w = this._track.width;
            this._fill.width = Math.max(0, Math.min(w, Math.round(w * pos / p.length)));
            this._pos.text = formatTime(pos);
            this._len.text = formatTime(p.length);
        });
    }

    update(player, last, strings, colors, coverFile) {
        const info = player || last;
        this._body.visible = this._controls.visible = !!player;
        this._empty.visible = !player;
        this._switch.visible = this._ext.players().length > 1;
        this._switch.accessible_name = strings.switch_player || '';
        const app = player ? player.app() : null;
        if (app)
            this._appIcon.gicon = app.get_icon();
        else
            this._appIcon.icon_name = 'audio-x-generic-symbolic';
        this._appName.text = (info && info.identity) || '';
        if (player) {
            this._title.text = player.title || strings.unknown_title || '';
            this._artist.text = player.artists.join(', ') || strings.unknown_artist || '';
            this._play.child.icon_name = player.playing
                ? 'media-playback-pause-symbolic' : 'media-playback-start-symbolic';
            this._prev.reactive = player.canPrev;
            this._next.reactive = player.canNext;
            this._prev.opacity = player.canPrev ? 255 : 110;
            this._next.opacity = player.canNext ? 255 : 110;
            this._cover.set_style(coverStyle(coverFile) ||
                `background-color: ${rgba(colors.fgRgb, 0.12)};`);
        } else {
            this._emptyLabel.text = last
                ? `${strings.last_played || ''} ${last.title}${last.artists.length ? ` · ${last.artists.join(', ')}` : ''}`
                : (strings.nothing_playing || '');
            this._openBtn.visible = !!(last && last.desktopEntry);
            this._openBtn.label = (strings.open_player || '').replace('%1', (last && last.identity) || '');
        }
        this.actor.set_style(`background-color: ${colors.bg}; color: ${colors.fg};`);
        this._track.set_style(`background-color: ${rgba(colors.fgRgb, 0.2)};`);
        this._fill.set_style(`background-color: ${colors.accent};`);
        this._setBlur(colors.blur);
        if (this._open)
            this._tick();
    }

    _setBlur(on) {
        const effect = this.actor.get_effect(BLUR_NAME);
        if (on && !effect)
            this.actor.add_effect_with_name(BLUR_NAME, makeBlur());
        else if (!on && effect)
            this.actor.remove_effect_by_name(BLUR_NAME);
    }

    destroy() {
        this.setOpen(false);
        this.actor.destroy();
        this.actor = null;
    }
}

function makeBlur() {
    const effect = new Shell.BlurEffect({ mode: Shell.BlurMode.BACKGROUND, brightness: 0.85 });
    if ('radius' in effect)
        effect.radius = 30; // GNOME 46+
    else
        effect.sigma = 15;
    return effect;
}

// --- Görev çubuğundaki küçük kontrol ---

const LinwasMediaButton = GObject.registerClass(
class LinwasMediaButton extends PanelMenu.Button {
    _init(ext) {
        super._init(0.5, 'Linwas media', false);
        this._ext = ext;
        const box = new St.BoxLayout({ style_class: 'linwas-media-mini' });
        this._cover = new St.Widget({ style_class: 'linwas-media-mini-cover', width: 20, height: 20,
            y_align: Clutter.ActorAlign.CENTER });
        this._label = new St.Label({ style_class: 'linwas-media-mini-label', y_align: Clutter.ActorAlign.CENTER });
        this._pp = new St.Button({ style_class: 'linwas-media-mini-btn', can_focus: true,
            y_align: Clutter.ActorAlign.CENTER,
            child: new St.Icon({ icon_name: 'media-playback-start-symbolic', icon_size: 16 }) });
        // Oynat/duraklat menüyü açmasın
        this._pp.connect('button-press-event', () => Clutter.EVENT_STOP);
        this._pp.connect('clicked', () => {
            this._ext.current()?.playPause();
            return Clutter.EVENT_STOP;
        });
        box.add_child(this._cover);
        box.add_child(this._label);
        box.add_child(this._pp);
        this.add_child(box);
        this.card = new MediaCard(ext);
        this.menu.box.add_child(this.card.actor);
        this.menu.connect('open-state-changed', (menu, open) => this.card.setOpen(open));
    }

    setChromeless(on) {
        // Saydam/bulanık kartta menünün kendi opak zemini kaldırılır; görünen yüzey kart olur
        this.menu.box.set_style(on
            ? 'background-color: transparent; box-shadow: none; border: none; padding: 0;'
            : null);
    }

    update(player, strings, coverFile, accessibleLabel) {
        this.visible = !!player;
        if (!player)
            return;
        const artist = player.artists.join(', ');
        this._label.text = artist ? `${player.title} · ${artist}` : player.title;
        this._pp.child.icon_name = player.playing
            ? 'media-playback-pause-symbolic' : 'media-playback-start-symbolic';
        this._pp.accessible_name = accessibleLabel;
        this._cover.set_style(coverStyle(coverFile) || 'background-color: rgba(127,127,127,0.3);');
    }
});

// --- Eklenti ---

class LinwasTaskbar {
    enable() {
        this._cfg = {};
        this._signals = [];
        this._coverFile = null;
        this._coverRgb = null;
        this._coverUrl = '';
        this._playerIndex = 0;
        this._applyId = 0;
        this._button = null;
        this._calendarCard = null;
        this._hiddenSection = null;
        this._sectionSignal = 0;
        this._styledPanel = null;
        this._blurred = [];
        this._styledMenus = [];

        const path = GLib.build_filenamev([GLib.get_user_data_dir(), 'linwas', 'taskbar.json']);
        this._file = Gio.File.new_for_path(path);
        this._monitor = this._file.monitor_file(Gio.FileMonitorFlags.NONE, null);
        this._monitor.connect('changed', () => this._queueApply(true));

        this._iface = new Gio.Settings({ schema_id: 'org.gnome.desktop.interface' });
        this._connect(this._iface, 'changed::color-scheme', () => this._queueApply(false));
        this._connect(this._iface, 'changed::gtk-theme', () => this._queueApply(false));
        this._connect(Main.extensionManager, 'extension-state-changed', () =>
            this._queueApply(false));

        this._media = new MediaManager(() => this._onMediaChanged());
        this._load();
        this._apply();
    }

    disable() {
        if (this._applyId)
            GLib.source_remove(this._applyId);
        this._applyId = 0;
        for (const [obj, id] of this._signals)
            obj.disconnect(id);
        this._signals = [];
        if (this._monitor) {
            this._monitor.cancel();
            this._monitor = null;
        }
        this._media.destroy();
        this._media = null;
        this._removeButton();
        this._removeCalendarCard();
        this._resetPanel();
        this._iface = null;
    }

    _connect(obj, signal, callback) {
        this._signals.push([obj, obj.connect(signal, callback)]);
    }

    _queueApply(reload) {
        if (reload)
            this._reload = true;
        if (this._applyId)
            return;
        this._applyId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
            this._applyId = 0;
            if (this._reload) {
                this._reload = false;
                this._load();
            }
            this._apply();
            return GLib.SOURCE_REMOVE;
        });
    }

    _load() {
        try {
            const [ok, bytes] = this._file.load_contents(null);
            this._cfg = ok ? JSON.parse(new TextDecoder().decode(bytes)) : {};
        } catch (e) {
            this._cfg = {};
        }
    }

    get strings() {
        return this._cfg.strings || {};
    }

    // Renkler

    _dark() {
        const scheme = this._iface.get_string('color-scheme');
        if (scheme === 'prefer-dark')
            return true;
        if (scheme === 'prefer-light')
            return false;
        return this._iface.get_string('gtk-theme').toLowerCase().includes('dark');
    }

    _palette() {
        const pal = this._cfg.palette || {};
        const mode = (this._dark() ? pal.dark : pal.light) || {};
        const dark = this._dark();
        return {
            bg: hexToRgb(mode.panel) || (dark ? [37, 37, 39] : [235, 235, 239]),
            card: hexToRgb(mode.card) || (dark ? [44, 44, 46] : [255, 255, 255]),
            accent: mode.accent || pal.accent || '#0066d6',
            dark,
        };
    }

    _baseColor(source, fallback) {
        const pal = this._palette();
        if (source === 'accent')
            return mix(fallback, hexToRgb(pal.accent) || fallback, 0.35);
        if (source === 'cover' && this._coverRgb)
            return mix(this._coverRgb, pal.dark ? [0, 0, 0] : [255, 255, 255], pal.dark ? 0.45 : 0.55);
        return fallback;
    }

    _alpha(style) {
        if (style === 'matte')
            return 1;
        const t = Number(this._cfg.transparency);
        return 1 - (Number.isFinite(t) ? Math.max(0, Math.min(90, t)) : 35) / 100;
    }

    _cardColors() {
        const pal = this._palette();
        const style = this._cfg.card_style || 'matte';
        const base = this._cfg.cover_color ? this._baseColor('cover', pal.card) : pal.card;
        // Saydam/bulanık: görev çubuğuyla aynı saydamlık; mat: tamamen opak
        const alpha = style === 'matte' ? 1 : this._alpha(style);
        const fg = fgFor(base);
        return {
            bg: rgba(base, alpha), fg, fgRgb: hexToRgb(fg), accent: pal.accent,
            blur: style === 'blur', chromeless: style !== 'matte',
        };
    }

    // Görev çubuğu arka planı

    _dtpActive() {
        const ext = Main.extensionManager.lookup(DTP_UUID);
        return !!(ext && ext.state === 1 && global.dashToPanel);
    }

    _dtpSettings() {
        if (this._dtp !== undefined)
            return this._dtp;
        this._dtp = null;
        try {
            const ext = Main.extensionManager.lookup(DTP_UUID);
            const dir = ext && ext.dir.get_child('schemas');
            if (dir && dir.query_exists(null)) {
                const src = Gio.SettingsSchemaSource.new_from_directory(dir.get_path(),
                    Gio.SettingsSchemaSource.get_default(), false);
                const schema = src.lookup(DTP_SCHEMA, true);
                if (schema)
                    this._dtp = new Gio.Settings({ settings_schema: schema });
            }
        } catch (e) {
            this._dtp = null;
        }
        return this._dtp;
    }

    _apply() {
        this._applyPanel();
        this._onMediaChanged();
        this._applyMenus();
    }

    // Görev çubuğundaki bütün açılır menüler (hızlı ayarlar, takvim, ses, ağ, diğer simgeler)

    _menuBoxes() {
        const boxes = [];
        for (const key in Main.panel.statusArea) {
            const item = Main.panel.statusArea[key];
            if (!item || item === this._button)
                continue; // medya menüsünün zemini kart olur (ayrıca ayarlanır)
            const box = item.menu && item.menu.box;
            if (box && typeof box.set_style === 'function' && !boxes.includes(box))
                boxes.push(box);
        }
        return boxes;
    }

    _menuStyle() {
        const pal = this._palette();
        const style = this._cfg.card_style || 'matte';
        const alpha = style === 'matte' ? 1 : this._alpha(style);
        return {
            css: `background-color: ${rgba(pal.card, alpha)}; color: ${fgFor(pal.card)};`,
            blur: style === 'blur',
        };
    }

    _applyMenus() {
        const boxes = this._menuBoxes();
        const look = this._menuStyle();
        for (const box of this._styledMenus) {
            if (!boxes.includes(box))
                this._resetMenu(box);
        }
        for (const box of boxes) {
            try {
                box.set_style(look.css);
                const effect = box.get_effect(BLUR_NAME);
                if (look.blur && !effect)
                    box.add_effect_with_name(BLUR_NAME, makeBlur());
                else if (!look.blur && effect)
                    box.remove_effect_by_name(BLUR_NAME);
            } catch (e) {}
        }
        this._styledMenus = boxes;
    }

    _resetMenu(box) {
        try {
            box.set_style(null);
            box.remove_effect_by_name(BLUR_NAME);
        } catch (e) {}
    }

    _applyPanel() {
        const style = this._cfg.panel_style || 'blur';
        const pal = this._palette();
        const base = this._baseColor(this._cfg.panel_color || 'theme', pal.bg);
        const alpha = this._alpha(style);
        const blur = style === 'blur';
        const targets = [];
        if (this._dtpActive()) {
            this._resetMainPanel();
            const s = this._dtpSettings();
            if (s) {
                const hex = toHex(base);
                if (s.get_string('trans-bg-color') !== hex)
                    s.set_string('trans-bg-color', hex);
                if (!s.get_boolean('trans-use-custom-bg'))
                    s.set_boolean('trans-use-custom-bg', true);
                if (!s.get_boolean('trans-use-custom-opacity'))
                    s.set_boolean('trans-use-custom-opacity', true);
                if (Math.abs(s.get_double('trans-panel-opacity') - alpha) > 0.005)
                    s.set_double('trans-panel-opacity', alpha);
                if (s.get_boolean('trans-use-dynamic-opacity'))
                    s.set_boolean('trans-use-dynamic-opacity', false);
            }
            for (const p of global.dashToPanel.panels || []) {
                const actor = p.panelBox || p.panel;
                if (actor)
                    targets.push(actor);
            }
        } else {
            Main.panel.set_style(`background-color: ${rgba(base, alpha)}; color: ${fgFor(base)};`);
            this._styledPanel = Main.panel;
            targets.push(Main.panel);
        }
        this._setBlur(targets, blur);
    }

    _setBlur(targets, on) {
        for (const actor of this._blurred) {
            if (!targets.includes(actor) || !on) {
                try {
                    actor.remove_effect_by_name(BLUR_NAME);
                } catch (e) {}
            }
        }
        this._blurred = [];
        if (!on)
            return;
        for (const actor of targets) {
            if (!actor.get_effect(BLUR_NAME))
                actor.add_effect_with_name(BLUR_NAME, makeBlur());
            this._blurred.push(actor);
        }
    }

    _resetMainPanel() {
        if (this._styledPanel) {
            this._styledPanel.set_style(null);
            this._styledPanel = null;
        }
    }

    _resetPanel() {
        this._resetMainPanel();
        this._setBlur([], false);
        for (const box of this._styledMenus || [])
            this._resetMenu(box);
        this._styledMenus = [];
    }

    // Medya

    players() {
        return this._media ? this._media.players() : [];
    }

    current() {
        if (!this._media)
            return null;
        const list = this.players();
        if (this._pinned && list.find(p => p.busName === this._pinned))
            return list.find(p => p.busName === this._pinned);
        return this._media.current();
    }

    nextPlayer() {
        const list = this.players();
        if (list.length < 2)
            return;
        const cur = this.current();
        const i = list.indexOf(cur);
        this._pinned = list[(i + 1) % list.length].busName;
        this._onMediaChanged();
    }

    openLast() {
        const last = this._media && this._media.last;
        if (!last || !last.desktopEntry)
            return;
        const app = Shell.AppSystem.get_default().lookup_app(`${last.desktopEntry}.desktop`);
        if (app)
            app.activate();
    }

    _onMediaChanged() {
        if (!this._media)
            return;
        const player = this.current();
        const url = player ? player.artUrl : (this._media.last ? this._media.last.artUrl : '');
        if (url !== this._coverUrl) {
            this._coverUrl = url;
            coverPath(url, path => {
                if (url !== this._coverUrl)
                    return;
                this._coverFile = path;
                this._coverRgb = path ? averageColor(path) : null;
                if (this._cfg.panel_color === 'cover')
                    this._applyPanel();
                this._render();
            });
        }
        this._render();
    }

    _render() {
        if (!this._media)
            return;
        const player = this.current();
        const last = this._media.last;
        const colors = this._cardColors();
        const strings = this.strings;
        if (this._cfg.media_panel !== false) {
            if (!this._button) {
                this._button = new LinwasMediaButton(this);
                Main.panel.addToStatusArea('linwas-media', this._button, 0, 'right');
            }
            const label = player && player.playing ? strings.pause : strings.play;
            this._button.update(player, strings, this._coverFile, label || '');
            this._button.setChromeless(colors.chromeless);
            this._button.card.update(player, last, strings, colors, this._coverFile);
        } else {
            this._removeButton();
        }
        if (this._cfg.media_calendar !== false) {
            this._addCalendarCard();
            if (this._calendarCard) {
                this._calendarCard.actor.visible = !!(player || last);
                this._calendarCard.update(player, last, strings, colors, this._coverFile);
            }
        } else {
            this._removeCalendarCard();
        }
    }

    _removeButton() {
        if (this._button) {
            this._button.card.setOpen(false);
            this._button.destroy();
            this._button = null;
        }
    }

    _addCalendarCard() {
        if (this._calendarCard)
            return;
        const dateMenu = Main.panel.statusArea.dateMenu;
        const list = dateMenu && dateMenu._messageList;
        const sections = list && list._sectionList;
        if (!sections)
            return; // bu GNOME sürümünde yapı farklı: kart eklenmez
        this._calendarCard = new MediaCard(this);
        sections.insert_child_at_index(this._calendarCard.actor, 0);
        this._calendarMenuId = dateMenu.menu.connect('open-state-changed',
            (menu, open) => this._calendarCard?.setOpen(open));
        // GNOME'un kendi medya bölümü gizlenir (görünür olmaya çalıştıkça yeniden gizlenir)
        const media = list._mediaSection;
        if (media) {
            this._hiddenSection = media;
            media.visible = false;
            this._sectionSignal = media.connect('notify::visible', () => {
                if (media.visible)
                    media.visible = false;
            });
        }
    }

    _removeCalendarCard() {
        if (this._calendarMenuId) {
            Main.panel.statusArea.dateMenu?.menu.disconnect(this._calendarMenuId);
            this._calendarMenuId = 0;
        }
        if (this._calendarCard) {
            this._calendarCard.destroy();
            this._calendarCard = null;
        }
        if (this._hiddenSection) {
            this._hiddenSection.disconnect(this._sectionSignal);
            this._sectionSignal = 0;
            if (typeof this._hiddenSection._sync === 'function')
                this._hiddenSection._sync();
            else
                this._hiddenSection.visible = true;
            this._hiddenSection = null;
        }
    }
}
