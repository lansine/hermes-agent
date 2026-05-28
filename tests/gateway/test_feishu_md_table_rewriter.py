"""Unit tests for ``_rewrite_markdown_table_to_kv_list`` in feishu gateway.

Defense Line 3 of the four-line markdown-table guard (added 2026-05-27):
the rewriter detects markdown tables in outbound feishu messages and
rewrites them into ``**field**：value`` key-value paragraphs that
feishu's post renderer actually displays correctly.

These tests pin behavior on 8 scenarios — basic tables, code-block
protection, plain text early-exit, empty cells, the D-Chat real-world
case, and three boundary cases (escaped header pipe, header-only
table, and a table immediately followed by a fenced code block).
"""

import re

import pytest

from gateway.platforms.feishu import _rewrite_markdown_table_to_kv_list


_MD_TABLE_RE = re.compile(r"^\s*\|[^\n]*\|\s*\n\s*\|[-:|\s]+\|", re.MULTILINE)


class TestRewriteMarkdownTableToKvList:
    def test_basic_3x3_table_becomes_nine_kv_pairs(self):
        """3 cols × 3 body rows → 9 ``**header**：value`` entries with blank-line separators."""
        text = (
            "| 字段A | 字段B | 字段C |\n"
            "|---|---|---|\n"
            "| a1 | b1 | c1 |\n"
            "| a2 | b2 | c2 |\n"
            "| a3 | b3 | c3 |\n"
        )
        result = _rewrite_markdown_table_to_kv_list(text)

        # No table syntax should remain.
        assert "|---|" not in result
        assert not _MD_TABLE_RE.search(result)

        # All 9 KV pairs should be present.
        for header in ("字段A", "字段B", "字段C"):
            for value in ("1", "2", "3"):
                expected = f"**{header}**：{header[-1].lower()}{value}"
                assert expected in result, f"missing pair: {expected!r}"

        # Three rows → three KV paragraphs separated by blank lines.
        paragraphs = [p for p in result.split("\n\n") if p.strip()]
        assert len(paragraphs) == 3, f"expected 3 paragraphs, got {len(paragraphs)}: {paragraphs!r}"

    def test_pipes_inside_fenced_code_block_are_preserved(self):
        """Pipes inside ```...``` fences must survive verbatim — we never rewrite code."""
        text = (
            "前置说明：\n"
            "```\n"
            "| not | a | table |\n"
            "|---|---|---|\n"
            "| inside | code | block |\n"
            "```\n"
            "后置说明。\n"
        )
        result = _rewrite_markdown_table_to_kv_list(text)

        # Code block content stays exactly as written.
        assert "| not | a | table |" in result
        assert "|---|---|---|" in result
        assert "| inside | code | block |" in result
        # Make sure we did not silently inject any kv_list output.
        assert "**not**" not in result
        assert "**inside**" not in result

    def test_plain_text_without_pipe_returns_unchanged(self):
        """No ``|`` anywhere → early-exit, original string returned by identity."""
        text = "Hello world.\n这是一段普通文本，没有表格。\n第二行。"
        result = _rewrite_markdown_table_to_kv_list(text)
        assert result == text

    def test_empty_cells_render_as_field_colon_no_value(self):
        """Empty body cells produce ``**field**：`` (no orphan colon, no missing field name)."""
        text = (
            "| Name | Email | Phone |\n"
            "|---|---|---|\n"
            "| Alice |  | 555-1234 |\n"
        )
        result = _rewrite_markdown_table_to_kv_list(text)

        assert "**Name**：Alice" in result
        # Empty Email cell — field name kept, colon present, no value.
        assert "**Email**：" in result
        # And not "**Email**：Alice" or similar leak.
        assert "**Email**：Alice" not in result
        assert "**Phone**：555-1234" in result

    def test_dchat_real_world_5x2_with_emoji_and_parentheses(self):
        """D-Chat live scenario: 5 rows × 2 cols, content has emoji + parentheses.

        With column headers ``维度 / 现状`` the rewriter pairs each header with
        the cell underneath it — *not* the row's first cell — so each body row
        produces two KV lines. Spot-check that emoji + 全角 parens survive.
        """
        text = (
            "| 维度 | 现状 |\n"
            "|---|---|\n"
            "| 🚀 部署 | 已上线（生产） |\n"
            "| 📊 监控 | Grafana + Prometheus |\n"
            "| 🔐 鉴权 | OAuth2.0（仅内网） |\n"
            "| 🐛 已知问题 | 飞书 md 表格不渲染 |\n"
            "| ⏭ 下一步 | 切键值列表格式 |\n"
        )
        result = _rewrite_markdown_table_to_kv_list(text)

        assert not _MD_TABLE_RE.search(result)

        # Each body row produces two KV pairs — the column header is the key,
        # the body cell is the value. Spot-check across multiple rows that
        # emoji + 全角 parens flow through to both halves.
        assert "**维度**：🚀 部署" in result
        assert "**现状**：已上线（生产）" in result
        assert "**维度**：🔐 鉴权" in result
        assert "**现状**：OAuth2.0（仅内网）" in result
        assert "**维度**：⏭ 下一步" in result
        assert "**现状**：切键值列表格式" in result

        # Five body rows → five KV paragraphs (each paragraph is two lines).
        paragraphs = [p for p in result.split("\n\n") if p.strip()]
        assert len(paragraphs) == 5
        for para in paragraphs:
            lines = [ln for ln in para.splitlines() if ln.strip()]
            assert len(lines) == 2, f"each row should render as 2 KV lines, got {lines!r}"

    def test_header_with_escaped_pipe_does_not_crash(self):
        """Boundary: a header cell containing ``\\|`` must not raise — graceful degradation OK."""
        text = (
            "| col\\|escaped | other |\n"
            "|---|---|\n"
            "| v1 | v2 |\n"
        )
        # We don't assert exact output here; the rewriter doesn't need to
        # honor markdown's backslash-escape semantics. The contract is
        # "must not crash" — any return value is acceptable.
        result = _rewrite_markdown_table_to_kv_list(text)
        assert isinstance(result, str)

    def test_header_only_table_no_body(self):
        """Boundary: header + separator with no body rows — no markdown table syntax should leak."""
        text = "| h1 | h2 |\n|---|---|\n"
        result = _rewrite_markdown_table_to_kv_list(text)

        # Either fully erased or rewritten to nothing — but never leaks raw separators.
        assert "|---|" not in result
        assert not _MD_TABLE_RE.search(result)

    def test_table_immediately_followed_by_fenced_code_block(self):
        """Boundary: table is rewritten, code block right after stays untouched."""
        text = (
            "| 项 | 值 |\n"
            "|---|---|\n"
            "| 配置A | 1 |\n"
            "| 配置B | 2 |\n"
            "```python\n"
            "tbl = [['a', 'b'], ['c', 'd']]  # | not | a | table |\n"
            "print(tbl)\n"
            "```\n"
        )
        result = _rewrite_markdown_table_to_kv_list(text)

        # Table got converted.
        assert "**项**：配置A" in result
        assert "**值**：1" in result
        assert "**项**：配置B" in result
        assert "**值**：2" in result
        assert not _MD_TABLE_RE.search(result.split("```")[0])

        # Code block survives intact, including its literal pipes.
        assert "```python" in result
        assert "tbl = [['a', 'b'], ['c', 'd']]  # | not | a | table |" in result
        assert "print(tbl)" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
