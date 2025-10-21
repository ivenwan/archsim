from __future__ import annotations

from archsim.core.simulator import Simulator
from archsim.core.topology import Topology
from archsim.resources.bus import Bus
from archsim.resources.compute import ComputeUnit
from archsim.resources.memory import Memory


def build(topo: Topology) -> Simulator:
    cpu = ComputeUnit("cpu0", total_requests=50, request_size=64, issue_interval=1)
    bus = Bus("bus", bandwidth=128)
    mem = Memory("memory", latency=10, max_issue_per_tick=1)

    bus.add_input("in_cpu0")
    topo.add(cpu, bus, mem)

    topo.connect(cpu, "out", bus, "in_cpu0", bandwidth=128, latency=1)
    topo.connect(bus, "out", mem, "in", bandwidth=128, latency=1)
    topo.connect(mem, "out", cpu, "in", bandwidth=128, latency=0)

    return Simulator(topo)


if __name__ == "__main__":
    sim = build(Topology())
    sim.run(max_ticks=300)
    print(sim.metrics.summary())

