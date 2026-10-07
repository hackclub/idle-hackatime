# Hackatime for Python IDLE

Tracks your coding time in [IDLE](https://docs.python.org/3/library/idle.html) and sends it to [Hackatime](https://hackatime.hackclub.com). Works on macOS and Linux with Python 3.8 or newer.

## Install

Run the installer with the same Python you use to open IDLE:

```sh
curl -fsSLO https://raw.githubusercontent.com/hackclub/idle-hackatime/main/IdleHackatime.py
python3 IdleHackatime.py install
```

The installer:

- copies `IdleHackatime.py` into your user `site-packages` so IDLE can import it
- enables the extension in `~/.idlerc/config-extensions.cfg`
- downloads [wakatime-cli](https://github.com/wakatime/wakatime-cli) into `~/.wakatime` if you don't have it
- asks for your API key if `~/.wakatime.cfg` doesn't have one

Restart IDLE afterwards. If you skipped the key, IDLE asks for it on start. You can change it later from **Options → Hackatime API Key...**.

To remove it: `python3 IdleHackatime.py uninstall`.

## What it sends

Heartbeats go through wakatime-cli, which reads `api_key` and `api_url` from `~/.wakatime.cfg`. If you already ran the Hackatime setup, there's nothing else to configure.

The plugin sends a heartbeat when you open or switch to a file, when you edit it (at most once every 2 minutes per file) and every time you save. Each heartbeat includes:

| Field | Source |
| --- | --- |
| `entity`, `type`, `time` | Saved file path, `file`, time of the activity |
| `is_write` | `true` on save, `false` otherwise |
| `lineno`, `cursorpos` | Cursor line and column (1-based) |
| `lines` | Lines in the editor buffer |
| `human_line_changes` | Net lines added or removed since the last heartbeat for that file |
| `category` | `coding` |
| `project`, `branch` | Detected by wakatime-cli from Git, otherwise the folder name |
| `language`, `dependencies` | Detected by wakatime-cli (`Python` for `.py`, `.pyw`, `.pyi`) |
| `user_agent`, `operating_system`, `machine` | `idle/<python version> idle-hackatime/<version>` plus wakatime-cli's OS and host details |

Untitled buffers aren't tracked until you save them, and the IDLE Shell window isn't tracked.

The status bar shows today's time. Logs are written to `~/.wakatime/idle-hackatime.log`; set `debug = true` in `~/.wakatime.cfg` for more detail.
