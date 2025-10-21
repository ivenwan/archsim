archsim — A tick-based computer architecture simulator

Overview
- archsim simulates shared resources (e.g., buses, memories, compute units) on a discrete tick timeline.
- Users define resources and connect them via a topology to model dataflow and contention.
- The simulator advances in ticks, moving messages along links with bandwidth and latency constraints.

Quick Start
1) Run the built-in example:

   - `python -m archsim`  (runs a simple CPU → Bus → Memory topology)

2) Or run with an explicit example file:

   - `python -m archsim examples/simple_bus.py`

Concepts
- Resource: Active component with input/output ports (e.g., `ComputeUnit`, `Bus`, `Memory`).
- Link: Directed connection from a resource output port to another resource input port with `bandwidth` (bytes/tick) and `latency` (ticks).
- Message: Data unit that flows through ports/links; carries `src`, `dst`, `size`, and `kind`.
- Topology: Registry of resources and links between their ports.
- Simulator: Coordinates ticking of resources and links, and collects basic metrics.

Extensibility
- Create new resources by subclassing `Resource` and implementing `tick`/`on_receive`.
- Connect components using `Topology.connect(src, src_port, dst, dst_port, bandwidth, latency)`.

