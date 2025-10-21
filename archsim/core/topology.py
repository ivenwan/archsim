from __future__ import annotations

from typing import Dict, List, Tuple

from .link import Link


class Topology:
    def __init__(self) -> None:
        self.resources: Dict[str, object] = {}
        self.links: List[Link] = []

    def add(self, *resources) -> None:
        for r in resources:
            if r.name in self.resources:
                raise ValueError(f"Resource with name '{r.name}' already exists")
            self.resources[r.name] = r

    def get(self, name: str):
        return self.resources[name]

    def connect(
        self,
        src,
        src_port: str,
        dst,
        dst_port: str,
        bandwidth: int = 1,
        latency: int = 1,
        name: str | None = None,
    ) -> Link:
        # Ensure ports exist
        src.add_port(src_port, direction="out")
        dst.add_port(dst_port, direction="in")
        link = Link(src, src_port, dst, dst_port, bandwidth=bandwidth, latency=latency, name=name)
        self.links.append(link)
        return link

    def connect_by_name(
        self,
        src_name: str,
        src_port: str,
        dst_name: str,
        dst_port: str,
        bandwidth: int = 1,
        latency: int = 1,
    ) -> Link:
        src = self.get(src_name)
        dst = self.get(dst_name)
        return self.connect(src, src_port, dst, dst_port, bandwidth=bandwidth, latency=latency)

