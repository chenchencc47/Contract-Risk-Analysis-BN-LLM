"""CUAD dataset preprocessing (P6.4).

Extracts and prepares CUAD data for evaluation:
- Unzip CUAD data archive
- Parse SQuAD-style JSON into per-contract clause presence labels
- Export as simplified JSON for benchmark use.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


CUAD_DIR = Path(__file__).resolve().parents[3] / "dataset" / "CUAD"
CUAD_ZIP = CUAD_DIR / "data.zip"
CUAD_JSON = CUAD_DIR / "data" / "CUADv1.json"
OUTPUT_PATH = CUAD_DIR / "data" / "cuad_labels.json"

# Map CUAD category names to our clause types
CATEGORY_TO_CLAUSE: dict[str, str] = {
    "Termination For Convenience": "termination",
    "Notice Period To Terminate Renewal": "termination",
    "Anti-Assignment": "termination",
    "Change Of Control": "termination",
    "Non-Compete": "termination",
    "Exclusivity": "termination",
    "No-Solicit Of Customers": "termination",
    "No-Solicit Of Employees": "termination",
    "Non-Disparagement": "termination",
    "Competitive Restriction Exception": "termination",
    "Rofr/Rofo/Rofn": "termination",
    "Minimum Commitment": "termination",
    "Volume Restriction": "termination",
    "Post-Termination Services": "termination",
    "Source Code Escrow": "termination",
    "Audit Rights": "termination",
    "Third Party Beneficiary": "termination",
    "Most Favored Nation": "termination",
    "Ip Ownership Assignment": "termination",
    "Joint Ip Ownership": "termination",
    "License Grant": "termination",
    "Non-Transferable License": "termination",
    "Affiliate License-Licensor": "termination",
    "Affiliate License-Licensee": "termination",
    "Unlimited/All-You-Can-Eat-License": "termination",
    "Irrevocable Or Perpetual License": "termination",
    "Revenue/Profit Sharing": "termination",
    "Price Restrictions": "termination",
    "Uncapped Liability": "liability_cap",
    "Cap On Liability": "liability_cap",
    "Liquidated Damages": "liability_cap",
    "Insurance": "liability_cap",
    "Warranty Duration": "liability_cap",
    "Covenant Not To Sue": "liability_cap",
    "Governing Law": "governing_law",
    "Document Name": "meta",
    "Parties": "meta",
    "Agreement Date": "meta",
    "Effective Date": "meta",
    "Expiration Date": "meta",
    "Renewal Term": "meta",
}


def preprocess_cuad(output_path: str | Path | None = None) -> list[dict]:
    """Extract CUAD data into a simplified format for evaluation.

    Each output item: {
        "contract_title": str,
        "contract_text": str,
        "clause_labels": {"termination": bool, "liability_cap": bool, ...}
    }

    Returns list of processed contracts.
    """
    out = Path(output_path) if output_path else OUTPUT_PATH

    # Unzip if needed
    if not CUAD_JSON.exists() and CUAD_ZIP.exists():
        print(f"Extracting {CUAD_ZIP}...")
        with zipfile.ZipFile(CUAD_ZIP, "r") as zf:
            zf.extractall(CUAD_DIR / "data")

    if not CUAD_JSON.exists():
        raise FileNotFoundError(f"CUAD data not found at {CUAD_JSON}")

    with open(CUAD_JSON, encoding="utf-8") as f:
        raw = json.load(f)

    contracts = raw.get("data", [])
    processed: list[dict] = []

    for contract in contracts:
        title = contract.get("title", "unknown")
        full_text_parts: list[str] = []
        clause_present: dict[str, bool] = {}

        for para in contract.get("paragraphs", []):
            full_text_parts.append(para.get("context", ""))
            for qa in para.get("qas", []):
                question = qa.get("question", "")
                has_answer = any(a.get("text", "") for a in qa.get("answers", []))
                for cat_name, ct in CATEGORY_TO_CLAUSE.items():
                    if cat_name.lower() in question.lower():
                        if ct not in clause_present:
                            clause_present[ct] = False
                        if has_answer:
                            clause_present[ct] = True

        full_text = "\n".join(full_text_parts)
        processed.append({
            "contract_title": title,
            "contract_text": full_text[:10000],  # truncate for LLM
            "clause_labels": clause_present,
            "text_length": len(full_text),
        })

    # Save
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    # Print stats
    clause_counts: dict[str, int] = {}
    for c in processed:
        for ct, present in c["clause_labels"].items():
            if present:
                clause_counts[ct] = clause_counts.get(ct, 0) + 1

    print(f"Preprocessed {len(processed)} contracts")
    print(f"Saved to {out}")
    print(f"Clause distribution: {json.dumps(clause_counts, ensure_ascii=False)}")

    return processed


def load_cuad_labels() -> list[dict]:
    """Load preprocessed CUAD labels (run preprocess_cuad first)."""
    if not OUTPUT_PATH.exists():
        return preprocess_cuad()
    with open(OUTPUT_PATH, encoding="utf-8") as f:
        return json.load(f)
