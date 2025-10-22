from __future__ import annotations

from archsim.core.simulator import Simulator
from archsim.core.topology import Topology
from archsim.resources.read_write_bus import ReadBus
from archsim.resources.arbiter import Arbiter
from archsim.resources.compute import ComputeUnit
from archsim.resources.memory import Memory
from archsim.core.channel import Channel
from archsim.resources.generator import BufferGenerator


def build(topo: Topology, mode: str = "shared") -> Simulator:
    # Two compute units, each with its own upstream read bus, merged by an arbiter
    cpu0 = ComputeUnit("cpu0", total_requests=20, request_size=64, issue_interval=1)
    cpu1 = ComputeUnit("cpu1", total_requests=20, request_size=64, issue_interval=1)
    # Generators periodically producing data buffers to memory
    gen0 = BufferGenerator("gen0", period=15, buffer_size=2048, target_memory="memory", start_tick=0, total=10)
    gen1 = BufferGenerator("gen1", period=20, buffer_size=4096, target_memory="memory", start_tick=5, total=10)
    # Per-CPU request read buses (shape request latency)
    rbus0 = ReadBus("rbus0")
    rbus1 = ReadBus("rbus1")
    rbus0.add_requester("cpu0")
    rbus1.add_requester("cpu1")
    rbus0.add_requester("gen0")
    rbus1.add_requester("gen1")
    arb = Arbiter("arb", mode=mode)
    mem = Memory("memory", latency=10, max_issue_per_tick=1)
    # Downstream channel (between arbiter and memory) for scheduling
    down = Channel("downstream", bandwidth=128, latency=5)
    # Response bus to model memory->CPU returns
    rbus_resp = ReadBus("rbus_resp", read_request_latency=5, data_response_latency=5, data_response_bandwidth=128)

    # Register requesters on response bus (for routing by dst)
    rbus_resp.add_requester("cpu0")
    rbus_resp.add_requester("cpu1")
    rbus_resp.add_requester("gen0")
    rbus_resp.add_requester("gen1")

    topo.add(cpu0, cpu1, gen0, gen1, rbus0, rbus1, arb, down, mem, rbus_resp)

    # CPUs -> their read buses (requests)
    topo.connect(cpu0, "out", rbus0, "in_cpu0", bandwidth=128, latency=1)
    topo.connect(cpu1, "out", rbus1, "in_cpu1", bandwidth=128, latency=1)
    # Generators -> read buses (buffer transfers destined to memory)
    topo.connect(gen0, "out", rbus0, "in_gen0", bandwidth=128, latency=1)
    topo.connect(gen1, "out", rbus1, "in_gen1", bandwidth=128, latency=1)

    # Read buses -> arbiter inputs (requests)
    arb.add_input("in0")
    arb.add_input("in1")
    topo.connect(rbus0, "out_req", arb, "in0", bandwidth=128, latency=1)
    topo.connect(rbus1, "out_req", arb, "in1", bandwidth=128, latency=1)

    # Arbiter -> channel -> memory
    topo.connect(arb, "out", down, "in", bandwidth=128, latency=1)
    topo.connect(down, "out", mem, "in", bandwidth=128, latency=1)
    # Inform arbiter of downstream channel for scheduling
    arb.set_downstream_channel(down)

    # Memory responses -> response bus -> CPUs
    topo.connect(mem, "out", rbus_resp, "in_mem_resp", bandwidth=128, latency=1)
    topo.connect(rbus_resp, "out_cpu0", cpu0, "in", bandwidth=128, latency=0)
    topo.connect(rbus_resp, "out_cpu1", cpu1, "in", bandwidth=128, latency=0)
    topo.connect(rbus_resp, "out_gen0", gen0, "in", bandwidth=128, latency=0)
    topo.connect(rbus_resp, "out_gen1", gen1, "in", bandwidth=128, latency=0)

    return Simulator(topo)


if __name__ == "__main__":
    for mode in ("shared", "scheduled"):
        print(f"\nRunning mode={mode}")
        sim = build(Topology(), mode=mode)
        sim.run(max_ticks=400)
        print(sim.metrics.summary())
