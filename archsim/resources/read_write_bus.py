from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional

from ..core.resource import Resource


class ReadBus(Resource):
    """
    ReadBus models a read interconnect that carries:
    - Read requests from multiple requesters toward memory
    - Data responses from memory back to requesters

    Parameters
    - read_request_latency: cycles to traverse the bus for requests (default 5)
    - data_response_latency: cycles to traverse the bus for responses (default 5)
    - data_response_bandwidth: bytes per tick for responses (default 128)

    Ports
    - Per-requester request input: `in_<name>`
    - Memory response input: `in_mem_resp`
    - Request output to memory: `out_req`
    - Per-requester response output: `out_<name>`
    """

    def __init__(
        self,
        name: str,
        read_request_latency: int = 5,
        data_response_latency: int = 5,
        data_response_bandwidth: int = 128,
    ) -> None:
        super().__init__(name)
        if read_request_latency < 0 or data_response_latency < 0:
            raise ValueError("Latencies must be >= 0")
        if data_response_bandwidth <= 0:
            raise ValueError("data_response_bandwidth must be > 0")

        self.read_request_latency = read_request_latency
        self.data_response_latency = data_response_latency
        self.data_response_bandwidth = data_response_bandwidth

        # Ports
        self.add_port("out_req", direction="out")
        self.add_port("in_mem_resp", direction="in")

        # Registered requester names and rr state
        self._requesters: List[str] = []
        self._rr_idx: int = 0

        # Internal pipelines
        self._req_pipeline: List[Deque] = [deque() for _ in range(max(1, read_request_latency))]
        self._resp_pipeline: List[Deque] = [deque() for _ in range(max(1, data_response_latency))]

    def add_requester(self, name: str) -> None:
        if name not in self._requesters:
            self._requesters.append(name)
            self.add_port(f"in_{name}", direction="in")
            self.add_port(f"out_{name}", direction="out")

    # Helpers
    def _next_nonempty_from(self, start: int) -> Optional[int]:
        if not self._requesters:
            return None
        n = len(self._requesters)
        for i in range(n):
            idx = (start + i) % n
            port = f"in_{self._requesters[idx]}"
            q = self.inbox.get(port)
            if q and len(q) > 0:
                return idx
        return None

    def tick(self, sim) -> None:
        # 1) Deliver any ready responses from the last stage to appropriate out_<dst> ports
        if self._resp_pipeline:
            capacity = self.data_response_bandwidth
            last = self._resp_pipeline[-1]
            while last and capacity >= getattr(last[0], "size", 1):
                msg = last.popleft()
                dst = getattr(msg, "dst", None)
                out_port = f"out_{dst}" if dst is not None else "out_unknown"
                # Ensure port exists for late-bound destinations
                if out_port not in self.outbox:
                    self.add_port(out_port, direction="out")
                self.send(out_port, msg)
                capacity -= getattr(msg, "size", 1)

            # Shift response pipeline forward
            for i in range(len(self._resp_pipeline) - 1, 0, -1):
                prev = self._resp_pipeline[i - 1]
                cur = self._resp_pipeline[i]
                while prev:
                    cur.append(prev.popleft())

            # Accept new responses into stage 0 (no limit besides input queue)
            inq = self.inbox.get("in_mem_resp")
            if inq is not None:
                while inq:
                    self._resp_pipeline[0].append(inq.popleft())

        # 2) Deliver any ready requests from last stage to out_req (no bandwidth limit specified)
        if self._req_pipeline:
            last = self._req_pipeline[-1]
            while last:
                self.send("out_req", last.popleft())

            # Shift request pipeline forward
            for i in range(len(self._req_pipeline) - 1, 0, -1):
                prev = self._req_pipeline[i - 1]
                cur = self._req_pipeline[i]
                while prev:
                    cur.append(prev.popleft())

            # Accept new requests into stage 0 with RR across requesters
            if self._requesters:
                start = self._rr_idx
                idx = self._next_nonempty_from(start)
                visited = 0
                moved_any = False
                while idx is not None and visited < len(self._requesters):
                    port = f"in_{self._requesters[idx]}"
                    q = self.inbox.get(port)
                    if q and q:
                        self._req_pipeline[0].append(q.popleft())
                        moved_any = True
                    visited += 1
                    # Find next non-empty
                    nxt = self._next_nonempty_from(idx + 1)
                    if nxt is None:
                        break
                    idx = nxt
                # Advance RR pointer each tick
                self._rr_idx = (start + 1) % len(self._requesters)


