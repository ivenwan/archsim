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
   - `python -m archsim examples/buffer_transfer.py`
   - `python -m archsim examples/semaphore_triggers.py`

Per-tick Tracing
- Enable tick-by-tick printouts via CLI flags:
  - `python -m archsim --trace --trace-queues --trace-links --max-ticks 20`
  - Options:
    - `--trace`: turn on tracing
    - `--trace-every N`: print every N ticks (default 1)
    - `--trace-queues`: show per-resource in/out queue lengths
    - `--trace-links`: show per-link bytes moved and pipeline occupancy
    - `--trace-show-empty`: include empty queues/links in output
    - `--max-ticks N`: limit run length for readability

Concepts
- Resource: Active component with input/output ports (e.g., `ComputeUnit`, `Bus`, `Memory`).
- Arbiter: Merges multiple upstream buses/ports into one downstream path.
  - Modes: `shared` (round-robin sharing) and `scheduled` (serve one input fully then switch).
- ReadBus: Read interconnect with `read_request_latency`, `data_response_latency`, and `data_response_bandwidth` (defaults 5, 5, 128).
- WriteBus: Write interconnect with `write_request_latency`, `write_response_latency` (default 5, 5) and `write_bandwidth` (default 128).
- Channel: Base class with `bandwidth` and `latency` used by buses and for arbiter scheduling.
  - `transfer_mode`: `interleaving` (default) or `blocking`.
    - `interleaving`: concurrent initiators share bandwidth; expected arrivals are recalculated when set changes.
    - `blocking`: one transfer uses the channel exclusively; others start after it completes.
- DataBuffer + BufferPool: global buffer tracking
  - `DataBuffer(size, content?)`: data unit moved between memories.
  - `BufferPool`: global registry available as `sim.buffer_pool`, tracks buffer ownership and supports transfer/delete.
  - States: `allocated` → `transit` → `arrived` → `responded` → `inuse` → `deallocated`.
  - Triggers: on state transitions, optional actions can be fired to a `SemaphoreStation`.
    - Attach triggers to a buffer via `buf.triggers = [{"on": "arrived", "action": "signal", "station": "sem", "index": 0}]`.
    - Or register via pool: `sim.buffer_pool.add_trigger(buf.id, {...})`.
    - Actions send `sem_signal`/`sem_wait` messages to the named station.
- SemaphoreStation: counting semaphores with wait/signal
  - Params: `count` (default 32) semaphores initialized to 0.
  - Ops via messages: `sem_wait` and `sem_signal` with `payload={"index": i}`.
  - Behavior: `wait` decrements if value>0 else enqueues; `signal` grants a waiter if present else increments.
- DataBuffer: Abstract data structure moved between memories.
  - Fields: `id`, `size`, optional `content` (defaults to random bytes).
  - Memory lifecycle: on `buffer_transfer` Memory allocates the buffer; on `buffer_consume` Memory deallocates it. Memory exposes `total_allocated_bytes`.
- Link: Directed connection from a resource output port to another resource input port with `bandwidth` (bytes/tick) and `latency` (ticks).
- Message: Data unit that flows through ports/links; carries `src`, `dst`, `size`, and `kind`.
- Topology: Registry of resources and links between their ports.
- Simulator: Coordinates ticking of resources and links, and collects basic metrics.

Extensibility
- Create new resources by subclassing `Resource` and implementing `tick`/`on_receive`.
- Connect components using `Topology.connect(src, src_port, dst, dst_port, bandwidth, latency)`.
- For `ReadBus`/`WriteBus`, register endpoints:
  - ReadBus: `bus.add_requester("cpu0")`; wire `cpu0.out -> bus.in_cpu0`, `bus.out_req -> mem.in`, `mem.out -> bus.in_mem_resp`, `bus.out_cpu0 -> cpu0.in`.
  - WriteBus: `bus.add_writer("cpu0")`; wire `cpu0.out -> bus.in_cpu0`, `bus.out_mem -> mem.in`, `mem.out -> bus.in_mem_resp`, `bus.out_cpu0 -> cpu0.in`.
- DataBuffer usage:
  - Create: `buf = DataBuffer(size=4096)`
  - Send to memory: emit a `Message(kind="buffer_transfer", payload={"buffer": buf.to_dict()})` destined for the memory.
  - Consume: emit `Message(kind="buffer_consume", payload={"buffer_id": buf.id})` to free it.
  - Ownership: Memory adopts ownership on `buffer_transfer` (pool transfer). Compute or other memories can later free via `buffer_consume`.
- Arbiter Scheduling
  - Arbiter can be informed of a downstream `Channel` via `arb.set_downstream_channel(channel)`.
  - On `buffer_transfer` requests, it estimates completion using the channel's bandwidth/latency and records an expected arrival tick in the `BufferPool`.
  - The simulator advances time and the pool updates buffer state to `arrived` when the expected tick is reached.
