from __future__ import annotations

from archsim.core.simulator import Simulator
from archsim.core.topology import Topology
from archsim.core.channel import Channel
from archsim.resources.arbiter import Arbiter
from archsim.resources.generator import BufferGenerator
from archsim.resources.memory import Memory
from archsim.resources.semaphore import SemaphoreStation
from archsim.resources.semaphore_recorder import SemaphoreRecorder


def build(topo: Topology, mode: str = "interleaving") -> Simulator:
    # Two generators producing equal-size buffers staggered in time
    gen0 = BufferGenerator(
        "gen0",
        period=1000,  # single buffer
        buffer_size=4096,
        target_memory="memory",
        start_tick=0,
        total=1,
        triggers=[{"on": "arrived", "action": "signal", "station": "sem", "index": 0}],
    )
    gen1 = BufferGenerator(
        "gen1",
        period=1000,
        buffer_size=4096,
        target_memory="memory",
        start_tick=2,  # starts slightly later
        total=1,
        triggers=[{"on": "arrived", "action": "signal", "station": "sem", "index": 0}],
    )

    arb = Arbiter("arb")
    down = Channel("down", bandwidth=256, latency=5, transfer_mode=mode)
    mem = Memory("memory", latency=0, max_issue_per_tick=8)
    sem = SemaphoreStation("sem", count=4)
    rec = SemaphoreRecorder("rec", station="sem", index=0, start_tick=0)

    topo.add(gen0, gen1, arb, down, mem, sem, rec)

    # Arbiter inputs
    arb.add_input("in0")
    arb.add_input("in1")

    # Connect generators -> arbiter
    topo.connect(gen0, "out", arb, "in0", bandwidth=9999, latency=0)
    topo.connect(gen1, "out", arb, "in1", bandwidth=9999, latency=0)

    # Arbiter -> channel -> memory
    topo.connect(arb, "out", down, "in", bandwidth=9999, latency=0)
    topo.connect(down, "out", mem, "in", bandwidth=9999, latency=0)
    arb.set_downstream_channel(down)
    mem.register_inbound_channel(down)

    # Memory acks back to generators (not needed for arrival measurement but keeps symmetry)
    topo.connect(mem, "out", gen0, "in", bandwidth=9999, latency=0)
    topo.connect(mem, "out", gen1, "in", bandwidth=9999, latency=0)

    # Wire semaphore station <-> recorder
    topo.connect(rec, "out", sem, "in", bandwidth=1, latency=0)
    topo.connect(sem, "out", rec, "in", bandwidth=1, latency=0)

    return Simulator(topo)


if __name__ == "__main__":
    for mode in ("interleaving", "blocking"):
        print(f"\nMode: {mode}")
        sim = build(Topology(), mode=mode)
        sim.run(max_ticks=200)
        rec = sim.topology.get("rec")
        print({"grants": rec.grants})
