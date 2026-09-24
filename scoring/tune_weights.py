"""Rough weight-tuning pass against closed_cases_history.csv: builds the same
four component proxies the agent would compute, correlates each against the
confirmed_fraud/cleared label, and suggests weights proportional to |correlation|.
This is a sanity check, not a real training run - eyeball it before touching
config.yaml. TODO: tune again once evidence_coverage reflects real gathering
instead of the flat proxy used here.

Usage: python scoring/tune_weights.py [--sample N]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backends.local import LocalBackend
from memory.case_memory import CaseMemory


def build_features(sample_n: int) -> pd.DataFrame:
    cc = pd.read_csv(REPO_ROOT / "closed_cases_history.csv")
    cc = cc.sample(min(sample_n, len(cc)), random_state=0)

    backend = LocalBackend()
    typologies = {t.typology_id: t.indicators.lower() for t in backend.get_typologies()}

    rows = []
    for _, case in cc.iterrows():
        # first_fraud_txn_id is only populated for confirmed_fraud rows (and pandas reads it
        # as float64, so str() gives "3000120.0" which never matches TransactionID as a
        # string) - txn_ids is populated for every case and its first entry works for both
        first_txn_id = str(case["txn_ids"]).split("|")[0]
        txn_rows = backend.df[backend.df["TransactionID"].astype(str) == first_txn_id]
        bank_risk = float(txn_rows["risk_score"].iloc[0]) if len(txn_rows) and pd.notna(txn_rows["risk_score"].iloc[0]) else 0.2

        notes = str(case["analyst_notes"]).lower()
        typology_match = max((sum(w in notes for w in ind.split()) / max(len(ind.split()), 1) for ind in typologies.values()), default=0.0)

        # k=2 and skip the case's own row - it's literally in the corpus it's being
        # queried against (CaseMemory seeds from this same closed_cases_history.csv),
        # so k=1 always self-matches at similarity 1.0
        sim = [s for s in backend.memory.query(notes, k=2, as_of=case["opened_at"]) if s["case_id"] != case["case_id"]]
        similarity = sim[0]["similarity"] if sim else 0.0

        evidence_coverage = 0.6  # flat proxy - historical cases don't have a real evidence log to measure

        rows.append(
            {
                "bank_risk": bank_risk,
                "typology_match": typology_match,
                "similarity": similarity,
                "evidence_coverage": evidence_coverage,
                "label": 1 if case["outcome"] == "confirmed_fraud" else 0,
            }
        )
    return pd.DataFrame(rows)


def suggest_weights(df: pd.DataFrame) -> dict:
    cols = ["bank_risk", "typology_match", "similarity", "evidence_coverage"]
    corr = {}
    for c in cols:
        r = df[c].corr(df["label"])
        corr[c] = 0.0 if pd.isna(r) else abs(r)  # zero-variance column (e.g. the flat evidence_coverage proxy) -> no signal, not "undefined everything"
    total = sum(corr.values()) or 1.0
    return {c: round(v / total, 3) for c, v in corr.items()}


COL_TO_WEIGHT_KEY = {"bank_risk": "bank_risk", "typology_match": "typology_match", "similarity": "similarity_to_fraud", "evidence_coverage": "evidence_coverage"}


def score(df: pd.DataFrame, weights: dict) -> pd.Series:
    return (
        df["bank_risk"] * weights["bank_risk"]
        + df["typology_match"] * weights["typology_match"]
        + df["similarity"] * weights["similarity_to_fraud"]
        + df["evidence_coverage"] * weights["evidence_coverage"]
    )


def accuracy(df: pd.DataFrame, weights: dict, threshold: float = 0.5) -> float:
    predicted = (score(df, weights) >= threshold).astype(int)
    return float((predicted == df["label"]).mean())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=300)
    ap.add_argument("--apply", action="store_true", help="write suggested weights to config.yaml if they clearly help")
    args = ap.parse_args()

    df = build_features(args.sample)
    print(df.describe())
    print()

    current_weights = {"bank_risk": 0.30, "typology_match": 0.30, "similarity_to_fraud": 0.25, "evidence_coverage": 0.15}
    suggested_raw = suggest_weights(df)
    suggested_weights = {COL_TO_WEIGHT_KEY[c]: w for c, w in suggested_raw.items()}

    acc_before = accuracy(df, current_weights)
    acc_after = accuracy(df, suggested_weights)

    print("current weights:  ", current_weights, f"-> accuracy {acc_before:.3f}")
    print("suggested weights:", suggested_weights, f"-> accuracy {acc_after:.3f}")
    print()

    improvement = acc_after - acc_before
    if improvement >= 0.02:
        print(f"suggested weights improve accuracy by {improvement:+.3f} - clear enough to adopt")
        if args.apply:
            import yaml

            cfg_path = REPO_ROOT / "config.yaml"
            cfg = yaml.safe_load(cfg_path.read_text())
            cfg["confidence_weights"] = suggested_weights
            cfg_path.write_text(yaml.dump(cfg, sort_keys=False))
            print("wrote suggested weights to config.yaml")
        else:
            print("re-run with --apply to write these to config.yaml")
    else:
        print(f"improvement is only {improvement:+.3f} - not clearly better, keeping current config.yaml weights as-is")
