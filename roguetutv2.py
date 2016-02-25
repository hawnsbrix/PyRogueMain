import libtcodpy as libtcod
import math
import textwrap
import shelve
import random

######################
# STATIC INFORMATION #
######################


#actual window size
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50

# 20 frames per second maximum
LIMIT_FPS = 20

#map size 
MAP_WIDTH = 80 
MAP_HEIGHT = 50

#size of the map portion on-screen
CAMERA_WIDTH = 80
CAMERA_HEIGHT = 43

#parameters for dungeon generator
ROOM_MAX_SIZE = 30
ROOM_MIN_SIZE = 3
MAX_ROOMS = 50

#nr of monsters that should generate
#MAX_ROOM_MONSTERS = 3

#nr of items to generate
#MAX_ROOM_ITEMS = 2

FOV_ALGO = 0 #default FOV algorithm 
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 13

#player color
color_player = libtcod.lighter_sepia


#sizes and coordinates relevant for the UI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT

#message bar
MSG_X = BAR_WIDTH + 10
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1 

#level-up screen
LEVEL_SCREEN_WIDTH = 40

#character screen
CHARACTER_SCREEN_WIDTH = 30

#inventory
INVENTORY_WIDTH = 50

#spell values
HEAL_AMOUNT = 40

LIGHTNING_DAMAGE = 40
LIGHTNING_RANGE = 5

FIREBALL_DAMAGE = 25
FIREBALL_RADIUS = 5

DIG_RANGE = 6

#ai stuff
CONFUSE_NUM_TURNS = 10
CONFUSE_RANGE = 8


#experience and level-ups
LEVEL_UP_BASE = 200
LEVEL_UP_FACTOR = 125

###########
# CLASSES #
###########

class Tile:
	#a tile of the map and its properties
	def __init__ (self, blocked, block_sight = None):
		self.blocked = blocked
		
		#all tiles start unexplored
		self.explored = False
	
		#by default, if a tile is blocked, it also blocks sight
		if block_sight is None: block_sight = blocked
		self.block_sight = block_sight

		
class Rect:
	#a rectangle on the map, used to characterize a room
	def __init__(self, x, y, w, h):
		self.x1 = x
		self.y1 = y 
		self.x2 = x + w 
		self.y2 = y + h 
		
	def center(self):
		center_x = (self.x1 + self.x2) / 2 
		center_y = (self.y1 + self.y2) / 2 
		return (center_x, center_y)
		
	def intersect(self, other):
		#returns true if this rectangle intersects with another one
		return (self.x1 <= other.x2 and self.x2 >= other.x1 and
				self.y1 <= other.y2 and self.y2 >= other.y1)
			
				
class Object:
	#generic object (player, monsters, items etc)
	#is always represented by a character on screen
	def __init__(self, x, y, char, name, color, blocks=False, always_visible=False, fighter=None, ai=None, item=None, equipment=None):
		self.x = x
		self.y = y
		self.char = char
		self.color = color
		self.name = name
		self.blocks = blocks
		self.always_visible = always_visible
		
		# ! composition ! #
		self.fighter = fighter
		if self.fighter: #let the fighter component know who owns it
			self.fighter.owner = self
			
		self.ai = ai
		if self.ai:
			self.ai.owner = self
			
		self.item = item 
		if self.item:
			self.item.owner = self
			
		self.equipment = equipment
		if self.equipment:
			self.equipment.owner = self
			
			#there must be an Item component for the equipment component to work proper	
			self.item = Item()
			self.item.owner = self
	
	def move_towards(self, target_x, target_y):
		#do some stuff before moving at all
		dx = target_x - self.x 
		dy = target_y - self.y 
		
		if self != player:
			if dx > 0:
				dx = 1
			if dx < 0:
				dx = -1 
			if dy > 0:
				dy = 1 
			if dy < 0:
				dy = -1
		
		self.move(dx, dy)
		
			
	def move(self, dx, dy):
		#move by the given amount if destination is not blocked
		#if not is_blocked(self.x + dx, self.y + dy): 
		if self != player:
			if not is_blocked(self.x, self.y + dy):
				self.y += dy
			if not is_blocked(self.x + dx, self.y):
				self.x += dx
		elif self == player:
			if not is_blocked(self.x + dx, self.y + dy):
				self.x += dx
				self.y += dy
		
	def send_to_back(self):
		#make this object be drawn first, so all other appear above it if they're in the same tile
		global objects
		objects.remove(self)
		objects.insert(0, self)
		
	def distance_to(self, other):
		#return the distance to another object
		dx = other.x - self.x
		dy = other.y - self.y 
		return math.sqrt(dx ** 2 + dy ** 2)
		
	def distance(self, x, y):
		#return the distance to some coordinates
		return math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)	
		
	def draw(self):
		#only show if it's visible to the player or: is set to always_visible and on an explored tile
		if (libtcod.map_is_in_fov(fov_map, self.x, self.y) or
		(self.always_visible and map[self.x][self.y].explored)):
			#do:
			(x, y) = to_camera_coordinates(self.x, self.y) 
			
			if x is not None:				
				#set the color and then draw the character that represents this object
				libtcod.console_set_default_foreground(con, self.color)
				libtcod.console_put_char(con, x, y, self.char, libtcod.BKGND_NONE)
	
	def clear(self):
		#erase the character that represents this object
		(x, y) = to_camera_coordinates(self.x, self.y)
		
		if x is not None and libtcod.map_is_in_fov(fov_map, self.x, self.y): #map[self.x][self.y].explored:
			libtcod.console_put_char(con, x, y, '.', color_dark_ground)
		elif x is not None:
			libtcod.console_put_char_ex(con, x, y, '.',libtcod.black, libtcod.black)
			
			
