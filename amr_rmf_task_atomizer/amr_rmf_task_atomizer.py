import uuid
import yaml
import threading
import json
import rclpy

from rclpy.node import Node, MutuallyExclusiveCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rcl_interfaces.msg import ParameterDescriptor
from collections import deque

from amr_rmf_task_atomizer.amr_task_dispatcher import AmrTaskDispatcher
from amr_rmf_task_atomizer.RobotObject import RobotObject
from amr_rmf_task_atomizer.StationObject import StationObject
from amr_rmf_task_atomizer.ItemObject import ItemObject
from amr_rmf_task_atomizer.TaskObject import TaskObject, TaskType
from rmf_fleet_msgs.msg import FleetState
from rmf_task_msgs.msg import ApiResponse
from amr_rmf_task_atomizer_msgs.msg import TaskState
from amr_rmf_task_atomizer_msgs.srv import ItemDispatch, ItemStatus
from std_msgs.msg import Int32


class AmrTaskAtomizer(Node):
    available_stations: dict[deque]
    available_robots: dict[deque]
    config_path: str

    def __init__(self):
        """Node which splits up transport orders into atomic tasks for RMF tasks"""
        super().__init__("Task_Atomizer")

        self.task_dispatcher = AmrTaskDispatcher(self)
        self.task_dispatched_event = threading.Event()
        self.dispatched_request_id = None
        self.latest_rmf_id = None


        self.available_stations = {}
        self.available_robots = {}

        # Service allowing for the dispatch of tasks
        self.atomic_task_request_service = self.create_service(
            ItemDispatch, "atomic_task_item_dispatch", self.atomic_item_dispatch_cb
        )

        # Service to provide feedback on the state of the current transport items / task
        self.task_state_service = self.create_service(
            ItemStatus, "atomic_task_item_status", self.atomic_item_status_cb
        )

        # Create publisher for the number of current tasks / items
        self.current_tasks_pub = self.create_publisher(Int32, "open_jobs", 10)

        self.create_subscription(FleetState, "fleet_states", self.fleet_state_cb, 10)

        self.create_subscription(
            TaskState, "amr_atomic_tasks_update", self.atomic_tasks_update_cb, 10
        )
        task_response_cb_group = MutuallyExclusiveCallbackGroup()
        self.create_subscription(ApiResponse, 'task_api_responses', self.task_response_cb, 10, callback_group=task_response_cb_group)
        self.create_timer(5.0, self.check_station_cb)
        self.create_timer(5.0, self._publish_current_tasks)

        self.declare_parameter(
            "config_path",
            "",
            ParameterDescriptor(
                description="Environment file holding the stations and robot fleets available."
            ),
        )

        self.declare_parameter(
            "combine_jobs",
            True,
            ParameterDescriptor(
                description="Whether or not to combine single transfer jobs to a chained or combined delivery task if possible"
            ),
        )

        self.declare_parameter(
            "task_history_length",
            15,
            ParameterDescriptor(
                description="How many tasks to keep in the history"
            ),
        )

        self.get_logger().info("Task Atomizer Node started")

        task_history_length = self.get_parameter("task_history_length").get_parameter_value().integer_value
        self.current_tasks = deque(maxlen=task_history_length)

        config_path = (
            self.get_parameter("config_path").get_parameter_value().string_value
        )

        if config_path == "":
            raise ValueError("No config path given!")

        # Load env yaml
        with open(config_path) as config_file:
            config = yaml.safe_load(config_file)

        if "stations" not in config.keys():
            raise ValueError("No stations given in config file")

        for station_name in config["stations"]:
            self.available_stations[station_name] = deque()

        self.combine_jobs = (
            self.get_parameter("combine_jobs").get_parameter_value().bool_value
        )
    
    def atomic_item_dispatch_cb(self, request, response):
        self.get_logger().info("Got called")

        # Add a transport pair to the given stations
        pair_id = self.add_transport_pair(request.pickup_station, request.dropoff_station)

        if pair_id == None:
            response.success = False
            response.message = "Given Station[s] not part of the available stations!"
            return response
        
        response.success = True
        response.task_id = str(pair_id)
        return response
    
    def atomic_item_status_cb(self, request, response):
        # Check if a task with the given item ID is currently active
        for task in self.current_tasks:
            if request.item_id in task.item_ids_pickup:
                response.success = True
                
                # Get the position of the item in pickup and dropoff id lists
                pickup_index = task.item_ids_pickup.index(request.item_id)
                dropoff_index = task.item_ids_dropoff.index(request.item_id)

                # Get the pickup position and dropoff position of the task
                response.pickup_station = task.pick_up_places[pickup_index]
                response.dropoff_station = task.drop_off_places[dropoff_index]

                # Check if the item is already picked up or dropped off
                if pickup_index < task.item_pick_up_count:
                    response.pickup_done = True
                else:
                    response.pickup_done = False
                
                if dropoff_index < task.item_drop_off_count:
                    response.dropoff_done = True
                else:
                    response.dropoff_done = False
                
                response.task_id = task.task_id
                response.task_status = task.status
                response.robot_id = task.robot_id
                return response
        # If no task was found check if the item is in the stations
        for station_name, station_deque in self.available_stations.items():
            for item in station_deque:
                self.get_logger().info(f"Item ID: {item.pair_id} Request ID: {request.item_id}")
                if item.pair_id == request.item_id and item.pick_up:
                    response.success = True
                    response.message = "Item is waiting to be dispatched as an atomic task"
                    response.pickup_station = station_name
                    return response
        
        response.success = False
        response.message = "Item not found in any task or station"
        return response

    def add_transport_pair(self, station_pickup, station_dropoff)->uuid.UUID:
        
        if station_pickup not in self.available_stations.keys() or station_dropoff not in self.available_stations.keys():
            self.get_logger().error("Given Station[s] not part of the available stations!")
            return None

        # Generate a uuid
        pair_id = uuid.uuid4()
        self.get_logger().info(f"Generated pair ID: {pair_id}")

        # Create two ItemObjects with the same id
        pickup_obj = ItemObject(pair_id, is_pickup=True)
        dropoff_obj = ItemObject(pair_id, is_pickup=False)
        self.available_stations[station_pickup].append(pickup_obj)
        self.available_stations[station_dropoff].append(dropoff_obj)

        return pair_id

    def add_robot(self, robot_id):
        self.available_robots[robot_id] = deque(maxlen=5)

    def check_station_cb(self):
        current_tasks = 0
        for _, station_deque in self.available_stations.items():
            current_tasks += len(station_deque)

        # Check if there are enough stations and robots available
        if len(self.available_stations) < 2 or len(self.available_robots) < 1:
            self.get_logger().info(
                "Cannot atomize tasks. Not enough stations or robots available"
            )
            return

        # Iterate over the stations in the dictionary directly
        for station_name, station_deque in self.available_stations.items():
            if not station_deque:
                continue

            # Get the first available item from the deque
            first_item = station_deque[0]
            if first_item.processed:
                continue

            # Check other stations for a matching pair
            for other_station_name, other_station_deque in self.available_stations.items():
                if station_name == other_station_name:
                    continue  # Skip the same station

                if not other_station_deque:
                    continue

                second_item = other_station_deque[0]
                if (
                    not second_item.processed
                    and first_item.pair_id == second_item.pair_id
                ):
                    # Ensure the first and second items are not marked as processed beforehand
                    if first_item.processed or second_item.processed:
                        continue

                    pickup_station, dropoff_station = self._identify_stations(first_item, station_name, second_item, other_station_name)

                    if self.combine_jobs:
                        self.get_logger().info("Checking for combinations")
                        pickup_stations, dropoff_stations = self._check_for_task_combination(pickup_station, dropoff_station)
                        # Collect all pair IDs for the combined task
                        item_ids_pickup = []
                        item_ids_dropoff = []
                        for station in pickup_stations:
                            for item in self.available_stations[station]:
                                if not item.processed:
                                    item_ids_pickup.append(str(item.pair_id))
                                    item.processed = True
                                    break
                        for station in dropoff_stations:
                            for item in self.available_stations[station]:
                                if not item.processed:
                                    item_ids_dropoff.append(str(item.pair_id))
                                    item.processed = True
                                    break
                    else:
                        pickup_stations = [pickup_station]
                        dropoff_stations = [dropoff_station]
                        item_ids_pickup = [str(self.available_stations[pickup_station][0].pair_id)]
                        item_ids_dropoff = [str(self.available_stations[dropoff_station][0].pair_id)]
                        first_item.processed = True
                        second_item.processed = True
                    # Create a task with the paired items
                    self.get_logger().info(f"Creating task with item ids {item_ids_pickup} and {item_ids_dropoff}")
                    self.create_task(pickup_stations, dropoff_stations, item_ids_pickup, item_ids_dropoff)

                    # Mark both items as processed after creating the task
                    first_item.processed = True
                    second_item.processed = True

                    return  # Return after creating the task

    def _identify_stations(self, first_item: ItemObject, station_name: str, second_item: ItemObject, other_station_name: str):
        if first_item.pick_up == True and second_item.pick_up == False:
            return station_name, other_station_name
        elif first_item.pick_up == False and second_item.pick_up == True:
            return other_station_name, station_name
        else:
            self.get_logger().error(f"Item pair with UUID: {first_item.pair_id} is not correctly initialized!")

    def _check_order(self, first_pickup_station, second_pickup_station, first_dropoff_station, second_dropoff_station):
        if first_pickup_station == second_dropoff_station:
            return [second_pickup_station, first_pickup_station], [second_dropoff_station, first_dropoff_station]
        else:
            return [first_pickup_station, second_pickup_station], [first_dropoff_station, second_dropoff_station]

    def _check_for_task_combination(self, pickup_station, dropoff_station):
        # Check underlaying items in both deques
        if len(self.available_stations[pickup_station]) > 1:
            upcoming_item_pickup = self.available_stations[pickup_station][1]
        else:
            upcoming_item_pickup = None

        if len(self.available_stations[dropoff_station]) > 1:
            upcoming_item_dropoff = self.available_stations[dropoff_station][1]
        else:
            upcoming_item_dropoff = None

        # If there are no underlaying items return the incoming items
        if upcoming_item_pickup == None and upcoming_item_dropoff == None:
            return [pickup_station], [dropoff_station]
        
        # Check if the underlaying items are a pair
        if upcoming_item_pickup != None and upcoming_item_dropoff != None and upcoming_item_pickup.pair_id == upcoming_item_dropoff.pair_id:
                self.get_logger().info("Got underlaying pair!")
                second_pickup, second_dropoff = self._identify_stations(upcoming_item_pickup, pickup_station, upcoming_item_dropoff, dropoff_station)
                return[pickup_station, second_pickup], [dropoff_station, second_dropoff]

        # Check if the underlaying items build a new pair with the remaining stations
        for station_name, station_deque in self.available_stations.items():
            if not station_deque:
                continue

            # Get the first available item from the deque
            first_item = station_deque[0]
            if first_item.processed:
                continue
            
            self.get_logger().info("Checking dropoff item")
            # If the item is upcoming item in the dropoff station is another dropoff we can combine the current item with the upcoming dropoff to create a dual dropoff task
            # If the upcomming item is a pickup we can combine the current item with the upcoming pickup to extend the chain
            if upcoming_item_dropoff != None and first_item.pair_id == upcoming_item_dropoff.pair_id:
                second_pickup, second_dropoff = self._identify_stations(first_item, station_name, upcoming_item_dropoff, dropoff_station)
                self.get_logger().info(f"Found combination with Pickup Stations {[pickup_station, second_pickup]} and Dropoff Stations {[dropoff_station, second_dropoff]}")
                return [pickup_station, second_pickup], [dropoff_station, second_dropoff]
            
            self.get_logger().info("Checking pickup item")
            # Because our stations are FIFO we can only combine the upcoming item on the pickup station if it is a another pickup
            if upcoming_item_pickup != None and first_item.pair_id == upcoming_item_pickup.pair_id and upcoming_item_pickup.pick_up == True :
                second_pickup, second_dropoff = self._identify_stations(first_item, station_name, upcoming_item_pickup, pickup_station)
                self.get_logger().info(f"Found combination with Pickup Stations {[pickup_station, second_pickup]} and Dropoff Stations {[dropoff_station, second_dropoff]}")
                return [pickup_station, second_pickup], [dropoff_station, second_dropoff]
            else:
                self.get_logger().info("Got no combination")
        return [pickup_station], [dropoff_station]
            
    def fleet_state_cb(self, msg):
        for robot in msg.robots:
            if robot.name not in self.available_robots.keys():
                self.get_logger().info(f"Added Robot with ID: {robot.name}")
                self.add_robot(robot.name)
        pass

    def atomic_tasks_update_cb(self, msg):
        # If we get a msg check if the task is in our current tasks
        for task in self.current_tasks:
            if task.task_id == msg.name:
                # Update station representations based on the state of the task
                self.update_task_and_stations(task, msg)

    def update_task_and_stations(self, task: TaskObject, msg: TaskState):
        task.status = msg.status
        task.robot_id = msg.robot_id

        # Check if new pickups or dropoffs happened
        pickup_station_to_pop, items_picked_up, dropoff_station_to_pop, items_dropped_off = task.get_stations_to_clear(msg.pickups_done, msg.dropoffs_done)
        # self.get_logger().info(f"Items picked up: {items_picked_up}")

        if pickup_station_to_pop != None:
            for i in range(0, items_picked_up):
                self.available_stations[pickup_station_to_pop].popleft()
                self.get_logger().info("Popped item")
        if dropoff_station_to_pop != None:
            for i in range(0, items_dropped_off):
                self.available_stations[dropoff_station_to_pop].popleft()
                self.get_logger().info("Popped item")

    def _publish_current_tasks(self):
        msg = Int32()
        # Loop over all stations and count the items
        current_items = 0
        for _, station_deque in self.available_stations.items():
            current_items += len(station_deque)
        # The number of current tasks is the number of items in the stations divided by 2
        current_tasks = current_items // 2
        # If there is one item left in the stations we have a task that is not completed yet
        if current_items % 2 != 0:
            current_tasks += 1
        msg.data = current_tasks
        self.current_tasks_pub.publish(msg)   

    ### RMF Task Msg generation

    def create_task(self, pickup_stations, dropoff_stations, item_ids_pickup, item_ids_dropoff):
        # Create sets from the incoming lists
        pickup_set = set(pickup_stations)
        dropoff_set = set(dropoff_stations)

        if len(dropoff_set) < len(dropoff_stations):
            if len(pickup_set) < len(pickup_stations):
                self.get_logger().info("Creating 1 to 1 Delivery with 2 Items")
                task = TaskObject(TaskType.PICKUP_TWO_SAME_DROPOFF, pick_up_places=pickup_stations, drop_off_places=dropoff_stations, item_ids_pickup=item_ids_pickup, item_ids_dropoff=item_ids_dropoff)
            else:
                self.get_logger().info(f"Creating n to 1 Delivery with Pickups {pickup_stations} and Dropoffs {dropoff_stations}")
                task = TaskObject(TaskType.DELIVERY_SINGLE_DROPOFF, pick_up_places=pickup_stations, drop_off_places=dropoff_stations, item_ids_pickup=item_ids_pickup, item_ids_dropoff=item_ids_dropoff)
        else:
            if len(pickup_set) < len(pickup_stations):
                self.get_logger().info("Creating 1 to 2 Delivery with 2 Items")
                task = TaskObject(TaskType.PICKUP_TWO_DIFFERENT_DROPOFFS, pick_up_places=pickup_stations, drop_off_places=dropoff_stations, item_ids_pickup=item_ids_pickup, item_ids_dropoff=item_ids_dropoff)
            else:
                self.get_logger().info(f"Creating (Chain) Delivery with Pickups {pickup_stations} and Dropoffs {dropoff_stations}")
                task = TaskObject(TaskType.DELIVERY_CHAINED, pick_up_places=pickup_stations, drop_off_places=dropoff_stations, item_ids_pickup=item_ids_pickup, item_ids_dropoff=item_ids_dropoff)

        # Dispatch the task
        self.dispatched_request_id = task.uuid
        self.task_dispatcher.dispatch_task(task)
        self.wait_for_api_response()
        
        # Set the id in the task object
        task.task_id = self.latest_rmf_id
        self.get_logger().debug(f"Got ID: {self.latest_rmf_id}")
        self.latest_rmf_id = None
        self.dispatched_request_id = None

        # Add task to the current tasks to monitor
        self.current_tasks.append(task)

    def wait_for_api_response(self):
        if not self.task_dispatched_event.is_set():
            self.get_logger().info(f"Waiting for answer for task {self.dispatched_request_id}")
            self.task_dispatched_event.wait()
            self.get_logger().info("Got answer!")
        else:
            self.get_logger().info("Already got an answer!")

        self.task_dispatched_event.clear()

    def task_response_cb(self, response_msg: ApiResponse):
        self.get_logger().info(f"Got called for response id {response_msg.request_id}")
        self.get_logger().info(f"Excpected id {self.dispatched_request_id}")
        if self.dispatched_request_id == None:
            return
        if self.dispatched_request_id == response_msg.request_id:
            self.get_logger().info("Should go ahead")
            response_data = json.loads(response_msg.json_msg)
            self.latest_rmf_id = response_data["state"]["booking"]["id"]
            self.task_dispatched_event.set()

    def debug_function(self):
        self.get_logger().info("Debugging")
        self.add_robot("Robot_1")


def main():
    rclpy.init()
    atomizer = AmrTaskAtomizer()

    # Create a MultiThreadedExecutor to run callbacks in parallel
    executor = MultiThreadedExecutor()
    executor.add_node(atomizer)

    # Run the executor
    try:
        atomizer.debug_function()
        executor.spin()
    finally:
        executor.shutdown()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
