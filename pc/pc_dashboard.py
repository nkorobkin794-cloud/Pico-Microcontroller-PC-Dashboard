import psutil
import serial
import time
import asyncio


# Windows media metadata using the working WinRT packages
try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager
        as MediaManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus
        as PlaybackStatus,
    )
    MEDIA_API_AVAILABLE = True
except Exception as error:
    print("Media API import failed:", repr(error))
    MEDIA_API_AVAILABLE = False


# Optional Windows master-volume reading
try:
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    VOLUME_API_AVAILABLE = True
except Exception:
    VOLUME_API_AVAILABLE = False


def clean_player_field(value, fallback="Unknown", limit=48):
    value = str(value or fallback)
    value = value.replace("|", "/")
    value = value.replace("\r", " ").replace("\n", " ")
    return value.strip()[:limit]


# Convert Russian Cyrillic into Latin characters for the Pico.
# English text and other characters pass through unchanged.
RUSSIAN_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g",
    "д": "d", "е": "e", "ё": "yo", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


def transliterate_russian(text):
    result = []

    for character in str(text):
        lowercase = character.lower()
        replacement = RUSSIAN_TO_LATIN.get(lowercase)

        if replacement is None:
            result.append(character)
        elif character.isupper() and replacement:
            result.append(replacement[0].upper() + replacement[1:])
        else:
            result.append(replacement)

    return "".join(result)

async def read_media_info_async():
    manager = await MediaManager.request_async()
    sessions = list(manager.get_sessions())

    if not sessions:
        return (
            "No media playing",
            "Open a supported media app",
            "No active session",
        )

    # Prefer a session that is currently playing.
    session = sessions[0]

    for candidate in sessions:
        info = candidate.get_playback_info()

        if (
            info is not None
            and info.playback_status == PlaybackStatus.PLAYING
        ):
            session = candidate
            break

    properties = await session.try_get_media_properties_async()
    playback = session.get_playback_info()

    title = clean_player_field(
        properties.title,
        "Unknown title",
    )
    artist = clean_player_field(
        properties.artist,
        "Unknown artist",
    )

    if playback is None:
        status = "Status unavailable"
    elif playback.playback_status == PlaybackStatus.PLAYING:
        status = "Playing"
    elif playback.playback_status == PlaybackStatus.PAUSED:
        status = "Paused"
    elif playback.playback_status == PlaybackStatus.STOPPED:
        status = "Stopped"
    else:
        status = "Not playing"

    return title, artist, status


def get_media_info():
    if not MEDIA_API_AVAILABLE:
        return (
            "Media info unavailable",
            "Media library unavailable",
            "Metadata API unavailable",
        )

    try:
        return asyncio.run(read_media_info_async())
    except Exception as error:
        print("Media read failed:", repr(error))
        return (
            "Media info unavailable",
            "Check supported media app",
            "Media API error",
        )


def get_volume_percent():
    if not VOLUME_API_AVAILABLE:
        return "--"

    try:
        speakers = AudioUtilities.GetSpeakers()

        try:
            endpoint = speakers.EndpointVolume
        except Exception:
            interface = speakers.Activate(
                IAudioEndpointVolume._iid_,
                CLSCTX_ALL,
                None,
            )
            endpoint = cast(
                interface,
                POINTER(IAudioEndpointVolume),
            )

        level = round(
            endpoint.GetMasterVolumeLevelScalar() * 100
        )
        return str(max(0, min(100, level)))

    except Exception:
        return "--"


# Configuration
PORT = "COM4"
BAUD = 115200
SEND_INTERVAL = 1.0

ser = None
sending = False
player_sending = False
last_player_send = 0.0
last_player_state = None

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
                if not sending:
                    last_send = 0
                    print("Started system monitor transfer")

                sending = True
                player_sending = False

            elif command == "STOP":
                sending = False
                player_sending = False

            elif command == "PLAYER_START":
                if not player_sending:
                    last_player_send = 0.0
                    last_player_state = None
                    print("Started player data transfer")

                sending = False
                player_sending = True

            elif command == "PLAYER_STOP":
                if player_sending:
                    print("Stopped player data transfer")

                player_sending = False
                last_player_state = None

        # Independent player sender: transmit only when values change
        now_player = time.monotonic()

        if (
            player_sending
            and now_player - last_player_send >= SEND_INTERVAL
        ):
            last_player_send = now_player

            title, artist, playback = get_media_info()
            volume = get_volume_percent()

            # Prepare text for the Pico's built-in font
            title = transliterate_russian(
                clean_player_field(title)
            )[:32]

            artist = transliterate_russian(
                clean_player_field(artist)
            )[:36]

            playback = clean_player_field(playback)

            current_player_state = (
                volume,
                title,
                artist,
                playback,
            )

            # First packet synchronizes the Pico.
            # Later packets are sent only when a value changes.
            if current_player_state != last_player_state:
                player_packet = (
                    f"PLAYER|VOLUME={volume}|"
                    f"TITLE={title}|"
                    f"ARTIST={artist}|"
                    f"PLAYBACK={playback}\n"
                )

                ser.write(player_packet.encode("utf-8"))

                last_player_state = current_player_state

                print(
                    "PLAYER SENT:",
                    player_packet.strip()
                )
        
        # Only send system statistics when the monitor is active
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
        
        
        # CPU clock frequency in MHz
        try:
            frequency_info = psutil.cpu_freq()

            if frequency_info and frequency_info.current:
                frequency = f"{frequency_info.current:.0f}"
            else:
                frequency = "--"
        except Exception:
            frequency = "--"

        # Number of logical CPU processors
        logical_cpus = psutil.cpu_count(logical=True)

        if logical_cpus is None:
            logical_cpus = "--"

        # Number of running processes
        processes = len(psutil.pids())

        # Battery percentage, if available
        try:
            battery_info = psutil.sensors_battery()

            if battery_info is not None:
                battery = str(round(battery_info.percent))
            else:
                battery = "--"
        except Exception:
            battery = "--"


        # Send one semicolon-separated packet
        packet = (
            f"CPU={cpu:.1f};"
            f"RAM={ram:.1f};"
            f"DISK={disk:.1f};"
            f"UPLOAD={upload:.1f};"
            f"DOWNLOAD={download:.1f};"
            f"UPTIME={uptime};"
            f"FREQ={frequency};"
            f"THREADS={logical_cpus};"
            f"PROCESSES={processes};"
            f"BATTERY={battery}\n"
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
        sending = False
        player_sending = False
        last_player_state = None

        while ser is None:
            try:
                print("Reconnecting...")
                ser = serial.Serial(PORT, BAUD, timeout=1)
                time.sleep(2)
                ser.reset_input_buffer()
                print("Reconnected!")

            except serial.SerialException:
                time.sleep(1)