class Item:
	#an item that can be picked up and used
	def __init__(self, use_function=None):
		self.use_function = use_function	

	def pick_up(self):
		#add to the player's inventory and remove from the map
		if len(inventory) >= 26:
			message('Your bags are too full to pick up ' + self.owner.name + '.', libtcod.red)
		else:
			inventory.append(self.owner)
			objects.remove(self.owner)
			message('You picked up a ' + self.owner.name + '.', libtcod.green)
				
	def use(self):
		
		#if object has Equipment component, selecting it will equiptoggle it
		if self.owner.equipment:
			self.owner.equipment.toggle_equip()
			return
		
		
		#just call the use_function if it is defined
		if self.use_function is None:
			message('The ' + self.owner.name + ' cannot be used.')
		else:
			if self.use_function() != 'cancelled':
				#inventory.remove(self.owner) #destroy after use, unless cancelled
				return
				
	def drop(self):
		#dequip first if needed	
		if self.owner.equipment:
			self.owner.equipment.dequip()
		
		#add to the map and remove from the players inventory, also place it at players coords
		objects.append(self.owner)
		inventory.remove(self.owner)
		self.owner.x = player.x
		self.owner.y = player.y
		message('You dropped a ' + self.owner.name + '.', libtcod.yellow)
		
class Equipment:
	#an object that can be equipped, automatically adds the Item Component
	def __init__(self, slot, power_bonus=0, defense_bonus=0, max_hp_bonus=0, use_function=None):
		self.power_bonus = power_bonus
		self.defense_bonus = defense_bonus
		self.max_hp_bonus = max_hp_bonus
		
		self.slot = slot
		self.is_equipped = False
		
		self.use_function = use_function
		
	def toggle_equip(self): #toggle equip/de-equip status
		if self.is_equipped:
			self.dequip()
		else:
			self.equip()
	
	def equip(self):
		#if slot is already being used, dequip whatever is there first
		old_equipment = get_equipped_in_slot(self.slot)
		if old_equipment is not None:
			old_equipment.dequip()	
	
		#equip object and show a message about it
		self.is_equipped = True
		message('Equipped ' + self.owner.name + ' on ' + self.slot + '.', libtcod.light_blue)
		
	def dequip(self):
		#dequip + message
		if not self.is_equipped: return
		self.is_equipped = False
		message('Dequipped ' + self.owner.name + ' from ' + self.slot + '.', libtcod.light_red)
	
		
class Fighter:
	#combat-related properties and methods (monster, player, npc)
	def __init__(self, hp, defense, power, xp, death_function=None, idle_function=None):
		self.hp = hp
		self.base_max_hp = hp
		self.base_power = power
		self.base_defense = defense
		self.xp = xp
		
		self.death_function = death_function
		self.idle_function = idle_function
	
	@property
	def power(self): #return actual power, by summing up bonuses from all equipped items
		bonus = sum(equipment.power_bonus for equipment in get_all_equipped(self.owner))
		return self.base_power + bonus
	
	@property
	def defense(self):
		bonus = sum(equipment.defense_bonus for equipment in get_all_equipped(self.owner))
		return self.base_defense + bonus
		
	@property
	def max_hp(self):
		bonus = sum(equipment.max_hp_bonus for equipment in get_all_equipped(self.owner))
		return self.base_max_hp + bonus

		
	def idle(self, turns):
	#make something stand in place and idle
		for i in range(0, turns, 1):
			if i > 0:
				function = self.idle_function
				if function is not None:
					function(self.owner)
				i + 1
					
	def attack(self, target):
	#simple formula for attack damage
		damage = self.power - target.fighter.defense
		
		if damage > 0:
			#make target take some damage
			message(self.owner.name.capitalize() + ' attacks ' + target.name + ' for ' + str(damage) + ' hit points. ')
			target.fighter.take_damage(damage)
		else:
			message(self.owner.name.capitalize() + ' attacks ' + target.name + ' but it has no effect! ')
		
	def take_damage(self, damage):
		#apply dmg if possible
		if damage > 0:
			self.hp -= damage
		
		#check for death, if there's a death function, call it	
		if self.hp <= 0:
			function = self.death_function
			if function is not None:
				function(self.owner)
				
			#yield xp to player
			if self.owner != player:
				player.fighter.xp += self.xp	
			
	def heal(self, amount):
		#heal for amount, dont go over maximum
		self.hp += amount
		if self.hp > self.max_hp:
			self.hp = self.max_hp
			
	def apply_effect(self, effect):
		#monster applies something to itself
		if effect == confusion:
			old_ai = self.owner.ai
			old_ai = monster.ai
			monster.ai = ConfusedMonster(old_ai, CONFUSE_NUM_TURNS)
			monster.ai.owner = monster #tell new component who owns it			
	
class BasicMonster:
	#AI for a basic monster
	def take_turn(self):
		#basic monster takes turn. if you can see it, it can see you
		monster = self.owner
		#if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
		
		#close enough to attack (if player is alive)
		if monster.distance_to(player) == 1 and player.fighter.hp > 0:
			monster.fighter.attack(player)	

		#if player is not within this range, the monster will randomly wander around
		elif monster.distance_to(player) >= 7:
			monster.move(libtcod.random_get_int(0, -1, 1), libtcod.random_get_int(0, -1, 1))
			
		#move towards player if far away
		elif monster.distance_to(player) <= 7 and monster.distance_to(player) >= 2:
			monster.move_towards(player.x, player.y)
														
class IdlingMonster:
	#AI for monsters that should do nothing in particular for a number of turns
	def __init(self, old_ai, num_turns):
		monster = self.owner
		self.old_ai = old_ai
		self.num_turns = num_turns
	
	def take_turn(self):
		if self.num_turns > 0: #still idling/waiting
			#do whatever it is that an idling monster should do:
			message('The ' + self.owner.name + ' stands around in place.', libtcod.grey)
			self.num_turns -= 1
			
		else: #restore previous AI
			self.owner.ai = self.old_ai
			message('The ' + self.owner.name + ' stops waiting and looks at you menacingly!', libtcod.white)
			
class ConfusedMonster:
	#AI used for a confused monster
	def __init__(self, old_ai=None, num_turns=CONFUSE_NUM_TURNS):
		self.old_ai = old_ai
		self.num_turns = num_turns
			
	def take_turn(self):
		monster = self.owner
		if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
			
			if self.num_turns > 0: #still confused...
				#move in a random direction and decrease number of turns confused
				self.owner.move(libtcod.random_get_int(0, -1, 1), libtcod.random_get_int(0, -1, 1))
				
				if self.owner.name == 'fiend':
					self.num_turns += 1
				else:
					self.num_turns -= 1 		
		
			else: #restore previous AI (delete this one since it's not referenced anymore)
				self.owner.ai = self.old_ai
				message('The ' + self.owner.name + ' is no longer confused!', libtcod.red)
				
		
###############		
# END CLASSES #
###############		
		
