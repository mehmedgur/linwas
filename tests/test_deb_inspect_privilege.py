# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
""".deb risk analizi ve root helper istemcisi testleri (gerçek root/pkexec gerekmez)."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from linwas.backend import deb_inspect
from linwas.core import privilege
from linwas.core.tasks import Task, TaskStep

# --- deb_inspect: ayrıştırıcılar ---


def test_parse_fields_joins_continuation_lines():
    text = "Package: vlc\nVersion: 3.0\nDescription: player\n more text\n"
    f = deb_inspect.parse_fields(text)
    assert f["Package"] == "vlc" and f["Description"] == "player\nmore text"


def test_parse_info_scripts():
    text = (
        " new Debian package, version 2.0.\n"
        "     500 bytes,    20 lines   *  postinst   #!/bin/sh\n"
        "     120 bytes,     5 lines      control\n"
        "      80 bytes,     3 lines   *  prerm      #!/bin/sh\n"
    )
    assert deb_inspect.parse_info_scripts(text) == ["postinst", "prerm"]


def test_parse_contents_and_flags():
    text = (
        "drwxr-xr-x root/root         0 2026-01-01 00:00 ./etc/\n"
        "-rw-r--r-- root/root        90 2026-01-01 00:00 ./etc/apt/sources.list.d/x.list\n"
        "-rw-r--r-- root/root        90 2026-01-01 00:00 ./usr/bin/app\n"
        "lrwxrwxrwx root/root         0 2026-01-01 00:00 ./lib/systemd/system/a.service -> b\n"
    )
    paths = deb_inspect.parse_contents(text)
    assert paths == ["etc/apt/sources.list.d/x.list", "usr/bin/app", "lib/systemd/system/a.service"]
    assert deb_inspect.flag_paths(paths) == {
        "repo": ["/etc/apt/sources.list.d/x.list"],
        "service": ["/lib/systemd/system/a.service"],
    }


def test_risk_levels():
    info = deb_inspect.DebInfo(path="x")
    assert info.risk == "low"
    info.reasons = ["scripts"]
    assert info.risk == "medium"
    info.reasons = ["scripts", "repo"]
    assert info.risk == "high"


def test_inspect_rejects_non_deb(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    assert deb_inspect.inspect(f).error == "not a .deb file"


@pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="dpkg-deb yok")
def test_inspect_real_package(tmp_path: Path, monkeypatch):
    root = tmp_path / "pkg"
    (root / "DEBIAN").mkdir(parents=True)
    (root / "DEBIAN" / "control").write_text(
        "Package: demo\nVersion: 1.0\nArchitecture: all\nMaintainer: x <x@x>\n"
        "Depends: libc6\nDescription: demo pkg\n long text\n"
    )
    postinst = root / "DEBIAN" / "postinst"
    postinst.write_text("#!/bin/sh\nexit 0\n")
    postinst.chmod(0o755)
    (root / "usr/share/keyrings").mkdir(parents=True)
    (root / "usr/share/keyrings/demo.gpg").write_bytes(b"k")
    deb = tmp_path / "demo.deb"
    subprocess.run(
        ["dpkg-deb", "--root-owner-group", "-b", str(root), str(deb)],
        check=True,
        capture_output=True,
    )
    # Depo sorgusu sistemden bağımsız olsun
    monkeypatch.setattr(deb_inspect, "_policy_candidate", lambda pkg: ("", "1.1"))

    info = deb_inspect.inspect(deb)
    assert info.error == ""
    assert (info.package, info.version, info.description) == ("demo", "1.0", "demo pkg")
    assert info.scripts == ["postinst"]
    assert info.flagged_files == {"repo": ["/usr/share/keyrings/demo.gpg"]}
    assert set(info.reasons) == {"repo", "scripts"} and info.risk == "high"
    assert info.repo_version == "1.1"


# --- privilege: sahte helper ile ---

_FAKE_HELPER = """
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    if req["params"].get("name") == "bad":
        print(json.dumps({"seq": req["seq"], "status": "error", "message": "boom"}))
        sys.exit(3)
    print("gürültü satırı")
    print(json.dumps({"seq": req["seq"], "status": "ok", "message": "", "progress": 1.0}))
"""


@pytest.fixture
def fake_helper(tmp_path: Path, monkeypatch):
    script = tmp_path / "helper.py"
    script.write_text(_FAKE_HELPER, encoding="utf-8")
    monkeypatch.setattr(privilege.shutil, "which", lambda name: "/usr/bin/pkexec")
    monkeypatch.setattr(privilege, "_helper_cmd", lambda: [sys.executable, str(script)])


def _task(*names: str) -> Task:
    return Task(
        label="t", steps=[TaskStep(op_id="package.install", params={"name": n}) for n in names]
    )


def test_helper_cmd_dev_mode(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(privilege, "_INSTALLED_HELPER", tmp_path / "yok")
    assert privilege._helper_cmd() == ["pkexec", sys.executable, "-m", "linwas.core.helper"]
    installed = tmp_path / "linwas-helper"
    installed.write_text("")
    monkeypatch.setattr(privilege, "_INSTALLED_HELPER", installed)
    assert privilege._helper_cmd() == ["pkexec", str(installed)]


def test_run_task_success(fake_helper):
    events = []
    responses = privilege.run_task(_task("vlc", "gimp"), on_progress=events.append)
    assert [r.status for r in responses] == ["ok", "ok"]
    assert [e.step_index for e in events] == [0, 1] and all(e.done for e in events)


def test_run_task_failure_raises(fake_helper):
    with pytest.raises(privilege.HelperError, match="boom"):
        privilege.run_task(_task("vlc", "bad"))


def test_iter_task_reports_error(fake_helper):
    events = list(privilege.iter_task(_task("bad")))
    assert events[-1].done and "boom" in events[-1].error


def test_run_task_without_pkexec(monkeypatch):
    monkeypatch.setattr(privilege.shutil, "which", lambda name: None)
    with pytest.raises(privilege.HelperError, match="pkexec"):
        privilege.run_task(_task("vlc"))


def test_requests_are_json_lines(fake_helper, tmp_path: Path, monkeypatch):
    log = tmp_path / "req.log"
    script = tmp_path / "echo.py"
    script.write_text(
        f"import sys\nopen({str(log)!r}, 'w').write(sys.stdin.read())\n", encoding="utf-8"
    )
    monkeypatch.setattr(privilege, "_helper_cmd", lambda: [sys.executable, str(script)])
    privilege.run_task(_task("vlc"))
    req = json.loads(log.read_text().splitlines()[0])
    assert req == {"seq": 0, "op_id": "package.install", "params": {"name": "vlc"}}
