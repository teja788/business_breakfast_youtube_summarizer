"""One-time: copy the fuller per-stock comment from each <date>.kutumba_rao.md
into a `detail` field on the matching recommendation in <date>.buys.json."""
import json
import re
from pathlib import Path

KDIR = Path("output/kutumba_rao")


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def parse_bullets(md_path):
    """Return [(stock_name, detail_text)] from the '## Stock calls' section."""
    out = []
    if not md_path.exists():
        return out
    in_section = False
    for line in md_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_section = line.strip().lower().startswith("## stock calls")
            continue
        if line.startswith("### "):
            in_section = False
            continue
        if in_section:
            # **Stock** [optional (viewer …) context] — full comment
            m = re.match(r"^-\s*\*\*(.+?)\*\*[^—]*—\s*(.+)$", line)
            if m:
                name = m.group(1).strip()
                detail = m.group(2).strip()
                detail = detail.replace("**", "")          # drop md bold
                detail = re.sub(r"\s+", " ", detail).strip()
                out.append((name, detail))
    return out


for buys in sorted(KDIR.glob("*.buys.json")):
    md = Path(str(buys).replace(".buys.json", ".kutumba_rao.md"))
    bullets = parse_bullets(md)
    bykey = {norm(n): d for n, d in bullets}
    doc = json.loads(buys.read_text(encoding="utf-8"))
    recs = doc.get("recommendations") or doc.get("buys") or []
    matched = 0
    for r in recs:
        k = norm(r.get("stock"))
        detail = bykey.get(k)
        if not detail:                                     # fuzzy: prefix either way
            for bk, bd in bykey.items():
                if bk and (bk.startswith(k) or k.startswith(bk)):
                    detail = bd
                    break
        if detail:
            r["detail"] = detail
            matched += 1
    buys.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{buys.name}: {matched}/{len(recs)} matched")