def get_equipped_in_slot(slot):
	for obj in inventory:
		if obj.equipment and obj.equipment.slot == slot and obj.equipment.is_equipped:
			return obj.equipment
	return None
		
def get_all_equipped(obj): #returns a list of equipped items
	if obj == player:
		equipped_list = []
		for item in inventory:
			if item.equipment and item.equipment.is_equipped:
				equipped_list.append(item.equipment)
		return equipped_list
	else:
		return [] #other objects have no equipment
		
def is_blocked(x, y):
	#first test the map tile
	if map[x][y].blocked:
		return True
			
	#now check for any blocking objects
	for object in objects:
		if object.blocks and object.x == x and object.y == y:
			return True			
	return False
	
def create_room(room):
	global map
	# go through the tiles in the rectangle and make them passable
	for x in range(room.x1 + 1, room.x2):
		for y in range(room.y1 + 1, room.y2):
			map[x][y].blocked = False
			map[x][y].block_sight = False
			
def create_circular_room(room):
	global map
	#centre of circle
	cx = (room.x1 + room.x2) / 2 
	cy = (room.y1 + room.y2) / 2 
	
	#radius of circle; makes it fit in the room
	width = room.x2 - room.x1
	height = room.y2 - room.y1
	r = min(width, height) / 2
	
	#go through the tiles in the circle and make them passable
	for x in range(room.x1, room.x2 +1):
		for y in range(room.y1, room.y2 +1):
			if math.sqrt((x - cx) ** 2 + (y - cy) ** 2) <= r:
				map[x][y].blocked = False
				map[x][y].block_sight = False 

def create_solid(room):
	global map
	#centre of circle
	cx = (room.x1 + room.x2) / 2 
	cy = (room.y1 + room.y2) / 2 
	
	#radius of circle; makes it fit in the room
	width = room.x2 - room.x1
	height = room.y2 - room.y1
	r = min(width, height) / 2
	
	#go through the tiles in the solid and block them
	for x in range(room.x1, room.x2 +1):
		for y in range(room.y1, room.y2 +1):
			if math.sqrt((x - cx) ** 2 + (y - cy) ** 2) <= r:
				map[x][y].blocked = True
				map[x][y].block_sight = True 				
			
def create_h_tunnel(x1, x2, y):
	global map
	#horizontal tunnel. min() and max() are used in case x1>x2
	for x in range(min(x1, x2), max(x1, x2) + 1):
		map[x][y].blocked = False
		map[x][y].block_sight = False 
	
def create_v_tunnel(y1, y2, x):
	global map
	#vertical tunnel
	for y in range(min(y1, y2), max(y1, y2) + 1):
		map[x][y].blocked = False
		map[x][y].block_sight = False
		
def create_d_tunnel(x1, x2, y1, y2, x, y):
	global map
	#diagonal tunnel
	for x in range(min(x1, x2), max(x1, x2) + 1): 
		for y in range(min(y1, y2), max(y1, y2) + 1):
			map[x][y].blocked = False
			map[x][y].block_sight = False

		
def make_map():
	global map, objects, downstairs, upstairs, theme
	
	global color_dark_wall, color_light_wall
	global color_dark_ground, color_light_ground
	
	global char_for_dark_walls, char_for_light_walls
	global char_color_on_dark_walls, char_color_on_light_walls
	
	global character_dark_floorstyle
	global character_light_floorstyle
	

	#MAP THEME PARAMETERS
		
	#themed maps are maps that should have only one type of room-shape(style)
	themed_map = False
	theme_tech = False
	theme_cave = False
	no_theme = False
	theme = False
	
	#roll to see if the map should be themed or not
	decide_themed = libtcod.random_get_int(0, 0, 10)
	if decide_themed < 5:
		themed_map == True	
		#decide which
		theme_number = libtcod.random_get_int(0, 0, 10)
		if theme_number < 5:
			theme = theme_tech
		elif theme_number > 5:
			theme = theme_cave		
	else:
		theme = no_theme
		
	##################################################################
	if theme == theme_cave:
		#colors for the floor, walls and the characters on those walls
		#dark:
		color_dark_wall = libtcod.black
		color_dark_ground = libtcod.darkest_sepia	
		char_color_on_dark_walls = libtcod.desaturated_orange
		
		#light:
		color_light_wall = libtcod.black
		color_light_ground = libtcod.desaturated_yellow	
		char_color_on_light_walls = libtcod.purple
		
		#characters used to display walls
		char_for_dark_walls = '4'
		char_for_light_walls = '4'

		#characters used to display floors
		character_dark_floorstyle = ' '
		character_light_floorstyle = '.'
	##################################################################
	elif theme == theme_tech:
		
		color_dark_wall = libtcod.black
		color_dark_ground = libtcod.darkest_sepia
		char_color_on_dark_walls = libtcod.desaturated_orange
		
		color_light_wall = libtcod.black 
		color_light_ground = libtcod.grey 
		char_color_on_light_walls = libtcod.white
	
		char_for_dark_walls = 'L'
		char_for_light_walls = 'L'
		
		character_dark_floorstyle = ' '
		character_light_floorstyle = '.'
	##################################################################
	else:
		theme == no_theme	
	
		color_dark_wall = libtcod.black
		color_dark_ground = libtcod.darkest_green
		char_color_on_dark_walls = libtcod.dark_green
		
		color_light_wall = libtcod.black
		color_light_ground = libtcod.lighter_green
		char_color_on_light_walls = libtcod.desaturated_green
		
		char_for_dark_walls = 'X'
		char_for_light_walls = 'X'
		
		character_light_floorstyle = ' '
		character_dark_floorstyle = '_'
		
	#making sure the initial room has a style associated with it:
	style = libtcod.random_get_int(0, 0, 1)
	
	#list of objects starting with the player
	objects = [player]
		
	#fill map with "blocked" tiles
	map = [[ Tile(True)
		for y in range(MAP_HEIGHT) ]
			for x in range(MAP_WIDTH) ]
				
	rooms = []
	num_rooms = 0
	
	# GO!
	for r in range(MAX_ROOMS):
		#random width and height
		w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
		h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
		#random position without going out of boundaries of map
		x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 2) #changed from 1 to see
		y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 2) #if it helps with the edge of the map (seems like it does)
			
		#rect class comes in play here	
		new_room = Rect(x, y, w, h)
		
		#run through other rooms and see if they intersect with this one
		failed = False
		solid = False
		for other_room in rooms:
			if new_room.intersect(other_room):
				#if width is lower than this number, go ahead anyway
				#otherwise, nope, intersects and is also too big
				if w and h > 15:			
					failed = True
					break	
				if w and h < 3:
					solid = True
					break
					
		if not failed:
			#no intersections, room is valid;	
			#"paint" it to the map's tiles
			if themed_map == False: #if map is not themed, decide the style for this particular room 
				style == libtcod.random_get_int(0, 0, 2)
				
			if style == 0:
				#squares
				create_room(new_room)
			elif style == 1:
				#circles
				create_circular_room(new_room)
			elif style == 2:
				#solids
				create_solid(new_room)
			
			if not solid:
				#add contents to this room, such as monsters
				place_objects(new_room)
			
			#center coords of new room, will be useful later
			(new_x, new_y) = new_room.center()
			
			#optional bit of code to label rooms
			room_no = Object(new_x, new_y, chr(65+num_rooms), 'Room Number', libtcod.white, blocks=False)
			objects.insert(0, room_no) #draw early so monsters are drawn on top
					
			if num_rooms == 0:
				#first room, where player starts
				player.x = new_x
				player.y = new_y
			elif not solid:
				#all rooms after the first:
				#connect it to the previous room with a tunnel
				
				#center coordinates of previous room
				(prev_x, prev_y) = rooms[num_rooms-1].center()
				
				#determine the direction of the tunnel
				direction = libtcod.random_get_int(0, 0, 2)
				if direction == 1:
					#first move horizontally, then vertically
					create_h_tunnel(prev_x, new_x, prev_y)
					create_v_tunnel(prev_y, new_y, new_x)
				elif direction == 2:
					#first move vertically, then horizontally
					create_v_tunnel(prev_y, new_y, prev_x)
					create_h_tunnel(prev_x, new_x, new_y)
				else:
					#diagonally
					create_d_tunnel(prev_x, new_x, prev_y, new_y, prev_x, prev_y)
					
					
			#finally, append the new room to the list
			rooms.append(new_room)
			num_rooms += 1

	#create stairs in the last room
	downstairs = Object(new_x, new_y, '>', 'downstairs', libtcod.white, always_visible=True)
	upstairs = Object(prev_x, prev_y, '<', 'upstairs', libtcod.white, always_visible=True)
	objects.append(downstairs)
	objects.append(upstairs)
	#stairs.send_to_back() #draw below monsters

	
