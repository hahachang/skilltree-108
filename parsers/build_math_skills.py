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


def main() -> None:
    spec = load("skills_math.json")
    raw = {r["code"]: r for r in load("raw_math.json") if r["kind"] == "content"}
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
    report(payload, spec["prereq"], save("graph_math.json", payload))


if __name__ == "__main__":
    main()
