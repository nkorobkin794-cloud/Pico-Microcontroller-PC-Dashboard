import digitalio
import board
import gc
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

# Clearing RAM
gc.collect()

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

# Separate data storage for the Volume menu
player_data = {}
player_serial_buffer = b""
last_mode_announce = 0

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
    ("FREQ", "CPU Clock", "MHz", "PC"),
    ("THREADS", "Logical CPUs", "", "PC"),
    ("PROCESSES", "Running Processes", "", "PC"),
    ("BATTERY", "Battery", "%", "PC"),
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
    # Reclaim unused memory before refreshing the display.
    gc.collect()

    start = stats_page * len(stats_rows)

    for row, labels in enumerate(stats_rows):
        panel, name_label, value_label = labels
        item_index = start + row

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

        # Do not rebuild the text when it has not changed.
        if name_label.text != name:
            name_label.text = name

        if value != "--" and unit:
            display_value = "{} {}".format(value, unit)
        else:
            display_value = str(value)

        if value_label.text != display_value:
            value_label.text = display_value

    for i, control in enumerate(stats_controls):
        control["bg"].fill = (
            PANEL_SELECTED if i == stats_control_index else PANEL
        )

    selected_control = stats_controls[stats_control_index]
    stats_control_highlight.x = selected_control["x"]

    
update_stats_ui()


# /// Volume Menu ///

# Load the existing icons
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

# Player header
volume_group.append(Rect(0, 0, 480, 5, fill=TIFFANY))

volume_group.append(Label(
    terminalio.FONT,
    text="MEDIA PLAYER",
    color=WHITE,
    x=24,
    y=25
))

volume_group.append(Label(
    terminalio.FONT,
    text="PLAYBACK CONTROLS",
    color=MUTED,
    x=24,
    y=45
))

volume_group.append(Rect(20, 57, 440, 1, fill=TIFFANY))

# Track information panel
volume_group.append(Rect(20, 68, 440, 100, fill=PANEL))

media_title = Label(
    terminalio.FONT,
    text="Waiting for track info...",
    color=WHITE,
    x=32,
    y=88
)
volume_group.append(media_title)

media_artist = Label(
    terminalio.FONT,
    text="Artist unavailable",
    color=MUTED,
    x=32,
    y=111
)
volume_group.append(media_artist)

media_status = Label(
    terminalio.FONT,
    text="Media controls ready",
    color=TIFFANY,
    x=32,
    y=143
)
volume_group.append(media_status)

# Volume indicator
volume_group.append(Rect(310, 119, 130, 1, fill=0x354554))

volume_group.append(Label(
    terminalio.FONT,
    text="VOLUME",
    color=MUTED,
    x=310,
    y=88
))

volume_level = 50
volume_actual_available = False

volume_value_label = Label(
    terminalio.FONT,
    text="50%*",
    color=GREEN,
    x=390,
    y=88
)
volume_group.append(volume_value_label)

# Ten individually updateable segments
volume_segments = []

for i in range(10):
    segment = Rect(
        310 + i * 13,
        128,
        10,
        8,
        fill=PANEL_SELECTED
    )
    volume_group.append(segment)
    volume_segments.append(segment)

volume_note = Label(
    terminalio.FONT,
    text="*ESTIMATE",
    color=MUTED,
    x=310,
    y=151
)
volume_group.append(volume_note)

# Five original icons, arranged across the bottom
buttons = []
volume_slots = [48, 144, 240, 336, 432]
button_y = 222

for i, name in enumerate(["prev", "play", "next", "volume", "back"]):

    bitmap = icons[name]["bitmap"]
    palette = icons[name]["palette"]

    tile = displayio.TileGrid(
        bitmap,
        pixel_shader=palette,
        x=volume_slots[i] - bitmap.width // 2,
        y=button_y - bitmap.height // 2
    )

    volume_group.append(tile)
    buttons.append(tile)

selected_index = 0

volume_highlight = Rect(
    volume_slots[selected_index] - 24,
    198,
    48,
    48,
    outline=TIFFANY
)
volume_group.append(volume_highlight)

volume_group.append(Label(
    terminalio.FONT,
    text="ROTATE: SELECT   PRESS: ACTIVATE",
    color=MUTED,
    x=24,
    y=280
))