def random_choice_index(chances):
	#choose one option from a list of chances, returning its index
	#the dice will land on some number between 1 and the sum of the chances
	dice = libtcod.random_get_int(0, 1, sum(chances))
	
	#go through all chances, keeping the sum so far
	running_sum = 0
	choice = 0
	for w in chances:
		running_sum += w
		
		#check if the dice landed in the part that corresponds with this choice
		if dice <= running_sum:
			return choice
		choice += 1

def random_choice(chances_dict):
	#choose one option from dictionary of chances, returning its key
	chances = chances_dict.values()
	strings = chances_dict.keys()
	
	return strings[random_choice_index(chances)]
	
def from_dungeon_level(table):
	#returns a value that depends on dlevel.
	#the table specifies what value occurs after each level, default=0
	for (value, level) in reversed(table):
		if dungeon_level >= level:
			return value
	return 0
	
def place_objects(room):
	# ! # here be spawn rates # ! #
	
	#maximum number of monsters per room
	max_monsters = from_dungeon_level([[2, 1], [3, 4], [5, 6]]) 
	
	#chance of each monster
	monster_chances = {} 
	monster_chances['aardwurm'] = 80 # always show up, even if all other monsters have 0 chance
	monster_chances['caco'] = from_dungeon_level([[15, 3], [30, 5], [40, 10]]) 
	monster_chances['fiend'] = from_dungeon_level([[10, 2], [30, 5], [60, 7]])
	monster_chances['korky'] = from_dungeon_level([[1, 1], [5, 3], [20, 6]])
	
	#maximum number of items per room
	max_items = from_dungeon_level([[1, 1], [2, 4]])
	
	#chance of each item (by default they have chance 0 at level 1, which then goes up)
	item_chances = {}
	#item_chances['heal'] = 35 #always potions, even if others are 0 chance
	item_chances['dig'] = from_dungeon_level([[5, 1]])
	item_chances['lightning'] = from_dungeon_level([[25, 4]])
	item_chances['fireball'] = from_dungeon_level([[25, 6]])
	item_chances['confuse'] = from_dungeon_level([[10, 2]])
	item_chances['heal'] = from_dungeon_level([[35, 1]])

	#choose random number of MONSTERS
	num_monsters = libtcod.random_get_int(0, 0, max_monsters)
	
	for i in range(num_monsters):
		#choose random spot for this monster
		x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
		y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
			
		#only place it if tile is not blocked
		if not is_blocked(x, y):
			choice = random_choice(monster_chances)
			if choice == 'aardwurm':
				#orc
				fighter_component = Fighter(hp=20, defense=0, power=4, xp=100, death_function=monster_death, idle_function=monster_idle)
				ai_component = BasicMonster()
				
				monster = Object(x, y, 'G', 'Aardwurm', libtcod.green,
					blocks=True, fighter=fighter_component, ai=ai_component)
					
			elif choice == 'caco':
				#troll
				fighter_component = Fighter(hp=30, defense=2, power=8, xp=100, death_function=monster_death, idle_function=monster_idle)
				ai_component = BasicMonster()
				
				monster = Object(x, y, 'C', 'Caco', libtcod.crimson,
					blocks=True, fighter=fighter_component, ai=ai_component)
			
			elif choice == 'fiend':
				#fiend
				fighter_component = Fighter(hp=40, defense=6, power=10, xp=150, death_function=monster_death, idle_function=monster_idle)		
				ai_component = BasicMonster()
				
				monster = Object(x, y, 'S', 'Fiend', libtcod.light_purple,
					blocks=True, fighter=fighter_component, ai=ai_component)
			
			elif choice == 'korky':
				#korky
				fighter_component = Fighter(hp=70, defense=4, power=20, xp=300, death_function=monster_death, idle_function=monster_idle)
				ai_component = BasicMonster()
				monster = Object(x, y, 'R', 'Korky', libtcod.light_sky, 
					blocks=True, fighter=fighter_component, ai=ai_component)
				
			objects.append(monster)


	#choose random number of ITEMS
	num_items = libtcod.random_get_int(0, 0, max_items)
		
	for i in range(num_items):
		#pick a spot for the item to spawn
		x = libtcod.random_get_int(0, room.x1+1, room.x2-1)
		y = libtcod.random_get_int(0, room.y1+1, room.y2-1)
			
		#only place it if the tile is not blocked
		if not is_blocked(x, y):
			choice = random_choice(item_chances)
			if choice == 'heal':
				#create a healing potion 
				item_component = Item(use_function=cast_heal)
				item = Object(x, y, '$', 'Medical Kit', libtcod.violet, item=item_component)			
			elif choice == 'lightning':
				#create lightning scroll 
				item_component = Item(use_function=cast_lightning)
				item = Object(x, y, '#', 'Scroll of Lightning Bolt', libtcod.white, item=item_component)
			elif choice == 'fireball':
				#create fireball scroll 
				item_component = Item(use_function=cast_fireball)
				item = Object(x, y, '#', 'Scroll of Fireball', libtcod.orange, item=item_component)
			elif choice == 'confuse':
				#create a confuse scroll 
				item_component = Item(use_function=cast_confuse)
				item = Object(x, y, '#', 'Scroll of Confusion', libtcod.light_cyan, item=item_component)
			elif choice == 'dig':
				#create a digging tool
				item_component = Item(use_function=cast_dig)
				item = Object(x, y, 'D', 'Digging Tool', libtcod.light_lime, item=item_component)
			
			
			objects.append(item)
			item.send_to_back() #items appear below other objects
			item.always_visible = False
			
