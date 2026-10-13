
export default class LinwasTaskbarExtension extends Extension {
    enable() {
        this._impl = new LinwasTaskbar();
        this._impl.enable();
    }

    disable() {
        this._impl.disable();
        this._impl = null;
    }
}
