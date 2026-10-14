#!/usr/bin/env python3
"""
YTGrab — paste a video URL, optionally clip a section, and download it.
Single-file desktop app (tkinter). Uses yt-dlp for downloading and ffmpeg
for clipping/merging. Works on Windows; runs anywhere Python + tkinter exist.
"""

import os
import sys
import json
import queue
import threading
import subprocess
from shutil import which
import urllib.request

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import yt_dlp
    from yt_dlp.utils import download_range_func
except Exception:
    yt_dlp = None

try:
    from PIL import Image, ImageTk
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


# ---------- paths & helpers ----------

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(APP_DIR, "ytgrab_config.json")
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        pass


def find_ffmpeg():
    local = os.path.join(APP_DIR, "bin", "ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if os.path.isfile(local):
        return local
    w = which("ffmpeg")
    return w


def hms_to_seconds(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        parts = [float(p) for p in text.split(":")]
    except ValueError:
        return None
    parts = parts[::-1]
    total = 0.0
    for i, p in enumerate(parts):
        total += p * (60 ** i)
    return max(0.0, total)


def seconds_to_hms(sec):
    sec = int(round(max(0, sec)))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


# ---------- app ----------

class YTGrab(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YTGrab")
        self.configure(bg="#111218")
        self.geometry("680x680")
        self.minsize(620, 620)
        try:
            if os.name == "nt":
                for base in (APP_DIR, getattr(sys, "_MEIPASS", APP_DIR)):
                    ico = os.path.join(base, "ytgrab.ico")
                    if os.path.isfile(ico):
                        self.iconbitmap(ico)
                        break
        except Exception:
            pass

        self.cfg = load_config()
        self.ffmpeg = find_ffmpeg()
        self.info = None
        self.duration = 0
        self.thumb_ref = None
        self.msgq = queue.Queue()
        self._syncing = False

        self._build_styles()
        self._build_ui()
        self.after(120, self._poll_queue)

        if yt_dlp is None:
            self._set_status("yt-dlp not installed — run:  pip install -U yt-dlp", error=True)

    # ---- styling ----
    def _build_styles(self):
        self.BG = "#111218"
        self.CARD = "#1a1b23"
        self.LINE = "#2a2b36"
        self.TXT = "#ededf2"
        self.MUT = "#8a8a99"
        self.ACC = "#ff3c5c"
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except Exception:
            pass
        s.configure("TFrame", background=self.BG)
        s.configure("Card.TFrame", background=self.CARD)
        s.configure("TLabel", background=self.BG, foreground=self.TXT, font=("Segoe UI", 10))
        s.configure("Card.TLabel", background=self.CARD, foreground=self.TXT, font=("Segoe UI", 10))
        s.configure("Muted.TLabel", background=self.BG, foreground=self.MUT, font=("Segoe UI", 9))
        s.configure("CardMuted.TLabel", background=self.CARD, foreground=self.MUT, font=("Segoe UI", 9))
        s.configure("Title.TLabel", background=self.CARD, foreground=self.TXT, font=("Segoe UI Semibold", 12))
        s.configure("TButton", font=("Segoe UI", 10), padding=6)
        s.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=8)
        s.map("Accent.TButton",
              background=[("!disabled", self.ACC), ("disabled", "#5a2630")],
              foreground=[("!disabled", "#ffffff")])
        s.configure("TCheckbutton", background=self.BG, foreground=self.TXT, font=("Segoe UI", 10))
        s.configure("TRadiobutton", background=self.BG, foreground=self.TXT, font=("Segoe UI", 10))
        s.configure("Horizontal.TProgressbar", background=self.ACC, troughcolor=self.LINE)

    # ---- layout ----
    def _build_ui(self):
        pad = {"padx": 16}

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(14, 6), **pad)
        ttk.Label(header, text="YTGrab", font=("Segoe UI Semibold", 18)).pack(side="left")
        ttk.Label(header, text="paste a link · clip it · download",
                  style="Muted.TLabel").pack(side="left", padx=(10, 0), pady=(6, 0))

        # URL row
        url_row = ttk.Frame(self)
        url_row.pack(fill="x", pady=6, **pad)
        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(url_row, textvariable=self.url_var, font=("Segoe UI", 11),
                                  bg=self.CARD, fg=self.TXT, insertbackground=self.TXT,
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=self.LINE, highlightcolor=self.ACC)
        self.url_entry.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 8))
        self.url_entry.bind("<Return>", lambda e: self.load_info())
        ttk.Button(url_row, text="Paste", command=self._paste).pack(side="left", padx=(0, 6))
        self.load_btn = ttk.Button(url_row, text="Load", command=self.load_info)
        self.load_btn.pack(side="left")

        # info card
        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="x", pady=8, **pad)
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="x", padx=12, pady=12)
        self.thumb_label = tk.Label(inner, bg=self.CARD, width=160, height=90, text="",
                                    fg=self.MUT)
        self.thumb_label.pack(side="left")
        meta = ttk.Frame(inner, style="Card.TFrame")
        meta.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.title_label = ttk.Label(meta, text="No video loaded", style="Title.TLabel",
                                     wraplength=420, justify="left")
        self.title_label.pack(anchor="w")
        self.sub_label = ttk.Label(meta, text="Paste a YouTube / TikTok / X / Instagram link above.",
                                   style="CardMuted.TLabel", wraplength=420, justify="left")
        self.sub_label.pack(anchor="w", pady=(4, 0))

        # clip card
        clip = ttk.Frame(self, style="Card.TFrame")
        clip.pack(fill="x", pady=8, **pad)
        clip_in = ttk.Frame(clip, style="Card.TFrame")
        clip_in.pack(fill="x", padx=12, pady=12)

        self.clip_on = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(clip_in, text="  Download only a clip", variable=self.clip_on,
                             command=self._toggle_clip, style="TCheckbutton")
        cb.configure(style="TCheckbutton")
        cb.pack(anchor="w")

        self.clip_body = ttk.Frame(clip_in, style="Card.TFrame")
        self.clip_body.pack(fill="x", pady=(10, 0))

        # start row
        srow = ttk.Frame(self.clip_body, style="Card.TFrame")
        srow.pack(fill="x", pady=3)
        ttk.Label(srow, text="Start", width=6, style="Card.TLabel").pack(side="left")
        self.start_scale = ttk.Scale(srow, from_=0, to=100, orient="horizontal",
                                     command=lambda v: self._scale_changed("start"))
        self.start_scale.pack(side="left", fill="x", expand=True, padx=8)
        self.start_var = tk.StringVar(value="0:00")
        se = tk.Entry(srow, textvariable=self.start_var, width=9, justify="center",
                      bg=self.BG, fg=self.TXT, insertbackground=self.TXT, relief="flat",
                      highlightthickness=1, highlightbackground=self.LINE, highlightcolor=self.ACC)
        se.pack(side="left")
        se.bind("<Return>", lambda e: self._entry_changed("start"))
        se.bind("<FocusOut>", lambda e: self._entry_changed("start"))

        # end row
        erow = ttk.Frame(self.clip_body, style="Card.TFrame")
        erow.pack(fill="x", pady=3)
        ttk.Label(erow, text="End", width=6, style="Card.TLabel").pack(side="left")
        self.end_scale = ttk.Scale(erow, from_=0, to=100, orient="horizontal",
                                   command=lambda v: self._scale_changed("end"))
        self.end_scale.pack(side="left", fill="x", expand=True, padx=8)
        self.end_var = tk.StringVar(value="0:00")
        ee = tk.Entry(erow, textvariable=self.end_var, width=9, justify="center",
                      bg=self.BG, fg=self.TXT, insertbackground=self.TXT, relief="flat",
                      highlightthickness=1, highlightbackground=self.LINE, highlightcolor=self.ACC)
        ee.pack(side="left")
        ee.bind("<Return>", lambda e: self._entry_changed("end"))
        ee.bind("<FocusOut>", lambda e: self._entry_changed("end"))

        prow = ttk.Frame(self.clip_body, style="Card.TFrame")
        prow.pack(fill="x", pady=(8, 0))
        self.prev_start_btn = ttk.Button(prow, text="Preview start frame",
                                         command=lambda: self.preview_frame("start"))
        self.prev_start_btn.pack(side="left")
        self.prev_end_btn = ttk.Button(prow, text="Preview end frame",
                                       command=lambda: self.preview_frame("end"))
        self.prev_end_btn.pack(side="left", padx=8)
        self.clip_len_label = ttk.Label(prow, text="", style="CardMuted.TLabel")
        self.clip_len_label.pack(side="left", padx=8)

        # options row
        opt = ttk.Frame(self)
        opt.pack(fill="x", pady=8, **pad)
        ttk.Label(opt, text="Format").pack(side="left")
        self.fmt_var = tk.StringVar(value=self.cfg.get("fmt", "mp4"))
        ttk.Radiobutton(opt, text="MP4 video", value="mp4", variable=self.fmt_var).pack(side="left", padx=(8, 4))
        ttk.Radiobutton(opt, text="MP3 audio", value="mp3", variable=self.fmt_var).pack(side="left", padx=4)
        ttk.Label(opt, text="   Quality").pack(side="left")
        self.q_var = tk.StringVar(value=self.cfg.get("quality", "Best"))
        ttk.Combobox(opt, textvariable=self.q_var, values=["Best", "1080p", "720p", "480p"],
                     width=7, state="readonly").pack(side="left", padx=8)

        # folder row
        frow = ttk.Frame(self)
        frow.pack(fill="x", pady=6, **pad)
        ttk.Label(frow, text="Save to").pack(side="left")
        default_dir = self.cfg.get("folder") or os.path.join(os.path.expanduser("~"), "Downloads")
        self.folder_var = tk.StringVar(value=default_dir)
        fe = tk.Entry(frow, textvariable=self.folder_var, font=("Segoe UI", 10),
                      bg=self.CARD, fg=self.TXT, insertbackground=self.TXT, relief="flat",
                      highlightthickness=1, highlightbackground=self.LINE, highlightcolor=self.ACC)
        fe.pack(side="left", fill="x", expand=True, ipady=5, padx=8)
        ttk.Button(frow, text="Browse", command=self._browse).pack(side="left")

        # download button + progress
        drow = ttk.Frame(self)
        drow.pack(fill="x", pady=(12, 4), **pad)
        self.dl_btn = ttk.Button(drow, text="Download", style="Accent.TButton", command=self.start_download)
        self.dl_btn.pack(fill="x")
        self.prog = ttk.Progressbar(self, style="Horizontal.TProgressbar", mode="determinate", maximum=100)
        self.prog.pack(fill="x", pady=(8, 2), **pad)
        self.status = ttk.Label(self, text="Ready.", style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(0, 10), **pad)

        if not self.ffmpeg:
            self._set_status("ffmpeg not found — clipping & MP3 need it. See the README to add it.", error=True)

        self._toggle_clip()

    # ---- small ui helpers ----
    def _paste(self):
        try:
            self.url_var.set(self.clipboard_get().strip())
        except Exception:
            pass

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.folder_var.get() or os.path.expanduser("~"))
        if d:
            self.folder_var.set(d)

    def _set_status(self, text, error=False):
        self.status.configure(text=text, foreground=(self.ACC if error else self.MUT))

    def _toggle_clip(self):
        state = "normal" if self.clip_on.get() else "disabled"
        for w in (self.start_scale, self.end_scale, self.prev_start_btn, self.prev_end_btn):
            try:
                w.configure(state=state)
            except Exception:
                pass
        self._update_clip_len()

    def _update_clip_len(self):
        if not self.clip_on.get():
            self.clip_len_label.configure(text="")
            return
        s = hms_to_seconds(self.start_var.get()) or 0
        e = hms_to_seconds(self.end_var.get()) or 0
        if e > s:
            self.clip_len_label.configure(text=f"clip length: {seconds_to_hms(e - s)}")
        else:
            self.clip_len_label.configure(text="end must be after start")

    def _scale_changed(self, which_):
        if self._syncing or not self.duration:
            return
        self._syncing = True
        if which_ == "start":
            self.start_var.set(seconds_to_hms(self.start_scale.get()))
        else:
            self.end_var.set(seconds_to_hms(self.end_scale.get()))
        self._syncing = False
        self._update_clip_len()

    def _entry_changed(self, which_):
        if self._syncing:
            return
        secs = hms_to_seconds(self.start_var.get() if which_ == "start" else self.end_var.get())
        if secs is None:
            return
        if self.duration:
            secs = min(secs, self.duration)
        self._syncing = True
        if which_ == "start":
            self.start_scale.set(secs)
            self.start_var.set(seconds_to_hms(secs))
        else:
            self.end_scale.set(secs)
            self.end_var.set(seconds_to_hms(secs))
        self._syncing = False
        self._update_clip_len()

    # ---- load info ----
    def load_info(self):
        url = self.url_var.get().strip()
        if not url:
            return
        if yt_dlp is None:
            messagebox.showerror("YTGrab", "yt-dlp isn't installed.\n\nOpen Command Prompt and run:\n    pip install -U yt-dlp")
            return
        self._set_status("Loading video info…")
        self.load_btn.configure(state="disabled")
        threading.Thread(target=self._load_info_worker, args=(url,), daemon=True).start()

    def _load_info_worker(self, url):
        try:
            opts = {"quiet": True, "skip_download": True, "noplaylist": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.msgq.put(("info", info))
        except Exception as ex:
            self.msgq.put(("info_err", str(ex)))

    def _apply_info(self, info):
        self.info = info
        self.duration = int(info.get("duration") or 0)
        title = info.get("title") or "Untitled"
        uploader = info.get("uploader") or info.get("channel") or ""
        dur_txt = seconds_to_hms(self.duration) if self.duration else "unknown length"
        self.title_label.configure(text=title)
        self.sub_label.configure(text=f"{uploader}   ·   {dur_txt}")
        # sliders
        hi = max(self.duration, 1)
        self.start_scale.configure(to=hi)
        self.end_scale.configure(to=hi)
        self._syncing = True
        self.start_scale.set(0)
        self.end_scale.set(self.duration)
        self.start_var.set("0:00")
        self.end_var.set(seconds_to_hms(self.duration))
        self._syncing = False
        self._update_clip_len()
        self._set_status("Loaded. Ready to download.")
        self.load_btn.configure(state="normal")
        # thumbnail
        thumb = info.get("thumbnail")
        if thumb and HAVE_PIL:
            threading.Thread(target=self._load_thumb, args=(thumb,), daemon=True).start()

    def _load_thumb(self, url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=15).read()
            from io import BytesIO
            im = Image.open(BytesIO(data)).convert("RGB")
            im.thumbnail((160, 110))
            self.msgq.put(("thumb", im))
        except Exception:
            pass

    # ---- preview frame (best effort) ----
    def preview_frame(self, which_):
        if not self.ffmpeg:
            messagebox.showinfo("YTGrab", "Frame preview needs ffmpeg. See the README to add it.")
            return
        if not self.info:
            return
        t = hms_to_seconds(self.start_var.get() if which_ == "start" else self.end_var.get()) or 0
        self._set_status(f"Grabbing frame at {seconds_to_hms(t)}…")
        threading.Thread(target=self._preview_worker, args=(self.url_var.get().strip(), t), daemon=True).start()

    def _preview_worker(self, url, t):
        try:
            opts = {"quiet": True, "skip_download": True, "noplaylist": True,
                    "format": "bv*[height<=720]/b[height<=720]/b"}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            vurl = info.get("url")
            if not vurl and info.get("requested_formats"):
                vurl = info["requested_formats"][0].get("url")
            if not vurl:
                raise RuntimeError("no stream url")
            out = os.path.join(APP_DIR, "_preview.jpg")
            cmd = [self.ffmpeg, "-y", "-ss", str(t), "-i", vurl,
                   "-frames:v", "1", "-q:v", "3", out]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=CREATE_NO_WINDOW, timeout=60)
            if HAVE_PIL and os.path.isfile(out):
                im = Image.open(out).convert("RGB")
                im.thumbnail((160, 110))
                self.msgq.put(("thumb", im))
                self.msgq.put(("status", f"Frame at {seconds_to_hms(t)}."))
            else:
                self.msgq.put(("status", "Preview unavailable for this video."))
        except Exception:
            self.msgq.put(("status", "Preview unavailable for this video (clip download still works)."))

    # ---- download ----
    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("YTGrab", "Paste a video link first.")
            return
        if yt_dlp is None:
            messagebox.showerror("YTGrab", "yt-dlp isn't installed.\n\nRun:  pip install -U yt-dlp")
            return
        folder = self.folder_var.get().strip() or os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(folder, exist_ok=True)

        clip = None
        if self.clip_on.get():
            s = hms_to_seconds(self.start_var.get())
            e = hms_to_seconds(self.end_var.get())
            if s is None or e is None or e <= s:
                messagebox.showinfo("YTGrab", "Set a valid start and end (end after start).")
                return
            if not self.ffmpeg:
                messagebox.showinfo("YTGrab", "Clipping needs ffmpeg. See the README to add it.")
                return
            clip = (s, e)

        # persist prefs
        self.cfg.update({"folder": folder, "fmt": self.fmt_var.get(), "quality": self.q_var.get()})
        save_config(self.cfg)

        self.dl_btn.configure(state="disabled")
        self.prog.configure(value=0)
        self._set_status("Starting…")
        threading.Thread(target=self._download_worker, args=(url, folder, clip), daemon=True).start()

    def _build_format(self):
        q = self.q_var.get()
        cap = {"1080p": 1080, "720p": 720, "480p": 480}.get(q)
        if self.fmt_var.get() == "mp3":
            return "ba/b"
        if cap:
            return f"bv*[height<={cap}]+ba/b[height<={cap}]/b"
        return "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"

    def _progress_hook(self, d):
        st = d.get("status")
        if st == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes", 0)
            if total:
                pct = done / total * 100
                self.msgq.put(("prog", pct))
            spd = d.get("speed")
            spd_txt = f"{spd/1048576:.1f} MB/s" if spd else ""
            self.msgq.put(("status", f"Downloading… {spd_txt}"))
        elif st == "finished":
            self.msgq.put(("prog", 100))
            self.msgq.put(("status", "Processing (merging / converting)…"))

    def _download_worker(self, url, folder, clip):
        try:
            outtmpl = os.path.join(folder, "%(title).200B [%(id)s].%(ext)s")
            opts = {
                "outtmpl": outtmpl,
                "format": self._build_format(),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "progress_hooks": [self._progress_hook],
                "retries": 5,
                "concurrent_fragment_downloads": 4,
            }
            if self.ffmpeg:
                opts["ffmpeg_location"] = os.path.dirname(self.ffmpeg)
            if self.fmt_var.get() == "mp3":
                opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                           "preferredcodec": "mp3",
                                           "preferredquality": "192"}]
            else:
                opts["merge_output_format"] = "mp4"
            if clip:
                s, e = clip
                opts["download_ranges"] = download_range_func(None, [(s, e)])
                opts["force_keyframes_at_cuts"] = True

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            self.msgq.put(("done", folder))
        except Exception as ex:
            self.msgq.put(("dl_err", str(ex)))

    # ---- queue poll ----
    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msgq.get_nowait()
                if kind == "info":
                    self._apply_info(payload)
                elif kind == "info_err":
                    self.load_btn.configure(state="normal")
                    self._set_status("Couldn't load that link.", error=True)
                    messagebox.showerror("YTGrab", f"Couldn't load that link:\n\n{payload}")
                elif kind == "thumb":
                    self.thumb_ref = ImageTk.PhotoImage(payload)
                    self.thumb_label.configure(image=self.thumb_ref, width=payload.width, height=payload.height)
                elif kind == "prog":
                    self.prog.configure(value=payload)
                elif kind == "status":
                    self._set_status(payload)
                elif kind == "done":
                    self.prog.configure(value=100)
                    self.dl_btn.configure(state="normal")
                    self._set_status(f"Done · saved to {payload}")
                    messagebox.showinfo("YTGrab", f"Download complete.\n\nSaved to:\n{payload}")
                elif kind == "dl_err":
                    self.dl_btn.configure(state="normal")
                    self._set_status("Download failed.", error=True)
                    messagebox.showerror("YTGrab", f"Download failed:\n\n{payload}")
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)


if __name__ == "__main__":
    app = YTGrab()
    app.mainloop()
