# Spec: BN Adaptive Confidence & Cross-Contract-Type Evidence Hardening

**Date:** 2026-05-18
**Status:** draft
**Scope:** BN 乘数效应 / 反事实数据的合同类型可信度分层 + 硬编码维度对配置化

---

## 1. Problem Statement

Current v2 pipeline uses the same Bayesian Network model (`bayesian_network_v2.json`, CPT calibrated from CUAD — 510 commercial/purchase contracts) for ALL contract types. This causes:

1. **Misleading precision**: Lease contracts and NDAs get the same "1.55x multiplier" presentation as purchase contracts, but the BN priors are uncalibrated for those domains.
2. **Over-reporting**: Simple contracts (e.g., NDA with 2 risks) still get 4 groups of multiplier analysis and 8 counterfactual items — noise, not signal.
3. **Hardcoded dimension pairs**: `consistency_validator.py:78-85` has 6 fixed pairs queried regardless of contract type. `bn_mapping.py:71-79` has fixed Chinese descriptions for cross-dimension risks.
4. **No extensibility hook**: The architecture supports per-contract-type BN configs (`build_model(config=...)`), but there's no routing to use them.

## 2. Design

### 2.1 Core mechanism: `bn_confidence` tier

Add one field to `config/contract_type_parameters.yaml` under each asset type:

```yaml
standard_equipment:
  bn_confidence: high       # CUAD covers equipment purchase well

custom_equipment:
  bn_confidence: medium     # partial coverage

bulk_commodity:
  bn_confidence: medium     # partial coverage

light_service:
  bn_confidence: low        # CUAD barely covers service contracts
```

When a contract type doesn't match any known asset type, default to `medium`.

### 2.2 Behavior per tier

| Aspect | `high` | `medium` | `low` |
|--------|--------|----------|-------|
| Multiplier pairs queried | All 6 pairs | Top 3 by multiplier | Top 1 only |
| Counterfactual items shown | Up to 8 | Up to 5 | Directional text only, no numbers |
| LLM₂ context framing | "以下量化数据可用于谈判" | "以下数据为方向性参考，请结合具体条款判断" | "本类型合同的量化模型仍在建设中，以下分析以法律判断为主" |
| BN data in report Ch.4 | Full tables with numbers | Simplified tables | Omit numerical tables, show qualitative direction |

### 2.3 Configuration-driven dimension pairs

Move the hardcoded 6 pairs from `consistency_validator.py:78-85` to a new config section in `config/contract_type_parameters.yaml`:

```yaml
bn_dimension_pairs:
  universal:  # always queried regardless of contract type
    - [financial_exposure_risk, clause_balance_risk]
    - [dispute_resolution_risk, legal_enforceability_risk]
  optional:   # only when bn_confidence != low
    - [performance_delivery_risk, legal_enforceability_risk]
    - [financial_exposure_risk, dispute_resolution_risk]
    - [performance_delivery_risk, financial_exposure_risk]
    - [performance_delivery_risk, dispute_resolution_risk]
```

`consistency_validator.py` reads this config and selects pairs based on `bn_confidence`:
- `high` → universal + optional (6 pairs)
- `medium` → universal + top 1 from optional (3 pairs)
- `low` → universal only (2 pairs)

### 2.4 Future contract-type-specific BN configs

Add optional field to `config/contract_type_routing.yaml`:

```yaml
contract_types:
  租赁合同:
    keywords: [...]
    nodes: [...]
    bn_config_override: null  # future: bayesian_network_v2_lease.json
```

`BnMappingService` already accepts `config` parameter in `build_model(config=...)`. When `bn_config_override` is set and the file exists, pass it; otherwise fall back to the default `bayesian_network_v2.json`. No code change needed — this is purely a documentation of the existing extension point.

### 2.5 Cross-dimension risk descriptions

Move the hardcoded `CROSS_DIMENSION_RISK_PAIRS` from `bn_mapping.py:71-79` to a config file or keep inline but add a comment marking it as the "universal fallback." Descriptions remain useful as LLM context hints even when BN numbers are uncertain.

## 3. Files changed

| File | Change |
|------|--------|
| `config/contract_type_parameters.yaml` | Add `bn_confidence` to each asset type; add `bn_dimension_pairs` section |
| `config/contract_type_routing.yaml` | Add `bn_config_override: null` placeholder on each contract type |
| `src/contract_risk_analysis/bn/consistency_validator.py` | Read `bn_confidence` + dimension pairs from config; select pairs dynamically |
| `src/contract_risk_analysis/review/report_writer.py` | Read `bn_confidence`; adjust Ch.2 multiplier display + Ch.4 counterfactual depth + LLM₂ prompt framing |
| `src/contract_risk_analysis/bn/bn_mapping.py` | Add comment on `CROSS_DIMENSION_RISK_PAIRS` noting it's universal fallback |
| `src/contract_risk_analysis/review/quantification.py` | If used for Ch.4 numbers, add `bn_confidence` gating |

## 4. Non-goals

- Changing CPT parameters or BN structure — no new data, no calibration
- Per-contract-type BN config files — spec documents the extension point but doesn't create them
- UI/frontend changes — this is pipeline-only

## 5. Rollback safety

All behavior changes are gated on `bn_confidence`. Setting all types to `high` restores current behavior exactly. The config-driven dimension pairs default to the same 6 pairs when the config key is absent.

## 6. Test strategy

- Unit: `consistency_validator.py` — verify pair selection logic with different `bn_confidence` values and config presence/absence
- Unit: `report_writer.py` — verify that `bn_confidence=low` produces qualitative-only Ch.4, no numerical tables
- Integration: Run the same purchase contract through `bn_confidence=high` and `bn_confidence=low`, diff the reports
- Regression: Existing golden tests must still pass (current behavior = `bn_confidence=high` for standard_equipment)
