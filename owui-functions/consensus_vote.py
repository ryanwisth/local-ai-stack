"""
title: Multiple-Choice Consensus
author: Ryan Wisth
version: 1.0.0
description: Self-consistency voting for multiple-choice questions - fires N samples at mtplx, majority-votes the "Answer: X" letter, shows the tally and one winning explanation.
requirements: aiohttp
"""

# Open WebUI 0.11 PIPE function.
#
# Contract (read from open_webui/functions.py + utils/plugin.py, 0.11.1):
#   - frontmatter docstring above with title/author/version (parsed by
#     extract_frontmatter; the function shows up as a model named by its title).
#   - class Pipe with a pydantic Valves model (admin-editable in the UI).
#   - async def pipe(self, body, ...dunder params...) -> str  (a str is wrapped
#     into a single chat chunk for stream=True and a full message otherwise).
#   - __event_emitter__ takes {"type": "status", "data": {"description", "done"}}.
#
# Behaviour:
#   1. Take the incoming messages, append "finish with `Answer: X`" to the last
#      user turn.
#   2. Fire N identical requests at mtplx via asyncio.gather. mtplx has a serial
#      scheduler so they queue; total wall time ~ N x one sample. Progress is
#      reported through status events as each sample lands.
#   3. Extract the letter from each sample (same regex family as
#      eval/mc_eval.py: last "Answer: X", else last standalone A-E on the
#      final line).
#   4. Majority vote. Ties -> the tied letter whose explanations are longest in
#      total (most "worked"), and the tie is reported.
#   5. Return Markdown: winning letter, tally, then the full explanation of the
#      shortest winning sample that still contains "Answer:".
#
# A sample that errors or times out is recorded as a failure and does not kill
# the vote; the vote runs on whatever succeeded.

import asyncio
import json
import re
from collections import Counter
from typing import Any, Awaitable, Callable, Optional

import aiohttp
from pydantic import BaseModel, Field

# --- letter extraction (mirrors mc_eval.extract_letter) --------------------
_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_THINK_OPEN_RE = re.compile(r"<think>.*\Z", re.S)  # unterminated think block
_ANSWER_RE = re.compile(r"Answer\s*[:\-]\s*\**\(?([A-E])\)?", re.I)
_STANDALONE_RE = re.compile(r"\b([A-E])\b")

# Keys the OWUI body carries that a plain OpenAI backend must not see.
_OWUI_ONLY_KEYS = {
    "model", "messages", "stream", "metadata", "chat_id", "id", "session_id",
    "files", "tool_ids", "features", "variables", "background_tasks",
    "params", "filter_ids", "tool_servers", "user", "n", "max_tokens",
    "temperature",
}

FINISH_INSTRUCTION = (
    "Solve it, then end your reply with exactly one line of the form "
    "`Answer: X` where X is the letter."
)


def strip_think(text: str) -> str:
    """Remove <think>...</think> blocks (and a dangling open one)."""
    text = _THINK_RE.sub("", text or "")
    text = _THINK_OPEN_RE.sub("", text)
    return text.strip()


def extract_letter(text: str) -> Optional[str]:
    """Last 'Answer: X' wins; fallback = last standalone A-E on the final line."""
    t = strip_think(text)
    m = _ANSWER_RE.findall(t)
    if m:
        return m[-1].upper()
    last_line = t.splitlines()[-1] if t else ""
    m = _STANDALONE_RE.findall(last_line)
    return m[-1].upper() if m else None


def append_instruction(messages: list[dict]) -> list[dict]:
    """Return a copy of messages with FINISH_INSTRUCTION appended to the last
    user turn (handles plain-string and multimodal list content). If the last
    message isn't a user turn, add a new user message instead."""
    msgs = [dict(m) for m in messages]
    if msgs and msgs[-1].get("role") == "user":
        content = msgs[-1].get("content", "")
        if isinstance(content, list):
            content = list(content) + [{"type": "text", "text": "\n\n" + FINISH_INSTRUCTION}]
        else:
            content = f"{content}\n\n{FINISH_INSTRUCTION}"
        msgs[-1]["content"] = content
    else:
        msgs.append({"role": "user", "content": FINISH_INSTRUCTION})
    return msgs


