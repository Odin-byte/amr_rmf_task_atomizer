from collections import deque

class StationObject:
    station_name: str
    current_items: deque

    def __init__(self, station_name):
        """Create an instance of a material handling station which can hold a FIFO queue of items for pickup and dropoff

        Args:
            station_name (str): Unique name of the station
            inital_item (ItemObject): ItemObject from the AMR RMF Task Atomizer pkg
        """
        self.station_name = station_name
        self.current_items = deque([])

    def pop_item(self):
        self.current_items.popleft()

    def get_available_item(self):
        """Get the top item of the station

        Returns:
            ItemObject: If an item is available returns a ItemObject, else returns None
        """
        if len(self.current_items) > 0:
            return self.current_items[0]
        else:
            return None
