import json
import socket
import struct
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from urllib import request as urlrequest
from urllib.error import HTTPError

MSG_AUTH = 0x01
MSG_AUTH_OK = 0x02
MSG_AUTH_FAIL = 0x03
MSG_OPEN = 0x10
MSG_DATA = 0x11
MSG_CLOSE = 0x12
MSG_PING = 0x30
MSG_PONG = 0x32

HEADER = struct.Struct(">BII")


class ApiClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.token = None

    def _request(self, method, path, body=None):
        url = self.base_url + path
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token

        req = urlrequest.Request(url, data=data, headers=headers, method=method)
        try:
            with urlrequest.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else None
        except HTTPError as exc:
            raw = exc.read().decode()
            try:
                payload = json.loads(raw)
                detail = payload.get("detail", "request_failed")
            except Exception:
                detail = "request_failed"
            raise RuntimeError(detail)

    def register(self, username, password):
        return self._request("POST", "/api/auth/register", {"username": username, "password": password})

    def login(self, username, password):
        return self._request("POST", "/api/auth/login", {"username": username, "password": password})

    def me(self):
        return self._request("GET", "/api/auth/me")

    def tunnels(self):
        return self._request("GET", "/api/tunnels")

    def create_tunnel(self, name, game, protocol, local_host, local_port):
        return self._request("POST", "/api/tunnels", {
            "name": name,
            "game": game,
            "protocol": protocol,
            "local_host": local_host,
            "local_port": local_port,
        })

    def delete_tunnel(self, tunnel_id):
        return self._request("DELETE", "/api/tunnels/" + tunnel_id)


