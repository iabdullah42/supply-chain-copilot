"""Tests for the agent loop, using a fake Claude so no API calls (and no cost) are needed."""
from types import SimpleNamespace as NS

from src.agent import MAX_STEPS, ask


class FakeClaude:
    """Plays back scripted replies: each item is ("sql", query) or ("text", answer)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        kind, value = self.script.pop(0) if self.script else ("sql", "SELECT 1")
        usage = NS(input_tokens=100, output_tokens=20)
        if kind == "sql":
            block = NS(type="tool_use", id=f"t{len(self.calls)}", name="run_sql", input={"query": value})
            return NS(stop_reason="tool_use", content=[block], usage=usage)
        return NS(stop_reason="end_turn", content=[NS(type="text", text=value)], usage=usage)


def test_query_result_is_sent_back_to_claude():
    fake = FakeClaude([("sql", "SELECT COUNT(*) AS n FROM suppliers"), ("text", "There are 12 suppliers.")])
    answer = ask("How many suppliers?", fake)
    assert answer.text == "There are 12 suppliers."
    assert answer.queries == ["SELECT COUNT(*) AS n FROM suppliers"]
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and "12" in tool_result["content"]
    assert tool_result["is_error"] is False


def test_blocked_query_is_reported_to_claude_as_an_error():
    fake = FakeClaude([("sql", "DELETE FROM purchase_orders"), ("text", "I can't change data.")])
    ask("Delete everything", fake)
    tool_result = fake.calls[1]["messages"][-1]["content"][0]
    assert tool_result["is_error"] is True


def test_tokens_are_counted_across_steps():
    fake = FakeClaude([("sql", "SELECT 1"), ("text", "done")])
    answer = ask("q", fake)
    assert (answer.input_tokens, answer.output_tokens, answer.steps) == (200, 40, 2)


def test_loop_stops_after_max_steps():
    fake = FakeClaude([])            # keeps asking for queries forever
    answer = ask("q", fake)
    assert answer.steps == MAX_STEPS
    assert answer.text.startswith("Stopped")
