import argparse, getpass, logging, os
from time import sleep
import requests

logger = logging.getLogger(__name__)


def getFiles(directory, extension):
    return [f for f in os.listdir(directory) if f.endswith(extension)]


def uploadFile(local_file, filename, dest, token):
    logger.info("Uploading %s", filename)
    with open(local_file, "rb") as f:
        data = f.read()

    headers = {
        "Authorization": f"Bearer {token}",
        "Dropbox-API-Arg": f'{{"path": "{dest}/{filename}", "mode": "overwrite"}}',
        "Content-Type": "application/octet-stream",
    }

    response = requests.post(
        "https://content.dropboxapi.com/2/files/upload",
        headers=headers,
        data=data,
    )
    return response.status_code == 200


def parse_args():
    parser = argparse.ArgumentParser(description="Upload PDFs to Dropbox on a schedule")
    parser.add_argument("--directory", required=True, help="Local directory to watch for PDFs")
    parser.add_argument("--destination", required=True, help="Dropbox destination path")
    parser.add_argument("--token", default=None, help="Dropbox access token (prompted if omitted)")
    parser.add_argument("--interval", type=int, default=3600, help="Seconds between upload passes (default 3600)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Logging level")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    token = args.token or getpass.getpass("Enter Dropbox access token: ")

    while True:
        files = getFiles(args.directory, ".pdf")
        for f in files:
            local_file = os.path.join(args.directory, f)
            if uploadFile(local_file, f, args.destination, token):
                os.remove(local_file)
            else:
                logger.warning("Upload failed for %s", f)
        logger.info("Sleeping %ds...", args.interval)
        sleep(args.interval)


if __name__ == "__main__":
    main()
