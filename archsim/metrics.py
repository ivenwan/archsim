from __future__ import annotations


class Metrics:
    def __init__(self) -> None:
        self.ticks: int = 0
        self.messages_delivered: int = 0
        self.bytes_transferred: int = 0

    def summary(self) -> dict:
        return {
            "ticks": self.ticks,
            "messages_delivered": self.messages_delivered,
            "bytes_transferred": self.bytes_transferred,
        }

