# CFEMAIL_V1 (2026-10-03): decode Cloudflare-scrambled email addresses in a release.
#
# Wire pages served through Cloudflare (newswire.ca / CNW, PR Newswire, many company WordPress sites) replace every
# email address with "[email protected]" and keep the real address only in the markup, XOR-encoded:
#   <a href="/cdn-cgi/l/email-protection" class="__cf_email__" data-cfemail="HEX">[email&#160;protected]</a>
#   <a href="/cdn-cgi/l/email-protection#HEX"><span class="__cf_email__" data-cfemail="HEX">[email&#160;protected]</span></a>
# The first byte of HEX is the key; every following byte XOR the key is one character. Readers saw
# "[email protected]" where the contact address should be (Justin, 2026-10-03).
#
# decode_row(html, body, excerpt) -> (html, body, excerpt, n) puts the real address back as a mailto link in the HTML
# and, in the plain text, replaces "[email protected]" with the addresses in document order (only when the counts
# match, or every decoded address is the same). Pure functions, no I/O. Anything that does not decode to a
# plausible address is left exactly as it was.
import re

_EMAIL_OK = re.compile(r"^[A-Za-z0-9._%+'\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,24}$")
_PLACEHOLDER = re.compile(r"\[email(?:&#160;|&nbsp;| |\s)protected\]", re.I)
# the anchor form (with or without the hex in the address), whatever is inside it
_A_PROT = re.compile(r"<a\b[^>]*?href=[\"'][^\"']*?/cdn-cgi/l/email-protection(?:#([0-9a-fA-F]+))?[\"'][^>]*>(.*?)</a\s*>",
                     re.I | re.S)
# a bare element carrying the hex
_EL_CF = re.compile(r"<(span|a)\b[^>]*?data-cfemail=[\"']([0-9a-fA-F]+)[\"'][^>]*>.*?</\1\s*>", re.I | re.S)
_HEX_IN = re.compile(r"data-cfemail=[\"']([0-9a-fA-F]+)[\"']", re.I)


def cf_decode(hexs: str):
    """The address hidden in a Cloudflare hex string, or None."""
    try:
        if not hexs or len(hexs) < 4 or len(hexs) % 2:
            return None
        key = int(hexs[:2], 16)
        s = "".join(chr(int(hexs[i:i + 2], 16) ^ key) for i in range(2, len(hexs), 2))
    except ValueError:
        return None
    return s if _EMAIL_OK.match(s) else None


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _link(addr: str) -> str:
    return '<a href="mailto:%s">%s</a>' % (_esc(addr), _esc(addr))


def decode_html(html: str):
    """(html with the addresses restored, [addresses in document order])."""
    if not html or ("cdn-cgi/l/email-protection" not in html and "data-cfemail" not in html):
        return html, []
    found = []

    def a_sub(m):
        hexs = m.group(1)
        if not hexs:
            mm = _HEX_IN.search(m.group(2) or "")
            hexs = mm.group(1) if mm else None
        addr = cf_decode(hexs) if hexs else None
        if not addr:
            return m.group(0)
        found.append((m.start(), addr))
        return _link(addr)

    out = _A_PROT.sub(a_sub, html)
    if "data-cfemail" in out:
        def el_sub(m):
            addr = cf_decode(m.group(2))
            if not addr:
                return m.group(0)
            found.append((m.start() + 10 ** 9, addr))   # after the anchors; order within this pass is kept
            return _link(addr)
        out = _EL_CF.sub(el_sub, out)
    # document order: anchors and bare elements were found in two passes, so re-read the order from the result
    addrs = re.findall(r'<a href="mailto:([^"]+)">', out)
    order = [a for a in addrs if a in {x for _, x in found}]
    return out, [a.replace("&amp;", "&") for a in order]


def decode_text(text: str, addrs):
    """Plain text with each '[email protected]' replaced by the next address; unchanged unless that is unambiguous."""
    if not text or not addrs:
        return text
    hits = _PLACEHOLDER.findall(text)
    if not hits:
        return text
    uniq = set(addrs)
    if len(hits) == len(addrs):
        it = iter(addrs)
        return _PLACEHOLDER.sub(lambda m: next(it), text)
    if len(uniq) == 1:
        a = next(iter(uniq))
        return _PLACEHOLDER.sub(lambda m: a, text)
    return text


def decode_row(html, body, excerpt):
    """(html, body, excerpt, number of addresses restored)."""
    new_html, addrs = decode_html(html or "")
    if not addrs:
        return html, body, excerpt, 0
    return new_html, decode_text(body, addrs), decode_text(excerpt, addrs), len(addrs)


def _selftest() -> int:
    bad = 0

    def enc(addr, key=0x5a):
        return "%02x" % key + "".join("%02x" % (ord(c) ^ key) for c in addr)

    h1 = enc("info@example.com")
    h2 = enc("jane.doe@goldco.ca", 0x13)
    cases = [
        ('<p>Contact: <a href="/cdn-cgi/l/email-protection" class="__cf_email__" data-cfemail="%s">[email&#160;protected]</a></p>' % h1,
         '<p>Contact: <a href="mailto:info@example.com">info@example.com</a></p>', ["info@example.com"]),
        ('<p>E: <a href="/cdn-cgi/l/email-protection#%s"><span class="__cf_email__" data-cfemail="%s">[email&#160;protected]</span></a> or '
         '<span class="__cf_email__" data-cfemail="%s">[email&#160;protected]</span></p>' % (h2, h2, h1),
         '<p>E: <a href="mailto:jane.doe@goldco.ca">jane.doe@goldco.ca</a> or <a href="mailto:info@example.com">info@example.com</a></p>',
         ["jane.doe@goldco.ca", "info@example.com"]),
        ('<p>no email here</p>', '<p>no email here</p>', []),
        ('<a href="https://x.com/cdn-cgi/l/email-protection#zz">[email&#160;protected]</a>',
         '<a href="https://x.com/cdn-cgi/l/email-protection#zz">[email&#160;protected]</a>', []),
        ('<span data-cfemail="5a00">x</span>', '<span data-cfemail="5a00">x</span>', []),
    ]
    for html, want, want_addrs in cases:
        got, addrs = decode_html(html)
        if got != want or addrs != want_addrs:
            bad += 1
            print("FAIL html", html[:60], "->", got, addrs)
    t = decode_text("Write to [email protected] or [email protected].", ["a@b.co", "c@d.co"])
    if t != "Write to a@b.co or c@d.co.":
        bad += 1; print("FAIL text1", t)
    t = decode_text("x [email protected] y [email protected]", ["a@b.co"])
    if t != "x a@b.co y a@b.co":
        bad += 1; print("FAIL text2", t)
    t = decode_text("x [email protected] y [email protected] z [email protected]", ["a@b.co", "c@d.co"])
    if t != "x [email protected] y [email protected] z [email protected]":
        bad += 1; print("FAIL text3", t)
    if cf_decode(h1) != "info@example.com" or cf_decode("00") is not None or cf_decode("zz11") is not None:
        bad += 1; print("FAIL decode")
    print("cfemail self-test:", "ok" if not bad else "%d FAILED" % bad)
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if _selftest() else 0)
