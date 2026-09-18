"""自然領綱〈附錄四：學習內容說明〉→ data/notes_natural.json。

課綱的條文常常只有一句（「原子模型的發展。」），真正寫「教到什麼程度、
哪些算哪些不算、和哪一條什麼關係」的是附錄。數學領綱把它做成學習內容表
裡的一個「備註」欄，所以 parse_math.py 順手就收進去了；自然領綱則是獨立
的附錄四（p95–235），一直沒抽。

版面有四種表頭，共通點是都成對出現「學習內容｜學習內容說明」：

  學習內容｜學習內容說明｜學習內容｜學習內容說明        國小，兩個學習階段並排
  主題｜次主題｜學習內容｜學習內容說明｜參考節數        高中
  主題｜次主題｜學習內容｜學習內容說明｜備註            國中
  次主題｜學習內容｜學習內容說明｜備註

所以不照欄位索引取，而是**先認出每一組「內容欄→說明欄」的 x 範圍再配對**。
國小那種一列裡有兩條不同編碼的兩欄式版面，這樣才不會把第三學習階段的說明
掛到第二學習階段的條目上。

第二個關鍵：國中與高中是**一個儲存格裡列好幾條**（Bc-Ⅳ-1～Bc-Ⅳ-4），說明欄
則寫成「1-1…2-1…3-1…」。那個開頭的數字就是條目的流水號，不是說明自己的
編號——所以說明要照這個數字切開，分別掛到 `Bc-Ⅳ-1`、`Bc-Ⅳ-2`…。只取整格
當成第一條的說明的話，國中高中會少掉八成（實測 458 條抽不到）。

跨頁續接時儲存格裡沒有編碼，這時沿用上一列的**編碼前綴**（`Bc-Ⅳ-`），再用
開頭數字組回完整編碼，並且回頭跟課綱的編碼表對一次——對不上就不要掛。
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_handbook_natural import (ALIAS, _cells, _overlap, codes_in,  # noqa: E402
                                    load_official, norm)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
PAGES = range(95, 236)          # 附錄四：學習內容說明
NOISE = re.compile(r"^(十二年國民基本教育課程綱要|自然科學領域|\d{1,3})$")


def flat(s: str) -> str:
    return re.sub(r"\s", "", norm(s))


def tidy(s: str) -> str:
    """把折行黏回去，但保留「一則說明一行」的分段。

    起一行的條件有三種：編號（1-1）、範圍（5~7）、條列符號（‧）。只認編號的話，
    三顆「‧」會被黏成一長行。
    """
    out: list[str] = []
    for ln in norm(s).split("\n"):
        ln = ln.strip()
        if not ln or NOISE.match(ln):
            continue
        if ONE.match(ln) or SPAN.match(ln) or ln.startswith(BULLET) or not out:
            out.append(ln)
        else:
            out[-1] += ln
    return "\n".join(out).strip()


def pairs_of(rows, words):
    """回傳 [(內容欄 x 範圍, 說明欄 x 範圍)]，以及表頭佔幾列。"""
    for hi in (0, 1):
        if hi >= len(rows):
            break
        cells = _cells(rows[hi], words)
        # 用 startswith 不用相等：表頭儲存格常常把第一列資料一起吃進來
        # （p207 的表頭是「學習內容⏎水可自解離產生H＋與OH－。」）。
        # 順序不能反——「學習內容說明」本身就以「學習內容」開頭。
        note = [(c[0], c[1]) for c in cells if flat(c[2]).startswith("學習內容說明")]
        cont = [(c[0], c[1]) for c in cells
                if flat(c[2]).startswith("學習內容")
                and not flat(c[2]).startswith("學習內容說明")]
        if not cont or not note:
            continue
        out = []
        for cx in sorted(cont):
            after = [n for n in sorted(note) if n[0] >= cx[0]]
            if after:
                out.append((cx, after[0]))
        if out:
            return out, hi + 1
    return [], 0


# 說明的開頭有三種寫法，對應三種歸屬方式：
#   1-1、2-3   前面那個數字是條目流水號，後面是該條目第幾則說明
#   5~7        一段說明同時涵蓋第 5 到第 7 條
#   ‧開頭      整組條目共通的提醒，沒有指定是哪一條
ONE = re.compile(r"^(\d{1,2})-\d{1,2}")
SPAN = re.compile(r"^(\d{1,2})[~～](\d{1,2})")
BULLET = ("‧", "•", "．")


def split_note(note: str):
    """回傳 (開頭沒編號的殘句, [(起, 迄, 文字)], [整組共通的說明])。

    第一項是被頁尾切斷、跟著翻到下一頁的半句話——它屬於**上一頁最後那一則**，
    不是新的一則，也不是整組共通的說明（實測 PEb-Ⅴc-5 只抽到一個「程。」）。
    """
    lead: list[str] = []
    chunks: list[list] = []
    common: list[str] = []
    cur = None
    for ln in note.split("\n"):
        m = ONE.match(ln)
        sp = SPAN.match(ln)
        if m or sp:
            lo = int((m or sp).group(1))
            hi = int(sp.group(2)) if sp else lo
            cur = [lo, hi, ln]
            chunks.append(cur)
        elif ln.startswith(BULLET):
            common.append(ln)
            cur = None
        elif cur:
            cur[2] += ln
        elif common:
            common[-1] += ln
        elif not chunks:
            lead.append(ln)
    return lead, chunks, common


def main(pdf_path: str) -> None:
    load_official()                       # 給 codes_in 用原文驗編碼
    with open(os.path.join(DATA, "raw_natural.json"), encoding="utf-8") as f:
        VALID = {r["code"] for r in json.load(f) if r["kind"] == "content"}
    notes: dict[str, list[str]] = defaultdict(list)
    order: list[str] = []
    orphan: list[str] = []
    sig_prev = None
    last: dict[int, str] = {}             # 欄 → 最近一次看到的編碼前綴
    tail: dict[int, list] = {}            # 欄 → 最近一則說明掛在哪幾條

    with pdfplumber.open(pdf_path) as pdf:
        for pno in PAGES:
            page = pdf.pages[pno - 1]
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
            for table in page.find_tables():
                rows = table.rows
                pairs, head = pairs_of(rows, words)
                if not pairs:
                    continue
                # 版面換了就不能再沿用上一張表的「這一欄目前是哪一條」
                sig = tuple(round(c[0][0]) for c in pairs)
                if sig != sig_prev:
                    last, tail = {}, {}
                    sig_prev = sig
                for row in rows[head:]:
                    cells = _cells(row, words)

                    def pick(span):
                        best, ov = "", 0.0
                        for (x0, x1, txt) in cells:
                            o = _overlap((x0, x1), span)
                            if o > ov and txt.strip():
                                best, ov = txt, o
                        return best

                    for i, (cspan, nspan) in enumerate(pairs):
                        body = pick(cspan)
                        note = tidy(pick(nspan))
                        cs = codes_in(body)
                        if cs:
                            # 前綴取「這一格裡最多數的前綴」，不能取第一個：附錄
                            # 把 BLb-Ⅴa-1 寫成領綱裡不存在的編碼，codes_in 會照
                            # ALIAS 換成 BFc-Ⅴa-1，拿它當前綴就會把同一格的
                            # BLb-Ⅴa-3、-4 組成不存在的 BFc-Ⅴa-3、-4。
                            pref = Counter(c.rsplit("-", 1)[0] + "-"
                                           for c in cs).most_common(1)[0][0]
                            last[i] = (pref, cs)
                        carried = last.get(i)
                        if not (carried and note):
                            continue
                        prefix, row_codes = carried

                        def put(code: str, text: str) -> None:
                            code = ALIAS.get(code, code)
                            if code not in VALID:
                                orphan.append(code)
                                return
                            if code not in notes:
                                order.append(code)
                            if text not in notes[code]:
                                notes[code].append(text)

                        lead, chunks, common = split_note(note)
                        # 沒有編號也沒有條列符號的說明有兩種，要分清楚：
                        #   這一列本身有編碼 → 是整組共通的說明（Na-Ⅳ-2～5 那種）
                        #   這一列沒有編碼   → 是被頁尾切斷、翻頁過來的半句話
                        if lead and cs:
                            for code in row_codes:
                                put(code, "".join(lead))
                        elif lead and tail.get(i):
                            # 「5~7」這種跨條目的說明要整組一起補，不能只補最後一條
                            for code in tail[i]:
                                if notes.get(code):
                                    notes[code][-1] += "".join(lead)
                        elif lead:
                            for code in row_codes:
                                put(code, "".join(lead))

                        for lo, hi, text in chunks:
                            group = []
                            for seq in range(lo, hi + 1):
                                put(prefix + str(seq), text)
                                group.append(ALIAS.get(prefix + str(seq),
                                                       prefix + str(seq)))
                            tail[i] = group
                        # 沒有編號的說明是整組共通的，掛給這一列所有條目
                        for text in common:
                            for code in row_codes:
                                put(code, text)

    merged = {code: "\n".join(notes[code]).strip() for code in order}

    path = os.path.join(DATA, "notes_natural.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)

    raw = VALID
    hit = sorted(set(merged) & raw)
    print(f"✓ notes_natural.json：{len(merged)} 條說明，"
          f"{sum(len(v) for v in merged.values()):,} 字，"
          f"{os.path.getsize(path)/1024:.0f} KB")
    print(f"  課綱 {len(raw)} 條學習內容中，{len(hit)} 條有附錄說明")
    if orphan:
        import collections as _c
        top = _c.Counter(orphan).most_common(8)
        print(f"  ⚠ 序號組回來對不上課綱編碼、已丟棄 {len(orphan)} 段："
              + "、".join(f"{k}×{v}" for k, v in top))
    short = [c for c, v in merged.items() if len(v) < 6]
    if short:
        print(f"  ⚠ 說明短得可疑（<6 字）{len(short)}：" + "、".join(short[:10]))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法：parse_natural_notes.py <自然領綱PDF>")
    main(sys.argv[1])
