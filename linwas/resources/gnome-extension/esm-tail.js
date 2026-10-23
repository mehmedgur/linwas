
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
