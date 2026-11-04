"""MAX signaling panel for MinecraftMAXHost.

Uses MAX Bot API Long Polling (development/testing only). Game traffic is NOT
carried by MAX: players connect directly to the host's Minecraft server.
"""
import json
import secrets
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import os

API = "https://platform-api2.max.ru"
DATA = Path(os.getenv("APPDATA", str(Path.home()))) / "MinecraftMAXHost"
CFG = DATA / "network.json"


def load_cfg():
    try:
        return json.loads(CFG.read_text("utf-8"))
    except Exception:
        return {}


def save_cfg(data):
    DATA.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def api_request(token, path, method="GET", params=None, body=None, timeout=40):
    url = API + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": token,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MinecraftMAXHost/2.0"
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", "replace")
        return json.loads(raw) if raw else {}


def send_message(token, chat_id, text):
    return api_request(token, "/messages", "POST", {"chat_id": str(chat_id)},
                       {"text": text}, timeout=20)


def update_text(update):
    message = update.get("message") or update.get("message_created", {}).get("message") or {}
    body = message.get("body") or {}
    return body.get("text") or message.get("text") or ""


def update_chat_id(update):
    message = update.get("message") or update.get("message_created", {}).get("message") or {}
    recipient = message.get("recipient") or {}
    return str(recipient.get("chat_id") or update.get("chat_id") or "")


