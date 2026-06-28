import digitalio
import board
import time
import usb_hid
import usb_cdc
import displayio
import terminalio
import busio
import fourwire
import adafruit_ahtx0
import adafruit_imageload
from circuitpython_st7796s import ST7796S
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_display_text.label import Label
from adafruit_display_shapes.rect import Rect

displayio.release_displays()

i2c = busio.I2C(board.GP1,board.GP4)  #Initilize i2c method of connecting itself to put it into the variables required for initilising the sensor

clk = digitalio.DigitalInOut(board.GP12)
dt = digitalio.DigitalInOut(board.GP11)
btn = digitalio.DigitalInOut(board.GP10)

spi = busio.SPI(clock=board.GP18, MOSI=board.GP19)
cs = board.GP17
dc = board.GP16
rst = board.GP20

clk.direction = digitalio.Direction.INPUT
clk.pull = digitalio.Pull.UP
dt.direction = digitalio.Direction.INPUT
dt.pull = digitalio.Pull.UP
btn.direction = digitalio.Direction.INPUT
btn.pull = digitalio.Pull.UP

try:
    from fourwire import FourWire
except ImportError:
    from displayio import FourWire

# Variables for encoder logic
loc = clk.value
cc = ConsumerControl(usb_hid.devices)
i = 0
last_event_time = 0

# Serial channel to PC
stats_serial = usb_cdc.data

# Dictionary for the field
pc_stats = {}

# Variables for menu innitialization
current_mode = "menu"
sub_mode = None
menu_index = 0

menu_group = None
stats_group = displayio.Group()
volume_group = displayio.Group()

# Initilizing the sensor
sensor = adafruit_ahtx0.AHTx0(i2c)

# Colours
WHITE = 0xFFFFFF
TIFFANY = 0x0ABAB5
BLACK = 0x000000

# Creating display bus
display_bus = FourWire(
    spi,
    command=dc,
    chip_select=cs,
    reset=rst
)

# Initializing display
display = ST7796S(
    display_bus,
    width=480,
    height=320,
    rotation=0
)

bl = digitalio.DigitalInOut(board.GP21)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True  # Turn on backlight

# Creating a group
group = displayio.Group()
display.root_group = group  # Creates a container for information on the screen

# Printing the text just for fun
label = Label(terminalio.FONT, text="Welcome Nikita")  # creating lable(text) to display it on the screen

label.x = 20  # Positioning text on the screen(like in pygame)
label.y = 20

group.append(label)  # Ataching text to the group, now it becomes visible

group.scale = 2

# Printing the temperature, humidity and CPU utillization

# Temperature
label_temp = Label(terminalio.FONT, text="")

label_temp.x = 20
label_temp.y = 60

stats_group.append(label_temp)

# Humidity
label_humidity = Label(terminalio.FONT, text="")

label_humidity.x = 20
label_humidity.y = 78

stats_group.append(label_humidity)

# CPU utilization:
label_cpu_util = Label(terminalio.FONT, text="")

label_cpu_util.x = 20
label_cpu_util.y = 98

stats_group.append(label_cpu_util)

# Images for the volume menu
icons = {}

for name in ["prev", "play", "next", "volume", "back"]:
    bitmap, palette = adafruit_imageload.load(
        f"/images/{name}.bmp",
        bitmap=displayio.Bitmap,
        palette=displayio.Palette
    )
    icons[name] = {
        "bitmap": bitmap,
        "palette": palette
    }

buttons = []

start_x = 25
spacing = 40
y_pos = 70

names =  ["prev", "play", "next", "volume", "back"]

for i, name in enumerate(names):
    tile = displayio.TileGrid(
        icons[name]["bitmap"],
        pixel_shader=icons[name]["palette"],
        x=start_x + i * spacing,
        y=y_pos
    )  
    volume_group.append(tile)
    buttons.append(tile)
    
selected_index = 0

highlight = Rect(
    x=buttons[selected_index].x - 2,
    y=buttons[selected_index].y - 2,
    width=buttons[selected_index].width + 32,
    height=buttons[selected_index].height + 32,
    outline=TIFFANY
)

volume_group.insert(0, highlight)
    

def switch_mode(new_mode):
    global current_mode
    group.pop()
    
    # Sending message to the PC to start data transfer:
    if current_mode != "stats" and new_mode == "stats":
        if stats_serial is not None:
            stats_serial.write(b"START\n")
    
    if current_mode == "stats" and new_mode != "stats":
        if stats_serial is not None:
            stats_serial.write(b"STOP\n")
            
    current_mode = new_mode
    
    if new_mode == "menu":
        group.append(menu_group)
    elif new_mode == "stats":
        group.append(stats_group)
    elif new_mode == "volume":
        group.append(volume_group)

