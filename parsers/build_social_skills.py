"""raw_social.json + skills_{history,geography,civics}.json → 三張社會科技能圖。

社會科拆成三棵樹，不是一棵。原因是歷史、地理、公民在國中以上幾乎是平行的
三科，彼此的依賴很少——自然科有「能量」「尺度」這些跨科概念把四科綁在一起，
社會科沒有等價物，硬併成一棵只會得到三團互不相連的東西。

國小社會不分科，57 條依內容歸到最接近的一科（social_spec.json 的
elementary_subject），所以三棵樹各自有自己的國小根。
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from skill_builder import DATA, build, load, report, save  # noqa: E402

TIER_OF_STAGE = {"Ⅱ": 4, "Ⅲ": 6, "Ⅳ": 9, "Ⅴ": 12}
STAGE_LABEL = {"Ⅱ": "第二學習階段・3–4年級", "Ⅲ": "第三學習階段・5–6年級",
               "Ⅳ": "第四學習階段・7–9年級（國中）",
               "Ⅴ": "第五學習階段・高中"}
DOMAINS = {"歷史": ("history", "skills_history.json"),
           "地理": ("geography", "skills_geography.json"),
           "公民與社會": ("civics", "skills_civics.json")}


def main() -> None:
    spec = load("social_spec.json")
    ES, GROUPS, TG = (spec["elementary_subject"], spec["groups"],
                      spec["topic_group"])
    all_raw = load("raw_social.json")

    def subject_of(r):
        if r["subject"] != "社會":
            return r["subject"]
        return ES.get(r["topic_code"], "公民與社會")

    def group_key(r, subj):
        # 國小的主題碼是兩碼（Ab），國中以上要從主題名稱取開頭那個字母（A.基本概念）
        st = "國小" if r["stage"] in ("Ⅱ", "Ⅲ") else r["stage"]
        tc = r["topic_code"] if r["subject"] == "社會" else (r.get("topic") or "").split(".")[0]
        return f"{subj}|{st}|{tc}"

    for subj, (domain, spec_name) in DOMAINS.items():
        sub = load(spec_name)
        raw = {r["code"]: r for r in all_raw if subject_of(r) == subj}
        groups = GROUPS[subj]

        missing = sorted({group_key(r, subj) for r in raw.values()
                          if group_key(r, subj) not in TG})
        if missing:
            sys.exit(f"✗ {subj}：這些主題沒有分組，補 social_spec.json："
                     + "、".join(missing))

        payload = build(
            raw, sub, domain=domain, topics=groups,
            topic_of=lambda r: TG[group_key(r, subj)],
            tier_of=lambda r: TIER_OF_STAGE.get(r["stage"], 12),
            # 「問題探究」「歷史考察」「地理方法的實踐」這類條目本質是綜合應用，
            # 和數學的「解題」、自然的跨科目主題同性質，畫成六角形
            applied_of=lambda r: any(k in r["text"] for k in
                                     ("問題探究", "挑選適當課題", "深入探究"))
            or (r.get("item") or "").startswith(("實踐", "實作")),
        )
        for n in payload["nodes"]:
            r = raw[n["src"]]
            # 共用的 title_of 會在「、」斷句，那是為數學與自然設計的（「長度、
            # 面積」確實是兩件事）。社會的條文本身就短（中位數 14 字），而且
            # 「宋、元時期的國際互動」斷在第一個頓號會變成「宋」。這裡只在
            # 「：」「（」斷，其餘直接截斷。
            head = re.split(r"[：:（(]", r["text"], maxsplit=1)[0].strip()
            n["name"] = (head or r["text"])[:18]
            n["stage"] = r["stage"]
            n["stage_label"] = STAGE_LABEL.get(r["stage"], r["stage_label"])
            n["subject"] = subj
            n["subject_key"] = domain
            n["curriculum_topic"] = r.get("topic") or ""
            if r.get("note"):
                n["note"] = r["note"]
            if r.get("hours"):
                n["hours"] = r["hours"]
        # 刻意不輸出 subjects：社會三科各自只有一個科目，「依科目上色」會變成
        # 整張圖同一個顏色。前端偵測不到 subjects 就會退回用分支（topics）上色，
        # 也不會顯示那顆沒有意義的「科目／跨科概念」切換。
        notes = sum(1 for n in payload["nodes"] if n.get("note"))
        hours = sum(1 for n in payload["nodes"] if n.get("hours"))
        print(f"【{subj}】附錄說明 {notes}／{len(payload['nodes'])}　"
              f"官方建議節數 {hours}")
        report(payload, sub["prereq"], save(f"graph_{domain}.json", payload))
        print()


if __name__ == "__main__":
    main()
