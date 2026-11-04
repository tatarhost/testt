import os, re, json, socket, struct, subprocess, threading, webbrowser, zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

DATA=Path(os.getenv("APPDATA",str(Path.home())))/"MinecraftMAXHost"
DATA.mkdir(parents=True,exist_ok=True)
CFG=DATA/"settings.json"
DEFAULT_MAX="https://web.max.ru/-80886078679113"

def cfg_read():
    try: return json.loads(CFG.read_text("utf-8"))
    except Exception: return {}
def cfg_write(v): CFG.write_text(json.dumps(v,ensure_ascii=False,indent=2),"utf-8")
def props(folder):
    d={}; f=Path(folder)/"server.properties"
    if f.exists():
        for line in f.read_text("utf-8",errors="replace").splitlines():
            line=line.strip()
            if line and not line.startswith("#") and "=" in line:
                k,v=line.split("=",1); d[k.strip()]=v.strip()
    return d
def scan_mods(folder):
    out=[]; d=Path(folder)/"mods"
    if not d.is_dir(): return out
    for f in sorted(d.glob("*.jar")):
        mid=ver="unknown"; name=f.stem
        try:
            with zipfile.ZipFile(f) as z:
                meta=next((x for x in ("META-INF/neoforge.mods.toml","META-INF/mods.toml") if x in z.namelist()),None)
                if meta:
                    s=z.read(meta).decode("utf-8","replace")
                    for key in ("modId","version","displayName"):
                        m=re.search(r'(?m)^\\s*'+key+r'\\s*=\\s*"([^"]+)"',s)
                        if m:
                            if key=="modId": mid=m.group(1)
                            elif key=="version": ver=m.group(1)
                            else: name=m.group(1)
        except Exception: pass
        out.append((mid,ver,name,f.name))
    return out
def vi(n):
    b=bytearray()
    while True:
        x=n&127; n>>=7
        if n: x|=128
        b.append(x)
        if not n: return bytes(b)
def read_vi(s):
    n=shift=0
    while shift<35:
        b=s.recv(1)
        if not b: raise OSError("Connection closed")
        n|=(b[0]&127)<<shift
        if not b[0]&128: return n
        shift+=7
    raise ValueError("Invalid VarInt")
def ping(port):
    with socket.create_connection(("127.0.0.1",port),timeout=1.2) as s:
        host=b"127.0.0.1"
        pkt=b"\\x00"+vi(765)+vi(len(host))+host+struct.pack(">H",port)+b"\\x01"
        s.sendall(vi(len(pkt))+pkt+b"\\x01\\x00")
        read_vi(s)
        if read_vi(s)!=0: raise ValueError("Unexpected status packet")
        n=read_vi(s); raw=b""
        while len(raw)<n:
            part=s.recv(n-len(raw))
            if not part: break
            raw+=part
        o=json.loads(raw.decode("utf-8")); p=o.get("players",{})
        return o.get("version",{}).get("name","?"),p.get("online",0),p.get("max",0),[x.get("name","") for x in p.get("sample",[])]

