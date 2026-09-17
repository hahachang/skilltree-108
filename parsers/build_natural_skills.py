"""raw_natural.json + skills_natural.json → data/graph_natural.json。

目前只涵蓋已標註的學習階段（第二～第四，即國小中年級到國中）。
高中兩階段尚未標註，不納入圖中——寧可少畫，也不要畫出沒有依據的邊。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skill_builder import build, load, report, save  # noqa: E402

# 依表三的課題架構，用七大跨科概念當分支色系（國中以上的主題碼對回所屬跨科概念）
TOPICS = {"INa": "物質與能量", "INb": "構造與功能", "INc": "系統與尺度",
          "INd": "改變與穩定", "INe": "交互作用", "INf": "科學與生活",
          "INg": "資源與永續性"}

# 學習階段對應的年級上緣，供「起始年級」基準判定使用
TIER_OF_STAGE = {"Ⅱ": 4, "Ⅲ": 6, "Ⅳ": 9, "Ⅴc": 12, "Ⅴa": 12}
SUBJECT_PREFIX = {"B": "生物", "P": "物理", "C": "化學", "E": "地科"}
SUBJECT_KEY = {"生物": "bio", "物理": "phy", "化學": "chem",
               "地科": "earth", "跨科": "cross"}
SUBJECTS = {"bio": "生物", "phy": "物理", "chem": "化學",
            "earth": "地球科學", "cross": "跨科"}


def sub_to_cross(taxonomy) -> dict[str, str]:
    out = {}
    for theme in taxonomy:
        for cross in theme["cross"]:
            for topic in cross["topics"]:
                for sub_code, _ in topic["subs"]:
                    out[sub_code] = cross["code"]
    return out


def main() -> None:
    spec = load("skills_natural.json")
    stages = set(spec["stages"])
    raw = {r["code"]: r for r in load("raw_natural.json")
           if r["kind"] == "content" and r["stage"] in stages}
    cross = sub_to_cross(load("taxonomy_natural.json")["taxonomy"])

    subj = load("subjects_natural.json")

    def subject_of(r):
        """判定科目。優先序：人工逐條標註 → 高中的編碼前綴 → 由次主題碼反推。

        高中的 B/P/C/E 前綴是課綱明列的；國中的次主題碼可從高中同碼反推
        （Da 在高中是 BDa，故為生物）；國小的 IN 碼與跨科的 M/N 系列沒有
        機械依據，只能逐條判定。
        """
        tc, code = r["topic_code"], r["code"]
        if code in subj["by_code"]:
            return subj["by_code"][code]
        if len(tc) == 3 and tc[0] in SUBJECT_PREFIX and not tc.startswith("IN"):
            return SUBJECT_PREFIX[tc[0]]
        base = tc[1:] if len(tc) == 3 and tc[0] in SUBJECT_PREFIX else tc
        return subj["by_subtopic"].get(base, "跨科")

    def topic_of(r):
        tc = r["topic_code"]
        if tc.startswith("IN"):
            return tc
        base = tc[1:] if len(tc) == 3 and tc[0] in SUBJECT_PREFIX else tc
        return cross.get(base, "INa")

    payload = build(
        raw, spec, domain="natural", topics=TOPICS,
        topic_of=topic_of,
        tier_of=lambda r: TIER_OF_STAGE.get(r["stage"], 12),
        # 國中的 IN 碼是課綱明列的「跨科目主題」，本質就是多科技能的綜合應用
        applied_of=lambda r: r["topic_code"].startswith("IN") and r["stage"] == "Ⅳ",
    )
    stage_label = {"Ⅱ": "第二學習階段・3–4年級", "Ⅲ": "第三學習階段・5–6年級",
                   "Ⅳ": "第四學習階段・7–9年級（國中）",
                   "Ⅴc": "第五學習階段・高中必修", "Ⅴa": "第五學習階段・高中加深加廣選修"}
    for n in payload["nodes"]:
        r = raw[n["src"]]
        n["stage"] = r["stage"]
        n["stage_label"] = stage_label.get(r["stage"], r["stage_label"])
        n["subject"] = subject_of(r)
        n["subject_key"] = SUBJECT_KEY[n["subject"]]
    payload["subjects"] = SUBJECTS
    import collections
    dist = collections.Counter(n["subject"] for n in payload["nodes"])
    print("  科目分布：" + "  ".join(f"{k}:{v}" for k, v in dist.most_common()))
    report(payload, spec["prereq"], save("graph_natural.json", payload))


if __name__ == "__main__":
    main()
