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


def clean_block(lines: list[str]) -> str:
    """同樣要做 NFC：手冊與課綱兩份 PDF 的相容字用法不一致，不統一就對不起來。"""
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln or NOISE.match(ln):
            continue
        out.append(ln)
    return unicodedata.normalize("NFC", "\n".join(out)).strip()


def main() -> None:
    pdf_path = sys.argv[1]
    with open(os.path.join(DATA, "raw_math.json"), encoding="utf-8") as f:
        raw = {r["code"]: unicodedata.normalize("NFC", r["text"])
               for r in json.load(f) if r["kind"] == "content"}

    sections: dict[str, dict] = {}
    cur = None
    buf: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for ln in (page.extract_text() or "").split("\n"):
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
                        sections[cur]["text"] = clean_block(buf)
                    cur = head
                    sections[cur] = {"code": head, "page": pno}
                    buf = []
                elif cur:
                    if STOP.match(ln.strip()):
                        sections[cur]["text"] = clean_block(buf)
                        cur, buf = None, []
                        continue
                    buf.append(ln)
    if cur:
        sections[cur]["text"] = clean_block(buf)

    # 手冊每條都明列「先備／連結／後續」的編碼——課綱本身沒有這些資訊，
    # 這是驗證人工標註前置關係的唯一官方依據，單獨抽成欄位。
    FIELD = re.compile(r"^(先備|連結|後續)[：:](.+?)。?$")
    for sec in sections.values():
        body, rel = [], {"prior": [], "linked": [], "after": []}
        key = {"先備": "prior", "連結": "linked", "後續": "after"}
        for ln in sec.get("text", "").split("\n"):
            m = FIELD.match(ln.strip())
            if m:
                rel[key[m.group(1)]] += re.findall(r"[NSGRAFD]-\d{1,2}-\d{1,2}", m.group(2))
            else:
                body.append(ln)
        MARK = re.compile(r"^(備註|基本說明|條目範圍|釋例|教學提示|說明|注意|補充)")
        first = next((i for i, ln in enumerate(body) if MARK.match(ln.strip())), None)
        if first is not None:
            body = body[first:]
        sec["text"] = "\n".join(body).strip()
        sec.update(rel)

    rows = [s for s in sections.values() if s.get("text")]
    covered = sorted(sections)
    missing = sorted(set(raw) - set(covered))
    chars = sum(len(s["text"]) for s in rows)
    out = os.path.join(DATA, "handbook_math.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"source": "十二年國教數學領域課程手冊（國家教育研究院，107 年 12 月）",
                   "sections": rows}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"✓ handbook_math.json：{len(rows)} 條解析，{chars:,} 字，"
          f"{os.path.getsize(out) / 1024:.0f} KB")
    print(f"  課綱 {len(raw)} 條中，{len(covered)} 條有解析，缺 {len(missing)} 條")
    if missing:
        print("  缺：" + "、".join(missing[:15]) + ("…" if len(missing) > 15 else ""))
    ln = sorted((len(s["text"]), s["code"]) for s in rows)
    print(f"  長度：中位數 {ln[len(ln)//2][0]} 字，最短 {ln[0][0]}（{ln[0][1]}）、"
          f"最長 {ln[-1][0]}（{ln[-1][1]}）")
    pr = sum(len(s["prior"]) for s in rows)
    lk = sum(len(s["linked"]) for s in rows)
    af = sum(len(s["after"]) for s in rows)
    have = sum(1 for s in rows if s["prior"])
    print(f"  手冊明列的關係：先備 {pr} 條（{have} 個條目有）、連結 {lk}、後續 {af}")


if __name__ == "__main__":
    main()
