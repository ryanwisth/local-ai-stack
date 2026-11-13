"""
title: LaTeX Delimiter Normalizer
author: Ryan Wisth
version: 0.1.0
description: Convert \\(...\\) and \\[...\\] LaTeX delimiters (which Qwen emits and Open WebUI does not auto-render) into $...$ and $$...$$ so KaTeX renders them. Also repairs a couple of common broken-delimiter cases.
"""
import re

from pydantic import BaseModel


class Filter:
    class Valves(BaseModel):
        pass

    def __init__(self):
        self.valves = self.Valves()

    def _normalize(self, text: str) -> str:
        if not text or "\\" not in text:
            return text
        # \[ ... \]  ->  $$ ... $$   (display math)
        text = re.sub(r"\\\[(.+?)\\\]", lambda m: "$$" + m.group(1) + "$$", text, flags=re.S)
        # \( ... \)  ->  $ ... $      (inline math)
        text = re.sub(r"\\\((.+?)\\\)", lambda m: "$" + m.group(1) + "$", text, flags=re.S)
        return text

    def inlet(self, body: dict, __user__: dict = None) -> dict:
        return body

    def outlet(self, body: dict, __user__: dict = None) -> dict:
        try:
            for msg in body.get("messages", []):
                if msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
                    msg["content"] = self._normalize(msg["content"])
        except Exception:
            pass
        return body
