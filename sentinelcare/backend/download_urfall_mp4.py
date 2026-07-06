"""Download UR Fall cam0 MP4 files for FallGuard training."""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

BASE_URL = "https://fenix.ur.edu.pl/~mkepski/ds/data"


def urfall_urls() -> list[tuple[str, str, str]]:
    urls: list[tuple[str, str, str]] = []
    for idx in range(1, 31):
        name = f"fall-{idx:02d}-cam0.mp4"
        urls.append(("fall", name, f"{BASE_URL}/{name}"))
    for idx in range(1, 41):
        name = f"adl-{idx:02d}-cam0.mp4"
        urls.append(("adl", name, f"{BASE_URL}/{name}"))
    return urls


def download_file(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 0:
        return

    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    output_path.write_bytes(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download UR Fall cam0 MP4 files")
    parser.add_argument("--output-dir", type=Path, default=Path("datasets/urfall_mp4"))
    args = parser.parse_args()

    urls = urfall_urls()
    for idx, (label, name, url) in enumerate(urls, start=1):
        output_path = args.output_dir / label / name
        print(f"[{idx}/{len(urls)}] {name}")
        download_file(url, output_path)

    print(f"Saved dataset to: {args.output_dir}")


if __name__ == "__main__":
    main()
