"""Eklenti yükleyici testleri."""

from linwas.core.plugins import (
    GuideEntry,
    OnboardingStep,
    PageSpec,
    PluginBase,
    PluginMeta,
    ScanCheck,
    TaskTypeSpec,
    TroubleshootingCard,
)
from linwas.core.plugins.loader import PluginLoader


class GoodPlugin(PluginBase):
    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(id="test.good", name="Good Plugin", version="1.0.0")

    def pages(self):
        return [PageSpec(id="test.page", label="Test Page")]

    def task_types(self):
        return [TaskTypeSpec(op_id="package.install", label="Install")]

    def scan_checks(self):
        return [ScanCheck(id="test.check", label="Test Check")]

    def troubleshooting_cards(self):
        return [TroubleshootingCard(id="test.card", symptom="Something wrong")]

    def guide_entries(self):
        return [GuideEntry(keywords=["test"], label="Test")]

    def onboarding_steps(self):
        return [OnboardingStep(id="test.step", label="Test Step")]


class WrongApiPlugin(PluginBase):
    @property
    def meta(self) -> PluginMeta:
        return PluginMeta(id="test.bad_api", name="Bad API", version="1.0.0", api_version="99")


class BrokenPlugin(PluginBase):
    @property
    def meta(self) -> PluginMeta:
        raise RuntimeError("meta kırık")


class NotAPlugin:
    pass


class TestPluginLoader:
    def test_load_class_good(self):
        loader = PluginLoader()
        plugin = loader.load_class(GoodPlugin)
        assert plugin is not None
        assert plugin.meta.id == "test.good"

    def test_load_class_wrong_api_returns_none(self):
        loader = PluginLoader()
        result = loader.load_class(WrongApiPlugin)
        assert result is None

    def test_load_class_broken_returns_none(self):
        loader = PluginLoader()
        result = loader.load_class(BrokenPlugin)
        assert result is None

    def test_plugins_list(self):
        loader = PluginLoader()
        loader.load_class(GoodPlugin)
        assert len(loader.plugins()) == 1

    def test_errors_list_wrong_api(self):
        loader = PluginLoader()
        loader.load_class(WrongApiPlugin)
        assert loader.errors() == []  # load_class hata listesine eklemez, None döner

    def test_discover_no_entry_points(self):
        # Kurulu linwas.plugins entry point yoksa discover boş çalışmalı
        loader = PluginLoader()
        loader.discover()
        # Hata fırlatmamalı; kurulu eklenti yoksa boş liste
        assert isinstance(loader.plugins(), list)


class TestPluginGates:
    def test_pages_gate(self):
        p = GoodPlugin()
        pages = p.pages()
        assert len(pages) == 1
        assert pages[0].id == "test.page"

    def test_task_types_gate(self):
        p = GoodPlugin()
        assert p.task_types()[0].op_id == "package.install"

    def test_defaults_empty(self):
        # GoodPlugin zaten dolduruyor ama PluginBase varsayılanları test et
        class MinimalPlugin(PluginBase):
            @property
            def meta(self):
                return PluginMeta(id="minimal", name="Minimal", version="0.1.0")

        p = MinimalPlugin()
        assert p.whitelist_proposals() == []
        assert p.ai_context() == {}
