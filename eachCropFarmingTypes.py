def hayFarmingTypes():
	for i in range(get_world_size()):
		for j in range(get_world_size()):
			if  get_ground_type() != Grounds.Grassland:
				till()
			elif can_harvest():
				harvest()
			move(North)
		move(East)
def woodFarmingTypes():
	for i in range(get_world_size()):
			for j in range(get_world_size()):
				if can_harvest():
					harvest()
					if (i + j) % 2 == 0:
						plant(Entities.Tree)
					else:
						plant(Entities.Bush)
				move(North)
			move(East)
def carrotsFarmingTypes():
	for i in range(get_world_size()):
			for j in range(get_world_size()):
				if get_ground_type() != Grounds.Soil:
					till()
					plant(Entities.Carrot)
				else:
					if can_harvest():
						harvest()
					plant(Entities.Carrot)
				move(North)
			move(East)
	