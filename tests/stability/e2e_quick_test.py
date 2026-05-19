"""Quick end-to-end test of Phase A pipeline. Run against local backend."""
import json, requests, time

CONTRACT = """买卖合同
甲方（买方）：北京测试科技有限公司
乙方（卖方）：上海设备制造有限公司
第一条 合同标的：乙方向甲方出售水质监测设备一套。
第二条 合同金额：本合同总价款为人民币1535万元整。
第三条 交付：甲方收货地点为北京市辖区范围内。甲方经核对产品数量无误及对产品质量进行初验收并签字确认后，视为乙方已交付。
第六条 质量保证：质保期为36个月，自最终验收合格之日起计算。外观验收不免除乙方内在质量保证责任。
第九条 付款方式：甲方于本合同签订后10日内向乙方支付合同金额的80%作为预付款。质保金为合同金额的5%，以支票形式提交。
第十条 违约责任：乙方逾期交货的，每延期一天向甲方支付合同总价款万分之五的违约金。由此给甲方造成损失的，乙方应承担赔偿责任。
第十三条 争议解决：因本合同引起的争议，向甲方住所地人民法院提起诉讼。"""

print("=== Phase A E2E Test ===")
t0 = time.time()

resp = requests.post(
    "http://localhost:9527/api/v2/review",
    json={"contract_text": CONTRACT, "contract_id": "e2e-phase-a-test", "review_party": "buyer"},
    timeout=600,
)
data = resp.json()
elapsed = time.time() - t0

print(f"Status: {resp.status_code} | Time: {elapsed:.0f}s")
print(f"Generation mode: {data.get('generation_mode')}")

free = data.get("free_review", {})
consistency = data.get("consistency", {})
segments = free.get("risk_segments", [])

print(f"Risk segments: {len(segments)}")
print(f"Counterfactuals: {len(consistency.get('counterfactuals', []))}")
print(f"BN annotations: {len(consistency.get('annotations', []))}")

# Show canonical_type coverage
canonical = [s for s in segments if s.get("canonical_type")]
print(f"Canonicalized: {len(canonical)}/{len(segments)}")
if canonical:
    for s in canonical[:5]:
        print(f"  {s.get('clause_type')} → {s.get('canonical_type')} [{s.get('severity')}]")

# Show narrative excerpt
report = data.get("report", {})
narrative = data.get("polished_report", {}).get("narrative_report", "")
if not narrative:
    # Try alternate path
    narrative = report.get("narrative_report", "")
has_dossier = "Report Dossier" in narrative or "报告事实清单" in narrative
print(f"Narrative length: {len(narrative)} chars | Contains dossier ref: {has_dossier}")

# Print first 300 chars of narrative
print(f"\nNarrative preview:\n{narrative[:400]}...")

print(f"\n=== Test {'PASSED' if resp.status_code == 200 and len(segments) > 0 else 'FAILED'} ===")
