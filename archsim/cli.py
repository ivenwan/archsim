from __future__ import annotations

import importlib.util
import runpy
import sys
from pathlib import Path

import argparse

from .core.simulator import Simulator
from .core.topology import Topology
from .resources.read_write_bus import ReadBus
from .resources.memory import Memory
from .resources.compute import ComputeUnit
from .display import show_topology


def run_example(args=None) -> int:
    # Fallback example: same as examples/simple_bus.py
    topo = Topology()
    cpu = ComputeUnit("cpu0", total_requests=20, request_size=64, issue_interval=1)
    bus = ReadBus("rbus", read_request_latency=5, data_response_latency=5, data_response_bandwidth=128)
    mem = Memory("memory", latency=10, max_issue_per_tick=1)
    bus.add_requester("cpu0")
    topo.add(cpu, bus, mem)

    topo.connect(cpu, "out", bus, "in_cpu0", bandwidth=128, latency=1)
    topo.connect(bus, "out_req", mem, "in", bandwidth=128, latency=1)
    topo.connect(mem, "out", bus, "in_mem_resp", bandwidth=128, latency=1)
    topo.connect(bus, "out_cpu0", cpu, "in", bandwidth=128, latency=0)

    # Tracing
    tracer = None
    if args and args.trace:
        from .trace import ConsoleTracer, TraceOptions
        tracer = ConsoleTracer(
            TraceOptions(
                every=args.trace_every,
                queues=args.trace_queues,
                links=args.trace_links,
                show_empty=args.trace_show_empty,
            )
        )

    # Print topology before running
    show_topology(topo)
    sim = Simulator(topo, tracer=tracer)
    sim.run(max_ticks=args.max_ticks if args else 200)
    print("archsim example run summary:")
    print(sim.metrics.summary())
    _print_channel_summary(sim)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archsim", add_help=True)
    parser.add_argument("config", nargs="?", help="Python config file with build(topology)->Simulator")
    parser.add_argument("--max-ticks", type=int, default=200, help="Max ticks to run")
    # Tracing flags
    parser.add_argument("--trace", action="store_true", help="Enable per-tick tracing output")
    parser.add_argument("--trace-every", type=int, default=1, help="Print every N ticks")
    parser.add_argument("--trace-queues", action="store_true", help="Trace resource queues")
    parser.add_argument("--trace-links", action="store_true", help="Trace link activity")
    parser.add_argument("--trace-show-empty", action="store_true", help="Include empty queues/links in output")

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not args.config:
        return run_example(args)

    # If an argument is provided, treat it as a Python config to execute
    config_path = Path(args.config)
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

    # Print topology before running
    show_topology(sim.topology)

    # Optional tracing for custom configs as well
    if args.trace:
        from .trace import ConsoleTracer, TraceOptions
        sim.tracer = ConsoleTracer(
            TraceOptions(
                every=args.trace_every,
                queues=args.trace_queues,
                links=args.trace_links,
                show_empty=args.trace_show_empty,
            )
        )

    sim.run(max_ticks=args.max_ticks)
    print(sim.metrics.summary())
    _print_channel_summary(sim)
    return 0


def _print_channel_summary(sim: Simulator) -> None:
    # Print average occupancy for channels
    from .core.channel import Channel

    rows = []
    for name, res in sim.topology.resources.items():
        if isinstance(res, Channel):
            rows.append((name, res.avg_occupancy, res._busy_ticks, res._ticks, res.transfer_mode))
    if not rows:
        return
    print("Channel utilization (avg busy ratio):")
    print("name\tavg\tbusy/ticks\tmode")
    for name, avg, busy, ticks, mode in rows:
        print(f"{name}\t{avg:.2f}\t{busy}/{ticks}\t{mode}")


if __name__ == "__main__":
    raise SystemExit(main())