class NetworkPanel:
    def __init__(self, parent, server_folder="", logger=None):
        self.parent = parent
        self.logger = logger or (lambda msg: None)
        self.win = tk.Toplevel(parent)
        self.win.title("MinecraftMAXHost 2.0 — Host / Player")
        self.win.geometry("760x650")
        self.win.minsize(680, 560)
        self.win.configure(bg="#0b0b0e")
        self.stop_event = threading.Event()
        self.poll_thread = None
        self.marker = None
        self.room_code = ""
        self.host_offer = None
        self.server_folder = server_folder
        self.cfg = load_cfg()
        self._ui()
        self.win.protocol("WM_DELETE_WINDOW", self.close)

    def _ui(self):
        style = ttk.Style()
        style.configure("TFrame", background="#0b0b0e")
        style.configure("TLabel", background="#0b0b0e", foreground="#eeeef2")
        style.configure("TLabelframe", background="#0b0b0e", foreground="#eeeef2")
        style.configure("TLabelframe.Label", background="#0b0b0e", foreground="#eeeef2")
        root = ttk.Frame(self.win, padding=16)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="MINECRAFT MAX HOST 2.0", font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(root, text="MAX = сигналы и запросы. Игровой трафик идёт напрямую между компьютерами.",
                  wraplength=700).pack(anchor="w", pady=(4, 12))
        cfg = ttk.LabelFrame(root, text="Подключение MAX Bot API", padding=10)
        cfg.pack(fill="x", pady=5)
        ttk.Label(cfg, text="Токен бота (хранится локально на этом ПК)").pack(anchor="w")
        self.token = ttk.Entry(cfg, show="•")
        self.token.pack(fill="x", pady=(2, 8))
        self.token.insert(0, self.cfg.get("token", ""))
        ttk.Label(cfg, text="ID группового чата MAX").pack(anchor="w")
        self.chat = ttk.Entry(cfg)
        self.chat.pack(fill="x", pady=(2, 8))
        self.chat.insert(0, self.cfg.get("chat_id", ""))
        ttk.Button(cfg, text="Сохранить и проверить MAX", command=self.connect).pack(anchor="w")
        self.connection_state = ttk.Label(cfg, text="Не подключено")
        self.connection_state.pack(anchor="w", pady=(6, 0))

        host = ttk.LabelFrame(root, text="Режим ХОСТ", padding=10)
        host.pack(fill="x", pady=7)
        ttk.Label(host, text="Адрес, доступный второму игроку (публичный IP или адрес VPN-сети)").pack(anchor="w")
        self.address = ttk.Entry(host)
        self.address.pack(fill="x", pady=3)
        self.address.insert(0, self.cfg.get("host_address", ""))
        portrow = ttk.Frame(host)
        portrow.pack(fill="x")
        ttk.Label(portrow, text="Порт Minecraft").pack(side="left")
        self.port = ttk.Entry(portrow, width=9)
        self.port.pack(side="left", padx=8)
        self.port.insert(0, "25565")
        ttk.Button(portrow, text="Создать комнату и объявить в MAX", command=self.create_room).pack(side="left", padx=8)
        self.room_label = ttk.Label(host, text="Комната не создана")
        self.room_label.pack(anchor="w", pady=(6, 0))

        player = ttk.LabelFrame(root, text="Режим ИГРОК", padding=10)
        player.pack(fill="x", pady=7)
        ttk.Label(player, text="Код комнаты, который сообщил хост").pack(anchor="w")
        row = ttk.Frame(player)
        row.pack(fill="x")
        self.join_code = ttk.Entry(row, width=18)
        self.join_code.pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Отправить запрос и найти хоста", command=self.join_room).pack(side="left")
        self.offer_label = ttk.Label(player, text="Ожидание приглашения отсутствует", wraplength=680)
        self.offer_label.pack(anchor="w", pady=(8, 0))

        logframe = ttk.LabelFrame(root, text="События", padding=8)
        logframe.pack(fill="both", expand=True, pady=7)
        self.log = tk.Text(logframe, height=8, bg="#15151b", fg="#eeeeF4",
                           insertbackground="white", relief="flat", wrap="word")
        self.log.pack(fill="both", expand=True)
        ttk.Label(root, text="Важно: для интернета хосту нужен доступный входящий порт 25565 или общая VPN-сеть. MAX не пробрасывает порты и не является игровым ретранслятором.",
                  wraplength=700).pack(anchor="w")

    def say(self, text):
        self.win.after(0, self._say_ui, str(text))

    def _say_ui(self, text):
        if not self.win.winfo_exists():
            return
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def credentials(self):
        token = self.token.get().strip()
        chat = self.chat.get().strip()
        if not token or not chat:
            raise ValueError("Укажи токен MAX-бота и ID группового чата.")
        return token, chat

    def connect(self):
        try:
            token, chat = self.credentials()
            result = api_request(token, "/chats/" + urllib.parse.quote(chat, safe=""))
            save_cfg({"token": token, "chat_id": chat, "host_address": self.address.get().strip()})
            self.connection_state.config(text="MAX API: соединение успешно")
            self.say("MAX API доступен. Чат: " + str(result.get("title", chat)))
            self._start_polling()
        except Exception as exc:
            self.connection_state.config(text="Ошибка подключения")
            messagebox.showerror("MAX API", str(exc), parent=self.win)

    def _start_polling(self):
        if self.poll_thread and self.poll_thread.is_alive():
            return
        self.stop_event.clear()
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _poll_loop(self):
        token = self.token.get().strip()
        chat_id = self.chat.get().strip()
        while not self.stop_event.is_set():
            try:
                params = {"timeout": 25, "limit": 100,
                          "types": "message_created"}
                if self.marker is not None:
                    params["marker"] = self.marker
                data = api_request(token, "/updates", params=params, timeout=35)
                self.marker = data.get("marker", self.marker)
                for update in data.get("updates", []):
                    if update_chat_id(update) not in ("", chat_id):
                        continue
                    text = update_text(update).strip()
                    if not text.startswith("MCH2|"):
                        continue
                    self._handle_signal(text)
            except Exception as exc:
                self.say("MAX polling: " + str(exc))
                self.stop_event.wait(5)

    def _handle_signal(self, text):
        parts = text.split("|")
        if len(parts) < 3:
            return
        kind, code = parts[1], parts[2]
        if kind == "HOST" and len(parts) >= 5:
            self.host_offer = {"code": code, "address": parts[3], "port": parts[4]}
            self.win.after(0, lambda: self.offer_label.config(
                text=f"Хост найден: {parts[3]}:{parts[4]} — код {code}. Введи этот адрес в Minecraft → Сетевая игра → Прямое подключение."))
            self.say("Найден хост комнаты " + code)
        elif kind == "JOIN" and code == self.room_code and len(parts) >= 4:
            player = parts[3][:32]
            self.say("Запрос на подключение от " + player + ". Проверь игрока в Minecraft.")
        elif kind == "STOP" and code == self.room_code:
            self.say("Хост завершил комнату.")

    def create_room(self):
        try:
            token, chat = self.credentials()
            address = self.address.get().strip()
            port = self.port.get().strip() or "25565"
            if not address or any(ch.isspace() for ch in address) or "|" in address:
                raise ValueError("Укажи адрес, доступный игроку, например публичный IP или адрес VPN-сети.")
            if not port.isdigit() or not 1 <= int(port) <= 65535:
                raise ValueError("Порт должен быть от 1 до 65535.")
            self.room_code = f"{secrets.randbelow(900000) + 100000}"
            send_message(token, chat, f"MCH2|HOST|{self.room_code}|{address}|{port}")
            self.room_label.config(text=f"КОМНАТА {self.room_code} опубликована. Адрес: {address}:{port}")
            save_cfg({"token": token, "chat_id": chat, "host_address": address})
            self._start_polling()
            self.say("Комната опубликована в MAX. Передай код игроку: " + self.room_code)
        except Exception as exc:
            messagebox.showerror("Не удалось создать комнату", str(exc), parent=self.win)

    def join_room(self):
        try:
            token, chat = self.credentials()
            code = self.join_code.get().strip()
            if not code.isdigit() or len(code) != 6:
                raise ValueError("Код комнаты должен состоять из 6 цифр.")
            send_message(token, chat, f"MCH2|JOIN|{code}|MinecraftPlayer")
            self.offer_label.config(text="Запрос отправлен. Ищу объявление хоста в MAX…")
            self._start_polling()
            self.say("Запрос на поиск комнаты " + code + " отправлен.")
        except Exception as exc:
            messagebox.showerror("Запрос подключения", str(exc), parent=self.win)

    def close(self):
        self.stop_event.set()
        self.win.destroy()
