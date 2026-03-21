from typing import List
from datetime import datetime


class ReasoningTrace:
    """
    Lightweight trace logger. Each service creates one instance,
    appends steps as it runs, and returns .steps at the end.
    This satisfies the hackathon's 10% Reasoning Trace criterion.
    """

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.steps: List[str] = []

    def log(self, message: str) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S")
        self.steps.append(f"[{self.service_name}] {ts} — {message}")

    def all(self) -> List[str]:
        return self.steps