class WriteBus(Resource):
    """
    WriteBus models a write interconnect that carries:
    - Write data/requests from multiple writers toward memory (bandwidth-limited)
    - Write responses/acks from memory back to writers

    Parameters
    - write_request_latency: cycles for request/data path (default 5)
    - write_bandwidth: bytes per tick for writer->memory (default 128)
    - write_response_latency: cycles for response path (default 5)

    Ports
    - Per-writer input: `in_<name>` (data/requests)
    - Output to memory: `out_mem`
    - Memory response input: `in_mem_resp`
    - Per-writer response output: `out_<name>`
    """

    def __init__(
        self,
        name: str,
        write_request_latency: int = 5,
        write_bandwidth: int = 128,
        write_response_latency: int = 5,
    ) -> None:
        super().__init__(name)
        if write_request_latency < 0 or write_response_latency < 0:
            raise ValueError("Latencies must be >= 0")
        if write_bandwidth <= 0:
            raise ValueError("write_bandwidth must be > 0")

        self.write_request_latency = write_request_latency
        self.write_bandwidth = write_bandwidth
        self.write_response_latency = write_response_latency

        self.add_port("out_mem", direction="out")
        self.add_port("in_mem_resp", direction="in")

        self._writers: List[str] = []
        self._rr_idx: int = 0

        self._req_pipeline: List[Deque] = [deque() for _ in range(max(1, write_request_latency))]
        self._resp_pipeline: List[Deque] = [deque() for _ in range(max(1, write_response_latency))]

    def add_writer(self, name: str) -> None:
        if name not in self._writers:
            self._writers.append(name)
            self.add_port(f"in_{name}", direction="in")
            self.add_port(f"out_{name}", direction="out")

    def _next_nonempty_from(self, start: int) -> Optional[int]:
        if not self._writers:
            return None
        n = len(self._writers)
        for i in range(n):
            idx = (start + i) % n
            port = f"in_{self._writers[idx]}"
            q = self.inbox.get(port)
            if q and len(q) > 0:
                return idx
        return None

    def tick(self, sim) -> None:
        # 1) Deliver ready responses
        if self._resp_pipeline:
            last = self._resp_pipeline[-1]
            while last:
                msg = last.popleft()
                dst = getattr(msg, "dst", None)
                out_port = f"out_{dst}" if dst is not None else "out_unknown"
                if out_port not in self.outbox:
                    self.add_port(out_port, direction="out")
                self.send(out_port, msg)

            # Shift
            for i in range(len(self._resp_pipeline) - 1, 0, -1):
                prev = self._resp_pipeline[i - 1]
                cur = self._resp_pipeline[i]
                while prev:
                    cur.append(prev.popleft())

            # Accept new responses
            inq = self.inbox.get("in_mem_resp")
            if inq is not None:
                while inq:
                    self._resp_pipeline[0].append(inq.popleft())

        # 2) Deliver ready requests to memory subject to bandwidth
        if self._req_pipeline:
            capacity = self.write_bandwidth
            last = self._req_pipeline[-1]
            while last and capacity >= getattr(last[0], "size", 1):
                msg = last.popleft()
                self.send("out_mem", msg)
                capacity -= getattr(msg, "size", 1)

            # Shift
            for i in range(len(self._req_pipeline) - 1, 0, -1):
                prev = self._req_pipeline[i - 1]
                cur = self._req_pipeline[i]
                while prev:
                    cur.append(prev.popleft())

            # Accept new requests with RR arbitration; enforce bandwidth at egress only
            if self._writers:
                start = self._rr_idx
                idx = self._next_nonempty_from(start)
                visited = 0
                while idx is not None and visited < len(self._writers):
                    port = f"in_{self._writers[idx]}"
                    q = self.inbox.get(port)
                    if q and q:
                        self._req_pipeline[0].append(q.popleft())
                    visited += 1
                    nxt = self._next_nonempty_from(idx + 1)
                    if nxt is None:
                        break
                    idx = nxt
                self._rr_idx = (start + 1) % len(self._writers)

