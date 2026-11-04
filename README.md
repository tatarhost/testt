# Minecraft MAX Host — Windows portable package

## Start
1. Extract the ZIP to any folder.
2. Run `MinecraftMAXHost.exe`. Python does not need to be installed.
3. Open **Minecraft auto-detect** and click **Scan Minecraft folders**.
4. The app checks common locations for the official Minecraft launcher, Prism Launcher, MultiMC, Modrinth, CurseForge, GDLauncher and ATLauncher. Select an instance to inspect its `mods` folder.
5. Click **Auto-detect servers** to search common Desktop / Downloads / Documents / Minecraft / Servers folders for `run.bat` or `start.bat`. If your server is elsewhere, click **Choose server**.
6. Start and stop the server from the top controls. The app reads server console events and server status.

## What is included
- One-file Windows executable.
- Automatic detection of common Minecraft Java folders and launcher instances.
- Client and server mod JAR inventory (metadata where available).
- NeoForge/Forge server start/stop using its existing `run.bat` or `start.bat`.
- Local server status query, console and join/leave events.
- MAX group shortcut.

## Important
- This is a local PC server manager, not cloud hosting. The PC must remain on while hosting.
- The app does not install Minecraft, Java, NeoForge or mods. It detects existing folders and uses the server's own launch script.
- Before starting, read the Minecraft EULA and set `eula=true` yourself only if you agree.
- The server folder must contain a working `run.bat` or `start.bat`.
- MAX opens the group in your browser. It does not access MAX accounts, scrape members, or send messages automatically.
- Player names in the status view are only those advertised by the server; join/leave events are read from this app's console session.
