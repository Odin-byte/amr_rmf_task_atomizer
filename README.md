# AMR_RMF_Task_Atomizer

This packages allows to dispatch non-atomic tasks to RMF by preprocessing incomming tasks into atomic "subtasks" which are passed to RMF.

## Functionality
This package provides an additional ros2 node holding an internal state representing every station within the environment as a FIFO queue.
Items can be dispatched to this node by calling the provided dispatch service.
The current state of an item can also be requested by calling the provided service using the item id returned when dispatching an item.

## Dependencies
This package relies on another package holding the needed task and msg definitions called
```
amr_rmf_task_atomizer_msgs
```