def next_level():
	global dungeon_level
	#advance to next level
	message('You carefully walk down the stairs.', libtcod.light_violet)
	dungeon_level += 1
	make_map() #create fresh new level
	initialize_fov()
	save_game()

def previous_level():
	global dungeon_level
	#go back up one floor
	message('You go back up.', libtcod.light_red)
	dungeon_level -= 1
	load_previous_map() # load the last map 
	initialize_fov()
	
def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
	#render a bar (HP, XP, MANA etc). First calculate the width of the bar
	bar_width = int(float(value) / maximum * total_width)
	
	#render background first
	libtcod.console_set_default_background(panel, back_color)
	libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)
	
	#now render the bar on top
	libtcod.console_set_default_background(panel, bar_color)
	if bar_width > 0:
		libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)
	
	#finally, some centered text with the values
	libtcod.console_set_default_foreground(panel, libtcod.white)
	libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE, libtcod.CENTER, 
		name + ': ' + str(value) + '/' + str(maximum))
	
	
def move_camera(target_x, target_y):
	global camera_x, camera_y, fov_recompute
	
	#new camera coordinates (top-left corner relative to the map)
	x = target_x - CAMERA_WIDTH / 2 #target at center of screen
	y = target_y - CAMERA_HEIGHT / 2 
	
	#make sure the camera doesn't see outside the map
	if x < 0: x = 0
		
	if y < 0: y = 0
		
	if x > MAP_WIDTH - CAMERA_WIDTH - 1:
		x = MAP_WIDTH - CAMERA_WIDTH - 1
		
	if y > MAP_HEIGHT - CAMERA_HEIGHT - 1:
		y = MAP_HEIGHT - CAMERA_HEIGHT - 1 
	
	if x != camera_x or y != camera_y:
		fov_recompute = True
	
	(camera_x, camera_y) = (x, y)

def to_camera_coordinates(x, y):
	#convert coordinates on the map to coords on screen
	(x, y) = (x - camera_x, y - camera_y)
		
	#if it's outside view, return nothing	
	if (x < 0 or y < 0 or x >= CAMERA_WIDTH or y >= CAMERA_HEIGHT):
		return (None, None) 
	
	return (x, y)
	
def render_all():
	global fov_map
	global fov_recompute

	
	
	move_camera(player.x, player.y)
	
	if fov_recompute:
		#recompute FOV if needed (player moved or w/e)
		fov_recompute = False
		libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)
		libtcod.console_clear(con)
		
		#go through all the tiles, and set their background colour
		for y in range(CAMERA_HEIGHT):
			for x in range(CAMERA_WIDTH):
				(map_x, map_y) = (camera_x + x, camera_y + y)
				visible = libtcod.map_is_in_fov(fov_map, map_x, map_y)
				
				wall = map[map_x][map_y].block_sight
				if not visible:
					#if it's not visible right now, player can only see it when explored
					if map[map_x][map_y].explored:
						if wall:
							#explored WALLS we can't see and the character on the wall:
							libtcod.console_put_char_ex(con, x, y, char_for_dark_walls, char_color_on_dark_walls, color_dark_wall)					
						else:
							#explored FLOORS we can't see:
							#libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET) 
							libtcod.console_put_char_ex(con, x, y, character_dark_floorstyle, color_dark_ground, libtcod.BKGND_SET)
							
				else:
					#it's visible
					if wall:
						#explored WALLS that are in view including the character on the wall:
						libtcod.console_put_char_ex(con, x, y, char_for_light_walls, char_color_on_light_walls, color_light_wall)						
					else:
						#explored FLOORS that are in view:
						#libtcod.console_set_char_background(con, x, y, color_light_ground, libtcod.BKGND_SET)
						libtcod.console_put_char_ex(con, x, y, character_light_floorstyle, color_light_ground, libtcod.BKGND_SET)
					#since it's visible, explore it
					map[map_x][map_y].explored = True
					
	#draw all objects in the list, except player (should be drawn last, over all the other stuff like items and corpses)
	for object in objects:
		if object != player:
			object.draw()
	player.draw()
		
	#blit contents of "con" to root console and present it 
	libtcod.console_blit(con, 0, 0, MAP_WIDTH, MAP_HEIGHT, 0, 0, 0)

	#prepare to render GUI panel
	libtcod.console_set_default_background(panel, libtcod.black)
	libtcod.console_clear(panel)
	
	#print the game messages, one line at a time
	y = 1
	for (line, color) in game_msgs:
		libtcod.console_set_default_foreground(panel, color)
		libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
		y += 1
	
	#show the player's stats
	render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp,
		libtcod.light_red, libtcod.darker_red)
	libtcod.console_print_ex(panel, 1, 3, libtcod.BKGND_NONE, libtcod.LEFT, 'Dungeon Level ' + str(dungeon_level))
	
	
	#display names of objects under the mouse
	libtcod.console_set_default_foreground(panel, libtcod.light_gray)
	libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT, get_names_under_mouse())
	
	
	#blit contents of panel to root console
	libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)

	
