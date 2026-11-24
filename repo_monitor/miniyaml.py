"""YAML-läsning för GitHub issue forms.

Använder PyYAML om det finns installerat. Annars används en liten inbyggd tolk
som klarar den delmängd av YAML som issue forms och config.yml använder:
mappningar, listor, listor av mappningar, block-strängar (| och >),
citerade strängar, inline-listor ([a, b]), true/false, tal och null.
"""

from __future__ import annotations

import json
import re


class YamlError(ValueError):
    pass


def load(text: str):
    try:
        import yaml  # type: ignore
    except ImportError:
        return mini_load(text)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:  # pragma: no cover - beror på PyYAML
        raise YamlError(str(exc)) from exc


def mini_load(text: str):
    return _Parser(text).parse()


def _strip_comment(s: str) -> str:
    quote = None
    for i, ch in enumerate(s):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def _split_flow(s: str) -> list[str]:
    parts, depth, quote, cur = [], 0, None, ""
    for ch in s:
        if quote:
            cur += ch
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _scalar(s: str):
    s = _strip_comment(s.strip())
    if s == "":
        return None
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return s[1:-1]
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        return s[1:-1].replace("''", "'")
    if s.startswith("[") and s.endswith("]"):
        return [_scalar(p) for p in _split_flow(s[1:-1])]
    if s.startswith("{") and s.endswith("}"):
        out = {}
        for p in _split_flow(s[1:-1]):
            k, _, v = p.partition(":")
            out[str(_scalar(k))] = _scalar(v)
        return out
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def _split_key(content: str):
    """'key: value' -> ('key', 'value'); None om raden inte är en nyckel."""
    quote = None
    for i, ch in enumerate(content):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"') and i == 0:
            quote = ch
            continue
        if ch == ":" and (i + 1 == len(content) or content[i + 1] in " \t"):
            key = content[:i].strip()
            return str(_scalar(key)) if key[:1] in ("'", '"') else key, content[i + 1:].strip()
    return None


class _Parser:
    def __init__(self, text: str):
        self.lines = text.replace("\t", "    ").splitlines()
        self.i = 0

    @staticmethod
    def _indent(line: str) -> int:
        return len(line) - len(line.lstrip(" "))

    def _peek(self):
        """Nästa betydelsefulla rad (hoppar över tomma rader och kommentarer)."""
        while self.i < len(self.lines):
            s = self.lines[self.i].strip()
            if s == "" or s.startswith("#") or s in ("---", "..."):
                self.i += 1
                continue
            return self.lines[self.i]
        return None

    def parse(self):
        line = self._peek()
        if line is None:
            return None
        value = self._block(self._indent(line))
        if self._peek() is not None:
            raise YamlError(f"Oväntad rad {self.i + 1}: {self.lines[self.i].strip()}")
        return value

    def _block(self, ind):
        line = self._peek()
        s = line.strip()
        if s == "-" or s.startswith("- "):
            return self._seq(ind)
        if _split_key(s) is not None:
            return self._map(ind)
        self.i += 1
        return _scalar(s)

    def _value_after_key(self, ind, rest):
        rest = _strip_comment(rest)
        if rest[:1] in ("|", ">"):
            return self._block_scalar(ind, rest)
        if rest != "":
            return _scalar(rest)
        nxt = self._peek()
        if nxt is None:
            return None
        nind = self._indent(nxt)
        ns = nxt.strip()
        if nind > ind:
            return self._block(nind)
        if nind == ind and (ns == "-" or ns.startswith("- ")):
            return self._seq(ind)
        return None

    def _map(self, ind):
        out = {}
        while True:
            line = self._peek()
            if line is None or self._indent(line) != ind:
                break
            s = line.strip()
            if s == "-" or s.startswith("- "):
                break
            kv = _split_key(s)
            if kv is None:
                raise YamlError(f"Kunde inte tolka rad {self.i + 1}: {s}")
            key, rest = kv
            self.i += 1
            out[key] = self._value_after_key(ind, rest)
        return out

    def _seq(self, ind):
        out = []
        while True:
            line = self._peek()
            if line is None or self._indent(line) != ind:
                break
            s = line.strip()
            if not (s == "-" or s.startswith("- ")):
                break
            content = s[1:].lstrip()
            col = ind + (len(s) - len(content))
            if content == "":
                self.i += 1
                nxt = self._peek()
                out.append(self._block(self._indent(nxt)) if nxt and self._indent(nxt) > ind else None)
            elif _split_key(content) is not None and not content.startswith(("[", "{")):
                self.lines[self.i] = " " * col + content
                out.append(self._map(col))
            else:
                self.i += 1
                if content[:1] in ("|", ">"):
                    out.append(self._block_scalar(ind, content))
                else:
                    out.append(_scalar(content))
        return out

    def _block_scalar(self, parent_ind, header):
        style = header[0]
        chomp = header[1:2]
        raw = []
        while self.i < len(self.lines):
            line = self.lines[self.i]
            if line.strip() == "" or self._indent(line) > parent_ind:
                raw.append(line)
                self.i += 1
            else:
                break
        while raw and raw[-1].strip() == "":
            raw.pop()
        if not raw:
            return ""
        bind = min(self._indent(l) for l in raw if l.strip())
        lines = [l[bind:] if l.strip() else "" for l in raw]
        if style == "|":
            text = "\n".join(lines)
        else:
            text, para = "", []
            for l in lines:
                if l == "":
                    text += " ".join(para) + "\n"
                    para = []
                else:
                    para.append(l)
            text += " ".join(para)
        return text if chomp == "-" else text + "\n"
