"""Project only the top-level reply string from incomplete JSON, never metadata."""
from __future__ import annotations

import json


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
                decoded = json.loads('"' + raw[index:end + 6] + '"')
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
        self.raw, self.emitted = "", ""

    def feed(self, delta):
        self.raw += delta
        if len(self.raw) > 64000:
            raise RuntimeError("Streamed course response exceeded the size limit.")
        prefix = reply_prefix(self.raw)[:1200]
        if not prefix.startswith(self.emitted):
            raise RuntimeError("Streamed reply changed unexpectedly.")
        addition, self.emitted = prefix[len(self.emitted):], prefix
        return addition
