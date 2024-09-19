# AMR_RMF_Task_Atomizer

This packages allows to dispatch non-atomic tasks to RMF by preprocessing incomming tasks into atomic "subtasks" which are passed to RMF.

## First steps
Before starting rmf with a new map you need to build a nav graph first. To achieve this run:
```
ros2 run rmf_building_map_tools building_map_generator nav src/amr_rmf/maps/<map_name>/<map_name>.building.yaml src/amr_rmf/maps/<map_name>/nav_graphs/
```
and rebuild the package with colcon