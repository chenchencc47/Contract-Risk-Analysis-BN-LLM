"""F-3: Build legal reference table from DISC-Law-SFT for LLM prompt injection.

Extracts contract-related QA pairs, maps legal citations to risk types,
and produces a compact reference table for the LLM₁ system prompt.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Risk type → keywords for classification ──
RISK_TYPE_KW = {
    "违约责任/违约金": ["违约金", "违约", "逾期", "迟延", "不履行", "瑕疵履行"],
    "付款/预付款": ["付款", "预付款", "首付", "尾款", "支付", "价款", "定金"],
    "合同解除/终止": ["解除", "终止", "解约", "撤销"],
    "损害赔偿": ["赔偿", "损失", "损害赔偿", "间接损失", "实际损失"],
    "格式条款": ["格式条款", "格式合同", "不公平", "加重责任", "限制权利"],
    "担保/保证": ["担保", "保证", "抵押", "质押", "留置", "保函", "保证金"],
    "合同效力": ["无效", "效力", "可撤销", "生效", "成立", "要约", "承诺"],
    "交付/验收": ["交付", "验收", "交货", "收货", "风险转移"],
    "保密/知识产权": ["保密", "知识产权", "商业秘密", "专利", "著作权", "商标"],
    "不可抗力/情势变更": ["不可抗力", "情势变更", "天灾", "战争", "疫情"],
    "争议解决": ["管辖", "仲裁", "诉讼", "争议解决", "法院"],
    "租赁": ["租赁", "出租", "承租", "租金", "押金", "转租"],
}

# ── 民法典 article mapping (common citations from analysis) ──
# Chinese numeral → digit mapping
CN_NUM = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,
          '百':100,'千':1000}

def cn_to_int(s: str) -> int | None:
    """Convert Chinese numeral to integer. E.g., '五百七十七' → 577"""
    if s.isdigit():
        return int(s)
    result = 0
    current = 0
    for ch in s:
        if ch in CN_NUM:
            val = CN_NUM[ch]
            if val >= 10:
                if current == 0:
                    current = 1
                result += current * val
                current = 0
            else:
                current = val
        else:
            return None
    result += current
    return result if result > 0 else None


def extract_article_number(cite: str) -> int | None:
    """Extract article number from citation like '第五百七十七条' or '第585条'."""
    # Try modern digit format: 第585条
    m = re.search(r'第(\d+)条', cite)
    if m:
        return int(m.group(1))
    # Try Chinese numeral: 第五百七十七条
    m = re.search(r'第([零一二三四五六七八九十百千]+)条', cite)
    if m:
        return cn_to_int(m.group(1))
    return None


def main():
    # ── Pass 1: Collect citations per risk type ──
    risk_cites: dict[str, Counter] = defaultdict(Counter)

    for fname in ['DISC-Law-SFT-Pair-QA-released.jsonl']:
        path = PROJECT_ROOT / "dataset" / fname
        with open(path, encoding='utf-8') as f:
            for line in f:
                obj = json.loads(line)
                text = obj.get('input', '') + obj.get('output', '')

                # Classify into risk types
                matched_types = []
                for rtype, keywords in RISK_TYPE_KW.items():
                    if any(kw in text for kw in keywords):
                        matched_types.append(rtype)
                if not matched_types:
                    continue

                # Extract article citations
                cites = re.findall(
                    r'民法典第[零一二三四五六七八九十百千\d]+条|第[零一二三四五六七八九十百千\d]+条',
                    text
                )
                for cite in cites:
                    art = extract_article_number(cite)
                    if art and 1 <= art <= 1260:  # 民法典共1260条
                        for rt in matched_types:
                            risk_cites[rt][art] += 1

    # ── Pass 2: Build reference table ──
    print("=" * 70)
    print("DISC-Law-SFT Legal Citation Reference for LLM Prompt")
    print("=" * 70)
    print()

    for rtype in sorted(risk_cites.keys()):
        top = risk_cites[rtype].most_common(5)
        if not top:
            continue
        articles = []
        for art_num, count in top:
            articles.append(f"第{art_num}条({count}次)")
        print(f"**{rtype}**: {', '.join(articles)}")

    print()
    print("=" * 70)
    print("Compact prompt injection format:")
    print("=" * 70)
    print()

    lines = [
        "## 民法典常用条文速查（基于中文法律QA统计，仅供审查时参考，禁止机械套用）",
        "",
    ]
    for rtype in sorted(risk_cites.keys()):
        top = risk_cites[rtype].most_common(3)
        if not top:
            continue
        arts = [f"第{art}条" for art, _ in top]
        lines.append(f"- {rtype}: {', '.join(arts)}")

    injection = "\n".join(lines)
    print(injection)

    # Save
    out_path = PROJECT_ROOT / "config" / "legal_reference_from_disc_law_sft.txt"
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(injection)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
