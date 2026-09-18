"""數學領域課程手冊 PDF → data/handbook_math.json（逐條學習內容解析）。

課程手冊由國教院發布，針對每一條學習內容提供教學解析。版面是散文式，
每一條以「編碼＋條目原文」起頭，一直到下一條為止。

判定標題的關鍵：不能只看「行首是編碼」——手冊行文中也會出現
「N-5-16。」這種以編碼開頭的句子。因此要求行首編碼後面能接上課綱原文
的開頭幾個字，才算是一條新的解析。
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata

import pdfplumber

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, "data")
CODE = re.compile(r"^([NSGRAFD]-\d{1,2}-\d{1,2})\s*(.*)$")
# 頁首頁尾固定出現，逐行剔除
NOISE = re.compile(r"^(十二年國教課程綱要國民中小學暨普通型高中|數學領域課程手冊|\d{1,3})$")
# 章節標題：碰到就結束目前這一條。11–12 年級用的編碼不在部定必修的集合裡，
# 沒有這道終止條件的話，最後一條會一路吞到書末（實測 D-10-4 吃掉 10 萬字）。
STOP = re.compile(
    r"^(▊|[壹貳參肆伍陸柒捌玖拾]、|附錄|\d{1,2}年級(數學[AB甲乙])?學習內容解析"
    r"|[一二三四五六七八九十]、(普通型|國民)" r")")


def clean_block(lines: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """丟掉頁首頁尾與空行，並做 NFC。

    同樣要做 NFC：手冊與課綱兩份 PDF 的相容字用法不一致，不統一就對不起來。
    每一行連同它的 PDF 頁次與書上印的頁碼一起留著——要做「跳到手冊第幾頁」，
    就得知道每個段落是從哪一頁開始的，段落切完再回頭找已經來不及。
    """
    out = []
    for pno, folio, ln in lines:
        ln = ln.strip()
        if not ln or NOISE.match(ln):
            continue
        out.append((pno, folio, unicodedata.normalize("NFC", ln)))
    return out


# 手冊逐條解析的固定小標。分塊呈現比一整片文字好讀，也才有辦法對「釋例」
# 這種含圖表、抽不完整的段落單獨做提示與頁碼跳轉。
MARK = re.compile(r"^(備註|基本說明|條目範圍|釋例|教學提示|說明|注意|補充)"
                  r"(?:[：:（(]|$|[^\u4e00-\u9fff])")


def split_blocks(lines: list[tuple[int, int, str]]) -> list[dict]:
    """把一條的內文依小標切成區塊，記下每一塊在手冊的哪一頁開始。"""
    blocks: list[dict] = []
    for pno, folio, ln in lines:
        m = MARK.match(ln)
        if m:
            title = m.group(1)
            rest = ln[len(title):].lstrip("：:").strip()
            blocks.append({"title": title, "page": pno, "folio": folio,
                           "lines": [rest] if rest else []})
        elif blocks:
            blocks[-1]["lines"].append(ln)
        # 小標出現之前的行一律丟掉。實測有 30 條（N-1-4、N-5-10、S-9-5…）整段
        # 都沒有小標，內容是隔壁「新舊課綱對照表」滲進來的儲存格碎片
        #（「（九年一貫）3-n-11…」「⟹」「二、四」），不是解析。以前整包塞進
        # text 看不出來，卡片上就直接把表格碎片當成教學解析顯示給使用者。
    out = []
    for b in blocks:
        text = "\n".join(b["lines"]).strip()
        if text:
            out.append({"title": b["title"], "page": b["page"],
                        "folio": b["folio"], "text": text})
    return out


def main() -> None:
    pdf_path = sys.argv[1]
    with open(os.path.join(DATA, "raw_math.json"), encoding="utf-8") as f:
        raw = {r["code"]: unicodedata.normalize("NFC", r["text"])
               for r in json.load(f) if r["kind"] == "content"}

    sections: dict[str, dict] = {}
    cur = None
    buf: list[tuple[int, int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            lines = (page.extract_text() or "").split("\n")
            # 書上印的頁碼在頁尾，和 PDF 頁次不一樣（前面有序、目次）。
            # 兩個都留：連結用 PDF 頁次，給人看的用書上的頁碼。
            folio = 0
            for cand in reversed(lines[-3:]):
                if re.fullmatch(r"\d{1,3}", cand.strip()):
                    folio = int(cand.strip())
                    break
            for ln in lines:
                ln = unicodedata.normalize("NFC", ln)
                m = CODE.match(ln.strip())
                head = None
                if m and m.group(1) in raw:
                    code, rest = m.group(1), m.group(2)
                    # 後面要接得上課綱原文才算標題，否則是行文中的引用
                    if rest and raw[code].replace(" ", "")[:4] in rest.replace(" ", ""):
                        head = code
                if head:
                    if cur:
                        sections[cur]["lines"] = clean_block(buf)
                    cur = head
                    sections[cur] = {"code": head, "page": pno, "folio": folio}
                    buf = []
                elif cur:
                    if STOP.match(ln.strip()):
                        sections[cur]["lines"] = clean_block(buf)
                        cur, buf = None, []
                        continue
                    buf.append((pno, folio, ln))
    if cur:
        sections[cur]["lines"] = clean_block(buf)

    # 手冊每條都明列「先備／連結／後續」的編碼——課綱本身沒有這些資訊，
    # 這是驗證人工標註前置關係的唯一官方依據，單獨抽成欄位。
    FIELD = re.compile(r"^(先備|連結|後續)[：:](.+?)。?$")
    for sec in sections.values():
        body, rel = [], {"prior": [], "linked": [], "after": []}
        key = {"先備": "prior", "連結": "linked", "後續": "after"}
        for pno, folio, ln in sec.pop("lines", []):
            m = FIELD.match(ln)
            if m:
                rel[key[m.group(1)]] += re.findall(r"[NSGRAFD]-\d{1,2}-\d{1,2}", m.group(2))
            else:
                body.append((pno, folio, ln))
        # 小標之前的殘句是被折行切開的標題殘跡，丟掉
        first = next((i for i, (_, _, ln) in enumerate(body) if MARK.match(ln)), None)
        if first is not None:
            body = body[first:]
        sec["blocks"] = split_blocks(body)
        if sec["blocks"]:
            sec["end_page"] = max(b["page"] for b in sec["blocks"])
        sec.update(rel)

    # 沒有解析但有先備關係的條目要留著——merge_official() 靠它做官方優先
    rows = [s for s in sections.values()
            if s["blocks"] or s["prior"] or s["linked"] or s["after"]]
    covered = sorted(sections)
    missing = sorted(set(raw) - set(covered))
    chars = sum(len(b["text"]) for s in rows for b in s["blocks"])
    out = os.path.join(DATA, "handbook_math.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source": "十二年國教數學領域課程手冊（國家教育研究院）",
                   "edition": "113 年 3 月更新版",
                   # 卡片要能跳到手冊的對應頁。抽取用的是 107 年 12 月版，但
                   # 已逐條核對過：227 條標題在 107 年 12 月版與線上 113 年 3 月
                   # 更新版落在**完全相同**的 PDF 頁次（782 頁、0 筆差異），
                   # 所以 #page= 連到線上最新版是準的。
                   "url": "https://www.naer.edu.tw/upload/1/16/doc/2021/"
                          "%E6%95%B8%E5%AD%B8%E9%A0%98%E5%9F%9F%E8%AA%B2%E7%A8%8B"
                          "%E6%89%8B%E5%86%8A%EF%BC%88113%E5%B9%B43%E6%9C%88"
                          "%E6%9B%B4%E6%96%B0%E7%89%88%EF%BC%89.pdf",
                   "sections": rows}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"✓ handbook_math.json：{len(rows)} 條解析，{chars:,} 字，"
          f"{os.path.getsize(out) / 1024:.0f} KB")
    print(f"  課綱 {len(raw)} 條中，{len(covered)} 條找到手冊標題，缺 {len(missing)} 條")
    if missing:
        print("  缺：" + "、".join(missing[:15]) + ("…" if len(missing) > 15 else ""))
    withb = [s for s in rows if s["blocks"]]
    ln = sorted((sum(len(b["text"]) for b in s["blocks"]), s["code"]) for s in withb)
    print(f"  有解析 {len(withb)} 條，長度中位數 {ln[len(ln)//2][0]} 字，"
          f"最短 {ln[0][0]}（{ln[0][1]}）、最長 {ln[-1][0]}（{ln[-1][1]}）")
    import collections as _c
    kinds = _c.Counter(b["title"] for s in withb for b in s["blocks"])
    print("  區塊：" + "　".join(f"{k} {v}" for k, v in kinds.most_common()))
    pr = sum(len(s["prior"]) for s in rows)
    lk = sum(len(s["linked"]) for s in rows)
    af = sum(len(s["after"]) for s in rows)
    have = sum(1 for s in rows if s["prior"])
    print(f"  手冊明列的關係：先備 {pr} 條（{have} 個條目有）、連結 {lk}、後續 {af}")


if __name__ == "__main__":
    main()
