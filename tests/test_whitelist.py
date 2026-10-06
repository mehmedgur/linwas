"""Whitelist doğrulama testleri."""

import pytest

from linwas.core.whitelist import ValidationError, validate


class TestPackageName:
    def test_valid(self):
        assert validate("package.install", {"name": "vlc"}) == {"name": "vlc"}

    def test_valid_with_plus(self):
        assert validate("package.install", {"name": "g++"}) == {"name": "g++"}

    def test_valid_with_dot(self):
        assert validate("package.install", {"name": "python3.11"}) == {"name": "python3.11"}

    def test_single_char_invalid(self):
        with pytest.raises(ValidationError):
            validate("package.install", {"name": "a"})

    def test_uppercase_invalid(self):
        with pytest.raises(ValidationError):
            validate("package.install", {"name": "VLC"})

    def test_space_invalid(self):
        with pytest.raises(ValidationError):
            validate("package.install", {"name": "vim && rm -rf /"})

    def test_semicolon_invalid(self):
        with pytest.raises(ValidationError):
            validate("package.install", {"name": "vlc;bash"})


class TestServiceName:
    def test_valid(self):
        p = validate("service.enable", {"name": "apache2"})
        assert p["name"] == "apache2"

    def test_valid_with_at(self):
        p = validate("service.enable", {"name": "getty@tty1.service"})
        assert p["name"] == "getty@tty1.service"

    def test_shell_metachar_invalid(self):
        with pytest.raises(ValidationError):
            validate("service.enable", {"name": "sshd; rm -rf /"})


class TestHttpsUrl:
    def test_valid(self):
        url = "https://packages.example.com/repo"
        keyring = "/usr/share/keyrings/linwas-example.gpg"
        p = validate("apt.add_key", {"url": url, "keyring_path": keyring})
        assert p["url"] == url

    def test_http_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "apt.add_key",
                {
                    "url": "http://packages.example.com/repo",
                    "keyring_path": "/usr/share/keyrings/linwas-example.gpg",
                },
            )

    def test_shell_metachar_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "apt.add_key",
                {
                    "url": "https://example.com/; rm -rf /",
                    "keyring_path": "/usr/share/keyrings/linwas-example.gpg",
                },
            )


class TestKeyringPath:
    def test_valid(self):
        p = validate(
            "apt.add_key",
            {
                "url": "https://example.com/key.gpg",
                "keyring_path": "/usr/share/keyrings/linwas-myrepo.gpg",
            },
        )
        assert p["keyring_path"] == "/usr/share/keyrings/linwas-myrepo.gpg"

    def test_wrong_dir_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "apt.add_key",
                {
                    "url": "https://example.com/key.gpg",
                    "keyring_path": "/tmp/evil.gpg",
                },
            )

    def test_no_linwas_prefix_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "apt.add_key",
                {
                    "url": "https://example.com/key.gpg",
                    "keyring_path": "/usr/share/keyrings/other.gpg",
                },
            )


class TestAptListName:
    def test_valid(self):
        p = validate(
            "apt.add_source",
            {
                "source_line": "deb https://example.com/repo jammy main",
                "list_name": "linwas-example.list",
            },
        )
        assert p["list_name"] == "linwas-example.list"

    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "apt.add_source",
                {
                    "source_line": "deb https://example.com/repo jammy main",
                    "list_name": "../etc/cron.d/evil.list",
                },
            )

    def test_no_linwas_prefix_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "apt.add_source",
                {
                    "source_line": "deb https://example.com/repo jammy main",
                    "list_name": "other.list",
                },
            )


class TestAptSourceLine:
    def test_valid(self):
        line = "deb https://dl.google.com/linux/chrome/deb/ stable main"
        p = validate(
            "apt.add_source",
            {
                "source_line": line,
                "list_name": "linwas-chrome.list",
            },
        )
        assert p["source_line"] == line

    def test_http_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "apt.add_source",
                {
                    "source_line": "deb http://evil.com/repo jammy main",
                    "list_name": "linwas-evil.list",
                },
            )


class TestDebPath:
    def test_valid(self):
        p = validate("deb.install", {"path": "/home/user/Downloads/app.deb"})
        assert p["path"] == "/home/user/Downloads/app.deb"

    def test_relative_rejected(self):
        with pytest.raises(ValidationError):
            validate("deb.install", {"path": "app.deb"})

    def test_traversal_rejected(self):
        with pytest.raises(ValidationError):
            validate("deb.install", {"path": "/home/../etc/passwd.deb"})

    def test_wrong_extension_rejected(self):
        with pytest.raises(ValidationError):
            validate("deb.install", {"path": "/tmp/evil.sh"})


class TestAllowedSystemPath:
    def test_valid_etc(self):
        p = validate(
            "file.write_text",
            {
                "path": "/etc/linwas/config.conf",
                "content": "key=value",
            },
        )
        assert p["path"] == "/etc/linwas/config.conf"

    def test_etc_passwd_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "file.write_text",
                {
                    "path": "/etc/passwd",
                    "content": "evil",
                },
            )

    def test_traversal_rejected(self):
        with pytest.raises(ValidationError):
            validate(
                "file.write_text",
                {
                    "path": "/etc/linwas/../../passwd",
                    "content": "evil",
                },
            )


class TestUnknownOperation:
    def test_unknown_op_raises(self):
        with pytest.raises(ValidationError, match="Bilinmeyen işlem"):
            validate("evil.op", {})


class TestExtraParams:
    def test_extra_param_raises(self):
        with pytest.raises(ValidationError, match="bilinmeyen parametreler"):
            validate("package.install", {"name": "vlc", "extra": "evil"})


class TestMissingRequiredParam:
    def test_missing_raises(self):
        with pytest.raises(ValidationError, match="zorunlu parametre eksik"):
            validate("package.install", {})


class TestNoParams:
    def test_update_all_no_params(self):
        assert validate("package.update_all", {}) == {}
