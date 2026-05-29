"""Behaviour of the streaming filter that feeds IndicF5.

These tests cover the actual failure modes we expect in production:
- Claude emits tokens, not sentences. Half-words must not reach TTS.
- Claude emits English code in ``` fences. None of it must be spoken.
- Code-fence boundaries can fall on any token boundary.
- Inline backtick spans (``foo()``) must not be spoken.
- Gujarati danda (।) is a sentence terminator.
- Mid-stream partial deltas accumulate across many calls.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from response_filter import ResponseFilter


def feed_chunked(text: str, chunk_size: int):
    """Feed ``text`` through the filter in chunks of ``chunk_size``."""
    f = ResponseFilter()
    out = []
    for i in range(0, len(text), chunk_size):
        out.extend(f.feed(text[i:i + chunk_size]))
    out.extend(f.flush())
    return out


# ---- Basic sentence buffering ------------------------------------------------

def test_buffers_until_period():
    # The period at end-of-buffer is deferred (could be "main.py" continuation).
    # In the real pipeline, ClaudeBridge calls flush() on the turn_end event,
    # which is what feed_chunked simulates here.
    f = ResponseFilter()
    assert f.feed("આ એક ") == []
    assert f.feed("વાક્ય ") == []
    assert f.feed("છે.") == []
    assert f.flush() == ["આ એક વાક્ય છે."]


def test_period_followed_by_space_emits_immediately():
    f = ResponseFilter()
    assert f.feed("આ વાક્ય છે. ") == ["આ વાક્ય છે."]


def test_danda_is_a_terminator():
    out = feed_chunked("આ વાક્ય છે। બીજું વાક્ય।", 1)
    assert out == ["આ વાક્ય છે।", "બીજું વાક્ય।"]


def test_question_and_exclamation():
    out = feed_chunked("શું તમે તૈયાર છો? હા! ચલો.", 3)
    assert out == ["શું તમે તૈયાર છો?", "હા!", "ચલો."]


def test_flush_emits_trailing_unterminated():
    f = ResponseFilter()
    f.feed("incomplete tail")
    assert f.flush() == ["incomplete tail"]


def test_blank_line_acts_as_terminator():
    out = feed_chunked("first thought\n\nsecond thought", 2)
    assert out == ["first thought", "second thought"]


# ---- Code blocks ------------------------------------------------------------

def test_drops_fenced_code_block_entirely():
    src = "પહેલાં વાક્ય. ```python\nprint('hi')\nprint('bye')\n``` બીજું વાક્ય."
    out = feed_chunked(src, 4)
    assert out == ["પહેલાં વાક્ય.", "બીજું વાક્ય."]


def test_code_fence_split_across_deltas():
    # Trailing periods are deferred until next char is known; the closing
    # fence + space (or flush) is what releases them.
    f = ResponseFilter()
    assert f.feed("શરૂઆત. ``") == ["શરૂઆત."]
    assert f.feed("`bash\necho hi\n``") == []
    f.feed("` અંત.")
    assert f.flush() == ["અંત."]


def test_unterminated_code_block_swallowed_by_flush():
    # "intro." is emitted streaming; flush is silent because we're still in
    # the open code block. Combined output must contain "intro." and nothing
    # from inside the block.
    out = feed_chunked("intro. ```python\nprint(", 8)
    assert out == ["intro."]


def test_inline_backtick_span_dropped():
    out = feed_chunked("Run the `git status` command.", 5)
    assert out == ["Run the  command."]


def test_back_to_back_code_blocks():
    src = "before. ```a``` middle. ```b``` after."
    out = feed_chunked(src, 3)
    assert out == ["before.", "middle.", "after."]


# ---- Stress: arbitrary chunking -------------------------------------------

def test_invariance_across_chunk_sizes():
    src = "પ્રથમ વાક્ય. બીજું? ```code``` ત્રીજું! ચોથું."
    expected = feed_chunked(src, len(src))
    for n in (1, 2, 3, 7, 13, len(src) - 1):
        assert feed_chunked(src, n) == expected, f"chunk={n} differs"


def test_period_inside_identifier_does_not_break():
    out = feed_chunked("Open main.py to see the bug.", 3)
    assert out == ["Open main.py to see the bug."]


def test_period_decimal_does_not_break():
    out = feed_chunked("Version 1.2.3 is out.", 4)
    assert out == ["Version 1.2.3 is out."]


def test_period_with_trailing_space_still_breaks():
    out = feed_chunked("End. New start.", 2)
    assert out == ["End.", "New start."]


def test_terminator_only_pieces_not_emitted():
    # After a sentence-end, a lone "." (e.g. from sloppy concatenation) must
    # not emit as a standalone sentence.
    out = feed_chunked("first sentence? . second sentence.", 4)
    assert out == ["first sentence?", "second sentence."]


def test_multiple_terminators_collapse():
    out = feed_chunked("Hey!! What?! No.", 3)
    assert out == ["Hey!", "What?", "No."]


def test_flush_resets_state():
    f = ResponseFilter()
    f.feed("partial")
    f.flush()
    # Filter must be reusable
    f.feed("next sentence.")
    assert f.flush() == ["next sentence."]