def update_volume_display(level=None, actual=False):
    global volume_level

    if level is not None:
        try:
            new_level = float(level)

            if 0 <= new_level <= 100:
                volume_level = int(round(new_level))
            else:
                actual = False

        except (ValueError, TypeError):
            actual = False

    value_text = (
        "{}%".format(volume_level)
        if actual else "{}%*".format(volume_level)
    )
    note_text = "SYSTEM VOLUME" if actual else "*ESTIMATE"

    if volume_value_label.text != value_text:
        volume_value_label.text = value_text

    if volume_note.text != note_text:
        volume_note.text = note_text

    # Fill a segment for each 10% of volume
    filled_segments = (volume_level + 9) // 10

    for index, segment in enumerate(volume_segments):
        segment.fill = (
            TIFFANY if index < filled_segments
            else PANEL_SELECTED
        )

update_volume_display()

    
# Main view logic
def switch_mode(new_mode):
    global current_mode, player_serial_buffer
    global last_mode_announce, volume_actual_available
    group.pop()
    
    # Sending message to the PC to start data transfer:
    if current_mode != "stats" and new_mode == "stats":
        if stats_serial is not None:
            stats_serial.write(b"START\n")
            
        last_mode_announce = time.monotonic()
    
    if current_mode == "stats" and new_mode != "stats":
        if stats_serial is not None:
            stats_serial.write(b"STOP\n")
            
    # Separate communication for the Volume menu
    if current_mode != "volume" and new_mode == "volume":
        gc.collect()
        player_serial_buffer = b""
        player_data.clear()

        if stats_serial is not None:
            stats_serial.write(b"PLAYER_START\n")
        
        last_mode_announce = time.monotonic()

    elif current_mode == "volume" and new_mode != "volume":
        if stats_serial is not None:
            stats_serial.write(b"PLAYER_STOP\n")
            
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
    
    # Repeat the current mode command to support late PC startup.
    now = time.monotonic()

    if (
        stats_serial is not None
        and now - last_mode_announce >= 2
    ):
        if current_mode == "stats":
            stats_serial.write(b"START\n")
            last_mode_announce = now

        elif current_mode == "volume":
            stats_serial.write(b"PLAYER_START\n")
            last_mode_announce = now
    

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

            
            page_count = (
                len(stats_items) + len(stats_rows) - 1
            ) // len(stats_rows)

            if stats_control_index == 0:
                stats_page = (stats_page - 1) % page_count
            elif stats_control_index == 1:
                stats_page = (stats_page + 1) % page_count
            else:
                switch_mode("menu")


            update_stats_ui()




    elif current_mode == "volume":
        
        
        
        # Separate receiver for Volume-menu packets.
        # Buffer raw bytes so UTF-8 characters cannot be split
        # across separate decode operations.
        if (
            stats_serial is not None
            and stats_serial.in_waiting > 0
        ):
            waiting = stats_serial.in_waiting
            player_serial_buffer += stats_serial.read(waiting)

        # Decode only after a complete packet has arrived.
        while b"\n" in player_serial_buffer:
            packet_bytes, player_serial_buffer = (
                player_serial_buffer.split(b"\n", 1)
            )

            try:
                packet = packet_bytes.decode("utf-8").strip()
            except UnicodeError:
                # Ignore a corrupted packet instead of crashing.
                continue

            if not packet.startswith("PLAYER|"):
                continue

            fields = packet.split("|")[1:]

            for field in fields:
                if "=" in field:
                    key, value = field.split("=", 1)
                    player_data[key] = value

            new_title = player_data.get(
                "TITLE", "Track info unavailable"
            )[:32]

            new_artist = player_data.get(
                "ARTIST", "Media info unavailable"
            )[:36]

            new_status = player_data.get(
                "PLAYBACK", "Media controls ready"
            )[:34]

            if media_title.text != new_title:
                media_title.text = new_title

            if media_artist.text != new_artist:
                media_artist.text = new_artist

            if media_status.text != new_status:
                media_status.text = new_status

            raw_volume = player_data.get("VOLUME", "--")

            try:
                actual_volume = float(raw_volume)

                if 0 <= actual_volume <= 100:
                    volume_actual_available = True
                    update_volume_display(actual_volume, True)

                elif not volume_actual_available:
                    update_volume_display(None, False)

            except (ValueError, TypeError):
                if not volume_actual_available:
                    update_volume_display(None, False)

            
        if sub_mode == "adjust_volume":
            
            if moved:
                cur = clk.value

                if dt.value != cur:
                    cc.send(ConsumerControlCode.VOLUME_INCREMENT)

                    if not volume_actual_available:
                        volume_level = min(100, volume_level + 2)

                else:
                    cc.send(ConsumerControlCode.VOLUME_DECREMENT)

                    if not volume_actual_available:
                        volume_level = max(0, volume_level - 2)

                # Keep the display consistent with its active data source.
                update_volume_display(None, volume_actual_available)

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
            
            volume_highlight.x = volume_slots[selected_index] - 24
            volume_highlight.y = 198
            
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