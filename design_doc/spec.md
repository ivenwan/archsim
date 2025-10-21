Let's work on building a computer architecture simulation tool named archsim in python. Archsim is a tick based simulator that simulate a computer system's internal behavior and produce insight of the system's performance bottlenecks, performance and other useful information for improve computer architecture. In Archsim, user can define shared resource, such as shared transmission data bus, share memory, time-sharing compute resource, etc. User can specifies the topology that connects the dataflow among these resources.

add arbiter as a building block in the archisim: arbitor allows data from multiple upstream buses to flow into a single downstream bus. The arbiter has several configrable mode: 1) shared: this mode share the downstream bandwidth among all requesters, the transmission will take longer for every winner by interleaving the transfer. 2) scheduled: this mode schedule the winner after all pending downstream transfers complete, using all bandwidth of the downstream bus. The arbiter scheme of choice affects how the downstream bus can complete the data buffer transfer.

Further differentiate the bus for read bus and write bus. Read bus can be specified for read request latency, data response latency and data response bandwidth. Write bus can be specified for write request latency, write bandwidth and write response latency. Put a default latency of 5 cycles respectively.

let's model the response on response bus.



Let's create data buffer which represents is the abstrate data structure that is transferred from one memory to another through the buses. The data buffer can be specified by 1) size in byte that the the total volume to be transfered. 2) content: which can be default to ramdom bytes to start with. later we will allow user to copy special data in it. The memory can alloc and delloc a data buffer. The memory can report all the allocated data buffer total compacity. When a data buffer is scheduled to trasmit to a memory, the memory will allocate it. When a compute consumes a data buffer, the data buffer in the memory will be delloc.

Actually I think it is better to have a global buffer_pool to book keeping all the dynamic data buffers in the system. data buffer can be create with size and content, can be owned by memory instances, can transfer ownership when transmissed from one memory to another. can be deleted when compute on a data buffer complete. Compute can create new data buffer as well. Please update the code.

create a generator resource which can periodically create a data buffer and transmit to a specified memory. Create two instances of the generator to hook to the two buses in the example.

Create a semaphore station whick keep track of an array of semaphores. the total number of semaphores can be speficied, default to be 32. Each semaphore default to a value 0. The supported operation for semaphores are: 1) "signal" a semaphore by increment the semaphore. 2) "wait" a semaphore: a client can wait a semaphore to become larger than 0. When the semaphore value is larger than 0, the client can decrement the semaphore and grant the wait.

we can model the data buffer's states as: 0) allocated 1) transit 2) arrived 3) responded 4) inuse 5) deallocated. At the state transition, it can trigger designated semaphores' operations.