class Pipe:
    class Valves(BaseModel):
        base_url: str = Field(
            default="http://127.0.0.1:8000/v1",
            description="OpenAI-compatible base URL of the sampling backend (mtplx).",
        )
        model: str = Field(
            default="mtplx-qwen38-27b-optimized-speed",
            description="Model id to request from the backend.",
        )
        api_key: str = Field(default="", description="Bearer token, blank for none (mtplx needs none).")
        n_samples: int = Field(default=5, ge=1, le=15, description="How many samples to vote over.")
        temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature (must be > 0 for diversity).")
        max_tokens: int = Field(default=3000, ge=64, description="max_tokens per sample.")
        timeout: int = Field(
            default=900, ge=10,
            description="Per-request timeout in seconds. mtplx queues samples serially, so this must cover ~N x one sample.",
        )
        show_all_letters: bool = Field(
            default=True,
            description="Append a compact per-sample list (letter, length, status) under the explanation.",
        )

    def __init__(self):
        self.valves = self.Valves()

    # -------------------------------------------------------------- helpers
    async def _emit(self, emitter, description: str, done: bool = False):
        """Status event; never raises (the emitter may be None under API use)."""
        if emitter is None:
            return
        try:
            await emitter({"type": "status", "data": {"description": description, "done": done}})
        except Exception:
            pass

    async def _one_sample(self, session: aiohttp.ClientSession, payload: dict, idx: int) -> dict:
        """One non-streaming chat/completions call. Returns a result dict; never raises."""
        headers = {"Content-Type": "application/json"}
        if self.valves.api_key:
            headers["Authorization"] = f"Bearer {self.valves.api_key}"
        url = self.valves.base_url.rstrip("/") + "/chat/completions"
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                raw = await resp.text()
                if resp.status != 200:
                    return {"idx": idx, "ok": False, "error": f"HTTP {resp.status}: {raw[:200]}"}
                data = json.loads(raw)
            msg = data["choices"][0].get("message", {})
            content = msg.get("content") or ""
            # mtplx returns reasoning separately; if content is empty the answer
            # may only live in the reasoning field, so fall back to it.
            if not content.strip():
                content = msg.get("reasoning_content") or msg.get("reasoning") or ""
            text = strip_think(content)
            return {
                "idx": idx,
                "ok": True,
                "text": text,
                "letter": extract_letter(text),
                "finish": data["choices"][0].get("finish_reason"),
            }
        except asyncio.TimeoutError:
            return {"idx": idx, "ok": False, "error": f"timeout after {self.valves.timeout}s"}
        except Exception as e:  # network error, bad JSON, unexpected shape
            return {"idx": idx, "ok": False, "error": f"{type(e).__name__}: {e}"}

    # ----------------------------------------------------------------- pipe
    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[dict], Awaitable[None]]] = None,
    ) -> str:
        v = self.valves
        messages = body.get("messages") or []
        if not messages:
            return "No messages received."

        # Backend payload: same messages + finish instruction; pass through any
        # harmless OpenAI params the UI set (top_p etc.), drop OWUI-only keys.
        passthrough = {k: val for k, val in body.items() if k not in _OWUI_ONLY_KEYS}
        payload = {
            **passthrough,
            "model": v.model,
            "messages": append_instruction(messages),
            "temperature": v.temperature,
            "max_tokens": v.max_tokens,
            "stream": False,
        }

        n = v.n_samples
        await self._emit(__event_emitter__, f"Firing {n} samples at {v.model} (serial queue on mtplx)...")

        results: list[dict] = []
        done_count = 0

        timeout = aiohttp.ClientTimeout(total=v.timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:

            async def run(idx: int) -> dict:
                nonlocal done_count
                r = await self._one_sample(session, payload, idx)
                done_count += 1
                tag = (r["letter"] or "?") if r["ok"] else "FAILED"
                await self._emit(__event_emitter__, f"sample {done_count}/{n} done ({tag}) ...")
                return r

            results = await asyncio.gather(*(run(i + 1) for i in range(n)))

        results = sorted(results, key=lambda r: r["idx"])
        ok = [r for r in results if r["ok"]]
        failed = [r for r in results if not r["ok"]]
        voted = [r for r in ok if r["letter"]]
        no_letter = [r for r in ok if not r["letter"]]

        if not voted:
            await self._emit(__event_emitter__, "No sample produced a letter.", done=True)
            lines = ["**No answer** - none of the samples produced an `Answer: X` line."]
            for r in failed:
                lines.append(f"- sample {r['idx']}: {r['error']}")
            for r in no_letter:
                lines.append(f"- sample {r['idx']}: finished ({r.get('finish')}) but no letter found")
            if no_letter:
                lines.append("\n---\nLast letter-less sample, for the record:\n\n" + no_letter[-1]["text"])
            return "\n".join(lines)

        # --- vote ----------------------------------------------------------
        tally = Counter(r["letter"] for r in voted)
        top = max(tally.values())
        tied = sorted(L for L, c in tally.items() if c == top)
        tie = len(tied) > 1
        if tie:
            # Tie-break: the tied letter with the most total explanation text.
            work = {L: sum(len(r["text"]) for r in voted if r["letter"] == L) for L in tied}
            winner = max(tied, key=lambda L: (work[L], -ord(L)))
        else:
            winner = tied[0]

        # Explanation: shortest winning sample that still contains 'Answer:',
        # else the shortest winning sample at all.
        winners = [r for r in voted if r["letter"] == winner]
        with_answer = [r for r in winners if _ANSWER_RE.search(r["text"])]
        pick = min(with_answer or winners, key=lambda r: len(r["text"]))

        # --- report --------------------------------------------------------
        order = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
        tally_str = "  ".join(f"{L}:{c}" for L, c in order)
        conf = f"{top}/{len(voted)}"

        out = [f"## Answer: **{winner}**", f"Votes: `{tally_str}`  (agreement {conf}, {n} requested)"]
        if tie:
            out.append(f"**Tie** between {', '.join(tied)} - broke it toward the letter with the most worked explanation ({winner}).")
        if failed or no_letter:
            bits = []
            if failed:
                bits.append(f"{len(failed)} failed")
            if no_letter:
                bits.append(f"{len(no_letter)} gave no letter")
            out.append(f"_Excluded from the vote: {', '.join(bits)}._")
        out.append("")
        out.append(f"### Explanation (sample {pick['idx']})")
        out.append(pick["text"])

        if v.show_all_letters:
            out.append("")
            out.append("<details><summary>All samples</summary>\n")
            for r in results:
                if r["ok"]:
                    out.append(f"- sample {r['idx']}: **{r['letter'] or '?'}** - {len(r['text'])} chars, finish={r.get('finish')}")
                else:
                    out.append(f"- sample {r['idx']}: FAILED - {r['error']}")
            out.append("\n</details>")

        await self._emit(__event_emitter__, f"Consensus {winner} ({tally_str})", done=True)
        return "\n".join(out)