def message(new_msg, color = libtcod.white):
	#split message if necessary, among multiple lines
	new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)
	
	for line in new_msg_lines:
		#if buffer is full, remove the first line to make room (fifo)
		if len(game_msgs) == MSG_HEIGHT:
			del game_msgs[0]
		
		#add the new line as a tuple, with the text and color
		game_msgs.append( (line, color) )

def msgbox(text, width=50):
	menu(text, [], width) #use menu() as a sort of "message box"

def menu(header, options, width):
	if len(options) > 26: raise ValueError('Cannot have menu with more than 26 different options!')
	
	#calculate total height for the header (after auto-wrap) and one line per option
	header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
	if header == '':
		header_height = 0
	height = len(options) + header_height

	#create an off-screen console that represents the menu's window
	window = libtcod.console_new(width, height)
	
	#print the header, with auto-wrap
	libtcod.console_set_default_foreground(window, libtcod.white)
	libtcod.console_print_rect_ex(window, 0, 0, width, height, libtcod.BKGND_NONE, libtcod.LEFT, header)
	
	#print all the options
	y = header_height
	letter_index = ord('a')
	for option_text in options:
		text = '(' + chr(letter_index) + ')' + option_text
		libtcod.console_print_ex(window, 0, y, libtcod.BKGND_NONE, libtcod.LEFT, text)
		y += 1
		letter_index += 1

	#blit contents of "window" to the root console
	x = SCREEN_WIDTH/2 - width/2
	y = SCREEN_HEIGHT/2 - height/2
	libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)
	
	#present the root console to the player and wait for a keypress
	libtcod.console_flush()
	key = libtcod.console_wait_for_keypress(True)
	
	if key.vk == libtcod.KEY_ENTER and key.lalt: #copied code: allow alt-enter in the main screen
		libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())	

	
	#convert the ASCII code to an index; if it corresponds to an option, return it
	index = key.c - ord('a')
	if index >= 0 and index < len(options): return index
	return None
	
def main_menu():
	img = libtcod.image_load('menu_background3.png')
	
	while not libtcod.console_is_window_closed():
		#show background image at twice the regular console resolution
		libtcod.image_blit_2x(img, 0, 0, 0)
		
		#show the game title and some credits
		libtcod.console_set_default_foreground(0, libtcod.light_yellow)
		libtcod.console_print_ex(0, SCREEN_WIDTH/2, SCREEN_HEIGHT/2-4, libtcod.BKGND_NONE, libtcod.CENTER,
			'CRASH-LANDER')
		libtcod.console_print_ex(0, SCREEN_WIDTH/2, SCREEN_HEIGHT-2, libtcod.BKGND_NONE, libtcod.CENTER,
			'lol')
		
		#show options and wait for the player's choice
		choice = menu('', ['Start New Game', 'Continue Last Game', 'Quit'], 24)
	
		if choice == 0: #new game
			new_game()
			play_game()
		if choice == 1: #load last game
			try:
				load_game()
			except:
				msgbox('\n No saved game to load.\n', 24)
				continue
			play_game()
		elif choice == 2: #quit
			break
			

	
def inventory_menu(header):
	#show a menu with each item of the inventory as an option 
	if len(inventory) == 0:
		options = ['Inventory is empty.']
	else:
		options = []
		for item in inventory:
			text = item.name
			#show additional info, in case it's equipped
			if item.equipment and item.equipment.is_equipped:
				text = text + ' (on ' + item.equipment.slot + ')'
			options.append(text)
				
	index = menu(header, options, INVENTORY_WIDTH)
	
	#if an item was chosen, return it
	if index is None or len(inventory) == 0: return None
	return inventory[index].item 
	
	
def player_move_or_attack(dx, dy):
	global fov_recompute
	
	#coordinates the player is moving or attacking to
	x = player.x + dx
	y = player.y + dy
	
	#try to find an attackable object there
	target = None
	for object in objects:
		if object.fighter and object.x == x and object.y == y:
			target = object
			break
	
	#attack if target found, move otherwise
	if target is not None:
		player.fighter.attack(target) 
	else:
		player.move(dx, dy)
		fov_recompute = True
	
	
def handle_keys():
	global keys
	
	if key.vk == libtcod.KEY_ENTER and key.lalt:
		libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())	#alt+enter: toggle fullscreen
	elif key.vk == libtcod.KEY_ESCAPE:
		return 'exit' #exit game
	
	if game_state == 'playing':
	
		#movement keys (arrows + numpad)
		if key.vk == libtcod.KEY_UP or key.vk == libtcod.KEY_KP8:
			player_move_or_attack(0, -1)
			
		elif key.vk == libtcod.KEY_DOWN or key.vk == libtcod.KEY_KP2:
			player_move_or_attack(0, 1)
			
		elif key.vk == libtcod.KEY_LEFT or key.vk == libtcod.KEY_KP4:
			player_move_or_attack(-1, 0)	
			
		elif key.vk == libtcod.KEY_RIGHT or key.vk == libtcod.KEY_KP6:
			player_move_or_attack(1, 0)
		#diagonals
		elif key.vk == libtcod.KEY_HOME or key.vk == libtcod.KEY_KP7:
			player_move_or_attack(-1, -1)
			
		elif key.vk == libtcod.KEY_PAGEUP or key.vk == libtcod.KEY_KP9:
			player_move_or_attack(1, -1)
			
		elif key.vk == libtcod.KEY_END or key.vk == libtcod.KEY_KP1:
			player_move_or_attack(-1, 1)
			
		elif key.vk == libtcod.KEY_PAGEDOWN or key.vk == libtcod.KEY_KP3:
			player_move_or_attack(1, 1)
		
		elif key.vk == libtcod.KEY_KP5:
			pass #do nothing i.e. wait for monster to come to you
		
		else:
			#test for other keys
			key_char = chr(key.c)
			
			if key_char == 'd':
				#show inventory; if an item is selected, drop it
				chosen_item = inventory_menu('Press the key next to an item to drop it, or any other key to cancel.\n')
				if chosen_item is not None:
					chosen_item.drop()
			
			if key_char == 'g':
				#grab/pickup an item
				for object in objects: #look for item in the players tile
					if object.x == player.x and object.y == player.y and object.item:
						object.item.pick_up()
						break
			
			if key_char == 'a':
				#show inventory, if an item is selected, use it 
				chosen_item = inventory_menu('Press the key next to an item to use it, or any other key to cancel.\n')
					
				if chosen_item is not None:
					chosen_item.use()								
					return
				elif chosen_item is None:
					message("You don't have that!", libtcod.red) 
					
			if key_char == '>':
				#go down stairs, if player is on them
				if downstairs.x == player.x and downstairs.y == player.y:
					next_level()
			if key_char == '<':
				#go up stairs, if player is on them
				if upstairs.x == player.x and upstairs.y == player.y:
					previous_level()
				
			if key_char == 'c':
				#show character information
				level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
				msgbox('Character Information\n\nLevel: ' + str(player.level) + '\nExperience: ' + str(player.fighter.xp) +
					'\nExperience to level up: ' + str(level_up_xp) + '\n\nMaximum HP: ' + str(player.fighter.max_hp) +
					'\nAttackpower: ' + str(player.fighter.power) + '\nDefense: ' + str(player.fighter.defense), CHARACTER_SCREEN_WIDTH)
			
			return 'didnt-take-turn'
			
			
