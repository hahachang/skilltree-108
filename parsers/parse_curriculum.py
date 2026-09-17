"""課綱 PDF → 學習重點節點 JSON（通用抽取器）。

自動辨識兩種版面：
* 表頭有「編碼」欄 → 逐列配對（數學、語文、社會）。
* 沒有編碼欄、條目全擠在 cell 裡 → 逐欄掃描後用編碼正規表達式切段（自然科學）。

輸出每筆：code / kind(content|performance) / stage / topic_code / seq / text / page
主題階層（課題→跨科概念→主題→次主題）由 data/taxonomy_*.json 另行掛載。
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdf_columns import (  # noqa: E402
    CODE_RE, clean, columns_by_table, fix_leading_orphans, fix_trailing_codes,
    header_stage, iter_pages, rows_by_table,
)

# 表格欄位標題與課題標題等版面雜訊，出現在續行碎片開頭時要剝掉
NOISE = re.compile(
    r"(課題\s*\d+[：:][^\n]*"
    r"|第[一二三四五]學習階段學習(內容|表現)(（必修）|（加深加廣選修）)?"
    r"|跨科概念|次主題|主題|項目|子項|探究學習內容|實作學習內容"
    r"|學習表現|學習內容|備註\s*\d*[：:]?)"
)

# 課綱 PDF 混用全形羅馬數字（Ⅴ）與 ASCII 大寫（V），需正規化成單一字面
ASCII_STAGE = {"I": "Ⅰ", "II": "Ⅱ", "III": "Ⅲ", "IV": "Ⅳ",
               "V": "Ⅴ", "Vc": "Ⅴc", "Va": "Ⅴa"}

STAGE_LABEL = {
    "Ⅰ": "第一學習階段", "Ⅱ": "第二學習階段", "Ⅲ": "第三學習階段",
    "Ⅳ": "第四學習階段", "Ⅴ": "第五學習階段",
    "Ⅴc": "第五學習階段（必修）", "Ⅴa": "第五學習階段（加深加廣選修）",
}


def normalize_stage(stage: str) -> str:
    return ASCII_STAGE.get(stage, stage)


def normalize_code(code: str) -> str:
    topic, stage, seq = code.split("-")
    return f"{topic}-{normalize_stage(stage)}-{seq}"


def strip_noise(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = NOISE.sub("", text, count=1).strip()
    return text


def make_node(code: str, desc: str, page: int) -> dict:
    topic, stage, seq = code.split("-")
    return {
        "code": code,
        "kind": "performance" if topic[0].islower() else "content",
        "topic_code": topic,
        "stage": stage,
        "stage_label": STAGE_LABEL.get(stage, stage),
        "seq": int(seq),
        "text": desc,
        "page": page,
    }


def _upsert(nodes: dict[str, dict], code: str, desc: str, page: int) -> None:
    old = nodes.get(code)
    if old is None:
        nodes[code] = make_node(code, desc, page)
    elif len(desc) > len(old["text"]):   # 同碼重複出現（對照表）→ 保留較完整者
        old["text"] = desc


def _col_index(header: list[str], *keys: str) -> int | None:
    for i, h in enumerate(header):
        if any(k in h.replace("\n", "") for k in keys):
            return i
    return None


def parse(pdf_path: str, pages: range) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    # 跨頁續行碎片要接回它原本那一條的尾巴。欄位索引在換頁時會因表格幾何改變而錯位，
    # 因此改用「編碼自帶的學習階段」當歸屬鍵——課綱的每一欄本來就是一個學習階段。
    last_code_in_col: dict[tuple, str] = {}
    for pno, page in iter_pages(pdf_path, pages):
        tables_rows = rows_by_table(page)
        tables_cols = columns_by_table(page)
        for ti, table in enumerate(tables_rows):
            header = table[0] if table else []
            i_code = _col_index(header, "編碼")
            i_text = _col_index(header, "學習內容條目", "學習表現", "學習內容")
            if i_code is not None and i_text is not None and i_code != i_text:
                for row in table[1:]:                       # 逐列配對版面
                    if max(i_code, i_text) >= len(row):
                        continue
                    code = row[i_code].replace("\n", "").strip()
                    if CODE_RE.fullmatch(code):
                        _upsert(nodes, normalize_code(code), clean(row[i_text]), pno)
                continue
            if ti >= len(tables_cols):                      # 逐欄掃描版面
                continue
            for col in tables_cols[ti]:
                if not CODE_RE.search(col):
                    # 整欄只有續行、沒有任何編碼（跨頁的尾巴）。
                    # 這種欄不能直接跳過，否則那段文字會憑空消失。
                    st = header_stage(col)
                    tail = clean(strip_noise(col))
                    prev = last_code_in_col.get((False, st)) if st else None
                    if tail and prev and prev in nodes:
                        nodes[prev]["text"] += tail
                    continue
                parts = CODE_RE.split(fix_leading_orphans(fix_trailing_codes(col)))
                topic, stage, _ = normalize_code(parts[1]).split("-")
                key = (topic[0].islower(), stage)
                head = clean(strip_noise(parts[0]))
                prev = last_code_in_col.get(key)
                if head and prev and prev in nodes:
                    nodes[prev]["text"] += head
                for i in range(1, len(parts), 2):
                    code = normalize_code(parts[i])
                    _upsert(nodes, code, clean(strip_noise(parts[i + 1])), pno)
                    last_code_in_col[key] = code
    return nodes


def apply_overrides(nodes: dict[str, dict], out_path: str) -> int:
    """套用人工核對後的覆寫表（PDF 版面造成、規則救不回來的少數誤差）。"""
    name = "overrides_" + os.path.basename(out_path).replace("raw_", "")
    path = os.path.join(os.path.dirname(out_path), name)
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as f:
        fixes = json.load(f).get("text", {})
    n = 0
    for code, text in fixes.items():
        if code in nodes:
            nodes[code]["text"] = text
            nodes[code]["overridden"] = True
            n += 1
        else:
            print(f"⚠ 覆寫表指向不存在的編碼：{code}")
    return n


def main() -> None:
    pdf_path, out_path = sys.argv[1], sys.argv[2]
    first = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    last = int(sys.argv[4]) if len(sys.argv) > 4 else 10**6
    nodes = parse(pdf_path, range(first - 1, last))
    fixed = apply_overrides(nodes, out_path)
    rows = sorted(nodes.values(),
                  key=lambda n: (n["kind"], n["topic_code"], n["stage"], n["seq"]))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    note = f"，人工覆寫 {fixed} 條" if fixed else ""
    print(f"{os.path.basename(out_path)}: {len(rows)} nodes {kinds}{note}")


if __name__ == "__main__":
    main()
