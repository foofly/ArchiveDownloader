# ArchiveDownloader

Downloads vintage magazine PDFs from [Archive.org](https://archive.org), injects PDF metadata, and uploads them to Dropbox.

## Requirements

```
pip install -r requirements.txt
```

Dependencies: `pikepdf`, `requests`

## Usage

### 1. Download & process — GUI

```bash
python DownloaderGUI.py
```

Opens a single-window tkinter interface. Fill in the required fields (Archive ID, Series, Pattern) and click **Run**. Log output streams into the window in real time; the form re-enables when the run completes. No extra dependencies beyond those already in `requirements.txt`.

### 2. Download & process — CLI

```bash
python ArchiveDownloader.py \
  --id "1982-10-byte-magazine-october-1-byte-magazine-21533" \
  --series "Byte Magazine" \
  --pattern "^(\d{4}) (\d{2})"
```

| Flag | Default | Description |
|---|---|---|
| `--id` | *(required)* | Archive.org item identifier |
| `--series` | *(required)* | Series name — written to PDF `/Author` field |
| `--pattern` | *(required)* | Regex with capture groups to build the issue name from the filename |
| `--download-dir` | `Downloads` | Staging directory for raw downloads |
| `--upload-dir` | `Uploads` | Output directory for processed PDFs |
| `--history-file` | `history.json` | Tracks already-processed files so reruns skip them |
| `--retries` | `3` | HTTP retry attempts with exponential backoff |
| `--log-level` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

The script fetches all PDFs for the given Archive.org item, skips any already recorded in the history file, downloads each one, injects `/Author` and `/Title` metadata via pikepdf, moves the result to the upload directory, and saves progress after every successful file.

### 3. Upload to Dropbox

```bash
python Uploader.py \
  --directory Uploads \
  --destination "/Magazines/Byte" \
  --token "$DROPBOX_TOKEN"
```

Omit `--token` to be prompted securely at startup (safe for cron jobs using an environment variable).

| Flag | Default | Description |
|---|---|---|
| `--directory` | *(required)* | Local directory to watch for PDFs |
| `--destination` | *(required)* | Dropbox destination path |
| `--token` | *(prompted)* | Dropbox access token |
| `--interval` | `3600` | Seconds between upload passes |
| `--log-level` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

Runs as a daemon: uploads all PDFs found in the directory, deletes them on success, then sleeps for `--interval` seconds and repeats.
