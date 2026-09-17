"""驗證自然↔數學的跨領域前置，輸出 data/graph_cross.json。

課綱兩份文件互不引用，這些邊全部是人工判定，所以驗證要嚴：編碼必須存在、
不可重複、方向一律是數學→自然，並檢查數學前置是否排在自然條目之後
（那代表標錯，或代表課綱本身就有順序衝突，兩種都要人工覆核）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skill_builder import die, load, save  # noqa: E402

# 自然的學習階段對應年級上緣，用來跟數學的年級比較
STAGE_TIER = {"Ⅱ": 4, "Ⅲ": 6, "Ⅳ": 9, "Ⅴc": 12, "Ⅴa": 12}


def main() -> None:
    spec = load("cross_links.json")["links"]
    nat = {n["id"]: n for n in load("graph_natural.json")["nodes"]}
    mat = {n["id"]: n for n in load("graph_math.json")["nodes"]}

    bad = [f"{e['nat']} ← {e['math']}" for e in spec
           if e["nat"] not in nat or e["math"] not in mat]
    if bad:
        die("跨領域連結指向不存在的技能", bad)
    dup = [k for k in {(e["nat"], e["math"]) for e in spec}
           if sum(1 for e in spec if (e["nat"], e["math"]) == k) > 1]
    if dup:
        die("重複的跨領域連結", dup)
    missing_why = [e["nat"] for e in spec if not e.get("why")]
    if missing_why:
        die("跨領域連結缺少理由（人工判定的邊一定要寫清楚依據）", missing_why)

    late = [(e["nat"], e["math"]) for e in spec
            if mat[e["math"]]["grade"] > STAGE_TIER.get(nat[e["nat"]]["stage"], 12)]
    if late:
        print(f"⚠ 數學前置排在自然條目之後（{len(late)}，請覆核）")
        for n, m in late[:10]:
            print(f"    {n}（{nat[n]['stage']}）← {m}（{mat[m]['grade']}年級）")

    links = [{"nat": e["nat"], "math": e["math"], "why": e["why"],
              "nat_name": nat[e["nat"]]["name"], "math_name": mat[e["math"]]["name"]}
             for e in spec]
    path = save("graph_cross.json", {"links": links})

    by_subject: dict[str, int] = {}
    for e in links:
        s = nat[e["nat"]]["subject"]
        by_subject[s] = by_subject.get(s, 0) + 1
    hot: dict[str, int] = {}
    for e in links:
        hot[e["math"]] = hot.get(e["math"], 0) + 1
    top = sorted(hot.items(), key=lambda kv: -kv[1])[:5]
    print(f"✓ {os.path.basename(path)}：{len(links)} 條跨領域前置，"
          f"涉及 {len(set(e['nat'] for e in links))} 個自然技能、"
          f"{len(set(e['math'] for e in links))} 個數學技能")
    print("  依自然科的科目：" + "  ".join(f"{k}:{v}" for k, v in
                                    sorted(by_subject.items(), key=lambda kv: -kv[1])))
    print("  最常被需要的數學：" + "  ".join(
        f"{mat[k]['name']}({v})" for k, v in top))


if __name__ == "__main__":
    main()
