"""LocalBackend: pandas + networkx over the real IEEE-CIS-derived data, no
TigerGraph needed. Builds a small BFS-bounded graph per query instead of one
giant graph over all 590k transactions.
"""
import json
import os
from pathlib import Path

import networkx as nx
import pandas as pd
import yaml
from dotenv import load_dotenv

from backends.base import GraphBackend
from contracts.tool_contracts import (
    AccountSubgraphOutput,
    Edge,
    FraudRingOutput,
    PolicyClause,
    PriorSimilarCasesOutput,
    SimilarCase,
    TransactionVelocityOutput,
    Typology,
    TxnSummary,
    WriteCaseOutput,
)
from memory.case_memory import CaseMemory

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
_CFG = yaml.safe_load((REPO_ROOT / "config.yaml").read_text())["graph"]

TXN_COLS = [
    "TransactionID", "TransactionDT", "TransactionAmt", "ProductCD",
    "card1", "card2", "card3", "card4", "card5", "card6",
    "addr1", "addr2", "P_emaildomain", "customer_id", "ts", "channel", "risk_score",
]
TXN_DTYPES = {
    "TransactionID": "int32", "TransactionDT": "int32", "TransactionAmt": "float32",
    "card1": "int32", "card2": "float32", "card3": "float32", "card5": "float32",
    "addr1": "float32", "addr2": "float32", "risk_score": "float32",
    "ProductCD": "category", "card4": "category", "card6": "category",
    "P_emaildomain": "category", "customer_id": "category", "channel": "category",
}
ID_COLS = ["TransactionID", "DeviceInfo", "id_30", "id_31", "id_33", "id_15"]
CARD_COLS = ["card1", "card2", "card3", "card4", "card5", "card6"]
DEVICE_FIELDS = ["DeviceInfo", "id_30", "id_31", "id_33"]

SHARE_COLS = [
    ("device_key", "SHARES_DEVICE"),
    ("P_emaildomain", "SHARES_EMAIL"),
    ("addr1", "SHARES_ADDRESS"),
]


def account_key(customer_id: str) -> str:
    """the one place account identity is defined - this dataset already ships real customer_ids"""
    return customer_id


def _card_key(row) -> str:
    """nan != nan, so a tuple of raw floats is a bad dict key - stringify instead"""
    return "|".join(str(getattr(row, c)) for c in CARD_COLS)


def _load_transactions() -> pd.DataFrame:
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    csv_path = data_dir / "transactions.csv"
    parquet_path = data_dir / "transactions.parquet"
    sample_rows = os.environ.get("SAMPLE_ROWS")
    sample_rows = int(sample_rows) if sample_rows else None

    if parquet_path.exists() and not sample_rows:
        return pd.read_parquet(parquet_path)

    chunks = [chunk for chunk in pd.read_csv(csv_path, usecols=TXN_COLS, dtype=TXN_DTYPES, chunksize=100_000, nrows=sample_rows)]
    df = pd.concat(chunks, ignore_index=True)
    df["ts"] = pd.to_datetime(df["ts"])

    if not sample_rows:
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(parquet_path)
    return df


def _load_identity() -> pd.DataFrame:
    idn = pd.read_csv(REPO_ROOT / "identity.csv", usecols=ID_COLS)
    idn["TransactionID"] = idn["TransactionID"].astype("int32")
    return idn


def _device_key(df: pd.DataFrame) -> pd.Series:
    non_null = df[DEVICE_FIELDS].notna().sum(axis=1)
    combined = df[DEVICE_FIELDS].fillna("?").astype(str).agg("|".join, axis=1)
    return combined.where(non_null >= _CFG["device_min_fields"])


def _common_values(df: pd.DataFrame, col: str) -> set:
    """entity values shared by more accounts than the cap - too common to be a useful link
    (the gmail.com problem, or a generic 'Windows | Chrome 63' device combo)"""
    cap = _CFG["address_max_shared_degree"] if col == "addr1" else _CFG["max_shared_degree"]
    degree = df.dropna(subset=[col]).groupby(col, observed=True)["customer_id"].nunique()
    return set(degree[degree > cap].index)




