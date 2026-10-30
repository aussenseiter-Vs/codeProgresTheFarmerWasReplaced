from eachCropFarmingTypes import hayFarmingTypes, woodFarmingTypes, carrotsFarmingTypes

cropYields = [8, 200, 8]
items = [Items.Hay, Items.Wood, Items.Carrot]
funcs = [hayFarmingTypes, woodFarmingTypes, carrotsFarmingTypes]

def getHighestCount():
	highest = 0
	for item in items:
		count = num_items(item)
		if count > highest:
			highest = count
	return highest

def getValidActiveIndex(gapForEachCrops):
	hayCount = num_items(items[0])
	woodCount = num_items(items[1])
	carrotCount = num_items(items[2])
	
	if carrotCount <= hayCount and carrotCount <= woodCount:
		requiredAmount = (carrotCount * 2) + gapForEachCrops
		if hayCount >= requiredAmount and woodCount >= requiredAmount:
			return 2
		else:
			if hayCount <= woodCount:
				return 0
			else:
				return 1
	elif hayCount <= woodCount:
		return 0
	else:
		return 1

def farmingRequirements(gapForEachCrops):
	hayCount = num_items(items[0])
	woodCount = num_items(items[1])
	carrotCount = num_items(items[2])
	
	activeIndex = getValidActiveIndex(gapForEachCrops)
	activeItem = items[activeIndex]
	activeFunc = funcs[activeIndex]
	
	# Calculate target based on crop type
	if activeItem == items[2]:
		minResource = None 
		if hayCount < woodCount:
			minResource = hayCount
		else: 
			minResource = woodCount
		
		# Calculate the maximum carrots Hay/Wood can currently support
		maxSafeCarrots = (minResource - gapForEachCrops) // 2
		targetAmount = maxSafeCarrots
			
	else:
		# Hay and Wood leapfrog normally
		targetAmount = getHighestCount() + gapForEachCrops

	# Don't start farming if target is already met or invalid
	if num_items(activeItem) >= targetAmount:
		return

	while num_items(activeItem) < targetAmount:
		# Safety check during Carrot farming: stop if Hay or Wood drop below ratio
		if activeItem == items[2]:
			currentCarrots = num_items(items[2])
			requiredReserve = (currentCarrots * 2) + gapForEachCrops
			if num_items(items[0]) < requiredReserve or num_items(items[1]) < requiredReserve:
				break
				
		activeFunc()