class TunnelWorker:
    def __init__(self, relay_host, relay_port, token, local_host, local_port, on_status):
        self.relay_host = relay_host
        self.relay_port = relay_port
        self.token = token
        self.local_host = local_host
        self.local_port = local_port
        self.on_status = on_status
        self.stop_event = threading.Event()
        self.sock = None
        self.streams = {}
        self.streams_lock = threading.Lock()

    def stop(self):
        self.stop_event.set()
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass

    def _send_frame(self, msg_type, stream_id, payload=b""):
        header = HEADER.pack(msg_type, stream_id, len(payload))
        self.sock.sendall(header + payload)

    def _read_exact(self, count):
        buf = b""
        while len(buf) < count:
            chunk = self.sock.recv(count - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return buf

    def _read_frame(self):
        header = self._read_exact(HEADER.size)
        msg_type, stream_id, length = HEADER.unpack(header)
        payload = self._read_exact(length) if length else b""
        return msg_type, stream_id, payload

    def _open_stream(self, stream_id):
        try:
            target = socket.create_connection((self.local_host, self.local_port), timeout=10)
        except Exception:
            try:
                self._send_frame(MSG_CLOSE, stream_id)
            except Exception:
                pass
            return
        with self.streams_lock:
            self.streams[stream_id] = target
        threading.Thread(target=self._pipe_stream, args=(stream_id, target), daemon=True).start()

    def _pipe_stream(self, stream_id, target):
        try:
            while not self.stop_event.is_set():
                chunk = target.recv(16384)
                if not chunk:
                    break
                try:
                    self._send_frame(MSG_DATA, stream_id, chunk)
                except Exception:
                    break
        finally:
            with self.streams_lock:
                self.streams.pop(stream_id, None)
            try:
                target.close()
            except Exception:
                pass
            try:
                self._send_frame(MSG_CLOSE, stream_id)
            except Exception:
                pass

    def _handle_frame(self, msg_type, stream_id, payload):
        if msg_type == MSG_OPEN:
            threading.Thread(target=self._open_stream, args=(stream_id,), daemon=True).start()
        elif msg_type == MSG_DATA:
            with self.streams_lock:
                target = self.streams.get(stream_id)
            if target is not None:
                try:
                    target.sendall(payload)
                except Exception:
                    pass
        elif msg_type == MSG_CLOSE:
            with self.streams_lock:
                target = self.streams.pop(stream_id, None)
            if target is not None:
                try:
                    target.close()
                except Exception:
                    pass
        elif msg_type == MSG_PING:
            try:
                self._send_frame(MSG_PONG, 0)
            except Exception:
                pass

    def _loop(self):
        auth_payload = json.dumps({"token": self.token}).encode()
        self._send_frame(MSG_AUTH, 0, auth_payload)

        msg_type, _, payload = self._read_frame()
        if msg_type == MSG_AUTH_FAIL:
            raise RuntimeError("Authentication failed")
        if msg_type != MSG_AUTH_OK:
            raise RuntimeError("Unexpected relay response")

        self.on_status("Online")

        def heartbeat():
            while not self.stop_event.is_set():
                if self.stop_event.wait(15):
                    return
                try:
                    self._send_frame(MSG_PING, 0)
                except Exception:
                    return

        threading.Thread(target=heartbeat, daemon=True).start()

        while not self.stop_event.is_set():
            msg_type, stream_id, payload = self._read_frame()
            self._handle_frame(msg_type, stream_id, payload)

    def run(self):
        delay = 2
        while not self.stop_event.is_set():
            self.on_status("Connecting...")
            try:
                self.sock = socket.create_connection((self.relay_host, self.relay_port), timeout=15)
                self._loop()
            except Exception as exc:
                self.on_status("Reconnecting...")
            finally:
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None

            if self.stop_event.wait(delay):
                break
            delay = min(delay * 2, 30)

        self.on_status("Stopped")


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Lanvexa Client")
        self.root.geometry("520x560")
        self.api = None
        self.user = None
        self.tunnels = []
        self.worker = None
        self.active_tunnel_id = None

        self.container = ttk.Frame(root, padding=16)
        self.container.pack(fill="both", expand=True)

        self.show_auth()

    def clear(self):
        for child in self.container.winfo_children():
            child.destroy()

    def show_auth(self):
        self.clear()
        ttk.Label(self.container, text="LANVEXA", font=("Segoe UI", 20, "bold")).pack(pady=(0, 16))

        ttk.Label(self.container, text="Server URL").pack(anchor="w")
        self.server_entry = ttk.Entry(self.container)
        self.server_entry.insert(0, "http://localhost:8000")
        self.server_entry.pack(fill="x", pady=(0, 12))

        ttk.Label(self.container, text="Username").pack(anchor="w")
        self.username_entry = ttk.Entry(self.container)
        self.username_entry.pack(fill="x", pady=(0, 12))

        ttk.Label(self.container, text="Password").pack(anchor="w")
        self.password_entry = ttk.Entry(self.container, show="*")
        self.password_entry.pack(fill="x", pady=(0, 16))

        button_row = ttk.Frame(self.container)
        button_row.pack(fill="x")

        ttk.Button(button_row, text="Sign In", command=self.do_login).pack(side="left", expand=True, fill="x", padx=(0, 6))
        ttk.Button(button_row, text="Sign Up", command=self.do_register).pack(side="left", expand=True, fill="x", padx=(6, 0))

        self.auth_status = ttk.Label(self.container, text="", foreground="red", wraplength=460)
        self.auth_status.pack(pady=(12, 0))

    def do_login(self):
        self._auth("login")

    def do_register(self):
        self._auth("register")

    def _auth(self, mode):
        url = self.server_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if not url or not username or not password:
            self.auth_status.config(text="All fields are required")
            return

        self.api = ApiClient(url)
        try:
            if mode == "login":
                result = self.api.login(username, password)
            else:
                result = self.api.register(username, password)
        except Exception as exc:
            self.auth_status.config(text=str(exc))
            return

        self.api.token = result["token"]
        self.user = result["user"]
        self.show_main()

    def show_main(self):
        self.clear()

        header = ttk.Frame(self.container)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Lanvexa", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(header, text="@" + self.user["username"]).pack(side="right")
        ttk.Button(header, text="Sign out", command=self.show_auth).pack(side="right", padx=(0, 8))

        create_box = ttk.LabelFrame(self.container, text="Create Tunnel", padding=12)
        create_box.pack(fill="x", pady=(0, 12))

        ttk.Label(create_box, text="Name").grid(row=0, column=0, sticky="w")
        self.name_entry = ttk.Entry(create_box)
        self.name_entry.insert(0, "Minecraft Server")
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))

        ttk.Label(create_box, text="Game").grid(row=1, column=0, sticky="w")
        self.game_box = ttk.Combobox(create_box, values=["minecraft-java", "terraria", "cs16", "valheim", "custom"], state="readonly")
        self.game_box.current(0)
        self.game_box.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))

        ttk.Label(create_box, text="Local Host").grid(row=2, column=0, sticky="w")
        self.host_entry = ttk.Entry(create_box)
        self.host_entry.insert(0, "127.0.0.1")
        self.host_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))

        ttk.Label(create_box, text="Local Port").grid(row=3, column=0, sticky="w")
        self.port_entry = ttk.Entry(create_box)
        self.port_entry.insert(0, "25565")
        self.port_entry.grid(row=3, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))

        create_box.columnconfigure(1, weight=1)
        ttk.Button(create_box, text="Create Tunnel", command=self.do_create_tunnel).grid(row=4, column=0, columnspan=2, pady=(8, 0), sticky="ew")

        tunnels_box = ttk.LabelFrame(self.container, text="Your Tunnels", padding=12)
        tunnels_box.pack(fill="both", expand=True)

        self.tunnels_tree = ttk.Treeview(tunnels_box, columns=("name", "public", "status"), show="headings", height=8)
        self.tunnels_tree.heading("name", text="Name")
        self.tunnels_tree.heading("public", text="Public Address")
        self.tunnels_tree.heading("status", text="Status")
        self.tunnels_tree.column("name", width=140)
        self.tunnels_tree.column("public", width=220)
        self.tunnels_tree.column("status", width=90)
        self.tunnels_tree.pack(fill="both", expand=True)

        action_row = ttk.Frame(tunnels_box)
        action_row.pack(fill="x", pady=(8, 0))

        ttk.Button(action_row, text="Refresh", command=self.refresh_tunnels).pack(side="left")
        ttk.Button(action_row, text="Connect", command=self.connect_selected).pack(side="left", padx=(6, 0))
        ttk.Button(action_row, text="Disconnect", command=self.disconnect).pack(side="left", padx=(6, 0))
        ttk.Button(action_row, text="Delete", command=self.delete_selected).pack(side="left", padx=(6, 0))

        self.conn_status = ttk.Label(self.container, text="Disconnected", foreground="#666")
        self.conn_status.pack(pady=(8, 0))

        self.refresh_tunnels()

    def set_status(self, text):
        self.root.after(0, lambda: self.conn_status.config(text=text))

    def refresh_tunnels(self):
        try:
            self.tunnels = self.api.tunnels()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return

        for item in self.tunnels_tree.get_children():
            self.tunnels_tree.delete(item)

        for tunnel in self.tunnels:
            address = tunnel["public_host"] + ":" + str(tunnel["public_port"])
            self.tunnels_tree.insert("", "end", iid=tunnel["id"], values=(tunnel["name"], address, tunnel["status"].upper()))

    def do_create_tunnel(self):
        try:
            local_port = int(self.port_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Local port must be a number")
            return

        try:
            tunnel = self.api.create_tunnel(
                name=self.name_entry.get().strip(),
                game=self.game_box.get(),
                protocol="tcp",
                local_host=self.host_entry.get().strip(),
                local_port=local_port,
            )
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return

        self.refresh_tunnels()
        messagebox.showinfo(
            "Tunnel Created",
            "Token:\n" + tunnel["token"] + "\n\nPublic address:\n" + tunnel["public_host"] + ":" + str(tunnel["public_port"])
        )

    def connect_selected(self):
        selection = self.tunnels_tree.selection()
        if not selection:
            messagebox.showwarning("Warning", "Select a tunnel first")
            return
        tunnel_id = selection[0]
        tunnel = next((t for t in self.tunnels if t["id"] == tunnel_id), None)
        if tunnel is None:
            return

        if self.worker is not None:
            messagebox.showwarning("Warning", "Already connected to a tunnel")
            return

        relay_host = tunnel["relay_host"]
        relay_port = int(tunnel["relay_port"])
        token = tunnel["token"]
        local_host = tunnel["local_host"]
        local_port = int(tunnel["local_port"])

        self.active_tunnel_id = tunnel_id
        self.worker = TunnelWorker(relay_host, relay_port, token, local_host, local_port, self.set_status)
        threading.Thread(target=self.worker.run, daemon=True).start()

    def disconnect(self):
        if self.worker is None:
            return
        self.worker.stop()
        self.worker = None
        self.active_tunnel_id = None
        self.set_status("Stopped")

    def delete_selected(self):
        selection = self.tunnels_tree.selection()
        if not selection:
            return
        tunnel_id = selection[0]
        if not messagebox.askyesno("Delete", "Delete this tunnel?"):
            return
        try:
            self.api.delete_tunnel(tunnel_id)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        if self.active_tunnel_id == tunnel_id:
            self.disconnect()
        self.refresh_tunnels()


def main():
    root = tk.Tk()
    try:
        root.style = ttk.Style()
        root.style.theme_use("clam")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()