def select_menu_mode():
    
    # Creating a group for menu templates
    menu_group = displayio.Group()
    group.append(menu_group)

    # Menu teplates parrameters and position
    box_w = 80
    box_h = 50
    gap = 20
    y_pos = 60

    # Left Box Creation
    box_vol = Rect(x=30, y=y_pos, width=box_w, height=box_h, fill=WHITE)
    menu_group.append(box_vol)

    # Right Box Creation
    box_stats = Rect(x=30 + box_w + gap, y=y_pos, width=box_w, height=box_h, fill=WHITE)
    menu_group.append(box_stats)

    # Selection Indicator Creation
    underline = Rect(x=30, y=y_pos + box_h + 6, width=box_w, height=5, fill=TIFFANY)
    menu_group.append(underline)

    # Text Inside The Templates
    label_vol = Label(terminalio.FONT, text="VOLUME", color=BLACK)
    label_vol.anchor_point = (0.5, 0.5)
    label_vol.anchored_position = (30 + box_w/2, y_pos + box_h/2)
    menu_group.append(label_vol)

    label_stats = Label(terminalio.FONT, text="STATS", color=BLACK)
    label_stats.anchor_point = (0.5, 0.5)
    label_stats.anchored_position = (30 + box_w + gap + box_w/2, y_pos + box_h/2)
    menu_group.append(label_stats)

    return underline, box_w, gap, menu_group

underline, box_w, gap, menu_group = select_menu_mode()


# Main Loop
while True:


    # Encoder logic handling
    cur = clk.value
    moved = cur != loc
    pressed = not btn.value
    

    if current_mode == "menu":
        # Updating Rotary Encoder
        if moved:
            if dt.value != cur:
                menu_index = 1
            else:
                menu_index = 0
            loc = cur

            # Updating Menu Selection
        if menu_index == 0:
            underline.x = 30
        else:
            underline.x = 30 + box_w + gap
        
        if pressed:
            while not btn.value:
                pass
            if menu_index == 0:
                switch_mode("volume")

            elif menu_index == 1:
                switch_mode("stats")




    elif current_mode == "stats":
        
        if stats_serial is not None and stats_serial.in_waiting > 0:
            try:
                packet = stats_serial.readline().decode().strip()
                
                # Ignore the empty fields:
                if packet:
                    fields = packet.split(";")
                
                    for field in fields:
                    
                        # Ignore malformed fields:
                        if "=" not in field:
                            continue
                    
                        key, value = field.split("=", 1)
                        pc_stats[key] = value
                        
            except Exception:
                pass
                
        # CPU utilization text updating
        label_cpu_util.text = f"CPU Utilization: {pc_stats.get('CPU', '--')} %"
        
        # Sensor update
        if time.monotonic() - last_event_time > 1:
            
            # Temperature updating
            temperature = sensor.temperature  # Getting data from the sensor
            humidity = sensor.relative_humidity
            
            # Temperature text updating
            label_temp.text = f"Room Temp: {temperature:.1f} C"
            label_humidity.text = f"Humidity: {humidity:.1f} %"
            

            last_event_time = time.monotonic()
            
        if pressed:
            while not btn.value:
                pass
            switch_mode("menu")


    elif current_mode == "volume":
            
        if sub_mode == "adjust_volume":
            
            if moved:
                cur = clk.value
                if dt.value != cur:
                    cc.send(ConsumerControlCode.VOLUME_INCREMENT)
                else:
                    cc.send(ConsumerControlCode.VOLUME_DECREMENT)
                loc = cur
            
            if pressed:
                while not btn.value:
                    pass
                sub_mode = None
                
            continue
            
        if moved:
            if dt.value != cur:
                selected_index += 1
            else:
                selected_index -= 1
            
            selected_index %= len(buttons)
            loc = cur
            
            highlight.x = buttons[selected_index].x - 2
            highlight.y = buttons[selected_index].y - 2
            
        if pressed:
            while not btn.value:
                pass
            if selected_index == 0:
                cc.send(ConsumerControlCode.SCAN_PREVIOUS_TRACK)
            
            elif selected_index == 1:
                cc.send(ConsumerControlCode.PLAY_PAUSE)
            
            elif selected_index == 2:
                cc.send(ConsumerControlCode.SCAN_NEXT_TRACK)
            
            elif selected_index == 3:
                sub_mode = "adjust_volume"
            
            elif selected_index == 4:
                sub_mode = None
                switch_mode("menu")
            
            last_event_time = time.monotonic()
