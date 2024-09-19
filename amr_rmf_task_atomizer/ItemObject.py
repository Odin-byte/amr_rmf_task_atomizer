

class ItemObject:
    pair_id: str
    is_pickup: bool
    processed: bool

    def __init__(self, pair_id, is_pickup):
        """ItemObject representing a part of a transport job. A job is from 2 items.
           Both ItemObjects share the same pair_id but one is marking the pickup station while the other is indicating the dropoff station.

        Args:
            pair_id (str): A unique uuid to mark the pair of items belonging to the same job
            is_pickup (bool): Indicates wether the item has to be picked up or is a placeholder for dropoff.
        """
        self.pair_id = str(pair_id)
        self.pick_up = is_pickup
        self.processed = False

    