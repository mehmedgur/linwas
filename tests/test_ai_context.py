# SPDX-FileCopyrightText: 2026 Mehmed Gürbüz and Linwas contributors
# SPDX-License-Identifier: GPL-3.0-or-later
# Additional terms (GPL-3.0 section 7): see NOTICE.md — keep this notice.
"""Sistem bağlamı ve sistem istemi testleri."""

from linwas.ai.context import build_context, build_system_prompt


def test_build_context_returns_string():
    ctx = build_context()
    assert isinstance(ctx, str)
    assert len(ctx) > 0


def test_context_contains_distribution():
    ctx = build_context()
    assert "Distribution:" in ctx


def test_context_no_sensitive_data():
    ctx = build_context()
    # Maskeleme çalışmış olmalı — Bearer, api_key vb. olmamalı
    assert "Bearer" not in ctx


def test_system_prompt_contains_instructions():
    prompt = build_system_prompt()
    assert "Linwas" in prompt
    assert "Linux" in prompt


def test_system_prompt_with_ops():
    prompt = build_system_prompt(include_operations=True)
    assert "package.install" in prompt
    assert "linwas_task" in prompt


def test_system_prompt_without_ops():
    prompt = build_system_prompt(include_operations=False)
    assert "linwas_task" not in prompt
