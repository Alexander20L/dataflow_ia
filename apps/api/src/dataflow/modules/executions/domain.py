from dataflow.modules.executions.contracts import RunState


def failure_state(attempts: int, maximum: int, retryable: bool) -> RunState:
    return "queued" if retryable and attempts < maximum else "failed"


def legacy_state(state: RunState) -> str:
    return "processing" if state == "running" else state
