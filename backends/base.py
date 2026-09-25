from abc import ABC, abstractmethod

from contracts.tool_contracts import (
    AccountSubgraphOutput,
    FraudRingOutput,
    PolicyClause,
    PriorSimilarCasesOutput,
    Typology,
    TransactionVelocityOutput,
    WriteCaseOutput,
)


class GraphBackend(ABC):
    # card_id is an optional hint: this dataset's real graph (TigerGraph) is
    # card-keyed, not customer-keyed, so account_id alone isn't enough to call it. The
    # agent has the real card_id from case_pack.csv for the case's own account; Mock/Local
    # ignore the hint since their own methods are already customer-keyed.
    @abstractmethod
    def get_account_subgraph(self, account_id: str, as_of: str | None = None, card_id: str | None = None) -> AccountSubgraphOutput: ...

    @abstractmethod
    def find_fraud_ring(self, account_id: str, as_of: str | None = None, card_id: str | None = None) -> FraudRingOutput: ...

    @abstractmethod
    def get_transaction_velocity(self, account_id: str, window_hours: float, as_of: str | None = None, card_id: str | None = None) -> TransactionVelocityOutput: ...

    @abstractmethod
    def get_prior_similar_cases(self, case_text: str, k: int = 5, as_of: str | None = None) -> PriorSimilarCasesOutput: ...

    @abstractmethod
    def get_policy_context(self, topic: str) -> list[PolicyClause]: ...

    @abstractmethod
    def get_typologies(self) -> list[Typology]: ...

    @abstractmethod
    def find_open_case(self, entity_id: str) -> str | None: ...

    @abstractmethod
    def write_case(self, case_id: str, case_json: str, opened_at: str | None = None) -> WriteCaseOutput: ...
