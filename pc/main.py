import psutil
import serial
import time

# Variables
PORT = "COM4"
BAUD = 115200

ser = None

print("STARTING SCRIPT...")

# Wait for Pico to establish connection
while ser is None:
    try:
        print(f"Trying to connect to {PORT}...")
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(2)  # allow Pico reset
        print("Connected to Pico!")

    except serial.SerialException as e:
        print("Waiting for Pico ...", e)
        time.sleep(1)


# Main Loop
while True:
    try:
        cpu = psutil.cpu_percent(interval=1)

        data = f"{cpu}\n"
        print("SENDING:", repr(data))

        ser.write(data.encode())
        ser.flush()

        print("WRITE OK")

    except serial.SerialException as e:
        print("Pico disconnected:", e)

        try:
            ser.close()
        except:
            pass

        ser = None

        while ser is None:
            try:
                print("Reconnecting...")
                ser = serial.Serial(PORT, BAUD, timeout=1)
                time.sleep(2)
                print("Reconnected!")

            except serial.SerialException:
                time.sleep(1)