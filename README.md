<div align="center">

# 🎵 Toxics Music & Video API

**High-speed, production-grade Music & Video Resolution & Streaming API**  
*Built specifically for Telegram Music Bots (PyTgCalls, Pyrogram, Telethon), Discord Bots, and Web Apps.*

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Uvicorn](https://img.shields.io/badge/Uvicorn-Standard-499848?style=for-the-badge&logo=uvicorn&logoColor=white)](https://www.uvicorn.org/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen?style=for-the-badge)](https://toxics.me)

[Live Website](https://toxics.me) • [API Documentation](https://toxics.me/developers) • [Live Playground](https://toxics.me/playground)

</div>

---

## ⚡ Key Highlights

- **⚡ Sub-Second Speeds**: Search & stream dispatch in under 200ms using multi-tiered memory caching and concurrent upstream resolvers.
- **🛡️ Anti-Datacenter IP Block Engine**: Bypasses YouTube's `Sign in to confirm you're not a bot` (HTTP 429) on Hetzner, AWS, OVH, DigitalOcean, and Oracle VPS by utilizing Android & iOS Innertube mobile client headers — **zero cookie files required**.
- **🔄 Robust Fallback Chain**:
  $$\text{Spotify (Primary)} \longrightarrow \text{JioSaavn 320kbps (Fallback 1)} \longrightarrow \text{iTunes (Fallback 2)} \longrightarrow \text{YouTube Mobile (Fallback 3)}$$
- **🎧 High Quality Audio (320kbps)**: Directly decodes Akamai CDN / Spotify VERY_HIGH streams without transcoding artifacts.
- **🎬 Full HD Video Playback (`/vplay`)**: Seamlessly extract video streams and deliver direct Google Video CDN playback URLs.
- **🔀 Smart 302/307 CDN Redirects**: Pass high-bandwidth audio and video streams straight from Google & Akamai CDNs to ffmpeg/PyTgCalls without wasting server RAM or CPU bandwidth.
- **📡 Universal Bot Compatibility**: Full `HEAD` and `GET` HTTP methods support for immediate pre-flight validation by voicechat players.

---

## 📡 API Endpoints

Base URL: `https://toxics.me/api/v1` *(or root aliases like `https://toxics.me/play`)*

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET, HEAD` | `/play?query={song}` | Resolve audio track metadata, direct stream URL, and cover art |
| `GET, HEAD` | `/vplay?query={song}` | Resolve video stream URL, thumbnail, duration, and metadata |
| `GET, HEAD` | `/stream/{id}` | Direct audio streaming (`audio/mp4`, `audio/ogg`, or 307 CDN redirect) |
| `GET, HEAD` | `/vstream/{id}` | Direct video streaming (302 redirect to Google Video CDN) |
| `GET, HEAD` | `/songs?query={q}&limit=10` | Search tracks across Spotify, JioSaavn, iTunes, and YouTube |
| `GET, HEAD` | `/info/{id}` | Get metadata for a specific track ID or link |
| `GET` | `/health` | API health check status (`{"status": "ok"}`) |

---

## 🚀 Quickstart (Local Development)

### 1. Clone the repository
```bash
git clone https://github.com/dotshv/music-api
cd music-api
```

### 2. Create and activate a Virtual Environment
```bash
python3 -m venv venv

# On Linux / macOS:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
Copy the example environment configuration:
```bash
cp env.example .env
```
Edit `.env` as required (Spotify username/password or credentials file optional).

### 5. Launch the Server
```bash
python3 main.py
```
The API is now running at `http://127.0.0.1:8000` (or `http://localhost:80`).  
Visit the web UI at `http://127.0.0.1:8000/developers` or `http://127.0.0.1:8000/playground`.

---

## 🌐 Ubuntu VPS Deployment (`toxics.me`)

The repository includes a 1-click deployment script ([deploy_vps.sh](deploy_vps.sh)) configured for Ubuntu 22.04 / 24.04:

```bash
cd /home/ubuntu/api
chmod +x deploy_vps.sh
./deploy_vps.sh
```

### Free SSL Activation (Certbot)
Point your DNS `A Record` for `toxics.me` to your VPS IP, then run:
```bash
sudo certbot --nginx -d toxics.me -d www.toxics.me
```

### Manage Service
```bash
# Restart API
sudo systemctl restart toxics-api

# Check Realtime Logs
sudo journalctl -u toxics-api -f

# Check Status
sudo systemctl status toxics-api
```

---

## 🤖 Telegram Music Bot Integration Example (PyTgCalls)

```python
import asyncio
import aiohttp
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped, VideoPiped

API_URL = "https://toxics.me/api/v1"

async def play_song(chat_id: int, query: str, call: PyTgCalls):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}/play", params={"query": query}) as resp:
            data = await resp.json()
            stream_url = data["stream_url"]
            title = data["title"]
            artist = data["artist"]

    # Stream directly into voice chat with ffmpeg
    await call.join_group_call(
        chat_id,
        AudioPiped(stream_url),
    )
    print(f"Now Playing: {title} by {artist}")

async def play_video(chat_id: int, query: str, call: PyTgCalls):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_URL}/vplay", params={"query": query}) as resp:
            data = await resp.json()
            video_url = data["stream_url"]

    await call.join_group_call(
        chat_id,
        VideoPiped(video_url),
    )
```

---

## ⚙️ Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DOMAIN` | `toxics.me` | Public domain name of the API |
| `SCHEME` | `https` | Protocol scheme (`http` or `https`) |
| `HOST` | `0.0.0.0` | Bind host address |
| `PORT` | `8000` | Port for the Uvicorn daemon |
| `SPOTIFY_USERNAME` | `""` | Optional Spotify username for user playback |
| `SPOTIFY_PASSWORD` | `""` | Optional Spotify password |
| `SPOTIFY_CREDENTIALS_FILE`| `credentials.json` | Path to stored librespot session credentials |
| `ENABLE_DOCS` | `true` | Enable `/docs` (Swagger) and `/redoc` |
| `RATE_LIMIT_PER_MIN` | `120` | Max requests allowed per IP per minute |
| `TRUST_PROXY` | `true` | Trust reverse proxy headers (`X-Forwarded-For`) |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

