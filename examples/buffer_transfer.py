from __future__ import annotations

from archsim.core.simulator import Simulator
from archsim.core.topology import Topology
from archsim.core.databuffer import DataBuffer
from archsim.resources.read_write_bus import WriteBus
from archsim.resources.memory import Memory
from archsim.resources.buffer_io import BufferProducer, BufferConsumer


def build(topo: Topology) -> Simulator:
    # Create a 4KB buffer
    buf = DataBuffer(size=4096)

    # Producer sends buffer to memory at tick 0; consumer frees it at tick 50
    prod = BufferProducer("producer", buffer=buf, target_memory="memory", issue_tick=0)
    cons = BufferConsumer("consumer", buffer_id=buf.id, target_memory="memory", consume_tick=50)
    wbus = WriteBus("wbus", write_request_latency=5, write_bandwidth=256, write_response_latency=5)
    mem = Memory("memory", latency=10, max_issue_per_tick=4)

    # Register endpoints as writers on WriteBus for routing
    wbus.add_writer("producer")
    wbus.add_writer("consumer")

    topo.add(prod, cons, wbus, mem)

    # Requests to memory: producer/consumer -> wbus -> mem
    topo.connect(prod, "out", wbus, "in_producer", bandwidth=256, latency=1)
    topo.connect(cons, "out", wbus, "in_consumer", bandwidth=64, latency=1)
    topo.connect(wbus, "out_mem", mem, "in", bandwidth=256, latency=1)

    # Acks from memory: mem -> wbus -> endpoints
    topo.connect(mem, "out", wbus, "in_mem_resp", bandwidth=256, latency=1)
    topo.connect(wbus, "out_producer", prod, "in", bandwidth=128, latency=0)
    topo.connect(wbus, "out_consumer", cons, "in", bandwidth=128, latency=0)

    return Simulator(topo)


if __name__ == "__main__":
    sim = build(Topology())
    # Run with limited ticks for demo
    sim.run(max_ticks=120)
    # Access memory resource to report total capacity (should be 0 after consume)
    mem = sim.topology.get("memory")
    print({"ticks": sim.ticks, "memory_allocated_bytes": mem.total_allocated_bytes})

