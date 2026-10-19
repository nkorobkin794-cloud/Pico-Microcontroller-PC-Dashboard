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
serial_buffer = ""
last_encoder_move = 0

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

# Root display group
group = displayio.Group()
display.root_group = group  # Creates a container for information on the screen


# /// Stats dashboard ///

NAVY = 0x101820
PANEL = 0x1B2835
PANEL_SELECTED = 0x263A49
MUTED = 0x91A4B7
GREEN = 0x5CE0A0

# Format: (data key, display name, unit, category)
stats_items = [
    ("CPU", "CPU Usage", "%", "PC"),
    ("RAM", "Memory Usage", "%", "PC"),
    ("DISK", "Disk Usage", "%", "PC"),
    ("UPLOAD", "Network Upload", "KB/s", "PC"),
    ("DOWNLOAD", "Network Download", "KB/s", "PC"),
    ("TEMP", "Room Temperature", "C", "ROOM"),
    ("HUMIDITY", "Humidity", "%", "ROOM"),
    ("UPTIME", "PC Uptime", "", "PC"),
]

stats_index = 0
stats_control_index = 0  # 0 = previous, 1 = next, 2 = back
room_temperature = "--"
room_humidity = "--"

# Dashboard background and header
stats_group.append(Rect(0, 0, 480, 5, fill=TIFFANY))

title = Label(
    terminalio.FONT,
    text="SYSTEM MONITOR",
    color=WHITE,
    x=20,
    y=22
)
stats_group.append(title)

welcome_stats = Label(
    terminalio.FONT,
    text="WELCOME, NIKITA!",
    color=TIFFANY,
    x=330,
    y=22
)
stats_group.append(welcome_stats)

subtitle = Label(
    terminalio.FONT,
    text="PC PERFORMANCE  /  ROOM ENVIRONMENT",
    color=MUTED,
    x=20,
    y=43
)
stats_group.append(subtitle)
stats_group.append(Rect(20, 53, 440, 1, fill=TIFFANY))

# Display five metrics per page
stats_page = 0
stats_rows = []

row_y = [75, 112, 149, 186, 223]

for y in row_y:
    panel = Rect(20, y - 13, 440, 32, fill=PANEL)
    stats_group.append(panel)

    name_label = Label(
        terminalio.FONT,
        text="",
        color=WHITE,
        x=32,
        y=y
    )

    value_label = Label(
        terminalio.FONT,
        text="--",
        color=GREEN,
        x=300,
        y=y
    )

    stats_group.append(name_label)
    stats_group.append(value_label)
    stats_rows.append((panel, name_label, value_label))


# Bottom-right virtual controls, selected using the rotary encoder
stats_group.append(Rect(20, 270, 440, 1, fill=0x354554))

stats_controls = []
control_specs = [
    ("<", 322, 44),
    (">", 368, 44),
    ("BACK", 414, 44),
]

