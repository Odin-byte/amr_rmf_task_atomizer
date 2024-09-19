from collections import deque

class RobotObject:
    name: str
    last_jobs: deque[str]

    def __init__(self, name: str):
        """A container object representing an available robot, holding its last job ids

        Args:
            name (str): Name of the robot
        """
        self.name = name
        self.last_jobs = deque([], maxlen=5)
