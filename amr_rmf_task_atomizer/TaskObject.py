import uuid
from enum import Enum


class TaskType(Enum):
    PICK_UP = 1
    DROP_OFF = 2
    DELIVERY_SINGLE_DROPOFF = 3
    DELIVERY_CHAINED = 4
    PICKUP_TWO_SAME_DROPOFF = 5
    PICKUP_TWO_DIFFERENT_DROPOFFS = 6

class TaskStatus(Enum):
    STATUS_QUEUED = 0
    STATUS_ACTIVE=1
    STATUS_WAITING=2
    STATUS_DONE=3
    STATUS_CANCELED=4

class TaskObject:
    def __init__(self, type: TaskType, pick_up_places: list[str], drop_off_places: list[str], ):
        self.type = type
        self.status = None

        self.pick_up_places = pick_up_places
        self.drop_off_places = drop_off_places

        self.pick_up_places_without_duplicates = list(dict.fromkeys(self.pick_up_places))
        self.drop_off_places_without_duplicates = list(dict.fromkeys(self.drop_off_places))

        self.pickups_done = 0
        self.dropoffs_done = 0
        
        self.uuid = str(uuid.uuid4())
        self.task_id = None

    def get_stations_to_clear(self, pickups_done, dropoffs_done):
        pickup_station_to_clear = None
        dropoff_station_to_clear = None
        pickup_count = 0
        dropoff_count = 0

        # Check if a pickup happened
        if self.pickups_done < pickups_done:
            self.pickups_done = pickups_done
            pickup_station_to_clear = self.pick_up_places_without_duplicates[self.pickups_done - 1]
            # Count total occurrences of this station in the pickup list
            pickup_count = self.pick_up_places.count(pickup_station_to_clear)

        # Check if a dropoff happened
        if self.dropoffs_done < dropoffs_done:
            self.dropoffs_done = dropoffs_done
            dropoff_station_to_clear = self.drop_off_places_without_duplicates[self.dropoffs_done - 1]
            # Count total occurrences of this station in the drop-off list
            dropoff_count = self.drop_off_places.count(dropoff_station_to_clear)

        return pickup_station_to_clear, pickup_count, dropoff_station_to_clear, dropoff_count
