# Minecraft MAX Host (NeoForge)

Windows desktop panel for an already-installed Minecraft Java NeoForge server.

## Build
Push to `main` or run **Build Windows EXE** in GitHub Actions. The workflow builds a one-file `MinecraftMAXHost.exe` and uploads it as an artifact.

## Setup
1. Install NeoForge server with the official installer.
2. Run its `run.bat` once. Review Minecraft's EULA and set `eula=true` yourself only if you agree.
3. Start the app, select the server root folder (the one containing `run.bat`), then Start.
4. In MAX tab set your group URL and open it in your browser. Sign in manually.

## Features
- Start/stop server through console, log viewer, join/leave log events.
- Reads server.properties and scans mods/*.jar metadata.
- Queries Minecraft Java status for online/max, version and advertised sample.
- Opens the configured MAX group.

## Limits
This is a self-hosted PC manager, not cloud hosting; PC must stay on. External access needs router/firewall configuration. Server status may not publish full player names. Mods installed on remote players cannot be read. MAX personal-account message automation is not included; this app does not access passwords, QR codes, or browser session data.