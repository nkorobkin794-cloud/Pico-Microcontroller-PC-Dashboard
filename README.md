\# Pico-Microcontroller-PC-Dashboard



A real-time system using Raspberry Pi Pico + PC Python application.



\---



\## Features



\- Live stats monitoring from PC

\- Temperature \& humidity sensor (AHT10)

\- ST7796 TFT display UI

\- USB serial packet-based communication

\- Menu system (stats / volume)

\- Rotary encoder navigation for menu control and selection



\---



\## Architecture



\*\*Pico:\*\*

\- UI rendering on ST7796 display

\- Sensor data acquisition (AHT10)

\- Rotary encoder input handling (menu navigation + selection)

\- Display state management (menu / stats / volume)



\*\*PC:\*\*

\- System performance monitoring (CPU utilization, memory usage, disk usage, network upload, network download, PC uptime)

\- Telemetry data transmission via USB serial



\*\*Communication:\*\*

\- USB serial packet-based communication between PC and Pico



\---



\## Status



Early development (v0.5)

