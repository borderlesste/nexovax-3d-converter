"""Herramienta de desarrollo: envuelve con tr("...") los literales de texto visibles de un módulo.

Uso:  python tools/i18n_wrap.py u3dc/ui/main_window.py [...]
Respeta docstrings, identificadores (minúsculas sin espacios), hojas de estilo, textos ya envueltos
y concatenaciones implícitas ("a" "b"). Las cadenas f"" se convierten a mano: tr("… {x} …", x=…).
"""
import io
import re
import sys
import tokenize

SKIP_RE = re.compile(r"^[a-z0-9_.\-/\\:|*]*$")
IGNORE = re.compile(r"^(Ctrl|F\d+$|Delete$|Segoe|Fusion$|PNG$|JPEG$|MDTV|APPDATA$|U3DC_|#)")
SKIP_FUNCS = {"tr", "tr_msg", "icon", "getattr", "hasattr", "setObjectName", "setProperty", "value", "setValue",
              "QKeySequence", "environ", "get", "findData", "startswith", "endswith"}
SKIP_TOK = (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT)


def is_ui_text(s: str) -> bool:
    if not re.search(r"[A-Za-zÀ-ÿ]", s):
        return False
    if SKIP_RE.match(s) or IGNORE.match(s):
        return False
    if any(k in s for k in ("{", ";", "font-", "rgba", "QFrame", "QPushButton", "<svg", "http", "%H")):
        return False
    return True


def wrap(path: str) -> int:
    src = open(path, encoding="utf-8").read()
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    lines = src.splitlines(keepends=True)
    offs = [0]
    for l in lines:
        offs.append(offs[-1] + len(l))
    pos = lambda rc: offs[rc[0] - 1] + rc[1]  # noqa: E731
    edits, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t.type != tokenize.STRING:
            i += 1
            continue
        group = [i]
        j = i + 1
        while j < len(toks) and (toks[j].type == tokenize.STRING or toks[j].type in (tokenize.NL, tokenize.COMMENT)):
            if toks[j].type == tokenize.STRING:
                group.append(j)
            j += 1
        i = j
        texts = [toks[g].string for g in group]
        if any(re.match(r"^[A-Za-z]+", s) for s in texts) or any(s.startswith(("'''", '"""')) for s in texts):
            continue
        k = group[0] - 1
        while k >= 0 and toks[k].type in SKIP_TOK:
            k -= 1
        if k < 0 or toks[k].type == tokenize.NEWLINE or toks[k].string in (":",) and toks[k - 1].string == ")":
            continue                                    # docstring / sentencia suelta
        nxt = toks[j] if j < len(toks) else None
        if toks[k].type == getattr(tokenize, "FSTRING_END", -1) or (nxt is not None and nxt.type == getattr(tokenize, "FSTRING_START", -1)):
            continue                                    # concatenada con una cadena f""
        if toks[k].string == "(" and k > 0 and toks[k - 1].string in SKIP_FUNCS:
            continue
        if toks[k].string == "[" :                      # índices tipo x["clave"]
            continue
        val = "".join(eval(s) for s in texts)
        if not is_ui_text(val):
            continue
        s0, e0 = pos(toks[group[0]].start), pos(toks[group[-1]].end)
        edits.append((s0, e0, "tr(" + src[s0:e0] + ")"))
    for s, e, rep in reversed(edits):
        src = src[:s] + rep + src[e:]
    if edits and "import tr" not in src:
        rel = "..i18n" if ("/ui/" in path.replace("\\", "/") or "/core/" in path.replace("\\", "/")) else ".i18n"
        src = re.sub(r"(\nfrom __future__ import annotations\n)", rf"\1\nfrom {rel} import tr, tr_msg\n", src, count=1)
    open(path, "w", encoding="utf-8", newline="").write(src)
    return len(edits)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, wrap(p))
