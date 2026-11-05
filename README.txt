YTGrab — desktop video downloader with clipping
================================================

WHAT IT DOES
  Paste a YouTube / TikTok / X / Instagram link, optionally pick a
  start and end to grab just a clip, choose MP4 or MP3, and download.

------------------------------------------------------------
ONE-TIME SETUP (makes a real app you can pin)
------------------------------------------------------------
1. Make sure Python is installed (you already have 3.13).
2. Install ffmpeg (needed for clipping, MP3, and frame preview).
   Easiest — open Command Prompt and run:
       winget install Gyan.FFmpeg
   (Alternative: download a build, then drop ffmpeg.exe into a folder
    named "bin" next to YTGrab. The app checks there too.)
3. Double-click  build.bat  and wait. It installs everything and
   creates:   dist\YTGrab.exe
4. Open the dist folder, right-click YTGrab.exe -> Pin to taskbar.

   From now on you just click the taskbar icon. No Python, no IDLE.

------------------------------------------------------------
DON'T WANT TO BUILD AN EXE?
------------------------------------------------------------
  - First time: open Command Prompt in this folder and run:
        pip install -r requirements.txt
  - Then double-click  "run ytgrab.bat"  to launch it.
  (To pin this version: make a desktop shortcut to "run ytgrab.bat",
   then drag the shortcut to the taskbar.)

------------------------------------------------------------
USING THE CLIP FEATURE
------------------------------------------------------------
  1. Paste a link, click Load. The title, length, and thumbnail show up.
  2. Check "Download only a clip".
  3. Drag the Start and End sliders (or type times like 1:05:30).
  4. Click "Preview start/end frame" to see roughly where you're cutting.
  5. Click Download. Only that section is pulled — not the whole video.

------------------------------------------------------------
SEND TO DEVICE (phone / tablet / another PC)
------------------------------------------------------------
  After a download finishes, click "Send to device". A QR code pops up.
  Scan it with your phone's camera (phone must be on the same Wi-Fi)
  and the video downloads straight to the phone. Or tap "Copy link"
  and open it on any device on your network.
  Click "Stop sharing" when done (it also stops when you close YTGrab).
  Note: the first time, Windows may ask to allow YTGrab through the
  firewall on Private networks — click Allow.

------------------------------------------------------------
GETTING VIDEOS FROM (ALMOST) ANY SITE
------------------------------------------------------------
  The engine supports ~1,800 sites plus a generic mode for others,
  so most links just work. For videos that need you logged in
  (age-restricted, members-only, private), set the "Sign-in" dropdown
  to the browser you're logged into (e.g. Chrome) and YTGrab will use
  that browser's login.
  Can't be downloaded by anything: DRM streams like Netflix / Disney+.
  If a normally-working site breaks, update the engine (see below).

------------------------------------------------------------
NOTES
  - Your save folder and format are remembered between runs.
  - Frame preview is best-effort; if a site blocks it, the clip
    download still works fine.
  - If downloads ever stop working, the site changed something —
    update the engine:  pip install -U yt-dlp
