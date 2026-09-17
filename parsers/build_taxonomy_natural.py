"""自然科學領綱「表三 學習內容架構表」→ data/taxonomy_natural.json。

表三是合併儲存格且主題名稱會跨行，機器抽取極易錯位，故以人工謄錄後固化為
可稽核的 JSON（課綱自 107 年發布後未修訂，屬穩定靜態規格）。
來源：自然科學領域課程綱要 PDF 第 14–15 頁。
"""
import json
import os

# 課題 -> 跨科概念(國小) -> 主題(國中以上) -> 次主題
TAXONOMY = [
    {
        "theme": "1.自然界的組成與特性",
        "cross": [
            {"code": "INa", "name": "物質與能量", "topics": [
                {"code": "A", "name": "物質的組成與特性", "subs": [
                    ("Aa", "物質組成與元素的週期性"),
                    ("Ab", "物質的形態、性質及分類")]},
                {"code": "B", "name": "能量的形式、轉換及流動", "subs": [
                    ("Ba", "能量的形式與轉換"),
                    ("Bb", "溫度與熱量"),
                    ("Bc", "生物體內的能量與代謝"),
                    ("Bd", "生態系中能量的流動與轉換")]},
            ]},
            {"code": "INb", "name": "構造與功能", "topics": [
                {"code": "C", "name": "物質的結構與功能", "subs": [
                    ("Ca", "物質的分離與鑑定"),
                    ("Cb", "物質的結構與功能")]},
                {"code": "D", "name": "生物體的構造與功能", "subs": [
                    ("Da", "細胞的構造與功能"),
                    ("Db", "動植物體的構造與功能"),
                    ("Dc", "生物體內的恆定性與調節")]},
            ]},
            {"code": "INc", "name": "系統與尺度", "topics": [
                {"code": "E", "name": "物質系統", "subs": [
                    ("Ea", "自然界的尺度與單位"),
                    ("Eb", "力與運動"),
                    ("Ec", "氣體"),
                    ("Ed", "宇宙與天體")]},
                {"code": "F", "name": "地球環境", "subs": [
                    ("Fa", "組成地球的物質"),
                    ("Fb", "地球與太空"),
                    ("Fc", "生物圈的組成")]},
            ]},
        ],
    },
    {
        "theme": "2.自然界的現象、規律及作用",
        "cross": [
            {"code": "INd", "name": "改變與穩定", "topics": [
                {"code": "G", "name": "演化與延續", "subs": [
                    ("Ga", "生殖與遺傳"), ("Gb", "演化"), ("Gc", "生物多樣性")]},
                {"code": "H", "name": "地球的歷史", "subs": [
                    ("Ha", "地球的起源與演變"), ("Hb", "地層與化石")]},
                {"code": "I", "name": "變動的地球", "subs": [
                    ("Ia", "地表與地殼的變動"), ("Ib", "天氣與氣候變化"),
                    ("Ic", "海水的運動"), ("Id", "晝夜與季節")]},
            ]},
            {"code": "INe", "name": "交互作用", "topics": [
                {"code": "J", "name": "物質的反應、平衡及製造", "subs": [
                    ("Ja", "物質反應規律"), ("Jb", "水溶液中的變化"),
                    ("Jc", "氧化與還原反應"), ("Jd", "酸鹼反應"),
                    ("Je", "化學反應速率與平衡"),
                    ("Jf", "有機化合物的性質、製備及反應")]},
                {"code": "K", "name": "自然界的現象與交互作用", "subs": [
                    ("Ka", "波動、光及聲音"), ("Kb", "萬有引力"),
                    ("Kc", "電磁現象"), ("Kd", "量子現象"), ("Ke", "基本交互作用")]},
                {"code": "L", "name": "生物與環境", "subs": [
                    ("La", "生物間的交互作用"), ("Lb", "生物與環境的交互作用")]},
            ]},
        ],
    },
    {
        "theme": "3.自然界的永續發展",
        "cross": [
            {"code": "INf", "name": "科學與生活", "topics": [
                {"code": "M", "name": "科學、科技、社會及人文", "subs": [
                    ("Ma", "科學、技術及社會的互動關係"), ("Mb", "科學發展的歷史"),
                    ("Mc", "科學在生活中的應用"), ("Md", "天然災害與防治"),
                    ("Me", "環境汙染與防治")]},
            ]},
            {"code": "INg", "name": "資源與永續性", "topics": [
                {"code": "N", "name": "資源與永續發展", "subs": [
                    ("Na", "永續發展與資源的利用"), ("Nb", "氣候變遷之影響與調適"),
                    ("Nc", "能源的開發與利用")]},
            ]},
        ],
    },
]

# 高中階段在主題碼前加的科別前綴
SUBJECT_PREFIX = {"B": "生物", "P": "物理", "C": "化學", "E": "地球科學"}

# 學習表現架構表（表二）：第1碼 -> (項目, 子項)
PERFORMANCE = {
    "ti": ("思考智能", "想像創造"), "tr": ("思考智能", "推理論證"),
    "tc": ("思考智能", "批判思辨"), "tm": ("思考智能", "建立模型"),
    "po": ("問題解決", "觀察與定題"), "pe": ("問題解決", "計劃與執行"),
    "pa": ("問題解決", "分析與發現"), "pc": ("問題解決", "討論與傳達"),
    "ai": ("科學的態度與本質", "培養科學探究的興趣"),
    "ah": ("科學的態度與本質", "養成應用科學思考與探究的習慣"),
    "an": ("科學的態度與本質", "認識科學本質"),
}

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "taxonomy_natural.json")
    payload = {"taxonomy": TAXONOMY, "subject_prefix": SUBJECT_PREFIX,
               "performance": PERFORMANCE}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    subs = sum(len(t["subs"]) for th in TAXONOMY for c in th["cross"] for t in c["topics"])
    print(f"{out}: {len(TAXONOMY)} 課題 / "
          f"{sum(len(t['cross']) for t in TAXONOMY)} 跨科概念 / "
          f"{sum(len(c['topics']) for t in TAXONOMY for c in t['cross'])} 主題 / {subs} 次主題")
