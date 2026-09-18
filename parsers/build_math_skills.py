"""raw_math.json + skills_math.json → data/graph_math.json（重構後的數學技能圖）。

與第一版的差別：
* 丟掉依課綱流水號自動串的 seq / stage 鏈——那是編號順序，不是知識依賴。
* 只保留人工標註的真實概念前置，另附課綱明文的編碼引用作為「延伸關聯」。
* 節點允許拆解（N-6-7 → N-6-7a/b/c），但保留 src 指回課綱原條目。
* 縱軸改用 depth（依賴圖上的最長路徑），不是年級。
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skill_builder import build, load, report, save  # noqa: E402

TOPICS = {"N": "數與量", "S": "空間與形狀", "G": "坐標幾何",
          "R": "關係", "A": "代數", "F": "函數", "D": "資料與不確定性"}
REF_RE = re.compile(r"[A-Za-z]{1,4}-[0-9]{1,2}-[0-9]{1,2}")


def is_applied(text: str) -> bool:
    """課綱裡以「解題」開頭的條目＝多個技能的綜合應用，在圖上用另一種形狀呈現。"""
    return re.split(r"[：:。]", text, maxsplit=1)[0].strip() == "解題"


def merge_official(spec: dict, skills_of_code) -> dict:
    """官方優先：課程手冊有列先備的條目就用手冊的，沒列的才用人工標註。

    手冊只列「直接先備」，而且 227 條裡只有 138 條有列；全面改用官方會讓
    其餘 89 條變成孤兒、整張圖斷開，所以是「有就用、沒有才退回人工」。

    編碼層級要對齊：手冊講的是課綱條目，我們的圖可能把一條拆成 a/b/c。
    指向被拆解的條目時取最後一個子技能（子技能之間本來就串成鏈，
    要到最後一個等於要整條都會）；被拆解條目本身的官方先備則掛在第一個。
    """
    hb = {x["code"]: x for x in load("handbook_math.json")["sections"]}
    alias, splits, mine = spec["alias"], spec["splits"], spec["prereq"]

    def last_of(code):
        code = alias.get(code, code)
        return code + splits[code][-1][0] if code in splits else code

    merged, stats = {}, {"official": 0, "mine": 0, "dropped": []}
    for sid in mine:
        src = skills_of_code(sid)
        is_first_part = sid == src or (src in splits and sid == src + splits[src][0][0])
        official = hb.get(src, {}).get("prior") or []
        if official and is_first_part:
            mapped = []
            for c in official:
                t = last_of(c)
                if t in mine and t != sid:
                    mapped.append(t)
                elif t not in mine:
                    stats["dropped"].append(f"{src} ← {c}")
            if mapped:
                merged[sid] = sorted(set(mapped))
                stats["official"] += 1
                continue
        merged[sid] = mine[sid]
        stats["mine"] += 1
    return merged, stats


def main() -> None:
    spec = load("skills_math.json")
    raw = {r["code"]: r for r in load("raw_math.json") if r["kind"] == "content"}
    # 官方優先：先把 prereq 換成合併後的版本，再交給共用建構器驗證
    def code_of(sid):
        for c in spec["splits"]:
            for suf, _ in spec["splits"][c]:
                if sid == c + suf:
                    return c
        return sid
    merged, stats = merge_official(spec, code_of)
    spec = dict(spec, prereq=merged)
    print(f"  前置來源：官方手冊 {stats['official']} 條、人工標註 {stats['mine']} 條"
          + (f"，官方指向不在部定必修的 {len(stats['dropped'])} 條已略過"
             if stats["dropped"] else ""))

    payload = build(
        raw, spec, domain="math", topics=TOPICS,
        topic_of=lambda r: r["topic_code"],
        tier_of=lambda r: r["grade"],
        applied_of=lambda r: is_applied(r["text"]),
        ref_re=REF_RE,
    )
    for n in payload["nodes"]:
        n["grade"] = raw[n["src"]]["grade"]
        n["stage_label"] = raw[n["src"]]["stage_label"]
        # 課綱附錄的「學習內容說明」——條文本身很短，這段才寫了教到什麼程度、
        # 和哪一條的關係。227 條裡 166 條有，總共才 8 千字，直接帶進圖裡。
        if raw[n["src"]].get("note"):
            n["note"] = raw[n["src"]]["note"]
    report(payload, spec["prereq"], save("graph_math.json", payload))


if __name__ == "__main__":
    main()
