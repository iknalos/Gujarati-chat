"""Filter Claude's streaming text deltas into TTS-ready sentences.

Three jobs:
1. Strip fenced code blocks (``` ... ```). Speaking English code with a
   Gujarati TTS produces gibberish.
2. Strip inline backtick spans (`like_this`).
3. Buffer text until a sentence terminator — Gujarati danda (।), period,
   question mark, exclamation mark, or a blank line — then emit the sentence.

The filter is incremental: it can be fed one token at a time and will hold
any text that *might* be part of an unfinished fence or unfinished sentence
until the next ``feed()`` resolves the ambiguity.
"""
from __future__ import annotations

import re
from typing import List

_FENCE = "```"
_TERMINATORS = set("।.?!")


class ResponseFilter:
    def __init__(self) -> None:
        self._tail = ""        # raw chars not yet decided (may end in `` or `)
        self._pending = ""     # cleaned chars after last sentence terminator
        self._in_code = False  # currently inside a ``` ... ``` block?

    # ---- Public API --------------------------------------------------------

    def feed(self, delta: str) -> List[str]:
        if not delta:
            return []
        self._tail += delta
        cleaned = self._strip_code(flush=False)
        self._pending += cleaned
        return self._split_sentences(flush=False)

    def flush(self) -> List[str]:
        cleaned = self._strip_code(flush=True)
        self._pending += cleaned
        sentences = self._split_sentences(flush=True)
        self._tail = ""
        self._pending = ""
        self._in_code = False
        return sentences

    # ---- Code-fence handling ----------------------------------------------

    def _strip_code(self, flush: bool) -> str:
        """Walk ``self._tail`` and return text guaranteed to be outside any
        fenced code block. Leaves up to two trailing backticks in ``self._tail``
        when ``flush=False`` so a future delta can complete a fence."""
        buf = self._tail
        n = len(buf)
        i = 0
        out_parts: List[str] = []
        while i < n:
            fence_at = buf.find(_FENCE, i)
            if self._in_code:
                if fence_at == -1:
                    # Drop content inside the block, but preserve trailing
                    # backticks that might complete the closing fence.
                    if not flush and buf.endswith("``"):
                        i = max(i, n - 2)
                    elif not flush and buf.endswith("`"):
                        i = max(i, n - 1)
                    else:
                        i = n
                    break
                self._in_code = False
                i = fence_at + len(_FENCE)
                continue
            # not in code
            if fence_at == -1:
                if not flush and buf.endswith("``"):
                    safe_end = max(i, n - 2)
                elif not flush and buf.endswith("`"):
                    safe_end = max(i, n - 1)
                else:
                    safe_end = n
                out_parts.append(buf[i:safe_end])
                i = safe_end
                break
            out_parts.append(buf[i:fence_at])
            self._in_code = True
            i = fence_at + len(_FENCE)
        self._tail = "" if flush else buf[i:]
        return "".join(out_parts)

    # ---- Sentence splitting ------------------------------------------------

    def _split_sentences(self, flush: bool) -> List[str]:
        text = self._strip_inline(self._pending)
        out: List[str] = []
        start = 0
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch in _TERMINATORS:
                end = i + 1
                while end < n and text[end] in " \t\n\r":
                    end += 1
                piece = text[start:end].strip()
                if piece:
                    out.append(piece)
                start = end
                i = end
                continue
            if ch in "\n\r":
                run_end = i
                while run_end < n and text[run_end] in "\n\r":
                    run_end += 1
                if (run_end - i) >= 2 or flush:
                    piece = text[start:i].strip()
                    if piece:
                        out.append(piece)
                    start = run_end
                    i = run_end
                    continue
                i = run_end
                continue
            i += 1
        if flush:
            piece = text[start:].strip()
            if piece:
                out.append(piece)
            self._pending = ""
        else:
            self._pending = text[start:]
        return out

    @staticmethod
    def _strip_inline(text: str) -> str:
        # Drop `inline backtick` spans entirely. Leaves unmatched single ` alone
        # so we can still match it when the closing backtick arrives later.
        return re.sub(r"`[^`\n]*`", "", text)
