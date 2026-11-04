import os
import re
import json
import socket
import struct
import subprocess
import threading
import webbrowser
import zipfile
from pathlib import Path
import tkinter as tk
from network_panel import NetworkPanel
from tkinter import ttk, filedialog, messagebox

APP_NAME = "Minecraft MAX Host"
DATA = Path(os.getenv("APPDATA", str(Path.home()))) / "MinecraftMAXHost"
DATA.mkdir(parents=True, exist_ok=True)
CFG = DATA / "settings.json"
DEFAULT_MAX = "https://web.max.ru/-80886078679113"


def cfg_read():
    try:
        return json.loads(CFG.read_text("utf-8"))
    except Exception:
        return {}


def cfg_write(value):
    CFG.write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")


def read_properties(folder):
    result = {}
    file = Path(folder) / "server.properties"
    if file.exists():
        for line in file.read_text("utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
    return result


def scan_mods(folder):
    result = []
    directory = Path(folder) / "mods"
    if not directory.is_dir():
        return result
    for jar in sorted(directory.glob("*.jar")):
        mod_id, version, name = "unknown", "unknown", jar.stem
        try:
            with zipfile.ZipFile(jar) as archive:
                names = set(archive.namelist())
                meta = next((item for item in (
                    "META-INF/neoforge.mods.toml",
                    "META-INF/mods.toml"
                ) if item in names), None)
                if meta:
                    content = archive.read(meta).decode("utf-8", "replace")
                    for key in ("modId", "version", "displayName"):
                        match = re.search(
                            r'(?m)^\s*' + key + r'\s*=\s*"([^"]+)"',
                            content
                        )
                        if match:
                            if key == "modId":
                                mod_id = match.group(1)
                            elif key == "version":
                                version = match.group(1)
                            else:
                                name = match.group(1)
        except (OSError, zipfile.BadZipFile, RuntimeError):
            pass
        result.append((mod_id, version, name, jar.name))
    return result


def minecraft_roots():
    home = Path.home()
    appdata = Path(os.getenv("APPDATA", home / "AppData/Roaming"))
    local = Path(os.getenv("LOCALAPPDATA", home / "AppData/Local"))
    roots = [
        appdata / ".minecraft",
        home / ".minecraft",
        appdata / "PrismLauncher" / "instances",
        local / "Programs" / "PrismLauncher" / "instances",
        appdata / "MultiMC" / "instances",
        home / "MultiMC" / "instances",
        appdata / "ModrinthApp" / "profiles",
        local / "ModrinthApp" / "profiles",
        appdata / "CurseForge" / "Minecraft" / "Instances",
        local / "CurseForge" / "Minecraft" / "Instances",
        home / "curseforge" / "minecraft" / "Instances",
        appdata / "gdlauncher" / "instances",
        local / "GDLauncher" / "instances",
        appdata / "ATLauncher" / "instances",
        home / "Documents" / "Minecraft",
        home / "Games" / "Minecraft",
    ]
    return list(dict.fromkeys(p for p in roots if p.exists()))


def discover_minecraft():
    found = {}
    for root in minecraft_roots():
        candidates = [root]
        try:
            candidates.extend(p for p in root.iterdir() if p.is_dir())
        except OSError:
            pass
        for folder in candidates:
            mods = folder / "mods"
            versions = folder / "versions"
            if mods.is_dir() or versions.is_dir() or (folder / "instance.cfg").exists():
                key = str(folder.resolve())
                if key not in found:
                    kind = "Minecraft"
                    low = key.lower()
                    if "prism" in low or "multimc" in low:
                        kind = "Prism / MultiMC"
                    elif "modrinth" in low:
                        kind = "Modrinth"
                    elif "curseforge" in low or "curseforge" in low:
                        kind = "CurseForge"
                    elif "gdlauncher" in low:
                        kind = "GDLauncher"
                    count = len(list(mods.glob("*.jar"))) if mods.is_dir() else 0
                    found[key] = {
                        "path": key,
                        "name": folder.name if folder != root else "Minecraft main",
                        "kind": kind,
                        "mods": count,
                    }
    return sorted(found.values(), key=lambda item: (item["kind"], item["name"].lower()))


def discover_servers():
    home = Path.home()
    roots = [
        home / "Desktop", home / "Downloads", home / "Documents",
        home / "Minecraft", home / "Servers", home / "Games",
        Path(os.getenv("APPDATA", home)) / "MinecraftServers",
    ]
    found = {}
    for root in roots:
        if not root.exists():
            continue
        try:
            for current, dirs, files in os.walk(root):
                current_path = Path(current)
                depth = len(current_path.relative_to(root).parts)
                dirs[:] = dirs[:30] if depth < 3 else []
                if depth > 3:
                    continue
                if "run.bat" in files or "start.bat" in files:
                    key = str(current_path.resolve())
                    found[key] = key
        except (OSError, ValueError):
            continue
    return sorted(found.values(), key=str.lower)


def encode_varint(number):
    output = bytearray()
    while True:
        value = number & 0x7F
        number >>= 7
        if number:
            value |= 0x80
        output.append(value)
        if not number:
            return bytes(output)


def read_varint(sock):
    number = shift = 0
    while shift < 35:
        byte = sock.recv(1)
        if not byte:
            raise OSError("Connection closed")
        number |= (byte[0] & 0x7F) << shift
        if not byte[0] & 0x80:
            return number
        shift += 7
    raise ValueError("Invalid VarInt")


def server_ping(port):
    with socket.create_connection(("127.0.0.1", port), timeout=1.2) as sock:
        host = b"127.0.0.1"
        packet = b"\x00" + encode_varint(765) + encode_varint(len(host)) + host
        packet += struct.pack(">H", port) + b"\x01"
        sock.sendall(encode_varint(len(packet)) + packet + b"\x01\x00")
        read_varint(sock)
        if read_varint(sock) != 0:
            raise ValueError("Unexpected status packet")
        size = read_varint(sock)
        raw = b""
        while len(raw) < size:
            part = sock.recv(size - len(raw))
            if not part:
                break
            raw += part
        status = json.loads(raw.decode("utf-8"))
        players = status.get("players", {})
        names = [player.get("name", "") for player in players.get("sample", [])]
        return status.get("version", {}).get("name", "?"), players.get("online", 0), players.get("max", 0), names


class Host:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1120x760")
        self.root.minsize(900, 620)
        self.root.configure(bg="#0b0b0e")
        self.proc = None
        config = cfg_read()
        self.folder = config.get("server_folder", config.get("folder", ""))
        self.client_folder = config.get("client_folder", "")
        self._build_ui()
        self.max_url.insert(0, config.get("max_url", DEFAULT_MAX))
        self._refresh_server()
        self.scan_all(show_message=False)
        self.root.after(3000, self._tick)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#0b0b0e")
        style.configure("TLabel", background="#0b0b0e", foreground="#eeeef2")
        style.configure("TButton", padding=8)
        style.configure("Treeview", background="#17171c", fieldbackground="#17171c",
                        foreground="#eeeef2", rowheight=25)
        style.configure("Treeview.Heading", background="#292930", foreground="white")
        base = ttk.Frame(self.root, padding=16)
        base.pack(fill="both", expand=True)
        header = ttk.Frame(base)
        header.pack(fill="x")
        ttk.Label(header, text="MINECRAFT  /  MAX HOST  /  NEOFORGE",
                  font=("Segoe UI", 18, "bold")).pack(side="left")
        self.state = ttk.Label(header, text="OFFLINE")
        self.state.pack(side="right")

        server_row = ttk.Frame(base)
        server_row.pack(fill="x", pady=(12, 5))
        self.path_label = ttk.Label(server_row, text="Server: not detected")
        self.path_label.pack(side="left", expand=True, fill="x")
        ttk.Button(server_row, text="Auto-detect servers", command=self.auto_server).pack(side="right")
        ttk.Button(server_row, text="Choose server", command=self.choose_server).pack(side="right", padx=6)

        controls = ttk.Frame(base)
        controls.pack(fill="x", pady=(5, 12))
        ttk.Button(controls, text="▶ START SERVER", command=self.start).pack(side="left")
        ttk.Button(controls, text="■ STOP", command=self.stop).pack(side="left", padx=8)
        ttk.Button(controls, text="Refresh", command=self._refresh_server).pack(side="left")
        ttk.Button(controls, text="HOST / PLAYER", command=self.open_network).pack(side="left", padx=8)

        tabs = ttk.Notebook(base)
        tabs.pack(fill="both", expand=True)
        overview = ttk.Frame(tabs, padding=10)
        mods_tab = ttk.Frame(tabs, padding=10)
        client_tab = ttk.Frame(tabs, padding=10)
        console_tab = ttk.Frame(tabs, padding=10)
        max_tab = ttk.Frame(tabs, padding=10)
        for pane, title in (
            (overview, "Server overview"), (mods_tab, "Server mods"),
            (client_tab, "Minecraft auto-detect"), (console_tab, "Console"),
            (max_tab, "MAX group")
        ):
            tabs.add(pane, text=title)

        self.info = tk.Text(overview, bg="#17171c", fg="#f1f1f5",
                            relief="flat", font=("Consolas", 11), wrap="word")
        self.info.pack(fill="both", expand=True)

        self.server_tree = ttk.Treeview(mods_tab, columns=("version", "file"), show="headings")
        self.server_tree.heading("version", text="Mod ID / version / name")
        self.server_tree.heading("file", text="JAR file")
        self.server_tree.column("version", width=470)
        self.server_tree.column("file", width=480)
        self.server_tree.pack(fill="both", expand=True)

        client_top = ttk.Frame(client_tab)
        client_top.pack(fill="x", pady=(0, 8))
        ttk.Button(client_top, text="Scan Minecraft folders", command=self.scan_all).pack(side="left")
        ttk.Button(client_top, text="Choose Minecraft folder", command=self.choose_client).pack(side="left", padx=8)
        self.client_tree = ttk.Treeview(client_tab, columns=("type", "mods", "path"), show="headings")
        self.client_tree.heading("type", text="Launcher")
        self.client_tree.heading("mods", text="Mods")
        self.client_tree.heading("path", text="Detected game / instance folder")
        self.client_tree.column("type", width=150)
        self.client_tree.column("mods", width=70, anchor="center")
        self.client_tree.column("path", width=700)
        self.client_tree.pack(fill="both", expand=True)
        self.client_tree.bind("<<TreeviewSelect>>", self._client_selected)
        self.client_mods = tk.Text(client_tab, height=7, bg="#17171c", fg="#eeeef2",
                                   relief="flat", font=("Consolas", 9))
        self.client_mods.pack(fill="x", pady=(8, 0))

        self.log = tk.Text(console_tab, bg="#111115", fg="#dddde5",
                           relief="flat", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)

        ttk.Label(max_tab, text="MAX group URL").pack(anchor="w")
        self.max_url = ttk.Entry(max_tab)
        self.max_url.pack(fill="x", pady=7)
        ttk.Button(max_tab, text="Save and open MAX group", command=self.open_max).pack(anchor="w")
        ttk.Label(
            max_tab,
            text="MAX opens in your browser. Sign in there yourself. This app does not read private account data or automate messages.",
            wraplength=900
        ).pack(anchor="w", pady=12)

    def open_network(self):
        NetworkPanel(self.root, self.folder, self.write)

    def save(self):
        cfg_write({
            "server_folder": self.folder,
            "client_folder": self.client_folder,
            "max_url": self.max_url.get().strip()
        })

    def write(self, message):
        self.log.insert("end", str(message) + "\n")
        self.log.see("end")

    def choose_server(self):
        folder = filedialog.askdirectory(title="Select NeoForge server folder")
        if folder:
            self.folder = folder
            self.save()
            self._refresh_server()

    def auto_server(self):
        servers = discover_servers()
        if not servers:
            messagebox.showinfo("Auto-detect", "No server folder with run.bat/start.bat was found in common folders. Use Choose server.")
            return
        if len(servers) == 1:
            self.folder = servers[0]
            self.save()
            self._refresh_server()
            messagebox.showinfo("Server found", self.folder)
            return
        choice = tk.Toplevel(self.root)
        choice.title("Detected server folders")
        choice.geometry("760x330")
        listing = tk.Listbox(choice, bg="#17171c", fg="white", font=("Consolas", 9))
        listing.pack(fill="both", expand=True, padx=10, pady=10)
        for item in servers:
            listing.insert("end", item)
        def select():
            selection = listing.curselection()
            if selection:
                self.folder = servers[selection[0]]
                self.save()
                self._refresh_server()
                choice.destroy()
        ttk.Button(choice, text="Use selected folder", command=select).pack(pady=(0, 10))
        listing.selection_set(0)

    def choose_client(self):
        folder = filedialog.askdirectory(title="Select Minecraft game or instance folder")
        if folder:
            self.client_folder = folder
            self.save()
            self.scan_all(show_message=False)
            self._show_client_mods(folder)

    def scan_all(self, show_message=True):
        items = discover_minecraft()
        if self.client_folder and Path(self.client_folder).exists():
            known = {item["path"] for item in items}
            if str(Path(self.client_folder).resolve()) not in known:
                items.insert(0, {
                    "path": str(Path(self.client_folder).resolve()),
                    "name": Path(self.client_folder).name,
                    "kind": "Manually selected",
                    "mods": len(list((Path(self.client_folder) / "mods").glob("*.jar")))
                })
        for item in self.client_tree.get_children():
            self.client_tree.delete(item)
        for item in items:
            self.client_tree.insert("", "end", iid=item["path"],
                                    values=(item["kind"], item["mods"], item["path"]))
        if self.client_folder and self.client_folder in [x["path"] for x in items]:
            self.client_tree.selection_set(self.client_folder)
            self._show_client_mods(self.client_folder)
        elif items:
            self.client_tree.selection_set(items[0]["path"])
            self._show_client_mods(items[0]["path"])
        else:
            self.client_mods.delete("1.0", "end")
            self.client_mods.insert("end", "No Minecraft installation detected in standard launcher folders.")
        if show_message:
            messagebox.showinfo("Scan complete", f"Detected Minecraft installations / instances: {len(items)}")

    def _client_selected(self, _event=None):
        selection = self.client_tree.selection()
        if selection:
            self.client_folder = selection[0]
            self.save()
            self._show_client_mods(self.client_folder)

    def _show_client_mods(self, folder):
        self.client_mods.delete("1.0", "end")
        mods = scan_mods(folder)
        self.client_mods.insert("end", f"Folder: {folder}\nMods detected: {len(mods)}\n")
        for mod_id, version, name, filename in mods:
            self.client_mods.insert("end", f"• {name} [{mod_id}] {version} — {filename}\n")
        if not mods:
            self.client_mods.insert("end", "No .jar mods found in this folder's mods directory.\n")

    def _refresh_server(self):
        if not self.folder:
            self.path_label.config(text="Server: not selected")
            self.info.delete("1.0", "end")
            self.info.insert("end", "No server folder selected.\nUse Auto-detect servers or Choose server.\n")
            return
        self.path_label.config(text="Server: " + self.folder)
        properties = read_properties(self.folder)
        mods = scan_mods(self.folder)
        for item in self.server_tree.get_children():
            self.server_tree.delete(item)
        for mod_id, version, name, filename in mods:
            self.server_tree.insert("", "end", values=(f"{mod_id} | {version} | {name}", filename))
        self.info.delete("1.0", "end")
        self.info.insert("end", (
            f"Folder: {self.folder}\n"
            f"Loader: NeoForge / Forge (folder selected; verify server files)\n"
            f"Mods in server mods/: {len(mods)}\n"
            f"Port: {properties.get('server-port', '25565')}\n"
            f"Max players: {properties.get('max-players', '20')}\n"
            f"Java: {os.getenv('JAVA_HOME', 'Use Java from PATH or server script')}\n"
        ))

    def start(self):
        if not self.folder or not Path(self.folder).exists():
            messagebox.showwarning("Server", "Select or auto-detect the server folder first.")
            return
        if self.proc and self.proc.poll() is None:
            return
        eula = Path(self.folder) / "eula.txt"
        if not eula.exists() or not re.search(r"(?im)^eula\s*=\s*true\s*$",
                                               eula.read_text("utf-8", errors="ignore")):
            messagebox.showwarning("EULA", "Read Minecraft EULA and set eula=true yourself only if you agree.")
            return
        launcher = next((name for name in ("run.bat", "start.bat")
                         if (Path(self.folder) / name).exists()), None)
        if not launcher:
            messagebox.showerror("Launcher", "run.bat/start.bat not found. Select the server root folder.")
            return
        try:
            self.proc = subprocess.Popen(
                ["cmd.exe", "/c", launcher], cwd=self.folder,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            self.state.config(text="STARTING")
            self.write("Starting server...")
            threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        except Exception as error:
            messagebox.showerror("Start failed", str(error))

    def _reader(self, process):
        for line in process.stdout:
            line = line.rstrip()
            self.root.after(0, self.write, line)
            joined = re.search(r"([A-Za-z0-9_]{3,16}) joined the game", line)
            left = re.search(r"([A-Za-z0-9_]{3,16}) left the game", line)
            if joined:
                self.root.after(0, self.write, "[PLAYER JOIN] " + joined.group(1))
            if left:
                self.root.after(0, self.write, "[PLAYER LEAVE] " + left.group(1))
        process.wait()
        self.root.after(0, lambda: self.state.config(text="OFFLINE"))

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
                self.write("Stop command sent.")
            except Exception:
                self.proc.terminate()

    def _tick(self):
        if self.folder:
            port = int(read_properties(self.folder).get("server-port", "25565") or 25565)
            try:
                version, online, maximum, names = server_ping(port)
                self.state.config(text="ONLINE")
                self.info.delete("1.0", "end")
                self.info.insert("end", (
                    f"ONLINE\nVersion: {version}\nPlayers: {online}/{maximum}\nPort: {port}\n"
                    f"Advertised player sample: {', '.join(names) if names else 'not published'}\n"
                    f"Server mods: {len(scan_mods(self.folder))}\n"
                ))
            except Exception:
                self.state.config(text="STARTING" if self.proc and self.proc.poll() is None else "OFFLINE")
        self.root.after(3000, self._tick)

    def open_max(self):
        self.save()
        url = self.max_url.get().strip()
        if not url.startswith("https://web.max.ru/"):
            messagebox.showerror("MAX", "Enter a valid MAX group URL.")
            return
        webbrowser.open(url)


def main():
    root = tk.Tk()
    Host(root)
    root.mainloop()


if __name__ == "__main__":
    main()
