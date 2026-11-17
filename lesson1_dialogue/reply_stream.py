"""Project only the top-level reply string from incomplete JSON, never metadata."""

from __future__ import annotations

import json
from .presentation import check_public_reply


def _string_prefix(raw, start):
    output, index = [], start + 1
    while index < len(raw):
        char = raw[index]
        if char == '"':
            break
        if char == "\\":
            if index + 1 >= len(raw):
                break
            end = index + (6 if raw[index + 1] == "u" else 2)
            if end > len(raw):
                break
            decoded = json.loads('"' + raw[index:end] + '"')
            if len(decoded) == 1 and 0xD800 <= ord(decoded) <= 0xDBFF:
                if end + 6 > len(raw):
                    break
                decoded = json.loads('"' + raw[index : end + 6] + '"')
                end += 6
            if any(0xD800 <= ord(item) <= 0xDFFF for item in decoded):
                raise ValueError("Invalid Unicode in streamed reply")
            output.append(decoded)
            index = end
        else:
            if ord(char) < 32:
                raise ValueError("Invalid JSON string")
            output.append(char)
            index += 1
    return "".join(output)


def reply_prefix(raw):
    decoder, index = json.JSONDecoder(), 0
    raw = raw.lstrip()
    if not raw.startswith("{"):
        return ""
    index = 1
    while index < len(raw):
        while index < len(raw) and raw[index].isspace():
            index += 1
        try:
            key, index = decoder.raw_decode(raw, index)
            while index < len(raw) and raw[index].isspace():
                index += 1
            if index >= len(raw) or raw[index] != ":":
                return ""
            index += 1
            while index < len(raw) and raw[index].isspace():
                index += 1
            if index >= len(raw):
                return ""
            if key == "reply":
                return _string_prefix(raw, index) if raw[index] == '"' else ""
            _, index = decoder.raw_decode(raw, index)
            while index < len(raw) and raw[index].isspace():
                index += 1
            if index >= len(raw) or raw[index] != ",":
                return ""
            index += 1
        except json.JSONDecodeError:
            return ""
    return ""


class ReplyProjector:
    def __init__(self):
        self.raw, self.emitted, self.published = "", "", ""

    def feed(self, delta):
        self.raw += delta
        if len(self.raw) > 64000:
            raise RuntimeError("Streamed course response exceeded the size limit.")
        prefix = reply_prefix(self.raw)[:1200]
        if not prefix.startswith(self.emitted):
            raise RuntimeError("Streamed reply changed unexpectedly.")
        self.emitted=prefix
        check_public_reply(prefix)
        # Do not expose half an internal identifier. Natural sentence boundaries
        # may be released immediately; otherwise retain a small lookahead window.
        boundary=max((prefix.rfind(c)+1 for c in '。！？\n'),default=0)
        ready=max(boundary,len(prefix)-64,len(self.published))
        addition=prefix[len(self.published):ready];self.published=prefix[:ready]
        return addition

    def finish(self):
        check_public_reply(self.emitted)
        addition=self.emitted[len(self.published):];self.published=self.emitted
        return addition