class LocalBackend(GraphBackend):
    def __init__(self):
        df = _load_transactions()
        idn = _load_identity()
        df = df.merge(idn, on="TransactionID", how="left")
        df["device_key"] = _device_key(df)

        self.df = df
        self.common_devices = _common_values(df, "device_key")
        self.common_emails = _common_values(df, "P_emaildomain")
        self.common_addrs = _common_values(df, "addr1")

        self._confirmed_fraud_accounts = self._load_confirmed_fraud_accounts()
        self.memory = CaseMemory()
        self._open_cases_path = REPO_ROOT / "memory" / ".cache" / "open_cases.json"
        self._open_cases = self._load_open_cases()

    def _load_confirmed_fraud_accounts(self) -> set:
        path = REPO_ROOT / "closed_cases_history.csv"
        if not path.exists():
            return set()
        cc = pd.read_csv(path, usecols=["customer_id", "outcome"])
        return set(cc.loc[cc["outcome"] == "confirmed_fraud", "customer_id"])

    def _load_open_cases(self) -> dict:
        if self._open_cases_path.exists():
            return json.loads(self._open_cases_path.read_text(encoding="utf-8"))
        return {}

    def _account_window(self, account_id: str, as_of: str | None) -> pd.DataFrame:
        sub = self.df[self.df["customer_id"] == account_id]
        if as_of:
            sub = sub[sub["ts"] <= pd.Timestamp(as_of)]
        sub = sub.sort_values("ts")
        if len(sub) == 0:
            return sub
        cutoff = sub["ts"].max() - pd.Timedelta(days=_CFG["case_window_days"])
        sub = sub[sub["ts"] >= cutoff]
        if len(sub) > _CFG["case_max_txns"]:
            sub = sub.tail(_CFG["case_max_txns"])
        return sub

    def _synth_card_ids(self, account_id: str, win: pd.DataFrame) -> dict[str, str]:
        seen: dict[str, str] = {}
        for row in win.sort_values("ts").itertuples():
            key = _card_key(row)
            if key not in seen:
                seen[key] = f"{account_id}-K{len(seen) + 1}"
        return seen

    def get_account_subgraph(self, account_id: str, as_of: str | None = None, card_id: str | None = None) -> AccountSubgraphOutput:
        win = self._account_window(account_id, as_of)
        if win.empty:
            return AccountSubgraphOutput(accounts=[account_id], transactions=[], cards=[], devices=[], emails=[], addresses=[], edges=[])

        card_map = self._synth_card_ids(account_id, win)
        cutoff = pd.Timestamp(as_of) if as_of else win["ts"].max()

        txns = [
            TxnSummary(
                txn_id=str(r.TransactionID),
                ts=r.ts.isoformat(),
                amount=float(r.TransactionAmt),
                product_cd=str(r.ProductCD),
                channel=str(r.channel),
                risk_score=float(r.risk_score) if pd.notna(r.risk_score) else None,
                card_id=card_map[_card_key(r)],
                device_new=(r.id_15 == "New") if pd.notna(getattr(r, "id_15", None)) else None,
                addr1=str(r.addr1) if pd.notna(r.addr1) else None,
            )
            for r in win.itertuples()
        ]

        edges = []
        common_by_col = {"device_key": self.common_devices, "P_emaildomain": self.common_emails, "addr1": self.common_addrs}
        ring_window = pd.Timedelta(days=_CFG["ring_window_days"])
        sub = self.df[(self.df["ts"] <= cutoff) & (self.df["ts"] >= cutoff - ring_window)]
        near = win[win["ts"] >= cutoff - ring_window]
        for col, edge_type in SHARE_COLS:
            for val in near[col].dropna().unique():
                if val in common_by_col[col]:
                    continue
                sharers = sub.loc[(sub[col] == val) & (sub["customer_id"] != account_id), "customer_id"].unique()
                for other in sharers:
                    edges.append(Edge(src=account_id, dst=str(other), type=edge_type))

        return AccountSubgraphOutput(
            accounts=[account_id],
            transactions=txns,
            cards=sorted(set(card_map.values())),
            devices=sorted(win["device_key"].dropna().unique().tolist()),
            emails=sorted(win["P_emaildomain"].dropna().astype(str).unique().tolist()),
            addresses=sorted(win["addr1"].dropna().astype(str).unique().tolist()),
            edges=edges,
        )

    def find_fraud_ring(self, account_id: str, as_of: str | None = None, card_id: str | None = None) -> FraudRingOutput:
        acct_rows = self.df[self.df["customer_id"] == account_id]
        if acct_rows.empty:
            return FraudRingOutput(ring_id="", size=1, members=[account_id], known_fraud_count=0, shared_via=[])
        cutoff = pd.Timestamp(as_of) if as_of else acct_rows["ts"].max()
        sub = self.df[self.df["ts"] <= cutoff]
        window = pd.Timedelta(days=_CFG["ring_window_days"])

        common_by_col = {"device_key": self.common_devices, "P_emaildomain": self.common_emails, "addr1": self.common_addrs}
        g = nx.Graph()
        g.add_node(account_id)
        # frontier maps account -> the timestamp its link into the ring was discovered at, so each
        # hop only looks at that account's activity NEAR that moment, not its whole history - a
        # heavy customer's 6 months of transactions would otherwise multiplicatively explode the ring
        frontier = {account_id: cutoff}
        visited = {account_id}

        for _hop in range(2):
            next_frontier: dict = {}
            for cid, anchor in frontier.items():
                rows = sub[(sub["customer_id"] == cid) & (sub["ts"] >= anchor - window) & (sub["ts"] <= anchor + window)]
                for col, edge_type in SHARE_COLS:
                    for val in rows[col].dropna().unique():
                        if val in common_by_col[col]:
                            continue
                        sharer_rows = sub[(sub[col] == val) & (sub["customer_id"] != cid) & (sub["ts"] >= anchor - window) & (sub["ts"] <= anchor + window)]
                        for other, other_ts in zip(sharer_rows["customer_id"], sharer_rows["ts"]):
                            g.add_edge(cid, other, type=edge_type)
                            if other not in visited:
                                next_frontier[other] = other_ts
            visited |= set(next_frontier)
            frontier = next_frontier
            if not frontier:
                break

        if account_id not in g or g.degree(account_id) == 0:
            return FraudRingOutput(ring_id="", size=1, members=[account_id], known_fraud_count=0, shared_via=[])

        members = sorted(str(m) for m in nx.node_connected_component(g, account_id))
        shared_via = sorted({d["type"] for _, _, d in g.edges(members, data=True)})
        known_fraud = sum(1 for m in members if m in self._confirmed_fraud_accounts)

        return FraudRingOutput(
            ring_id=f"RING-{account_id}",
            size=len(members),
            members=members,
            known_fraud_count=known_fraud,
            shared_via=shared_via,
        )

    def get_transaction_velocity(self, account_id: str, window_hours: float, as_of: str | None = None, card_id: str | None = None) -> TransactionVelocityOutput:
        win = self._account_window(account_id, as_of)
        if win.empty:
            return TransactionVelocityOutput(count=0, sum_amount=0, max_amount=0, z_score=0, baseline_mean=0, baseline_std=0)

        cutoff = pd.Timestamp(as_of) if as_of else win["ts"].max()
        window = win[win["ts"] > cutoff - pd.Timedelta(hours=window_hours)]

        amounts = win["TransactionAmt"]
        mean = float(amounts.mean())
        std = float(amounts.std(ddof=0)) or 1.0
        window_sum = float(window["TransactionAmt"].sum())

        return TransactionVelocityOutput(
            count=len(window),
            sum_amount=window_sum,
            max_amount=float(window["TransactionAmt"].max()) if len(window) else 0.0,
            z_score=(window_sum - mean) / std,
            baseline_mean=mean,
            baseline_std=std,
        )

    def get_prior_similar_cases(self, case_text: str, k: int = 5, as_of: str | None = None) -> PriorSimilarCasesOutput:
        results = self.memory.query(case_text, k=k, as_of=as_of)
        return PriorSimilarCasesOutput(results=[SimilarCase(**r) for r in results])

    def get_policy_context(self, topic: str) -> list[PolicyClause]:
        # only 19 short clauses total - a topic filter risks dropping something relevant
        # (e.g. "risk_score" as a topic string literal-matches POL-001 and nothing else,
        # excluding R1/POL-004 which is exactly the rule that applies to risk_score-only
        # triggers) for no real benefit, so just return the whole policy every time
        clauses = json.loads((REPO_ROOT / "docs" / "policy" / "chunks" / "policy_clauses.json").read_text(encoding="utf-8"))
        return [PolicyClause(clause_id=c["id"], text=c["text"]) for c in clauses]

    def get_typologies(self) -> list[Typology]:
        typ = json.loads((REPO_ROOT / "docs" / "policy" / "chunks" / "typologies.json").read_text(encoding="utf-8"))
        return [Typology(typology_id=t["id"], name=t["title"], indicators=t["text"]) for t in typ]

    def find_open_case(self, entity_id: str) -> str | None:
        return self._open_cases.get(entity_id)

    def write_case(self, case_id: str, case_json: str, opened_at: str | None = None) -> WriteCaseOutput:
        case = json.loads(case_json)
        c = case.get("case", {})
        text = c.get("summary", "") + " " + " ".join(e.get("claim", "") for e in c.get("evidence", []))
        outcome = {"fraud": "confirmed_fraud", "legitimate": "cleared", "uncertain": "uncertain"}.get(c.get("verdict"), "uncertain")

        links = self.memory.add_case(case_id, text, outcome, c.get("pattern", "none"), opened_at=opened_at or pd.Timestamp.now().isoformat())

        self._open_cases_path.parent.mkdir(parents=True, exist_ok=True)
        self._open_cases_path.write_text(json.dumps(self._open_cases, indent=2), encoding="utf-8")

        return WriteCaseOutput(written=True, graph_case_id=f"LOCAL-{case_id}", similar_to=links)
