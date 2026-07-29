"""The advisor's conversation memory.

The point of this module is that the thread outlives the claude CLI session, so
these tests care about two things: turns persist and stay bounded, and the recap
actually re-establishes the conversation when the session is gone.
"""
from __future__ import annotations

from app.services import chat


def test_key_matches_the_advisor_session_convention():
    # These keys are shared with the advisor's session and history maps. If they
    # drift, a follow-up resumes the wrong conversation — or none at all.
    assert chat.key_for("portfolio", None) == "portfolio:brief"
    assert chat.key_for("portfolio", "NVDA") == "portfolio:brief"
    assert chat.key_for("strategy", None) == "strategy:plan"
    assert chat.key_for("stock", "nvda") == "stock:NVDA"
    assert chat.key_for("breakout", "AMD") == "breakout:AMD"


def test_records_and_returns_turns_oldest_first():
    key = chat.key_for("portfolio", None)
    chat.record(key, "first question", "first answer", ["a"])
    chat.record(key, "second question", "second answer", ["b", "c"])

    turns = chat.recent(key)
    assert [t["q"] for t in turns] == ["first question", "second question"]
    assert turns[1]["points"] == ["b", "c"]
    assert turns[0]["ts"]


def test_contexts_do_not_bleed_into_each_other():
    chat.record(chat.key_for("stock", "NVDA"), "about nvda", "nvda answer")
    chat.record(chat.key_for("stock", "AMD"), "about amd", "amd answer")

    assert [t["q"] for t in chat.recent(chat.key_for("stock", "NVDA"))] == ["about nvda"]
    assert [t["q"] for t in chat.recent(chat.key_for("stock", "AMD"))] == ["about amd"]


def test_log_is_bounded():
    key = chat.key_for("stock", "CAP")
    for i in range(chat.KEEP_TURNS + 25):
        chat.record(key, f"q{i}", f"a{i}")

    turns = chat.recent(key)
    assert len(turns) == chat.KEEP_TURNS
    # The OLDEST turns are the ones dropped.
    assert turns[-1]["q"] == f"q{chat.KEEP_TURNS + 24}"
    assert turns[0]["q"] == f"q{25}"


def test_recent_respects_its_limit():
    key = chat.key_for("stock", "LIM")
    for i in range(10):
        chat.record(key, f"q{i}", f"a{i}")
    assert [t["q"] for t in chat.recent(key, 3)] == ["q7", "q8", "q9"]


def test_recap_is_empty_with_no_history():
    # No conversation means no recap block — the cold prompt must not carry an
    # empty "here is your conversation" header.
    assert chat.recap_block(chat.key_for("stock", "NONE")) == ""


def test_recap_carries_the_thread_and_forbids_reintroduction():
    key = chat.key_for("portfolio", None)
    chat.record(key, "should I sell VRT?", "Hold it, the thesis is intact.")

    block = chat.recap_block(key)
    assert "should I sell VRT?" in block
    assert "Hold it, the thesis is intact." in block
    # The instructions are the whole point: without them he restates context and
    # re-asks things you already told him.
    assert "same advisor" in block
    assert "Do not" in block and "reintroduce" in block


def test_recap_only_uses_the_most_recent_turns():
    key = chat.key_for("stock", "RCP")
    for i in range(chat.RECAP_TURNS + 6):
        chat.record(key, f"question number {i}", f"answer number {i}")

    block = chat.recap_block(key)
    assert f"question number {chat.RECAP_TURNS + 5}" in block
    assert "question number 0" not in block


def test_clear_forgets_the_conversation():
    key = chat.key_for("portfolio", None)
    chat.record(key, "q", "a")
    chat.record(key, "q2", "a2")

    assert chat.clear(key) == 2
    assert chat.recent(key) == []
    # A cleared conversation must not come back through the recap.
    assert chat.recap_block(key) == ""


def test_reset_memory_also_drops_the_conversation():
    # reset_memory exists to purge stale backward memory. If the conversation
    # survived it, the recap would hand the same stale claims straight back.
    from app.services import advisor

    key = chat.key_for("portfolio", None)
    chat.record(key, "did I act on the $191 add?", "Yes, that one is done.")
    advisor.reset_memory()

    assert chat.recent(key) == []