def get_names_under_mouse():
	global mouse
	
	#return a string with the names of all objects under the mouse
	(x, y) = (mouse.cx, mouse.cy)
	(x, y) = (camera_x + x, camera_y + y) #from screen to map coords
	
	#create a list with the names of all objects at the mouse coords and in FOV
	names = [obj.name for obj in objects 
		if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]
		
	#join the names, seperated by commas
	names = ', '.join(names)
	return names.capitalize()				

def target_tile(max_range=None):
	#return the position of a tile left-clicked in player's FOV (optionally in range), or (None,None) if right-clicked.
	global key, mouse
	while True:
		#render the screen, this erases(?) the inv and shows the names of objects under the mouse
		libtcod.console_flush()
		libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE, key, mouse)
		render_all()
		
		(x, y) = (mouse.cx, mouse.cy)
		(x, y) = (camera_x + x, camera_y + y) #from screen to map coords
		
		if (mouse.lbutton_pressed and libtcod.map_is_in_fov(fov_map, x, y) and
			(max_range is None or player.distance(x, y) <= max_range)):
			return (x, y)
		if mouse.rbutton_pressed or key.vk == libtcod.KEY_ESCAPE:
			return (None, None) #cancel @ Rightclick or Escape

def target_monster(max_range=None):
	#returns a clicked monster inside FOV up to a range, or None if right-clicked
	while True:
		(x, y) = target_tile(max_range)
		if x is None: #player cancelled
			return None
		
		#return the first clicked monster, otherwise continue looping
		for obj in objects:
			if obj.x == x and obj.y == y and obj.fighter and obj != player:
				return obj

def check_level_up():
	#is xp enough to level up?
	level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
	if player.fighter.xp >= level_up_xp:
		#it is!
		player.level += 1
		player.fighter.xp -= level_up_xp
		message('You leveled up! You are now level ' + str(player.level) + '!', libtcod.yellow)
	
		choice = None
		while choice == None: #keep asking until a choice is made
			choice = menu('Choose a stat to raise:\n',
				['Endurance (+20 HP, previously: ' + str(player.fighter.base_max_hp) + ')',
				'Power (+1 Attack, previously: ' + str(player.fighter.base_power) + ')',
				'Defense (+1 Defense, prevously: ' + str(player.fighter.base_defense) + ')'], LEVEL_SCREEN_WIDTH)
		
		if choice == 0:
			player.fighter.base_max_hp += 20
			player.fighter.hp += 20
		elif choice == 1:
			player.fighter.base_power += 1 
		elif choice == 2:
			player.fighter.base_defense += 1 
			
		#cast heal(max_hp instead of HEAL_AMOUNT) on the player at level-up
		#(the heal function doesn't allow going over max health)
		player.fighter.heal(player.fighter.max_hp)
		
def player_death(player):
	#the game ended!
	global game_state
	message('YOU DIED!', libtcod.red)
	game_state = 'dead'
	
	#for added effect, change the player into a corpse!
	player.char = '%'
	player.color = libtcod.darker_red
	
def monster_death(monster):
	#transform monster into a corpse (that is not in the way and doesnt move)
	message('The ' + monster.name.capitalize() + ' is dead! You gain ' + str(monster.fighter.xp) + ' XP.', libtcod.orange)
	monster.char = '%'
	monster.color = libtcod.dark_red
	monster.blocks = False
	monster.fighter = None
	monster.ai = None
	monster.name = 'The remains of a ' + monster.name
	monster.send_to_back()
	#always show corpses y/n:
	monster.always_visible = False

def monster_idle(monster):
	#the monster stands around doing nothing
	monster.ai = None
	monster.name = 'Idling ' + monster.name
	
def closest_monster(max_range):
	#find closes enemy, up to a maximum range, and in the player's FOV_ALGO
	closest_enemy = None
	closest_dist = max_range + 1 #start with slightly more than max range
	
	for object in objects:
		if object.fighter and not object == player and libtcod.map_is_in_fov(fov_map, object.x, object.y):
			#calculate distance between object and player
			dist = player.distance_to(object)
			if dist < closest_dist: #its closer, so remember it
				closest_enemy = object
				closest_dist = dist
	return closest_enemy
			
			
	
def cast_heal():
	#heal the player
	if player.fighter.hp == player.fighter.max_hp:
		message('You are already at full health.', libtcod.red)
		return 'cancelled'
	
	message('Your wounds start to heal!', libtcod.light_violet)
	player.fighter.heal(HEAL_AMOUNT)

def	cast_lightning():
	#find closest enemy (inside a maximum range) and damage it
	monster = closest_monster(LIGHTNING_RANGE)
	if monster is None: #no enemy found within range
		message('There are no enemies in range to strike.', libtcod.red)
		return 'cancelled'
	
	#zap it
	message('A lightning bolt strikes the ' + monster.name + 'for ' + str(LIGHTNING_DAMAGE)
		+ ' hit points.', libtcod.light_blue)
	monster.fighter.take_damage(LIGHTNING_DAMAGE)

