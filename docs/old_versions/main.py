import digitalio
import board
import time
import usb_hid
import displayio
import terminalio
import busio
import fourwire
import adafruit_ahtx0
from circuitpython_st7796s import ST7796S
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode
from adafruit_display_text.label import Label

displayio.release_displays()

i2c = busio.I2C(board.GP1, board.GP4) #initilize i2c method of connecting itself to put it into the variables required for initilising the sensor

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
    from displayio import FourWire  # not on Pico, so you need a "fourwire.py" helper


loc = clk.value
cc = ConsumerControl(usb_hid.devices)
i = 0
last_event_time = 0

sensor = adafruit_ahtx0.AHTx0(i2c) #initilize the sensor itself



# Create display bus
display_bus = FourWire(
    spi,
    command=dc,
    chip_select=cs,
    reset=rst
)

# Initialize display
display = ST7796S(
    display_bus,    # pass the bus object here
    width=480,
    height=320,
    rotation=0
)

bl = digitalio.DigitalInOut(board.GP21)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True   # turn on backlight



group = displayio.Group()
display.root_group = group #creates a container for information on the screen

#printing the text just for fun
label = Label(terminalio.FONT, text="Welcome Nikita")#creating lable(text) to display it on the screen

label.x = 20 #position text on the screen(like in pygame)
label.y = 20

group.append(label)#atach text to the group, Now it becomes visible

group.scale = 2

#printing the temperature and humidity

#Temperature
label_temp = Label(terminalio.FONT, text="")

label_temp.x = 20
label_temp.y = 60

group.append(label_temp)


#Humidity
label_humidity = Label(terminalio.FONT, text="")

label_humidity.x = 20
label_humidity.y = 78

group.append(label_humidity)




while True:
    
    #Temperature updating
    temperature = sensor.temperature #get the data itself from the sensor
    humidity = sensor.relative_humidity
    
    label_temp.text = f"Room Temp: {temperature:.1f} C"
    label_humidity.text = f"Humidity: {humidity:.1f} %"
    
    # rotary encoder logic
    cur = clk.value
    if cur != loc:
        if dt.value != cur:
            cc.send(ConsumerControlCode.VOLUME_INCREMENT)
        else:
            cc.send(ConsumerControlCode.VOLUME_DECREMENT)
    loc = cur
    
    
    if not btn.value:
        i += 1
        last_event_time = time.monotonic()
        print("Button")
        
    if time.monotonic() - last_event_time > 0.5:   
        if i == 1:
            cc.send(ConsumerControlCode.PLAY_PAUSE)
        
        if i == 3:
            cc.send(ConsumerControlCode.SCAN_PREVIOUS_TRACK)
        
        if i == 2:
            cc.send(ConsumerControlCode.SCAN_NEXT_TRACK)
        i = 0
    
        
    time.sleep(0.3)
        


