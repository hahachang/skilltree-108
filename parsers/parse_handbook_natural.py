"""自然科學領域課程手冊 PDF → data/handbook_natural.json（逐條官方註解）。

和數學手冊不一樣，這本手冊**沒有**逐條的「先備／連結／後續」欄位。
它的〈肆、學習重點解析〉開宗明義寫著：國小與國中的學習重點解析請看領綱
附錄，手冊本身只解析高中與探究實作。所以「官方優先」那套前置關係替換，
在自然科是做不到的——自然科的前置仍然全部是人工標註。

但手冊裡確實有大量逐條的官方文字，只是散在五種版面不同的表格裡：

  國小新舊對照   p17–24    課題｜學習內容｜新增/調移/刪減｜說明
  高中99對照     p45–64    次主題｜十二年國教學習內容｜99課綱｜差異說明
  加深加廣歸課   p108–112  次主題｜加深加廣選修學習內容（含課程名稱標題）
  化學章節建議   p135–142  建議章節順序｜部定必修學習內容｜建議教材與教學方式
  地科教學建議   p143–152  主題｜次主題｜學習內容｜建議教材與教學方式／學習內容說明

表格的欄位不能用索引對，因為合併儲存格會讓資料列相對表頭整列位移
（實測 p46 表頭在 index 1/4/7/10，資料列卻在 0/3/6/9）。這裡改用表頭
儲存格的 x 範圍去比對資料列儲存格的 x 範圍，重疊最多的就是那一欄。

跨頁與跨列的續接：有註解但該列沒有編碼時，併回前一個編碼群組。
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
from pdf_columns import _lines_from_words  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")

# 手冊把 Ⅴ（U+2164）打成半形 V，Ⅱ/Ⅲ/Ⅳ 也可能是 ASCII。統一成領綱的寫法。
ROMAN = {"V": "Ⅴ", "II": "Ⅱ", "III": "Ⅲ", "IV": "Ⅳ", "I": "Ⅰ"}
CODE = re.compile(
    r"([A-Z][A-Za-z]{1,3})-(Ⅴ[ac]|V[ac]|[ⅡⅢⅣⅤ]|I{1,3}|IV|V)-(\d{1,2})")


# 三條編碼對不上圖。前兩條是領綱自己就把同一個概念列了兩次，
# skills_natural.json 已經把它們合併成別名（BLb-Ⅴa-1→BFc-Ⅴa-1、
# BMc-Ⅴa-1→BGa-Ⅴa-7），這裡跟著合併；第三條 CMc-Ⅴc-4 才是手冊印錯。
# 不換的話這幾段官方文字會變成掛不到任何技能的孤兒。
ALIAS = {
    "BLb-Ⅴa-1": "BFc-Ⅴa-1",   # 生態學的研究層級
    "BMc-Ⅴa-1": "BGa-Ⅴa-7",   # 生物科技的應用
    "CMc-Ⅴc-4": "CMc-Ⅴc-1",   # 水的處理過程
}


def norm(s: str) -> str:
    """NFC 正規化 + 去掉頁首頁尾與軟體字型的私用區符號。"""
    s = unicodedata.normalize("NFC", s or "")
    # 手冊字型把箭頭與項目符號放在私用區。箭頭有意義（ⅣⅢ 是「從第四
    # 學習階段調到第三」），先換成 →，其餘私用區符號直接丟掉。
    s = s.replace("\uf0e0", "→")
    s = re.sub("[\uf000-\uf8ff]", "", s)
    return s


def norm_code(m: re.Match) -> str:
    stage = m.group(2)
    tail = ""
    if stage[-1] in "ac" and stage[0] in "VⅤ":
        tail, stage = stage[-1], stage[:-1]
    stage = ROMAN.get(stage, stage)
    return f"{m.group(1)}-{stage}{tail}-{int(m.group(3))}"


# 領綱原文，用來反查手冊印錯的編碼。手冊把 EFb-Ⅴc-1（由地球觀察恆星的視
# 運動）印成 EFa-Ⅴc-1，而 EFa-Ⅴc-1 本身是另一條真實存在的條目（地震波
# 分層）——這種撞號沒辦法用固定的別名表處理，只能拿條文原文去對。
OFFICIAL: dict[str, str] = {}
BY_TEXT: dict[str, str] = {}
FIXED: list[str] = []
FOLIO: dict[int, int] = {}


def load_official() -> None:
    path = os.path.join(DATA, "raw_natural.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for r in json.load(f):
            if r.get("kind") != "content":
                continue
            key = re.sub(r"[。，、\s]", "", norm(r["text"]))[:12]
            OFFICIAL[r["code"]] = key
            BY_TEXT.setdefault(key, r["code"])


def codes_in(text: str) -> list[str]:
    """抓出這段文字裡的編碼；編碼後面若接著條文原文，順便驗一次對不對。"""
    text = norm(text)
    out, seen = [], set()
    hits = list(CODE.finditer(text))
    for i, m in enumerate(hits):
        c = ALIAS.get(norm_code(m), norm_code(m))
        tail = text[m.end():hits[i + 1].start() if i + 1 < len(hits) else len(text)]
        key = re.sub(r"[。，、\s]", "", tail)[:12]
        if key and OFFICIAL and OFFICIAL.get(c, "")[:8] != key[:8]:
            real = BY_TEXT.get(key) or next(
                (v for k, v in BY_TEXT.items() if k[:8] == key[:8]), None)
            if real and real != c:
                FIXED.append(f"{c}→{real}")
                c = real
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def tidy(s: str) -> str:
    """把儲存格裡的折行黏回去，但保留條列的分行語意。"""
    s = norm(s)
    s = re.sub(r"\n+", "", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip()


# ---------------------------------------------------------------- 表格 → 角色列

def _overlap(a, b) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def role_rows(page, roles: dict[str, str], with_cells: bool = False,
              with_top: bool = False):
    """把一頁裡符合 roles 的表格轉成 [{角色: 文字}]。

    roles 是 {表頭文字: 角色名}。表頭文字用 in 比對（表頭會折行、會多空白）。
    with_cells=True 時，每列多回傳一份 {角色: [(x0, x1, 文字), ...]}，
    給「一個表頭橫跨兩個子欄」的版面自己再切一次用。
    """
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    out = []
    for table in page.find_tables():
        rows = table.rows
        if not rows:
            continue
        mapping = []                      # [(x0, x1, role)]
        head_rows = 1
        for (x0, x1, txt) in _cells(rows[0], words):
            flat = re.sub(r"\s", "", norm(txt))
            for key, role in roles.items():
                if key in flat:
                    mapping.append((x0, x1, role))
                    break
        if len({r for *_, r in mapping}) < 2:
            continue                      # 不是我們要的表
        # 第二列可能是子表頭（國小對照表的 新增／調移／刪減 掛在 學習階段 底下）。
        # 有子表頭時它的 x 範圍比父欄窄，直接覆蓋掉父欄那一段。
        if len(rows) > 1:
            subs = [(x0, x1, roles[re.sub(r"\s", "", norm(t))])
                    for (x0, x1, t) in _cells(rows[1], words)
                    if re.sub(r"\s", "", norm(t)) in roles]
            if len(subs) >= 2:
                mapping = [m for m in mapping
                           if not any(_overlap(m[:2], sub[:2]) > 0 for sub in subs)] + subs
                head_rows = 2
        for row in rows[head_rows:]:
            rec: dict[str, str] = {}
            cells: dict[str, list] = defaultdict(list)
            for (x0, x1, txt) in _cells(row, words):
                if not txt.strip():
                    continue
                best, span = None, 0.0
                for (hx0, hx1, role) in mapping:
                    ov = _overlap((x0, x1), (hx0, hx1))
                    if ov > span:
                        best, span = role, ov
                if best:
                    rec[best] = (rec.get(best, "") + "\n" + txt).strip()
                    cells[best].append((x0, x1, txt))
            if rec:
                if with_cells:
                    out.append((rec, dict(cells)))
                elif with_top:
                    out.append((rec, table.bbox[1]))
                else:
                    out.append(rec)
    return out


def _cells(row, words) -> list[tuple[float, float, str]]:
    cells = []
    for bbox in row.cells:
        if bbox is None:
            continue
        x0, top, x1, bottom = bbox
        inside = [w for w in words
                  if x0 - 1 <= (w["x0"] + w["x1"]) / 2 <= x1 + 1
                  and top - 1 <= w["top"] <= bottom + 1]
        inside.sort(key=lambda w: (round(w["top"] / 3), w["x0"]))
        lines, last = [], None
        for w in inside:
            key = round(w["top"] / 3)
            if key != last:
                lines.append(w["text"])
                last = key
            else:
                lines[-1] += w["text"]
        cells.append((x0, x1, "\n".join(lines)))
    return cells


# ---------------------------------------------------------------- 五種區塊

def folio_of(page) -> int:
    """書上印的頁碼（頁尾那個數字）。和 PDF 頁次差十幾頁，因為前面有序與目次。
    連結要用 PDF 頁次，給人看的要用書上的頁碼，兩個都得留。"""
    lines = [ln.strip() for ln in norm(page.extract_text() or "").split("\n")]
    for cand in reversed(lines[-3:]):
        if re.fullmatch(r"\d{1,3}", cand):
            return int(cand)
    return 0


def block_rows(pdf, pages, roles, with_cells: bool = False):
    for pno in pages:
        page = pdf.pages[pno - 1]
        FOLIO[pno] = FOLIO.get(pno) or folio_of(page)
        for rec in role_rows(page, roles, with_cells):
            yield pno, rec


def section_elementary(pdf, add):
    """國小新舊課綱對照：每條學習內容的官方說明，以及新增／調移／刪減。"""
    roles = {"課題": "課題", "學習內容": "content", "新增": "新增",
             "調移": "調移", "刪減": "刪減", "說明": "note"}
    last: list[str] = []
    topic = ""
    for pno, rec in block_rows(pdf, range(17, 25), roles):
        cs = codes_in(rec.get("content", ""))
        note = tidy(rec.get("note", ""))
        # 課題是跨列合併的儲存格，只印在該群第一列，要自己往下帶。
        topic = tidy(rec.get("課題", "")) or topic
        if cs:
            last = cs
            marks = []
            for k in ("新增", "調移", "刪減"):
                v = tidy(rec.get(k, ""))
                if v:
                    marks.append(k + (f"（{v}）" if v not in ("", "") else ""))
            for c in cs:
                add(c, {"kind": "國小新舊對照", "page": pno, "課題": topic,
                        "異動": "／".join(marks), "說明": note})
        elif note and last:
            for c in last:
                add(c, {"kind": "國小新舊對照", "page": pno, "說明": note,
                        "續前": True})


def section_senior_99(pdf, add):
    """高中必修與 99 課綱的逐條差異說明。"""
    roles = {"次主題": "次主題", "十二年國教": "content",
             "99課綱": "old", "差異說明": "note"}
    last: list[str] = []
    for pno, rec in block_rows(pdf, range(45, 65), roles):
        cs = codes_in(rec.get("content", ""))
        note = tidy(rec.get("note", ""))
        old = tidy(rec.get("old", ""))
        if cs:
            last = cs
            for c in cs:
                add(c, {"kind": "高中99對照", "page": pno,
                        "次主題": tidy(rec.get("次主題", "")),
                        "99課綱": old, "說明": note})
        elif note and last:
            for c in last:
                add(c, {"kind": "高中99對照", "page": pno, "說明": note,
                        "續前": True})


COURSE = re.compile(r"^課程名稱[：:](.+)$")


def section_elective(pdf, add, courses):
    """加深加廣選修：課程名稱在表格外的行，表格只有次主題與學習內容。"""
    roles = {"次主題": "次主題", "加深加廣選修學習內容": "content"}
    carry = None                       # 課程名稱會跨頁延續到下一張表
    for pno in range(107, 113):
        page = pdf.pages[pno - 1]
        FOLIO[pno] = FOLIO.get(pno) or folio_of(page)
        # 一頁可能有兩張表、兩個課程名稱，所以要按 y 綁定，不能取整頁最後一個。
        heads = []
        for top, line in _lines_from_words(page.extract_words()):
            m = COURSE.match(norm(line).strip())
            if m:
                heads.append((top, m.group(1).strip()))
        for rec, ttop in role_rows(page, roles, with_top=True):
            above = [name for top, name in heads if top < ttop]
            cur = above[-1] if above else carry
            carry = cur
            for c in codes_in(rec.get("content", "")):
                if cur:
                    courses.setdefault(c, cur)
                add(c, {"kind": "加深加廣課程", "page": pno, "課程名稱": cur,
                        "次主題": tidy(rec.get("次主題", ""))})


CHAPTER = re.compile(r"^(\d{1,2})[.．](.+)$")


def section_chem(pdf, add, order):
    """化學部定必修的建議章節順序與教材教法。這是手冊裡唯一的官方排序。"""
    roles = {"建議章節順序": "chapter", "部定必修學習內容": "content",
             "建議教材與教學方式": "note"}
    last: list[str] = []
    cur_chapter = cur_unit = ""
    unit_x = chap_x = None
    for pno, (rec, cells) in block_rows(pdf, range(135, 143), roles, True):
        # 「建議章節順序」的表頭橫跨兩個子欄：左邊是大單元、右邊是章節，
        # 但兩欄的折行會在文字裡交錯（「物質的/組成」與「1.物質的狀/態」），
        # 所以只能按 x 分，不能按「開頭有沒有編號」分。
        chap_cells = sorted(cells.get("chapter", []))
        if len(chap_cells) >= 2:
            unit_x = chap_cells[0][0] if unit_x is None else min(unit_x, chap_cells[0][0])
            chap_x = chap_cells[1][0] if chap_x is None else max(chap_x, chap_cells[1][0])
            cur_unit, cur_chapter = tidy(chap_cells[0][2]), tidy(chap_cells[1][2])
        elif len(chap_cells) == 1:
            # 只有一格時不能看「開頭有沒有編號」——章節後半段（水、大氣、
            # 綠色化學）本來就沒編號。用 x 跟已知的兩欄起點比才分得開。
            x0, _, txt = chap_cells[0]
            txt = tidy(txt)
            if unit_x is not None and abs(x0 - unit_x) <= abs(x0 - (chap_x or 1e9)):
                cur_unit, cur_chapter = txt, ""
            else:
                cur_chapter = txt
        cs = codes_in(rec.get("content", ""))
        note = tidy(rec.get("note", ""))
        if cs:
            last = cs
            order.append({"單元": cur_unit, "章節": cur_chapter,
                          "codes": cs, "page": pno})
            for c in cs:
                add(c, {"kind": "化學章節建議", "page": pno, "單元": cur_unit,
                        "建議章節": cur_chapter, "說明": note})
        elif note and last:
            for c in last:
                add(c, {"kind": "化學章節建議", "page": pno, "說明": note,
                        "續前": True})


def section_earth(pdf, add):
    """地科（含探究實作前的兩張表）：逐條教材教法或學習內容說明。"""
    roles = {"主題": "主題", "次主題": "次主題", "學習內容": "content",
             "建議教材與教學方式": "note", "學習內容說明": "note"}
    last: list[str] = []
    for pno, rec in block_rows(pdf, range(143, 153), roles):
        cs = codes_in(rec.get("content", ""))
        note = tidy(rec.get("note", ""))
        if cs:
            last = cs
            for c in cs:
                add(c, {"kind": "地科教學建議", "page": pno,
                        "主題": tidy(rec.get("主題", "")),
                        "次主題": tidy(rec.get("次主題", "")), "說明": note})
        elif note and last:
            for c in last:
                add(c, {"kind": "地科教學建議", "page": pno, "說明": note,
                        "續前": True})


# ---------------------------------------------------------------- 主流程

def main(pdf_path: str) -> None:
    entries: dict[str, list] = defaultdict(list)
    courses: dict[str, str] = {}
    order: list = []

    def add(code: str, rec: dict) -> None:
        rec = {k: v for k, v in rec.items() if v not in ("", None)}
        if rec.get("page"):
            rec["folio"] = FOLIO.get(rec["page"], 0)
        if len(rec) <= 3:            # 只剩 kind／page／folio，沒有內容就不收
            return
        entries[code].append(rec)

    load_official()
    with pdfplumber.open(pdf_path) as pdf:
        section_elementary(pdf, add)
        section_senior_99(pdf, add)
        section_elective(pdf, add, courses)
        section_chem(pdf, add, order)
        section_earth(pdf, add)

    out = {
        "source": "十二年國教課程綱要國民中小學暨普通型高中 自然科學領域課程手冊（國教院）",
        "edition": "108 年 1 月定稿版",
        # 線上定稿版與本機這份逐頁核對過：544 頁，抽出來的 JSON 完全相同，
        # 所以卡片上的 #page= 連結指到線上版是準的。
        # 國教院同一份檔有兩個路徑，doc/2025 是課程手冊頁現在掛的那個。
        "url": "https://www.naer.edu.tw/upload/1/16/doc/2025/"
               "%E8%87%AA%E7%84%B6%E7%A7%91%E5%AD%B8%E9%A0%98%E5%9F%9F"
               "%E8%AA%B2%E7%A8%8B%E6%89%8B%E5%86%8A(%E5%AE%9A%E7%A8%BF%E7%89%88).pdf",
        "entries": {k: v for k, v in sorted(entries.items())},
        "elective_courses": dict(sorted(courses.items())),
        "chem_order": order,
    }
    path = os.path.join(DATA, "handbook_natural.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    total = sum(len(v) for v in entries.values())
    chars = sum(len(json.dumps(v, ensure_ascii=False)) for v in entries.values())
    print(f"條目 {len(entries)}　段落 {total}　字數約 {chars}")
    kinds: dict[str, int] = defaultdict(int)
    for v in entries.values():
        for r in v:
            kinds[r["kind"]] += 1
    for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {k}: {n}")
    print(f"加深加廣課程歸屬 {len(courses)}　化學章節列 {len(order)}")
    if FIXED:
        seen = sorted(set(FIXED))
        print(f"手冊編碼與條文對不上、依原文改回 {len(seen)} 處：{'、'.join(seen)}")
    if ALIAS:
        print(f"定稿前舊編碼（人工比對原文確認）{len(ALIAS)} 處："
              + "、".join(f"{k}→{v}" for k, v in ALIAS.items()))
    print(f"→ {path}  ({os.path.getsize(path)/1024:.0f}KB)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法：parse_handbook_natural.py <課程手冊-自然.pdf>")
    main(sys.argv[1])
