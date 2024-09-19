import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
import asyncio
import websockets
import json
from typing import Callable, Dict, List, Optional, Tuple
from amr_rmf_task_atomizer_msgs.msg import TaskState, TaskStatus

class RmfMsgType:
    FleetState = "fleet_state_update"
    TaskState = "task_state_update"
    TaskLog = "task_log_update"
    FleetLog = "fleet_log_update"

STATUS_MAPPING = {
    "queued": TaskStatus.STATUS_QUEUED,
    "underway": TaskStatus.STATUS_ACTIVE,
    "standby": TaskStatus.STATUS_WAITING,
    "completed": TaskStatus.STATUS_DONE,
    "canceled": TaskStatus.STATUS_CANCELED
}

def filter_rmf_msg(
        json_str: str,
        filters: Dict[RmfMsgType, List[str]] = {}
) -> Optional[Tuple[RmfMsgType, Dict]]:
    obj = json.loads(json_str)
    if "type" not in obj:
        print("ERROR: type is not available as JSON key")
        return None

    if obj["type"] not in filters:
        return None

    msg_type = obj["type"]
    data = obj["data"]
    if not filters[msg_type]:  # empty list
        return msg_type, data

    for filter in filters[msg_type]:
        if filter not in data:
            print(f"Key ERROR!!, indicated data_filter: [{filter}] is not available in {data}")
            return None

        data = data[filter]
    return msg_type, data

class AsyncRmfMsgObserver:
    def __init__(self,
                 callback_fn: Callable[[dict], None],
                 server_url: str = "ws://localhost",
                 server_port: str = "7878",
                 msg_filters: Dict[RmfMsgType, List[str]] = {}):
        self.callback_fn = callback_fn
        self.server_url = server_url
        self.server_port = server_port
        self.msg_filters = msg_filters
        self.future = asyncio.Future()

    async def __msg_handler(self, websocket, path):
        try:
            async for message in websocket:
                ret_data = filter_rmf_msg(message, self.msg_filters)
                if ret_data:
                    msg_type, data = ret_data
                    if msg_type == RmfMsgType.TaskState:
                        asyncio.create_task(self.callback_fn(data))  # Non-blocking callback with asyncio task
        except Exception as e:
            print(f"Error in WebSocket connection: {e}")

    async def run(self):
        print("Starting WebSocket server")
        async with websockets.serve(self.__msg_handler, self.server_url, self.server_port):
            await asyncio.Future()  # Keep the server running indefinitely

class TaskPublisherNode(Node):
    def __init__(self):
        super().__init__("task_publisher")
        
        # Declare parameters
        self.declare_parameter("server_url", "localhost")
        self.declare_parameter("port", 7878)
        self.declare_parameter("msg_filters", [])

        # Get parameters
        self.server_url = self.get_parameter("server_url").get_parameter_value().string_value
        self.port = self.get_parameter("port").get_parameter_value().integer_value
        self.msg_filters = self.get_parameter("msg_filters").get_parameter_value().string_array_value

        self.publisher = self.create_publisher(TaskState, "amr_atomic_tasks_update", 10)
        print(f"Node configured with server_url: {self.server_url}, port: {self.port}, msg_filters: {self.msg_filters}")

    async def count_pickups_and_dropoffs_done(self, task_data):
        """ This is now an async function to allow asynchronous computation if needed """
        pickup_completed = 0
        dropoff_completed = 0

        # Safely access 'phases' with .get() and check if it's a dictionary
        phases = task_data.get("phases")
        
        if not isinstance(phases, dict):
            # This happens when external requests are checked or requests are queued
            self.get_logger().debug(f"No valid 'phases' found in task_data: {task_data}")
            return pickup_completed, dropoff_completed  # Return 0, 0 if 'phases' is missing or not valid

        
        # Iterate over each phase
        for _, phase in phases.items():
            # Iterate over the events in each phase
            for _, event in phase['events'].items():
                # Look for 'Pick up' and 'Drop Off' events
                event_name = event['name'].lower()
                if event_name == 'pick up' and event['status'] == 'completed':
                    pickup_completed += 1
                elif event_name == 'drop off' and event['status'] == 'completed':
                    dropoff_completed += 1
    
        return pickup_completed, dropoff_completed

    def get_status_value(self, status_str):
        return STATUS_MAPPING.get(status_str.lower(), TaskStatus.STATUS_QUEUED)

    async def publish_task_state(self, task_data):
        """ Convert to an async function """
        task_state_msg = TaskState()
        task_state_msg.name = task_data["booking"]["id"]
        task_state_msg.category = task_data["category"]
        task_state_msg.fleet_id = task_data["assigned_to"]["group"]
        task_state_msg.robot_id = task_data["assigned_to"]["name"]

        # Await pickup and dropoff count in case it's time-consuming
        if task_state_msg.category == "multi_delivery":
            task_state_msg.pickups_done, task_state_msg.dropoffs_done = await self.count_pickups_and_dropoffs_done(task_data)

        status = TaskStatus()
        status.status = self.get_status_value(task_data["status"])
        task_state_msg.status = status

        self.publisher.publish(task_state_msg)  # Publishing is still fast, so no need for async

async def ros_spin(executor):
    """Async function to spin ROS 2 nodes."""
    while rclpy.ok():
        executor.spin_once(timeout_sec=0.1)
        await asyncio.sleep(0.01)  # Prevent blocking

async def main_async():
    rclpy.init()
    task_publisher_node = TaskPublisherNode()
    executor = MultiThreadedExecutor()

    # Add the node to the executor
    executor.add_node(task_publisher_node)

    # Create the WebSocket observer
    observer = AsyncRmfMsgObserver(
        callback_fn=task_publisher_node.publish_task_state,
        server_url=task_publisher_node.server_url,
        server_port=str(task_publisher_node.port),
        msg_filters={RmfMsgType.TaskState: task_publisher_node.msg_filters}
    )

    # Run ROS spinning and WebSocket server in parallel
    await asyncio.gather(
        ros_spin(executor),
        observer.run()
    )

def main():
    try:
        # Start the asyncio loop and run both WebSocket and ROS
        asyncio.run(main_async())
    finally:
        rclpy.shutdown()

if __name__ == "__main__":
    main()