class Host:
 def __init__(self,root):
    self.root=root; self.root.title("Minecraft MAX Server Host"); self.root.geometry("1020x700"); self.root.minsize(850,560); self.root.configure(bg="#0b0b0e")
    self.proc=None; c=cfg_read(); self.folder=c.get("folder","")
    self._ui(); self.max_url.insert(0,c.get("max_url",DEFAULT_MAX)); self._refresh(); self.root.after(3000,self._tick)
 def _ui(self):
    st=ttk.Style(); st.theme_use("clam")
    st.configure("TFrame",background="#0b0b0e"); st.configure("TLabel",background="#0b0b0e",foreground="#eeeef2"); st.configure("TButton",padding=8)
    st.configure("Treeview",background="#17171c",fieldbackground="#17171c",foreground="#eeeef2",rowheight=25); st.configure("Treeview.Heading",background="#292930",foreground="white")
    base=ttk.Frame(self.root,padding=16); base.pack(fill="both",expand=True)
    top=ttk.Frame(base); top.pack(fill="x"); ttk.Label(top,text="MINECRAFT  /  MAX HOST  /  NEOFORGE",font=("Segoe UI",19,"bold")).pack(side="left")
    self.state=ttk.Label(top,text="OFFLINE"); self.state.pack(side="right")
    row=ttk.Frame(base); row.pack(fill="x",pady=12); self.path=ttk.Label(row,text="Server folder not selected"); self.path.pack(side="left",expand=True,fill="x"); ttk.Button(row,text="Choose server folder",command=self.choose).pack(side="right")
    row=ttk.Frame(base); row.pack(fill="x",pady=(0,12)); ttk.Button(row,text="▶ START",command=self.start).pack(side="left"); ttk.Button(row,text="■ STOP",command=self.stop).pack(side="left",padx=8); ttk.Button(row,text="Refresh",command=self._refresh).pack(side="left")
    tabs=ttk.Notebook(base); tabs.pack(fill="both",expand=True)
    ov=ttk.Frame(tabs,padding=10); mt=ttk.Frame(tabs,padding=10); lg=ttk.Frame(tabs,padding=10); mx=ttk.Frame(tabs,padding=10)
    for pane,title in ((ov,"Overview"),(mt,"Mods"),(lg,"Console"),(mx,"MAX")): tabs.add(pane,text=title)
    self.info=tk.Text(ov,bg="#17171c",fg="#f1f1f5",relief="flat",font=("Consolas",11)); self.info.pack(fill="both",expand=True)
    self.tree=ttk.Treeview(mt,columns=("version","file"),show="headings")
    self.tree.heading("version",text="Mod ID / version / name"); self.tree.heading("file",text="JAR file"); self.tree.column("version",width=420); self.tree.column("file",width=480); self.tree.pack(fill="both",expand=True)
    self.log=tk.Text(lg,bg="#111115",fg="#dddde5",relief="flat",font=("Consolas",9)); self.log.pack(fill="both",expand=True)
    ttk.Label(mx,text="MAX group URL").pack(anchor="w"); self.max_url=ttk.Entry(mx); self.max_url.pack(fill="x",pady=7)
    ttk.Button(mx,text="Save and open group in browser",command=self.open_max).pack(anchor="w")
    ttk.Label(mx,text="Sign in manually in MAX. This app does not collect passwords, QR codes or browser session data, and does not automate personal-account message sending.",wraplength=850).pack(anchor="w",pady=12)
 def save(self): cfg_write({"folder":self.folder,"max_url":self.max_url.get().strip()})
 def choose(self):
    d=filedialog.askdirectory(title="Choose NeoForge server root")
    if d: self.folder=d; self.save(); self._refresh()
 def write(self,s): self.log.insert("end",str(s)+"\\n"); self.log.see("end")
 def _refresh(self):
    if not self.folder:
        self.info.delete("1.0","end"); self.info.insert("end","Choose the NeoForge server root folder containing run.bat."); return
    self.path.config(text=self.folder); p=props(self.folder); mm=scan_mods(self.folder)
    for x in self.tree.get_children(): self.tree.delete(x)
    for mid,ver,name,file in mm: self.tree.insert("","end",values=(f"{mid} | {ver} | {name}",file))
    self.info.delete("1.0","end")
    self.info.insert("end",f"Folder: {self.folder}\\nLoader: NeoForge (selected server folder)\\nMods in mods/: {len(mm)}\\nPort: {p.get('server-port','25565')}\\nMax players: {p.get('max-players','20')}\\n")
 def start(self):
    if not self.folder or not Path(self.folder).exists(): messagebox.showwarning("Server","Choose server folder first."); return
    if self.proc and self.proc.poll() is None: return
    eula=Path(self.folder)/"eula.txt"
    if not eula.exists() or not re.search(r"(?im)^eula\\s*=\\s*true\\s*$",eula.read_text("utf-8",errors="ignore")):
        messagebox.showwarning("EULA","Review Minecraft EULA and set eula=true yourself only if you agree."); return
    launcher=next((x for x in ("run.bat","start.bat") if (Path(self.folder)/x).exists()),None)
    if not launcher: messagebox.showerror("Launcher","run.bat/start.bat not found. Select the NeoForge server root."); return
    try:
        self.proc=subprocess.Popen(["cmd.exe","/c",launcher],cwd=self.folder,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding="utf-8",errors="replace",creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        self.state.config(text="STARTING"); self.write("Starting server..."); threading.Thread(target=self._reader,args=(self.proc,),daemon=True).start()
    except Exception as e: messagebox.showerror("Start failed",str(e))
 def _reader(self,proc):
    for line in proc.stdout:
        line=line.rstrip(); self.root.after(0,self.write,line)
        m=re.search(r"([A-Za-z0-9_]{3,16}) joined the game",line)
        if m: self.root.after(0,self.write,"[PLAYER JOIN] "+m.group(1))
        m=re.search(r"([A-Za-z0-9_]{3,16}) left the game",line)
        if m: self.root.after(0,self.write,"[PLAYER LEAVE] "+m.group(1))
    proc.wait(); self.root.after(0,lambda:self.state.config(text="OFFLINE"))
 def stop(self):
    if self.proc and self.proc.poll() is None:
        try: self.proc.stdin.write("stop\\n"); self.proc.stdin.flush(); self.write("Stop command sent.")
        except Exception: self.proc.terminate()
 def _tick(self):
    if self.folder:
        port=int(props(self.folder).get("server-port","25565") or 25565)
        try:
            ver,on,mx,sample=ping(port); self.state.config(text="ONLINE")
            self.info.delete("1.0","end"); self.info.insert("end",f"ONLINE\\nVersion: {ver}\\nPlayers: {on}/{mx}\\nPort: {port}\\nAdvertised sample: {', '.join(sample) if sample else 'not published by server'}\\nMods: {len(scan_mods(self.folder))}\\n")
        except Exception: self.state.config(text="STARTING" if self.proc and self.proc.poll() is None else "OFFLINE")
    self.root.after(3000,self._tick)
 def open_max(self):
    self.save(); u=self.max_url.get().strip()
    if not u.startswith("https://web.max.ru/"): messagebox.showerror("MAX","Enter a MAX group URL."); return
    webbrowser.open(u)
def main():
    root=tk.Tk(); Host(root); root.mainloop()
if __name__=="__main__": main()
