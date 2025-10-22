from __future__ import annotations

from typing import Iterable

from .core.topology import Topology
from .core.link import Link
from .core.channel import Channel


def show_topology(topo: Topology) -> None:
    print("archsim topology:")
    # Resources
    print("- resources:")
    for name, res in topo.resources.items():
        kind = res.__class__.__name__
        extra = ""
        if isinstance(res, Channel):
            extra = f" (bw={res.bandwidth}, lat={res.latency}, mode={res.transfer_mode})"
        print(f"  - {name}: {kind}{extra}")
    # Links
    print("- links:")
    for lk in topo.links:
        print(
            f"  - {lk.src.name}:{lk.src_port} -> {lk.dst.name}:{lk.dst_port} (bw={lk.bandwidth}, lat={lk.latency})"
        )

