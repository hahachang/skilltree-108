"""技能圖共用建構器（數學／自然共用）。

把課綱條目 + 人工標註的前置關係，展開成一張通過驗證的有向無環圖：
別名合併 → 條目拆解 → 覆蓋率與指向檢查 → 環路偵測 → 以最長路徑計算 depth。

任何一項驗證失敗都直接中止。標註 300 條以上的依賴時，環路與指向錯誤幾乎
必然發生，靜默產出一張壞圖比中止昂貴得多。
"""
from __future__ import annotations

import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")


def load(name: str):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)


def save(name: str, payload) -> str:
    path = os.path.join(DATA, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    return path


def title_of(text: str, limit: int = 16) -> str:
    head = re.split(r"[：:。，；、（(]", text, maxsplit=1)[0]
    return head[:limit] if head else text[:limit]


def die(msg: str, items) -> None:
    items = list(items)
    print(f"✗ {msg}（{len(items)}）")
    for x in items[:20]:
        print("   ", x)
    sys.exit(1)


def build(raw: dict, spec: dict, *, domain: str, topics: dict,
          topic_of, tier_of, applied_of, ref_re=None) -> dict:
    """raw: {課綱編碼: 條目}；spec: alias / splits / prereq。"""
    alias, splits, prereq = spec["alias"], spec["splits"], spec["prereq"]

    canon = {}
    for a, c in alias.items():
        if a not in raw or c not in raw:
            die("別名指向不存在的課綱編碼", [f"{a} → {c}"])
        canon[a] = c

    skills: dict[str, dict] = {}
    for code, r in raw.items():
        if code in canon:
            continue
        also = [a for a, c in canon.items() if c == code]
        common = {"src": code, "also": also, "text": r["text"],
                  "topic": topic_of(r), "tier": tier_of(r),
                  "applied": applied_of(r), "domain": domain}
        if code in splits:
            for suffix, name in splits[code]:
                sid = code + suffix
                skills[sid] = dict(common, id=sid, name=name, split=True)
        else:
            skills[code] = dict(common, id=code, name=title_of(r["text"]), split=False)

    missing = sorted(set(skills) - set(prereq))
    if missing:
        die("這些技能沒有標註前置", missing)
    extra = sorted(set(prereq) - set(skills))
    if extra:
        die("prereq 的 key 不是有效技能", extra)
    bad = sorted({(k, p) for k, v in prereq.items() for p in v if p not in skills})
    if bad:
        die("前置指向不存在的技能（被拆解的母條目要指到具體子技能）", bad)

    depth, mark = {}, {}

    def resolve(node, trail):
        if mark.get(node) == "done":
            return depth[node]
        if mark.get(node) == "doing":
            die("前置關係有環路", [" → ".join(trail + [node])])
        mark[node] = "doing"
        d = 0
        for p in prereq[node]:
            d = max(d, resolve(p, trail + [node]) + 1)
        mark[node] = "done"
        depth[node] = d
        return d

    for sid in skills:
        resolve(sid, [])

    backwards = [(k, p) for k, v in prereq.items() for p in v
                 if skills[p]["tier"] > skills[k]["tier"]]
    if backwards:
        print(f"⚠ 前置的課綱年級高於本體（{len(backwards)}，請覆核是否標反）")
        for k, p in backwards[:10]:
            print(f"    {k}({skills[k]['tier']}) ← {p}({skills[p]['tier']})")

    # 課綱原文點名的其他編碼 → 延伸關聯（不當前置，只供閱讀時跳轉）
    related = []
    if ref_re is not None:
        def holder_of(code):
            code = canon.get(code, code)
            return code + splits[code][0][0] if code in splits else code
        for code, r in raw.items():
            src = holder_of(code)
            if src not in skills:
                continue
            body = r["text"] + " " + r.get("note", "")
            for ref in sorted(set(ref_re.findall(body)) - {code}):
                tgt = holder_of(ref)
                if tgt in skills and tgt != src:
                    related.append({"from": src, "to": tgt})

    order = sorted(skills, key=lambda k: depth[k])
    nxt: dict[str, list] = {}
    for sid in skills:
        for p in prereq[sid]:
            nxt.setdefault(p, []).append(sid)

    # reach：這個技能總共解鎖多少下游技能（影響範圍）
    reach: dict[str, set] = {}
    for sid in reversed(order):
        acc: set = set()
        for c in nxt.get(sid, []):
            acc.add(c)
            acc |= reach[c]
        reach[sid] = acc

    # gate：把它拿掉之後，有多少技能再也走不到（真正的必經關口）。
    # 解鎖規則是「前置全部完成」，所以可依深度順序一次掃完。
    def reachable(block):
        ok: dict[str, bool] = {}
        for sid in order:
            ok[sid] = sid != block and all(ok[p] for p in prereq[sid])
        return sum(ok.values())

    base = reachable(None)
    gate = {sid: (base - reachable(sid) - 1 if len(reach[sid]) >= 3 else 0)
            for sid in skills}

    nodes, edges = [], []
    for sid, s in sorted(skills.items(), key=lambda kv: (depth[kv[0]], kv[0])):
        nodes.append(dict(s, depth=depth[sid], reach=len(reach[sid]), gate=gate[sid]))
        for p in prereq[sid]:
            edges.append({"from": p, "to": sid, "type": "prereq"})

    return {"domain": domain, "topics": topics, "nodes": nodes,
            "edges": edges, "related": related, "max_depth": max(depth.values())}


def report(payload: dict, prereq: dict, path: str) -> None:
    layers: dict[int, int] = {}
    for n in payload["nodes"]:
        layers[n["depth"]] = layers.get(n["depth"], 0) + 1
    roots = sorted(n["id"] for n in payload["nodes"] if not prereq[n["id"]])
    applied = sum(1 for n in payload["nodes"] if n["applied"])
    hub = max(payload["nodes"], key=lambda n: n["gate"])
    print(f"  最大關口：{hub['id']} {hub['name']}（移除會斷掉 {hub['gate']} 個技能）")
    print(f"✓ {os.path.basename(path)}：{len(payload['nodes'])} 技能 / "
          f"{len(payload['edges'])} 前置邊 / {len(payload['related'])} 延伸關聯，"
          f"深度 0–{payload['max_depth']}，綜合應用 {applied} 個")
    print(f"  起點（無前置）{len(roots)} 個：{roots}")
    print("  各層技能數：" + "  ".join(f"L{k}:{layers[k]}" for k in sorted(layers)))
