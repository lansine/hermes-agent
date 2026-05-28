"""Unit tests for the cron platform-aware rendering-rule injection.

Defense Line 4 of the four-line markdown-table guard (added 2026-05-27):
``cron/scheduler.py:_build_job_prompt`` inspects the job's ``deliver``
field and prepends a ``[RENDERING TARGET: ...]`` directive *only* when
the cron output will land in a chat platform that mishandles markdown
tables (``feishu``/``weixin``/``wecom``/``dingtalk``). Other targets —
``telegram``, ``local``, ``origin``, missing ``deliver`` — must be
unaffected so we don't pollute prompts that don't need the warning.
"""

import pytest

from cron.scheduler import _build_job_prompt


_RENDERING_HEADER = "[RENDERING TARGET:"
_TABLE_BAN_PHRASE = "DO NOT use markdown tables"


def _make_job(deliver, prompt: str = "Generate today's report.") -> dict:
    """Minimal cron job dict — no skills, no script, just enough for the builder."""
    return {
        "id": "abcdef012345",
        "name": "test-job",
        "prompt": prompt,
        "deliver": deliver,
    }


class TestSchedulerPlatformHint:
    def test_feishu_target_injects_rendering_directive_and_table_ban(self):
        """deliver=feishu → prompt contains [RENDERING TARGET: feishu] + ban-tables rule."""
        prompt = _build_job_prompt(_make_job("feishu"))
        assert _RENDERING_HEADER in prompt
        assert "[RENDERING TARGET: feishu]" in prompt
        assert _TABLE_BAN_PHRASE in prompt
        # The original user prompt must still be present.
        assert "Generate today's report." in prompt

    def test_multi_chat_targets_combine_into_one_directive(self):
        """deliver=feishu,weixin → both platforms appear inside the same directive."""
        prompt = _build_job_prompt(_make_job("feishu,weixin"))
        assert _RENDERING_HEADER in prompt
        # The injection joins risky platforms with "/" (see scheduler.py:961).
        assert "feishu/weixin" in prompt
        assert _TABLE_BAN_PHRASE in prompt

    def test_telegram_target_does_not_inject_chat_platform_rules(self):
        """deliver=telegram → telegram renders markdown fine, no directive needed."""
        prompt = _build_job_prompt(_make_job("telegram"))
        assert _RENDERING_HEADER not in prompt
        assert _TABLE_BAN_PHRASE not in prompt
        # The base cron-execution guidance is still prepended (sanity check
        # that we built a real prompt and didn't short-circuit).
        assert "scheduled cron job" in prompt

    def test_local_only_delivery_does_not_inject_platform_rules(self):
        """deliver=local → no chat-platform delivery, no directive."""
        prompt = _build_job_prompt(_make_job("local"))
        assert _RENDERING_HEADER not in prompt
        assert _TABLE_BAN_PHRASE not in prompt
        assert "scheduled cron job" in prompt

    @pytest.mark.parametrize("deliver_value", [None, ""])
    def test_missing_or_empty_deliver_does_not_inject_platform_rules(self, deliver_value):
        """deliver=None / deliver="" both normalize to local — no directive injected."""
        prompt = _build_job_prompt(_make_job(deliver_value))
        assert _RENDERING_HEADER not in prompt
        assert _TABLE_BAN_PHRASE not in prompt
        assert "scheduled cron job" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
