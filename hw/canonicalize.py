"""Make a generated .kicad_pcb byte-reproducible.

pcbnew hands every item a FRESH random KIID and writes the file in KIID order,
so two runs of the same generator on the same inputs differ in item ORDER and
in every uuid.  That is not cosmetic: the router's own ordering follows the
file, and this board's placement measured 28 and 36 unconnected links across
two identical runs purely from it.

This rewrites, in place:
  * items whose order carries no meaning (footprints, tracks, vias, arcs,
    zones, graphics) are sorted by their own content with uuids masked out;
  * every uuid is then replaced by a uuid5 of that item's ordinal.
The header, the layer table, the setup block and the net table keep their
original order -- net order defines net codes.
"""
import re, sys, uuid

NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")   # uuid.NAMESPACE_OID
UUID_RE = re.compile(r'"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"')
SORTABLE = {"footprint", "segment", "via", "arc", "zone", "dimension", "group",
            "image", "target", "gr_line", "gr_arc", "gr_circle", "gr_rect",
            "gr_poly", "gr_curve", "gr_text", "gr_text_box", "gr_bbox"}


def _top_blocks(text):
    """(tag, start, end) for every block one level inside the root list."""
    depth = 0
    instr = False
    i = 0
    start = None
    while i < len(text):
        c = text[i]
        if instr:
            if c == "\\": i += 2; continue
            if c == '"': instr = False
        elif c == '"':
            instr = True
        elif c == "(":
            depth += 1
            if depth == 2:
                start = i
        elif c == ")":
            if depth == 2 and start is not None:
                m = re.match(r"\(([A-Za-z_0-9]+)", text[start:])
                yield (m.group(1) if m else ""), start, i + 1
                start = None
            depth -= 1
        i += 1


def canonicalize(path):
    text = open(path, encoding="utf-8").read()
    blocks = list(_top_blocks(text))
    if not blocks:
        raise SystemExit(f"{path}: no top-level blocks -- refusing to claim a "
                         f"canonicalisation that did not happen")
    head = text[:blocks[0][1]]
    tail = text[blocks[-1][2]:]
    gaps = [text[blocks[k][2]:text.index("(", blocks[k][2])] if k + 1 < len(blocks)
            else "" for k in range(len(blocks))]
    sep = "\n\t"
    fixed, movable = [], []
    for tag, s, e in blocks:
        (movable if tag in SORTABLE else fixed).append((tag, text[s:e]))
    n_sorted = len(movable)
    if not n_sorted:
        raise SystemExit(f"{path}: nothing sortable found")
    movable.sort(key=lambda t: (t[0], UUID_RE.sub('""', t[1])))
    ordered = [b for _, b in fixed] + [b for _, b in movable]
    joined = sep.join(ordered)
    k = [0]
    def sub(mo):
        k[0] += 1
        return '"%s"' % uuid.uuid5(NS, f"o2-probe/item/{k[0]}")
    joined = UUID_RE.sub(sub, joined)
    open(path, "w", encoding="utf-8").write(head + joined + tail)
    return n_sorted, k[0]


if __name__ == "__main__":
    for p in sys.argv[1:]:
        n, u = canonicalize(p)
        print(f"{p}: canonicalised {n} item(s), {u} uuid(s)")
