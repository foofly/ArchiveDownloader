import argparse, json, logging, os, re, time, urllib.parse
import pikepdf, requests

ROOT = "https://www.archive.org"
HISTORY_FILE = "history.json"
DOWNLOAD_DIR = "Downloads"
UPLOAD_DIR = "Uploads"

logger = logging.getLogger(__name__)


def _retry_get(url, retries=3, backoff_base=1.0):
    for attempt in range(retries):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response
            logger.warning("Attempt %d/%d failed for %s (HTTP %d)", attempt + 1, retries, url, response.status_code)
        except requests.RequestException as exc:
            logger.warning("Attempt %d/%d error for %s: %s", attempt + 1, retries, url, exc)
        if attempt < retries - 1:
            sleep_time = backoff_base * (2 ** attempt)
            logger.debug("Backing off %.1fs before retry", sleep_time)
            time.sleep(sleep_time)
    logger.error("All %d attempts failed for %s", retries, url)
    return None


def getMetadata(identifier, retries=3):
    url = f"{ROOT}/metadata/{identifier}"
    logger.info("Fetching metadata for %s", identifier)
    response = _retry_get(url, retries=retries)
    if response is None:
        logger.error("Failed to fetch metadata for %s", identifier)
        return None
    return response.json()


def loadHistory(history_file=HISTORY_FILE):
    history = {}
    if os.path.exists(history_file):
        logger.debug("Loading history from %s", history_file)
        with open(history_file, "r") as f:
            history = json.load(f)
    return history


def SaveHistory(history, history_file=HISTORY_FILE):
    logger.debug("Saving history to %s", history_file)
    with open(history_file, "w") as f:
        json.dump(history, f, indent=2)


def ensureDirectory(path):
    if not os.path.exists(path):
        os.makedirs(path)


def getPendingFilenames(identifier, history, metadata):
    done = set(history.get(identifier, []))
    pending = [
        f["name"]
        for f in metadata.get("files", [])
        if f["name"].lower().endswith(".pdf") and f["name"] not in done
    ]
    logger.info("%d pending, %d already done for %s", len(pending), len(done), identifier)
    return pending


def downloadFile(identifier, filename, download_dir=DOWNLOAD_DIR, retries=3):
    safe = urllib.parse.quote(filename, safe="")
    url = f"{ROOT}/download/{identifier}/{safe}"
    response = _retry_get(url, retries=retries)
    if response is None:
        logger.error("Failed to download %s", filename)
        return ""
    local_path = GetLocalFilename(filename, download_dir=download_dir)
    with open(local_path, "wb") as f:
        f.write(response.content)
    logger.info("Downloaded %s", local_path)
    return local_path


def GetLocalFilename(filename, download_dir=DOWNLOAD_DIR):
    return os.path.join(download_dir, filename)


def ApplyMetadata(filename, pattern, series, download_dir=DOWNLOAD_DIR, upload_dir=UPLOAD_DIR):
    local_filename = GetLocalFilename(filename, download_dir=download_dir)
    match = re.match(pattern, filename)
    if match is None:
        logger.error("Pattern %r did not match filename %r", pattern, filename)
        return False
    issue_name = "-".join(match.groups())
    new_filename = os.path.join(upload_dir, f"{series} {issue_name}.pdf")
    try:
        pdf = pikepdf.Pdf.open(local_filename)
        pdf.docinfo["/Author"] = series
        pdf.docinfo["/Title"] = issue_name
        pdf.save(new_filename)
        pdf.close()
    except Exception as exc:
        logger.error("pikepdf error processing %s: %s", filename, exc)
        return False
    os.remove(local_filename)
    logger.info("Processed %s -> %s", filename, new_filename)
    return True


def parse_args():
    parser = argparse.ArgumentParser(description="Download and process PDFs from Archive.org")
    parser.add_argument("--id", required=True, help="Archive.org item identifier")
    parser.add_argument("--series", required=True, help="Series name for PDF /Author field")
    parser.add_argument("--pattern", required=True, help="Regex pattern to extract issue groups from filename")
    parser.add_argument("--download-dir", default=DOWNLOAD_DIR, help="Download staging directory")
    parser.add_argument("--upload-dir", default=UPLOAD_DIR, help="Processed PDF output directory")
    parser.add_argument("--history-file", default=HISTORY_FILE, help="History file path")
    parser.add_argument("--retries", type=int, default=3, help="HTTP retry attempts")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    ensureDirectory(args.download_dir)
    ensureDirectory(args.upload_dir)

    history = loadHistory(args.history_file)
    if args.id not in history:
        history[args.id] = []

    metadata = getMetadata(args.id, retries=args.retries)
    if metadata is None:
        return 1

    pending = getPendingFilenames(args.id, history, metadata)
    if not pending:
        logger.info("No new PDFs to process")
        return 0

    for filename in pending:
        downloaded = downloadFile(args.id, filename, download_dir=args.download_dir, retries=args.retries)
        if not downloaded:
            continue
        applied = ApplyMetadata(filename, args.pattern, args.series,
                                download_dir=args.download_dir, upload_dir=args.upload_dir)
        if applied:
            history[args.id].append(filename)
            SaveHistory(history, args.history_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
