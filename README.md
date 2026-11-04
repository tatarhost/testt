# MinecraftMAXHost 2.0 — Windows portable package

## Start
1. Extract the ZIP.
2. Run MinecraftMAXHost.exe.
3. Use Minecraft auto-detect to inspect installed launcher instances and their mods folders.
4. Select or auto-detect a prepared server folder and start/stop it from the main window.
5. Open HOST / PLAYER for MAX signaling.

## MAX host/player signaling
Both computers run this app and use the same MAX bot token and group chat ID.
1. Create a MAX bot and add it to the group.
2. Give the bot permission to read group messages and write messages. The bot must be an administrator with read_all_messages and write.
3. In HOST / PLAYER, enter the bot token and group chat ID, then use Save and check MAX.
4. The host enters an address reachable by the other player and the Minecraft port (normally 25565), then publishes a room.
5. The player enters the six-digit room code and sends a join request. The host sees the request in the events log. The player receives the host address and enters it in Minecraft's Direct Connection screen.

## Important limitations
- This build uses MAX Bot API Long Polling, which MAX documents for development/testing only, not production. It is a prototype signaling transport; reliable production use needs a public HTTPS webhook service.
- MAX only carries room announcements and join requests. It does not carry Minecraft gameplay traffic and does not create an internet tunnel.
- For remote play, the host address and port must already be reachable from the other computer (for example, both players may use the same trusted private VPN network). This app does not configure routers, open firewall ports, or provide a relay.
- Do not post a public IP address in a group with people you do not trust. Share room codes only with invited players.
- The bot token is saved locally in %APPDATA%\MinecraftMAXHost\network.json. Keep it private; anyone with it can control the bot.
- Both computers should use the same MAX bot and group. MAX bot must be an administrator with permission to read all messages; group events may otherwise not arrive.

## Minecraft discovery and server management
- Detects common Minecraft Java and launcher folders, and inventories client/server mod JARs.
- Starts/stops an existing server using its run.bat or start.bat.
- Shows local server status and console output.
- This build does not yet install NeoForge/Forge automatically or build a server instance from a client modpack. The server folder must already contain valid server files.
- Read the Minecraft EULA and accept it yourself only if you agree. The app does not accept it on your behalf.

## Package
One-file Windows executable; Python is not required.
