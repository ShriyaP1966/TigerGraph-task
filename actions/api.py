"""Mock action APIs - what actually 'happens' when an action executes. No real
bank systems behind these, just a description string and a ledger entry."""


def execute_action(action: str, case_id: str, exposure_usd: float = 0) -> str:
    return {
        "ALLOW_TRANSACTION": "transaction allowed to proceed",
        "DECLINE_TRANSACTION": "flagged authorization declined, card stays active",
        "MONITOR_CARD": "card flagged for elevated monitoring for 72 hours",
        "MONITOR_CONNECTED_CARDS": "connected cards flagged for monitoring",
        "WARN_CUSTOMER": "informational message sent to customer",
        "VERIFY_WITH_CUSTOMER": "verification request sent to customer, card stays active",
        "STEP_UP_AUTH": "step-up authentication challenge issued",
        "BLOCK_CARD": "card blocked and reissue queued",
        "BLOCK_ALL_CARDS": "all customer cards blocked and reissue queued",
        "GENERATE_REPORT": "internal report written, no case opened",
        "CREATE_CASE": "case opened and written to the graph",
        "FILE_REPORT": "suspicious activity report filed with the regulator",
        "ESCALATE_TO_ANALYST": "handed to a human fraud analyst",
        "CLOSE_NO_FRAUD": "alert closed as legitimate",
    }.get(action, f"unrecognized action {action}, no-op")
