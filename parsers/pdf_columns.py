"""課綱 PDF 版面抽取工具。

課綱的學習重點全部放在多欄表格裡，但兩種版面並存：

* 「欄內混排」型（自然科學）：一個 cell 裡塞了整個次主題的十幾條條目。
* 「編碼獨立欄」型（數學、語文、社會）：表頭就叫「編碼」，一列一條條目。

兩者都不能用 pdfplumber 的 extract_table()——它會依偵測到的 cell 高度裁切文字，
實測會把 cell 尾端的條目整條吃掉（例如 INb-Ⅱ-5 消失）。因此這裡一律只借用
表格的 bbox 當範圍，文字自己從 word 座標重組。
"""
from __future__ import annotations

import re

import pdfplumber

# 編碼格式：<主題碼>-<階段碼>-<流水號>
# 主題碼：IN[a-g]（國小跨科概念）/ A~N（主題）/ 前綴 B,P,C,E（高中分科）/ 小寫（學習表現）
# 階段碼：Ⅰ-Ⅴ（全形羅馬）或 I-V（ASCII，課綱內兩種混用）或 1~12（數學用年級）
STAGE = r"(?:Ⅰ|Ⅱ|Ⅲ|Ⅳ|Ⅴc|Ⅴa|Ⅴ|I{1,3}|IV|V[ca]?|[0-9]{1,2})"
CODE_RE = re.compile(rf"((?:IN[a-g]|[A-Za-z]{{1,4}})-{STAGE}-[0-9]{{1,2}})")


def _lines_from_words(words) -> list[tuple[float, str]]:
    """把 word 依 y 座標聚成行，回傳 [(y, 行文字), ...]。"""
    words = sorted(words, key=lambda w: (round(w["top"], 0), w["x0"]))
    lines: list[tuple[float, list[str]]] = []
    last = None
    for w in words:
        if last is None or abs(w["top"] - last) > 3:
            lines.append((w["top"], []))
            last = w["top"]
        lines[-1][1].append(w["text"])
    return [(y, "".join(parts)) for y, parts in lines]


def columns_by_table(page, x_tol: float = 1.5) -> list[list[str]]:
    """逐表格切欄，回傳 [表格][欄] 的文字。

    一頁可能同時存在兩個幾何不同的表格（例如學習表現表尾接學習內容表頭），
    只取 find_tables()[0] 會讓第二個表格的編碼欄與敘述欄被錯誤切割。
    """
    tables = page.find_tables()
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    if not tables or not words:
        text = page.extract_text() or ""
        return [[text]] if text else []

    result = []
    for table in tables:
        _, top, _, bottom = table.bbox
        edges = sorted({round(c[0], 1) for c in table.cells}
                       | {round(c[2], 1) for c in table.cells})
        if len(edges) < 2:
            continue
        buckets: list[list] = [[] for _ in range(len(edges) - 1)]
        for w in words:
            if not (top - 2 <= w["top"] <= bottom + 2):
                continue
            cx = (w["x0"] + w["x1"]) / 2
            for i in range(len(edges) - 1):
                if edges[i] - x_tol <= cx < edges[i + 1] + x_tol:
                    buckets[i].append(w)
                    break
        result.append(["\n".join(t for _, t in _lines_from_words(b)) for b in buckets])
    return result


def rows_by_table(page) -> list[list[list[str]]]:
    """逐表格切列，回傳 [表格][列][欄] 的文字。"""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False)
    result = []
    for table in page.find_tables():
        rows = []
        for row in table.rows:
            cells = []
            for bbox in row.cells:
                if bbox is None:
                    cells.append("")
                    continue
                x0, top, x1, bottom = bbox
                inside = [w for w in words
                          if x0 - 1 <= (w["x0"] + w["x1"]) / 2 <= x1 + 1
                          and top - 1 <= w["top"] <= bottom + 1]
                cells.append("\n".join(t for _, t in _lines_from_words(inside)))
            rows.append(cells)
        result.append(rows)
    return result


