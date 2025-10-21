from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

from .core.simulator import Simulator
from .core.topology import Topology
from .resources.bus import Bus
from .resources.memory import Memory
from .resources.compute import ComputeUnit


def run_example() -> int:
    # Fallback example: same as examples/simple_bus.py
    topo = Topology()
    cpu = ComputeUnit("cpu0", total_requests=20, request_size=64, issue_interval=1)
    bus = Bus("bus", bandwidth=128)
    mem = Memory("memory", latency=10, max_issue_per_tick=1)
    bus.add_input("in_cpu0")
    topo.add(cpu, bus, mem)

    topo.connect(cpu, "out", bus, "in_cpu0", bandwidth=128, latency=1)
    topo.connect(bus, "out", mem, "in", bandwidth=128, latency=1)
    topo.connect(mem, "out", cpu, "in", bandwidth=128, latency=0)

    sim = Simulator(topo)
    sim.run(max_ticks=200)
    print("archsim example run summary:")
    print(sim.metrics.summary())
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return run_example()

    # If an argument is provided, treat it as a Python config to execute
    config_path = Path(argv[0])
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 2

    # Execute the config as a script; it may build and run a simulator
    # If it defines `build(topology: Topology) -> Simulator` we'll run it
    namespace = runpy.run_path(str(config_path))
    builder = namespace.get("build")
    if builder is None:
        print("Config did not define a build(topology)->Simulator function; exiting.")
        return 1

    topo = Topology()
    sim = builder(topo)
    if not isinstance(sim, Simulator):
        print("build() did not return a Simulator; exiting.")
        return 1

    sim.run(max_ticks=500)
    print(sim.metrics.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

