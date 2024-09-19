import uuid
import json
from concurrent.futures import Future, TimeoutError
import rclpy
from rclpy.qos import QoSProfile
from rclpy.qos import QoSHistoryPolicy as History
from rclpy.qos import QoSDurabilityPolicy as Durability
from rclpy.qos import QoSReliabilityPolicy as Reliability
from rmf_task_msgs.msg import ApiRequest, ApiResponse
from amr_rmf_task_atomizer.TaskObject import TaskObject, TaskType


class AmrTaskDispatcher():
    def __init__(self, node):
        self.node = node
        transient_qos = QoSProfile(
            history=History.KEEP_LAST,
            depth=1,
            reliability=Reliability.RELIABLE,
            durability=Durability.TRANSIENT_LOCAL)
        self.pub = self.node.create_publisher(ApiRequest, 'task_api_requests', transient_qos)
        self.latest_msg = None
        self.future = None
        self.result = None
        self.timeout_timer = None  # Timer for timeout checking

    def task_to_rmf_msg(self, task: TaskObject):
        if task.type == TaskType.DELIVERY_SINGLE_DROPOFF:
            msg = self._parse_single_dropoff_delivery(task)
        elif task.type == TaskType.DELIVERY_CHAINED:
            msg = self._parse_chained_dropoff_delivery(task)
        elif task.type == TaskType.PICKUP_TWO_SAME_DROPOFF:
            msg = self._parse_pickup_two_same_dropoff(task)
        elif task.type == TaskType.PICKUP_TWO_DIFFERENT_DROPOFFS:
            msg = self._parse_pickup_two_different_dropoffs(task)

        return msg

    def _parse_single_dropoff_delivery(self, task: TaskObject):
        msg = ApiRequest()
        msg.request_id = task.uuid

        payload = {}
        payload["type"] = "dispatch_task_request"

        request = {}
        now = self.node.get_clock().now().to_msg()
        start_time = now.sec * 1000 + round(now.nanosec / 10**6)
        request["unix_millis_earliest_start_time"] = start_time
        request["category"] = "compose"

        json_description = {}

        json_description["category"] = "multi_delivery"
        json_description["phases"] = []

        activities = []

        # Add the pickup locations with their quantity
        for number, station in enumerate(task.pick_up_places):
            if number % 2 == 0:
                orientation = "front"
            else:
                orientation = "back"

            place = station + "_" + orientation
            activities.append({
                "category": "pickup",
                "description": self._create_pickup_desc(place, station, item_position=orientation)
            })

        # Add the final dropoff
        station = task.drop_off_places[0]
        place = station + "_front"
        quantity = len(task.pick_up_places)
        activities.append({
            "category": "dropoff",
            "description": self._create_dropoff_desc(place, station, item_position="front", quantity=quantity)
        })

        # Add activities to phases
        json_description["phases"].append({"activity": {
            "category": "sequence",
            "description": {"activities": activities}
        }})

        request["description"] = json_description
        payload["request"] = request
        msg.json_msg = json.dumps(payload)

        return msg
    
    def _parse_chained_dropoff_delivery(self, task: TaskObject):
        msg = ApiRequest()
        msg.request_id = task.uuid

        payload = {}
        payload["type"] = "dispatch_task_request"

        request = {}
        now = self.node.get_clock().now().to_msg()
        start_time = now.sec * 1000 + round(now.nanosec / 10**6)
        request["unix_millis_earliest_start_time"] = start_time
        request["category"] = "compose"

        json_description = {}

        json_description["category"] = "multi_delivery"
        json_description["phases"] = []

        activities = []
        # Orientation is always front as we just get one item
        orientation = "front"
        for number, station in enumerate(task.pick_up_places):

            # Create the pickup activity
            place = station + "_" + orientation
            activities.append({
                "category": "pickup",
                "description": self._create_pickup_desc(place, station, item_position=orientation)
            })

            # After each pickup, create the corresponding dropoff activity
            # You can change the logic here depending on where you want the dropoff to happen
            dropoff_station = task.drop_off_places[number % len(task.drop_off_places)]  # Cycle through dropoff places
            dropoff_place = dropoff_station + "_front"
            quantity = 1  # Assuming you drop off the item picked at the corresponding pickup

            activities.append({
                "category": "dropoff",
                "description": self._create_dropoff_desc(dropoff_place, dropoff_station, item_position="front", quantity=quantity)
            })

        # Add activities to phases
        json_description["phases"].append({"activity": {
            "category": "sequence",
            "description": {"activities": activities}
        }})

        request["description"] = json_description
        payload["request"] = request
        msg.json_msg = json.dumps(payload)

        return msg
    
    def _parse_pickup_two_same_dropoff(self, task: TaskObject):
        msg = ApiRequest()
        msg.request_id = task.uuid

        payload = {}
        payload["type"] = "dispatch_task_request"

        request = {}
        now = self.node.get_clock().now().to_msg()
        start_time = now.sec * 1000 + round(now.nanosec / 10**6)
        request["unix_millis_earliest_start_time"] = start_time
        request["category"] = "compose"

        json_description = {}

        json_description["category"] = "multi_delivery"
        json_description["phases"] = []

        activities = []

        # Orientation is front for loading
        orientation = "front"

        # Add a pickup with the quantity of 2
        station = task.pick_up_places[0]
        place = station + "_" + orientation
        activities.append({
            "category": "pickup",
            "description": self._create_pickup_desc(place, station, item_position=orientation, quantity=2)
        })

        # Add a dropoff with the quantity of 2 with orientation back to ensure the correct unloading sequence of items 
        station = task.drop_off_places[0]
        orientation = "back"
        place = station + "_" + orientation

        activities.append({
            "category": "dropoff",
            "description": self._create_dropoff_desc(place, station, item_position=orientation, quantity=2)
        })

        # Add activities to phases
        json_description["phases"].append({"activity": {
            "category": "sequence",
            "description": {"activities": activities}
        }})

        request["description"] = json_description
        payload["request"] = request
        msg.json_msg = json.dumps(payload)

        return msg
    
    def _parse_pickup_two_different_dropoffs(self, task: TaskObject):
        msg = ApiRequest()
        msg.request_id = task.uuid

        payload = {}
        payload["type"] = "dispatch_task_request"

        request = {}
        now = self.node.get_clock().now().to_msg()
        start_time = now.sec * 1000 + round(now.nanosec / 10**6)
        request["unix_millis_earliest_start_time"] = start_time
        request["category"] = "compose"

        json_description = {}

        json_description["category"] = "multi_delivery"
        json_description["phases"] = []

        activities = []

        # Orientation is front for loading
        orientation = "front"

        # Add a pickup with the quantity of 1
        station = task.pick_up_places[0]
        place = station + "_" + orientation
        activities.append({
            "category": "pickup",
            "description": self._create_pickup_desc(place, station, item_position=orientation, quantity=2)
        })

        # Add the 2 dropoffs with the first unloading at the back to preserve the item order
        station = task.drop_off_places[0]
        orientation = "back"
        place = station + "_" + orientation

        activities.append({
            "category": "dropoff",
            "description": self._create_dropoff_desc(place, station, item_position=orientation, quantity=1)
        })

        station = task.drop_off_places[1]
        orientation = "front"
        place = station + "_" + orientation

        activities.append({
            "category": "dropoff",
            "description": self._create_dropoff_desc(place, station, item_position=orientation, quantity=1)
        })

        # Add activities to phases
        json_description["phases"].append({"activity": {
            "category": "sequence",
            "description": {"activities": activities}
        }})

        request["description"] = json_description
        payload["request"] = request
        msg.json_msg = json.dumps(payload)

        return msg

    def _create_pickup_desc(self, place, handler, item_position, quantity: int = 1, identifier: str = "Item"):
        payload = [{"sku": identifier, "quantity": quantity, "compartment": item_position}]

        return {
            "place": place,
            "handler": handler,
            "payload": payload,
        }

    def _create_dropoff_desc(self, place, handler, item_position, quantity: int = 1, identifier: str = "Item"):
        payload = [{"sku": identifier, "quantity": quantity, "compartment": item_position}]

        return {
            "place": place,
            "handler": handler,
            "payload": payload,
        }

    def dispatch_task(self, task: TaskObject):
        msg = self.task_to_rmf_msg(task)
        print(msg)
        self.pub.publish(msg)
        return msg.request_id
