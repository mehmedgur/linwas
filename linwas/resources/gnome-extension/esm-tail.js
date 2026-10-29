// SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.

export default class LinwasWindowGroupsExtension extends Extension {
    enable() {
        this._impl = new LinwasWindowGroups();
        this._impl.enable();
    }

    disable() {
        this._impl.disable();
        this._impl = null;
    }
}
