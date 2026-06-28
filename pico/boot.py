import usb_cdc

# Enable both the standard console (REPL) and the raw data channel
usb_cdc.enable(console=True, data=True)