def cast_fireball():
	global fov_recompute
	#ask player for a target tile to throw fire at
	message('Left-click a target for your Fireball, or right-click to cancel.', libtcod.light_cyan)
	(x, y) = target_tile()
	if x is None: 
		return 'cancelled'
	message('The fireball explodes, burning everything within ' + str(FIREBALL_RADIUS) + ' tiles!', libtcod.orange)
	
	for obj in objects: #damage every fighter in radius, including player
		if obj.distance(x, y) <= FIREBALL_RADIUS and obj.fighter:
			message('The ' + obj.name + ' gets burned for ' + str(FIREBALL_DAMAGE) + ' hit points!', libtcod.orange)
			obj.fighter.take_damage(FIREBALL_DAMAGE)
			
	fov_recompute = True
	
def cast_confuse():
	global fov_recompute
	#ask player for a target to confuse
	message('Left-click an enemy to confuse, or right-click to cancel.', libtcod.light_cyan)
	monster = target_monster(CONFUSE_RANGE)
	if monster is None:
		return 'cancelled'
		
	#confuse the monster (replace AI with confused AI for x turns as defined by constant)
	old_ai = monster.ai
	monster.ai = ConfusedMonster(old_ai, CONFUSE_NUM_TURNS)
	monster.ai.owner = monster #tell new component who owns it
	message('The ' + monster.name + ' stumbles around all confused!', libtcod.light_green)
	
	fov_recompute = True
	
def cast_dig():
	global fov_recompute
	#dig a big hole
	message('Left-click a direction to dig, or right-click to cancel.', libtcod.light_green) 
	
	(x, y) = target_tile()
	if x is None:
		return 'cancelled'
		
	old_x = player.x
	old_y = player.y
	
	if (x < old_x and y == old_y) or (x > old_x and y == old_y) :
		#dig horizontally
		create_h_tunnel(old_x, x, old_y)
		
	elif (y < old_y and x == old_x) or (y > old_y and x == old_x):
		#dig vertically
		create_v_tunnel(old_y, y, old_x)
		
	elif (x < old_x and y < old_y) or (x > old_x and y > old_y):
		#dig diagonally
		create_d_tunnel(old_x, x, old_y, y, x, y)
	
	fov_recompute = True
		
	
	
def idle(num_turns):
	old_ai = monster.ai
	monster.ai = IdlingMonster(old_ai, num_turns)
	monster.ai.owner = monster
	
			
### INITIALIZATION & MAIN LOOP ###
		
libtcod.console_set_custom_font('arial10x10edit.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'ROGUETUT', False)
libtcod.sys_set_fps(LIMIT_FPS)

con = libtcod.console_new(MAP_WIDTH, MAP_HEIGHT)

#panel stuff
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)

def new_game():
	global player, inventory, game_msgs, game_state, dungeon_level
	
	#create object representing the player
	fighter_component = Fighter(hp=50, defense=2, power=2, xp=0, death_function=player_death)
	player = Object(0, 0, '@', 'Player', color_player, blocks=True, fighter=fighter_component)
	
	#player xp level
	player.level = 1
	
	#dungeon floor we are at
	dungeon_level = 1
	
	#generate map (at this point it's not drawn to the screen)	
	make_map()
	initialize_fov()
	
	game_state = 'playing'
	#list of items that starts empty
	inventory = []
	
	#create the list of game messages and their colors, starts empty
	game_msgs = []
	
	#a welcoming message
	message('Welcome to the Dungeon!', libtcod.purple)
	
	#initial equipment
	equipment_component = Equipment(slot='right hand', power_bonus=10)
	obj = Object(0, 0, 'P', 'Mining Pick', libtcod.sky, equipment=equipment_component)
	inventory.append(obj)
	equipment_component.equip()
	obj.always_visible = True
	
def initialize_fov():
	global fov_recompute, fov_map
	fov_recompute = True
	
	#create the FOV map, according to generated map
	fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)
	
	libtcod.console_clear(con) #unexplored areas start with the default bg color (black)

	
	
def save_game():
	#open a new empty shelve (possibly overwriting an old one) to write the game data
	file = shelve.open('savegame', 'n')	
	file['map'] = map
	file['objects'] = objects
	file['player_index'] = objects.index(player) #index of player in objects list
	file['inventory'] = inventory
	file['game_msgs'] = game_msgs
	file['game_state'] = game_state
	file['stairs_index'] = objects.index(downstairs)
	file['stairs_index'] = objects.index(upstairs)
	file['dungeon_level'] = dungeon_level
	file.close()

def load_game():
	#open the previously saved shelve and load the game data
	global map, objects, player, inventory, game_msgs, game_state, downstairs, upstairs, dungeon_level
	
	file = shelve.open('savegame', 'r')
	map = file['map']
	objects = file['objects']
	player = objects[file['player_index']] #get index of player in objects list and access it
	inventory = file['inventory']
	game_msgs = file['game_msgs']
	game_state = file['game_state']
	downstairs = objects[file['stairs_index']]
	upstairs = objects[file['stairs_index']]
	dungeon_level = file['dungeon_level']
	file.close()
	initialize_fov()
	
def load_previous_map():
	#open the last map cus we done gone up a stairs
	global map, game_state
	
	file = shelve.open('savegame', 'r')
	map = file['map']
	
	game_state = file['game_state']
	file.close()
	initialize_fov()
	
	
#############
# MAIN LOOP #
#############

def play_game():
	global key, mouse, camera_x, camera_y
	
	player_action = None	
	
	mouse = libtcod.Mouse()
	key = libtcod.Key()
	
	(camera_x, camera_y) = (0, 0)
	
	while not libtcod.console_is_window_closed():
		
		libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
		#render the screen
		render_all()
		libtcod.console_flush()
		
		
		#check for level-ups before each turn
		check_level_up()
		
		#erase all objects at their old locations, before they move
		for object in objects:
			object.clear()
		
		#handle keys and exit game if needed
		player_action = handle_keys()
		if player_action == 'exit':
			save_game()
			break
			
		#let monsters take their turn
		if game_state == 'playing' and player_action != 'didnt-take-turn':
			for object in objects:
				if object.ai:
					object.ai.take_turn()
		
main_menu()
		
		
		
		
		
		