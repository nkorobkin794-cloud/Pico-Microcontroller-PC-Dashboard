import psutil
import serial
import time

# Variables
PORT = "COM4"
BAUD = 115200

ser = None
sending = False


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
    
    # Check for commands from Pico
    if ser.in_waiting > 0:
        command = ser.readline().decode().strip()
        
        if command == "START":
            sending = True
            print("Started data transfer")
            
        elif command == "STOP":
            sending = False
            print("Ended data transfer")
        
    if sending:
        try:
            cpu = psutil.cpu_percent(interval=1)
        
            # Data packet structure for sending:
            packet = (
            f"CPU={cpu:.1f}\n"
            )
        
            # DEBUG: print the sending packets
            print("SENDING:", repr(packet))

            # Sending the encoded data
            ser.write(packet.encode("utf-8"))
            ser.flush()

            # DEBUG: print if the write was successful
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
