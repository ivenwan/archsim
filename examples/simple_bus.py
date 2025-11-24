from __future__ import annotations

from archsim.core.simulator import Simulator
from archsim.core.topology import Topology
from archsim.resources.read_write_bus import ReadBus
from archsim.resources.compute import ComputeUnit
from archsim.resources.memory import Memory


def build(topo: Topology) -> Simulator:
    cpu = ComputeUnit("cpu0", total_requests=50, request_size=64, issue_interval=1)
    rbus = ReadBus("rbus", read_request_latency=5, data_response_latency=5, data_response_bandwidth=128)
    mem = Memory("memory", latency=10, max_issue_per_tick=1)

    rbus.add_requester("cpu0")
    topo.add(cpu, rbus, mem)

    # Requests: cpu -> rbus -> mem
    topo.connect(cpu, "out", rbus, "in_cpu0", bandwidth=128, latency=1)
    topo.connect(rbus, "out_req", mem, "in", bandwidth=128, latency=1)
    mem.register_inbound_channel(rbus)

    # Responses: mem -> rbus -> cpu
    topo.connect(mem, "out", rbus, "in_mem_resp", bandwidth=128, latency=1)
    topo.connect(rbus, "out_cpu0", cpu, "in", bandwidth=128, latency=0)

    return Simulator(topo)


if __name__ == "__main__":
    sim = build(Topology())
    sim.run(max_ticks=300)
    print(sim.metrics.summary())
