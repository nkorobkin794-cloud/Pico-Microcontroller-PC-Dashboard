import psutil
import serial
import time

# Configuration
PORT = "COM4"
BAUD = 115200
SEND_INTERVAL = 1.0

ser = None
sending = False

print("STARTING SCRIPT...")

# Connect to the Pico
while ser is None:
    try:
        print(f"Trying to connect to {PORT}...")
        ser = serial.Serial(PORT, BAUD, timeout=1)
        time.sleep(2)
        ser.reset_input_buffer()
        print("Connected to Pico!")

    except serial.SerialException as e:
        print("Waiting for Pico...", e)
        time.sleep(1)

# Initialize counters
start_time = time.monotonic()
last_send = 0

# Initialize CPU measurement
psutil.cpu_percent(interval=None)

# Initialize network counters
net_previous = psutil.net_io_counters()
net_previous_time = time.monotonic()

# Main loop
while True:
    try:
        # Read commands from the Pico
        while ser.in_waiting > 0:
            command = ser.readline().decode(
                "utf-8", errors="ignore"
            ).strip()

            if command == "START":
                sending = True
                print("Started data transfer")

            elif command == "STOP":
                sending = False
                print("Stopped data transfer")

        if not sending:
            time.sleep(0.05)
            continue

        # Limit the sending rate
        now = time.monotonic()
        if now - last_send < SEND_INTERVAL:
            time.sleep(0.02)
            continue

        last_send = now

        # Collect system statistics
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage(
            psutil.disk_partitions()[0].mountpoint
        ).percent

        # Network throughput
        net_current = psutil.net_io_counters()
        elapsed = max(now - net_previous_time, 0.001)

        upload = (
            net_current.bytes_sent - net_previous.bytes_sent
        ) / elapsed / 1024

        download = (
            net_current.bytes_recv - net_previous.bytes_recv
        ) / elapsed / 1024

        net_previous = net_current
        net_previous_time = now

        # PC uptime
        uptime = int(time.time() - psutil.boot_time())

        # Send one semicolon-separated packet
        packet = (
            f"CPU={cpu:.1f};"
            f"RAM={ram:.1f};"
            f"DISK={disk:.1f};"
            f"UPLOAD={upload:.1f};"
            f"DOWNLOAD={download:.1f};"
            f"UPTIME={uptime}\n"
        )

        ser.write(packet.encode("utf-8"))

        print("SENT:", packet.strip())

    except (serial.SerialException, OSError) as e:
        print("Pico disconnected:", e)

        try:
            ser.close()
        except Exception:
            pass

        ser = None

        while ser is None:
            try:
                print("Reconnecting...")
                ser = serial.Serial(PORT, BAUD, timeout=1)
                time.sleep(2)
                ser.reset_input_buffer()
                print("Reconnected!")

            except serial.SerialException:
                time.sleep(1)
