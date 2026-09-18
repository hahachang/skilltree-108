"""社會領綱〈附錄三：學習內容說明〉→ data/raw_social.json。

之前那份 raw_social.json 是用通用抽取器跑出來的，502 條裡有 459 條結尾黏著
科目字（「紀年與分期。歷」），16 條混進了「建議融入…示例」整欄——那是因為
社會領綱的表格和自然、數學都不一樣：**一個儲存格裡直接疊好幾條**，而且條目
本身帶科目前綴（歷／地／公）。

改從〈附錄三〉抽，因為那裡的**條目與說明在同一張表**，而且多給一欄「建議
節數」。三種表頭：

  主題軸｜項目｜階段｜條目｜說明              國小（社會不分科）
  主題｜項目｜條目｜說明｜建議節數            國中、高中
  主題｜項目｜階段｜條目｜說明｜建議節數

共通點是都有「條目」和「說明」，所以一樣用**表頭儲存格的 x 範圍**去配對，
不照欄位索引——合併儲存格會讓資料列整列相對表頭位移。

說明的歸屬和自然科不同：自然是「1-1」「2-1」逐條編號，社會的說明是寫給整個
**項目**（一組條目）的，所以一列的說明掛給那一列的所有條目。
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_handbook_natural import _cells, _overlap, norm  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
PAGES = range(97, 173)                       # 附錄三

# 學習內容的編碼：可選的科目字（歷／地／公）＋大寫主題碼＋階段＋流水號。
# 第一碼限定大寫字母，正好把學習表現（1a-Ⅱ-1、歷1c-Ⅳ-2）排除在外。
CODE = re.compile(r"(歷|地|公)?([A-Z][a-z]?)-([ⅡⅢⅣⅤ])-(\d{1,2})")
SUBJ = {"歷": "歷史", "地": "地理", "公": "公民與社會"}
STAGE_LABEL = {"Ⅱ": "第二學習階段・3–4年級", "Ⅲ": "第三學習階段・5–6年級",
               "Ⅳ": "第四學習階段・7–9年級（國中）",
               "Ⅴ": "第五學習階段・高中"}
ROLES = {"主題軸": "topic", "主題": "topic", "項目": "item", "階段": "stage",
         "條目": "content", "說明": "note", "建議節數": "hours"}
TOPIC_HEAD = re.compile(r"^[A-Z][.．、]")
ITEM_HEAD = re.compile(r"^[a-z][.．、]")


def flat(s: str) -> str:
    return re.sub(r"\s", "", norm(s))


def clean(s: str) -> str:
    """把折行黏回去，並修掉字型把 Ⅳ 打成「I＋Ⅴ」的情況。"""
    s = norm(s).replace("IⅤ", "Ⅳ").replace("IV", "Ⅳ")
    s = re.sub(r"\s+", "", s)
    return s.strip()


def role_map(rows, words):
    """從表頭建立 [(x0, x1, 角色)]，並回傳表頭佔幾列。"""
    for hi in (0, 1):
        if hi >= len(rows):
            break
        out = []
        for (x0, x1, txt) in _cells(rows[hi], words):
            f = flat(txt)
            for key, role in ROLES.items():
                if f.startswith(key):
                    out.append((x0, x1, role))
                    break
        if any(r == "content" for *_, r in out) and any(r == "note" for *_, r in out):
            return out, hi + 1
    return [], 0


def split_entries(cell: str):
    """一個儲存格裡疊了好幾條，切成 [(科目, 主題碼, 階段, 序號, 條文)]。"""
    text = clean(cell)
    hits = list(CODE.finditer(text))
    out = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = text[m.end():end].strip("　 。;；")
        out.append((m.group(1), m.group(2), m.group(3), int(m.group(4)), body))
    return out


def main(pdf_path: str) -> None:
    rows_out: dict[str, dict] = {}
    notes: dict[str, list[str]] = defaultdict(list)
    order: list[str] = []
    carry = {"topic": "", "item": "", "stage": "", "last": []}

    with pdfplumber.open(pdf_path) as pdf:
        for pno in PAGES:
            page = pdf.pages[pno - 1]
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            for table in page.find_tables():
                mapping, head = role_map(table.rows, words)
                if not mapping:
                    continue
                for row in table.rows[head:]:
                    cells = _cells(row, words)

                    def pick(role):
                        best, ov = "", 0.0
                        for (x0, x1, txt) in cells:
                            if not txt.strip():
                                continue
                            for (hx0, hx1, r) in mapping:
                                if r != role:
                                    continue
                                o = _overlap((x0, x1), (hx0, hx1))
                                if o > ov:
                                    best, ov = txt, o
                        return best

                    # 主題、項目、階段是跨列合併的，只印在該群第一列。
                    # 主題名稱還會跨頁被切開（「R.現代戰爭與國」「家暴力」被當成
                    # 兩個主題），所以不合「A.」開頭格式的就當成上一個的續行。
                    for k in ("topic", "item", "stage"):
                        v = clean(pick(k))
                        if not v:
                            continue
                        pat = TOPIC_HEAD if k == "topic" else (
                            ITEM_HEAD if k == "item" else None)
                        if pat and carry[k] and not pat.match(v):
                            carry[k] += v
                        else:
                            carry[k] = v
                    got = split_entries(pick("content"))
                    note = clean(pick("note"))
                    hours = clean(pick("hours"))

                    if got:
                        carry["last"] = []
                        for (subj, tc, st, seq, body) in got:
                            code = (subj or "") + tc + "-" + st + "-" + str(seq)
                            if code not in rows_out:
                                order.append(code)
                                rows_out[code] = {
                                    "code": code, "kind": "content",
                                    "topic_code": tc, "stage": st,
                                    "stage_label": STAGE_LABEL[st], "seq": seq,
                                    "text": body, "page": pno,
                                    "subject": SUBJ.get(subj, "社會"),
                                }
                            elif body and len(body) > len(rows_out[code]["text"]):
                                rows_out[code]["text"] = body   # 跨頁補完整
                            if hours:
                                rows_out[code]["hours"] = hours
                            carry["last"].append(code)
                            rows_out[code].setdefault("topic", carry["topic"])
                            rows_out[code].setdefault("item", carry["item"])
                    # 說明是寫給整個「項目」的，掛給這一列（或續接的上一列）所有條目
                    for code in carry["last"]:
                        if note and note not in notes[code]:
                            notes[code].append(note)

        # 附錄三沒有收「探究與實作」那幾門課（實測缺 9 條歷史學探究）。
        # 拿主表〈伍、學習重點〉補一輪，只補附錄沒有的，條文照樣從儲存格取。
        for pno in range(10, 67):
            page = pdf.pages[pno - 1]
            words = page.extract_words(keep_blank_chars=False,
                                       use_text_flow=False)
            for table in page.find_tables():
                cols = [(x0, x1) for (x0, x1, t) in _cells(table.rows[0], words)
                        if flat(t).startswith("條目")]
                if not cols:
                    continue
                head2 = {}
                for (x0, x1, t) in _cells(table.rows[0], words):
                    f = flat(t)
                    if f.startswith("主題"):
                        head2["topic"] = (x0, x1)
                    elif f.startswith("項目"):
                        head2["item"] = (x0, x1)
                topic = item = ""
                for row in table.rows[1:]:
                    cells = _cells(row, words)

                    def near(span):
                        best, ov2 = "", 0.0
                        for (x0, x1, txt) in cells:
                            if not txt.strip():
                                continue
                            o = _overlap((x0, x1), span)
                            if o > ov2:
                                best, ov2 = txt, o
                        return clean(best)

                    if "topic" in head2:
                        v = near(head2["topic"])
                        if v:
                            topic = (topic + v) if (topic and not TOPIC_HEAD.match(v)) else v
                    if "item" in head2:
                        v = near(head2["item"])
                        if v:
                            item = (item + v) if (item and not ITEM_HEAD.match(v)) else v
                    body, ov = "", 0.0
                    for (x0, x1, txt) in cells:
                        if not txt.strip():
                            continue
                        o = _overlap((x0, x1), cols[0])
                        if o > ov:
                            body, ov = txt, o
                    for (subj, tc, st, seq, text) in split_entries(body):
                        code = (subj or "") + tc + "-" + st + "-" + str(seq)
                        if code in rows_out:
                            continue
                        order.append(code)
                        rows_out[code] = {
                            "code": code, "kind": "content", "topic_code": tc,
                            "stage": st, "stage_label": STAGE_LABEL[st],
                            "seq": seq, "text": text, "page": pno,
                            "subject": SUBJ.get(subj, "社會"),
                            "topic": topic, "item": item, "from_main": True,
                        }

    # 跨頁被切開的主題名稱，前半段那幾條會停在「R.現代戰爭與國」。
    # 同科目同階段裡，若某個主題名是另一個的前綴，一律採用完整的那個。
    full: dict[tuple, list] = defaultdict(list)
    for r in rows_out.values():
        full[(r["subject"], r["stage"])].append(r.get("topic") or "")
    fix = {}
    for key, names in full.items():
        uniq = sorted(set(n for n in names if n), key=len, reverse=True)
        for short in uniq:
            for long in uniq:
                if long != short and long.startswith(short):
                    fix[(key, short)] = long
                    break
    for r in rows_out.values():
        k = ((r["subject"], r["stage"]), r.get("topic") or "")
        if k in fix:
            r["topic"] = fix[k]

    out = []
    for code in order:
        r = rows_out[code]
        if notes[code]:
            r["note"] = "\n".join(notes[code])
        out.append(r)

    path = os.path.join(DATA, "raw_social.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    import collections as _c
    st = _c.Counter(r["stage"] for r in out)
    sj = _c.Counter(r["subject"] for r in out)
    print(f"✓ raw_social.json：{len(out)} 條學習內容，"
          f"{os.path.getsize(path)/1024:.0f} KB")
    print("  階段：" + "　".join(f"{k} {v}" for k, v in sorted(st.items())))
    print("  科目：" + "　".join(f"{k} {v}" for k, v in sj.most_common()))
    print(f"  有附錄說明 {sum(1 for r in out if r.get('note'))}／{len(out)}"
          f"　有建議節數 {sum(1 for r in out if r.get('hours'))}")
    extra = [r["code"] for r in out if r.get("from_main")]
    if extra:
        print(f"  附錄三沒收、從主表補的 {len(extra)} 條："
              + "、".join(extra[:12]))
    bad = [r["code"] for r in out if len(r["text"]) < 4]
    if bad:
        print(f"  ⚠ 條文短得可疑 {len(bad)}：" + "、".join(bad[:12]))
    dirty = [r["code"] for r in out if re.search(r"(建議融入|示例)", r["text"])]
    if dirty:
        print(f"  ⚠ 條文疑似混到別欄 {len(dirty)}：" + "、".join(dirty[:12]))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法：parse_social.py <社會領綱PDF>")
    main(sys.argv[1])
