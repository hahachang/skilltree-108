"""數學領綱 PDF → data/raw_math.json。

數學版面是「一列一條條目」，且原表就附有「對應學習表現」欄——這是課綱裡
少數明文寫出的節點連結，直接收下來當技能樹的邊。
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_columns import CODE_RE, clean, iter_pages, rows_by_table  # noqa: E402

# 數學第 2 碼是年級（1-12），對應到十二年國教的學習階段
STAGE_OF_GRADE = {1: "Ⅰ", 2: "Ⅰ", 3: "Ⅱ", 4: "Ⅱ", 5: "Ⅲ", 6: "Ⅲ",
                  7: "Ⅳ", 8: "Ⅳ", 9: "Ⅳ", 10: "Ⅴ", 11: "Ⅴ", 12: "Ⅴ"}
STAGE_LABEL = {"Ⅰ": "第一學習階段", "Ⅱ": "第二學習階段", "Ⅲ": "第三學習階段",
               "Ⅳ": "第四學習階段", "Ⅴ": "第五學習階段"}


def col_index(header: list[str], *keys: str) -> int | None:
    for i, h in enumerate(header):
        flat = h.replace("\n", "")
        if any(k in flat for k in keys):
            return i
    return None


def parse(pdf_path: str) -> list[dict]:
    nodes: dict[str, dict] = {}
    for pno, page in iter_pages(pdf_path, range(11, 60)):
        for table in rows_by_table(page):
            if not table:
                continue
            header = table[0]
            i_code = col_index(header, "編碼")
            i_text = col_index(header, "學習內容條目", "學習表現")
            if i_code is None or i_text is None:
                continue
            i_note = col_index(header, "備註")
            i_tool = col_index(header, "參考教具")
            i_link = col_index(header, "對應學習表現")
            for row in table[1:]:
                if i_code >= len(row) or i_text >= len(row):
                    continue
                code = row[i_code].replace("\n", "").strip()
                if not CODE_RE.fullmatch(code):
                    continue
                topic, grade, seq = code.split("-")
                kind = "performance" if topic.islower() else "content"
                stage = (STAGE_OF_GRADE.get(int(grade), grade)
                         if kind == "content" else grade)
                node = {
                    "code": code,
                    "kind": kind,
                    "topic_code": topic,
                    "grade": int(grade) if kind == "content" else None,
                    "stage": stage,
                    "stage_label": STAGE_LABEL.get(stage, stage),
                    "seq": int(seq),
                    "text": clean(row[i_text]),
                    "page": pno,
                }
                if i_note is not None and i_note < len(row):
                    node["note"] = clean(row[i_note])
                if i_tool is not None and i_tool < len(row):
                    node["tools"] = clean(row[i_tool])
                if i_link is not None and i_link < len(row):
                    node["linked_performance"] = re.findall(
                        CODE_RE, row[i_link].replace("\n", ""))
                old = nodes.get(code)
                if old is None or len(node["text"]) > len(old["text"]):
                    nodes[code] = node
    return sorted(nodes.values(),
                  key=lambda n: (n["kind"], n["topic_code"], n["seq"], n["stage"]))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法：parse_math.py <數學領綱 PDF 路徑>")
    rows = parse(sys.argv[1])
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "raw_math.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    links = sum(len(r.get("linked_performance", [])) for r in rows)
    print(f"{out}: {len(rows)} nodes {kinds}, 內容→表現連結 {links} 條")
