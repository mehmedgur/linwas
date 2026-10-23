"""Sistem bağlamı: AI'ya gönderilecek sistem bilgisini toplar ve maskeler.

Kullanıcı her mesajda "Sistem bilgimi ekle" seçeneğiyle bağlamı gönderir;
gönderimden önce hassas veriler sanitizer ile maskelenir.
"""

from __future__ import annotations

import os
import platform

from linwas.backend.desktop import detect_desktop, detect_session_type
from linwas.backend.distro import detect_distro, evaluate_support
from linwas.core.sanitizer import sanitize


def build_context() -> str:
    """Kullanıcının sistem bilgisini metin olarak döner (maskelenmiş)."""
    distro = detect_distro()
    status = evaluate_support(distro)
    desktop = detect_desktop(os.environ)
    session = detect_session_type(os.environ) or "unknown"

    lines = [
        f"Distribution: {distro.display_name or 'unknown'}",
        f"Support status: {status.value}",
        f"Desktop: {desktop.name}",
        f"Session: {session}",
        f"Python: {platform.python_version()}",
        f"Architecture: {platform.machine()}",
    ]

    lines += _plugin_context()
    raw = "\n".join(lines)
    return sanitize(raw)


def _plugin_context() -> list[str]:
    """Etkin eklentilerin AI bağlamı (ör. donanım özeti); her eklenti bir satır JSON."""
    import json

    from linwas.core.plugins.loader import active

    loader = active()
    if loader is None:
        return []
    out = []
    for plugin in loader.plugins():
        try:
            data = plugin.ai_context()
        except Exception:  # bozuk eklenti yardımcıyı durdurmasın
            continue
        if data:
            text = json.dumps(data, ensure_ascii=False, default=str)[:4000]
            out.append(f"{plugin.meta.name}: {text}")
    return out


def build_system_prompt(include_operations: bool = True) -> str:
    """AI için sistem istemi oluşturur."""
    ops_section = ""
    if include_operations:
        from linwas.core.whitelist import OPERATIONS

        op_lines = []
        for op_id, spec in OPERATIONS.items():
            param_desc = ", ".join(f'"{p.name}": "..."' for p in spec.params if p.required)
            params_json = "{" + param_desc + "}" if param_desc else "{}"
            op_lines.append(f"- {op_id}: params={params_json} ({spec.label})")

        tag_example = (
            '<linwas_task op_id="OPERATION_ID" params=\'{"param": "value"}\'>'
            "Short label</linwas_task>"
        )
        ops_section = (
            "\n\nWhen you want to suggest a system action, append a task tag "
            "AT THE END of your response:\n"
            + tag_example
            + "\n\nAvailable operations:\n"
            + "\n".join(op_lines)
        )

    return (
        "You are Linwas AI, a helpful Linux assistant integrated into the Linwas application.\n"
        "Linwas helps users who are migrating from Windows to Linux (Debian/Ubuntu family).\n"
        "Your role: answer questions about Linux, explain differences from Windows, "
        "and suggest actions the user can apply through Linwas with one click.\n"
        "Be detailed, educational, and patient. Avoid jargon without explanation.\n"
        "Respond in the same language the user writes in." + ops_section
    )