for label_text, x, width in control_specs:
    control_bg = Rect(x, 282, width, 27, fill=PANEL)
    control_label = Label(
        terminalio.FONT,
        text=label_text,
        color=WHITE
    )
    control_label.anchor_point = (0.5, 0.5)
    control_label.anchored_position = (x + width // 2, 282 + 27 // 2)
    stats_group.append(control_bg)
    stats_group.append(control_label)
    stats_controls.append({
        "bg": control_bg,
        "label": control_label,
        "x": x,
        "width": width,
    })

stats_control_highlight = Rect(
    stats_controls[0]["x"], 282,
    stats_controls[0]["width"], 27,
    outline=TIFFANY
)
stats_group.append(stats_control_highlight)

stats_footer = Label(
    terminalio.FONT,
    text="ROTATE: SELECT CONTROL   PRESS: ACTIVATE",
    color=MUTED,
    x=20,
    y=296
)
stats_group.append(stats_footer)


def update_stats_ui():
    start = stats_page * 5

    for row, labels in enumerate(stats_rows):
        panel, name_label, value_label = labels
        item_index = start + row

        # Hide rows with no corresponding metric
        if item_index >= len(stats_items):
            panel.hidden = True
            name_label.hidden = True
            value_label.hidden = True
            continue

        panel.hidden = False
        name_label.hidden = False
        value_label.hidden = False

        key, name, unit, category = stats_items[item_index]

        if key == "TEMP":
            value = room_temperature
        elif key == "HUMIDITY":
            value = room_humidity
        else:
            value = pc_stats.get(key, "--")

        name_label.text = name

        if value != "--" and unit:
            value_label.text = "{} {}".format(value, unit)
        else:
            value_label.text = str(value)

    # Highlight the selected navigation control
    for i, control in enumerate(stats_controls):
        control["bg"].fill = (
            PANEL_SELECTED if i == stats_control_index else PANEL
        )

    selected_control = stats_controls[stats_control_index]
    stats_control_highlight.x = selected_control["x"]
    
update_stats_ui()


# /// Volume Menu ///

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

volume_highlight = Rect(
    x=buttons[selected_index].x - 2,
    y=buttons[selected_index].y - 2,
    width=buttons[selected_index].width + 32,
    height=buttons[selected_index].height + 32,
    outline=TIFFANY
)

volume_group.insert(0, volume_highlight)
    
# Main view logic
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

    menu_group = displayio.Group()

    menu_group.append(Rect(0, 0, 480, 5, fill=TIFFANY))

    heading = Label(
        terminalio.FONT,
        text="PICO CONTROL CENTER",
        color=WHITE,
        x=24,
        y=30
    )
    menu_group.append(heading)

    welcome = Label(
        terminalio.FONT,
        text="WELCOME, NIKITA!",
        color=TIFFANY,
        x=330,
        y=30
    )
    menu_group.append(welcome)

    subtitle = Label(
        terminalio.FONT,
        text="Choose a function",
        color=MUTED,
        x=24,
        y=55
    )
    menu_group.append(subtitle)
    menu_group.append(Rect(24, 68, 432, 1, fill=TIFFANY))

    box_w = 185
    box_h = 112
    gap = 26
    y_pos = 112
    left_x = 42
    right_x = left_x + box_w + gap

    box_vol = Rect(
        x=left_x, y=y_pos, width=box_w, height=box_h,
        outline=PANEL
    )
    box_stats = Rect(
        x=right_x, y=y_pos, width=box_w, height=box_h,
        outline=PANEL
    )
    menu_group.append(box_vol)
    menu_group.append(box_stats)

    label_vol = Label(
        terminalio.FONT, text="VOLUME", color=WHITE
    )
    label_vol.anchor_point = (0.5, 0.5)
    label_vol.anchored_position = (left_x + box_w // 2, y_pos + 48)
    menu_group.append(label_vol)

    vol_hint = Label(
        terminalio.FONT, text="Media controls", color=MUTED
    )
    vol_hint.anchor_point = (0.5, 0.5)
    vol_hint.anchored_position = (left_x + box_w // 2, y_pos + 75)
    menu_group.append(vol_hint)

    label_stats = Label(
        terminalio.FONT, text="SYSTEM MONITOR", color=WHITE
    )
    label_stats.anchor_point = (0.5, 0.5)
    label_stats.anchored_position = (right_x + box_w // 2, y_pos + 48)
    menu_group.append(label_stats)

    stats_hint = Label(
        terminalio.FONT, text="PC + room stats", color=MUTED
    )
    stats_hint.anchor_point = (0.5, 0.5)
    stats_hint.anchored_position = (right_x + box_w // 2, y_pos + 75)
    menu_group.append(stats_hint)

    menu_highlight = Rect(
        x=left_x, y=y_pos, width=box_w, height=box_h,
        outline=TIFFANY
    )
    menu_group.append(menu_highlight)

    instruction = Label(
        terminalio.FONT,
        text="ROTATE TO CHOOSE   /   PRESS TO OPEN",
        color=MUTED,
        x=24,
        y=270
    )
    menu_group.append(instruction)

    return menu_highlight, box_w, gap, menu_group


menu_highlight, box_w, gap, menu_group = select_menu_mode()

group.append(menu_group)

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
            menu_highlight.x = 42
        else:
            menu_highlight.x = 42 + box_w + gap
        
        if pressed:
            while not btn.value:
                pass
            if menu_index == 0:
                switch_mode("volume")

            elif menu_index == 1:
                switch_mode("stats")




    elif current_mode == "stats":

        # Read PC data without waiting for a full line
        if stats_serial is not None and stats_serial.in_waiting > 0:
            try:
                serial_buffer += stats_serial.read(
                    stats_serial.in_waiting
                ).decode()

                while "\n" in serial_buffer:
                    packet, serial_buffer = serial_buffer.split("\n", 1)
                    packet = packet.strip()

                    if packet:
                        for field in packet.split(";"):
                            if "=" in field:
                                key, value = field.split("=", 1)
                                pc_stats[key] = value

            except Exception:
                pass

        # Rotate to choose one of the three on-screen controls
        if moved:
            loc = cur
            now = time.monotonic()

            if now - last_encoder_move >= 0.004:
                if dt.value != cur:
                    stats_control_index = (
                        stats_control_index + 1
                    ) % len(stats_controls)
                else:
                    stats_control_index = (
                        stats_control_index - 1
                    ) % len(stats_controls)

                last_encoder_move = now
                update_stats_ui()

        # Update room sensors once per second
        if time.monotonic() - last_event_time > 1:
            try:
                room_temperature = "{:.1f}".format(
                    sensor.temperature
                )
                room_humidity = "{:.1f}".format(
                    sensor.relative_humidity
                )
                update_stats_ui()
            except Exception:
                pass

            last_event_time = time.monotonic()

        # Activate the selected on-screen control
        if pressed:
            while not btn.value:
                pass

            if stats_control_index == 0:
                stats_page = (stats_page - 1) % 2
            elif stats_control_index == 1:
                stats_page = (stats_page + 1) % 2
            else:
                switch_mode("menu")

            update_stats_ui()




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
            
            volume_highlight.x = buttons[selected_index].x - 2
            volume_highlight.y = buttons[selected_index].y - 2
            
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