def fix_trailing_codes(text: str) -> str:
    """把「敘述在前、編碼在行尾」的行反轉成「編碼在前」。

    自然領綱的編碼框與敘述框各自獨立，少數頁面編碼框 y 座標比同列敘述略低，
    依 y 分行時會被排到行尾（例如「水可自解離產生H＋與OH－。CJd-Vc-1」），
    不處理的話這段敘述會被誤掛到上一個編碼，而該編碼本身變成空字串。
    """
    out = []
    for line in text.split("\n"):
        m = re.search(rf"{CODE_RE.pattern}$", line)
        out.append(m.group(1) + line[: m.start()] if m and m.start() > 0 else line)
    return "\n".join(out)


def fix_leading_orphans(text: str) -> str:
    """修正「編碼整欄往下偏移一行」的版面。

    編碼框與敘述框各自獨立時，某些頁面的編碼 y 座標會落在它那一條的第二行，
    依 y 分行後看起來像這樣（EIb-Vc-6 其實屬於下一條，不是這一行）::

        大氣的水平運動主要受氣壓梯度力、科氏
        EIb-Vc-6力和摩擦力的影響。
        天氣圖是由各地氣象觀測資料繪製而成，
        EIb-Vc-7用以分析天氣。

    判斷依據是「上一行沒有編碼、且沒有收在句末標點」——正常的續行都收在句號，
    不會被誤判。判斷一律用原始行況，不能看已改寫的結果，否則第一次搬動後
    後續各行都會失去依據。
    """
    lines = text.split("\n")
    had_code = [bool(re.match(rf"^{CODE_RE.pattern}", ln)) for ln in lines]
    ends = [ln.rstrip().endswith(("。", "）", ")", "：", "；")) for ln in lines]

    # 偏移是整欄一致的版面特徵，不能逐行判斷：國中頁面在主題交界也會出現
    # 「編碼行的前一行沒有句號」，逐行套用會把下一條的開頭吃進上一條。
    shifted = normal = 0
    for i in range(1, len(lines)):
        if not had_code[i]:
            continue
        if had_code[i - 1] or ends[i - 1]:
            normal += 1
        else:
            shifted += 1
    if shifted < 2 or shifted <= normal:
        return text

    out: list[str] = []
    pending: str | None = None
    for i, line in enumerate(lines):
        m = re.match(rf"^{CODE_RE.pattern}", line)
        if m and i > 0 and out and not had_code[i - 1] and not ends[i - 1]:
            out[-1] += line[m.end():]      # 本行去掉編碼後的文字屬於上一條
            pending = m.group(1)           # 編碼本身留給下一行
            continue
        if pending:
            line = pending + line
            pending = None
        out.append(line)
    if pending:
        out.append(pending)
    return "\n".join(out)


def header_stage(text: str) -> str | None:
    """從欄位表頭判斷這一欄屬於哪個學習階段（給整欄沒有編碼的續行欄用）。"""
    if "第五學習階段" in text:
        return "Ⅴa" if "選修" in text else "Ⅴc" if "必修" in text else "Ⅴ"
    for label, stage in (("第一學習階段", "Ⅰ"), ("第二學習階段", "Ⅱ"),
                         ("第三學習階段", "Ⅲ"), ("第四學習階段", "Ⅳ")):
        if label in text:
            return stage
    return None


def clean(desc: str) -> str:
    """清掉換行、跨行斷字造成的空白與頁碼殘跡。"""
    s = re.sub(r"\s+", "", desc)
    s = re.sub(r"^\d{1,3}(?=[^\d])", "", s)  # 頁首頁碼
    s = re.sub(r"\d{1,3}$", "", s)           # 頁尾頁碼
    return s.strip()


def iter_pages(path: str, pages: range):
    with pdfplumber.open(path) as pdf:
        for i in pages:
            if i < len(pdf.pages):
                yield i + 1, pdf.pages[i]
