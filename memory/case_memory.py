"""Case similarity memory. Using TF-IDF + cosine (sklearn, already a dependency)
instead of sentence-transformers/FAISS from the original plan - avoids a torch
download nobody has time for mid-hackathon. Swap CaseMemory._vectorize if we
ever need real embeddings.
"""
import csv
import json
from pathlib import Path

import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

REPO_ROOT = Path(__file__).resolve().parent.parent
CLOSED_CASES_PATH = REPO_ROOT / "closed_cases_history.csv"
CACHE_DIR = REPO_ROOT / "memory" / ".cache"
ADDED_CASES_PATH = CACHE_DIR / "added_cases.json"


class CaseMemory:
    def __init__(self):
        self.case_id: list[str] = []
        self.text: list[str] = []
        self.outcome: list[str] = []
        self.pattern: list[str] = []
        self.opened_at: list[str] = []
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None

        self._seed_from_closed_cases()
        self._load_added_cases()
        self._fit_base()

    def _seed_from_closed_cases(self) -> None:
        if not CLOSED_CASES_PATH.exists():
            return
        with CLOSED_CASES_PATH.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                self._append(row["case_id"], row["analyst_notes"], row["outcome"], row["pattern"], row["opened_at"])

    def _load_added_cases(self) -> None:
        if not ADDED_CASES_PATH.exists():
            return
        for c in json.loads(ADDED_CASES_PATH.read_text(encoding="utf-8")):
            self._append(c["case_id"], c["text"], c["outcome"], c["pattern"], c.get("opened_at", ""))

    def _append(self, case_id: str, text: str, outcome: str, pattern: str, opened_at: str) -> None:
        self.case_id.append(case_id)
        self.text.append(text or "")
        self.outcome.append(outcome)
        self.pattern.append(pattern)
        self.opened_at.append(opened_at)

    def _fit_base(self) -> None:
        """Fits the vectorizer once. After this, new cases are transform()-ed and
        appended to the matrix rather than refitting - refitting on every add_case
        would recompute IDF over a growing corpus and retroactively shift every
        OTHER case's similarity score as more cases get written during a run
        (observed: a case's similarity to a fixed prior case drifted from 0.42 to
        0.25 purely because 19 unrelated cases got added to the corpus in between)."""
        if not self.text:
            self._vectorizer, self._matrix = None, None
            return
        self._vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        self._matrix = self._vectorizer.fit_transform(self.text)

    def query(self, text: str, k: int = 5, as_of: str | None = None) -> list[dict]:
        """as_of restricts memory to cases opened before the querying case, so an
        HHG case can't retrieve a closed case that hadn't happened yet - moot for
        the closed_cases_history.csv seed (all July-Oct, before the Nov-Dec case
        pack) but matters once the agent starts writing its own cases into memory."""
        if not self._vectorizer:
            return []
        idx = list(range(len(self.text)))
        if as_of:
            idx = [i for i in idx if not self.opened_at[i] or self.opened_at[i] <= as_of]
        if not idx:
            return []

        qvec = self._vectorizer.transform([text])
        sims = cosine_similarity(qvec, self._matrix[idx])[0]
        ranked = sorted(zip(idx, sims), key=lambda p: -p[1])[:k]
        return [
            {"case_id": self.case_id[i], "similarity": round(float(s), 4), "outcome": self.outcome[i], "pattern": self.pattern[i]}
            for i, s in ranked
        ]

    def add_case(self, case_id: str, text: str, outcome: str, pattern: str, opened_at: str, similarity_threshold: float = 0.75) -> list[str]:
        """Adds a new case (persisted to disk) and returns SIMILAR_TO links to
        prior cases scoring above the threshold, using the state before this add.
        Idempotent on case_id - re-running the same case (e.g. run_benchmark
        --no-resume) must not let it match a copy of its own prior write, which
        would also reshuffle the TF-IDF space and make similarity non-deterministic
        across reruns."""
        if case_id in self.case_id:
            # rare path (reprocessing the same case) - a full refit here is fine since
            # it's a one-off correction, not the normal growth pattern
            idx = self.case_id.index(case_id)
            self.text[idx], self.outcome[idx], self.pattern[idx] = text, outcome, pattern
            similar = self.query(text, k=11, as_of=None)
            links = [s["case_id"] for s in similar if s["similarity"] >= similarity_threshold and s["case_id"] != case_id]
            self._fit_base()
        else:
            similar = self.query(text, k=10, as_of=None)
            links = [s["case_id"] for s in similar if s["similarity"] >= similarity_threshold]
            self._append(case_id, text, outcome, pattern, opened_at)
            if self._vectorizer is None:
                self._fit_base()
            else:
                new_vec = self._vectorizer.transform([text])
                self._matrix = sp.vstack([self._matrix, new_vec]) if self._matrix is not None else new_vec

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        existing = json.loads(ADDED_CASES_PATH.read_text(encoding="utf-8")) if ADDED_CASES_PATH.exists() else []
        existing = [c for c in existing if c["case_id"] != case_id]
        existing.append({"case_id": case_id, "text": text, "outcome": outcome, "pattern": pattern, "opened_at": opened_at})
        ADDED_CASES_PATH.write_text(json.dumps(existing, indent=2), encoding="utf-8")

        return links
