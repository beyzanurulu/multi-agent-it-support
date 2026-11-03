"""Download the trained NLU model (GitHub Release asset) into models/nlu.

The ONNX model (~110 MB) is not committed to git. Training (ml/colab_train.ipynb) produces
nlu-model.zip, which is attached to a GitHub Release. This script fetches it; if no release
exists yet it exits 0 and the NLU service keeps using the rule-based backend.

    python ml/fetch_model.py [--url URL] [--dest models/nlu] [--force]
"""

import argparse
import io
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "beyzanurulu/multi-agent-it-support")
DEFAULT_URL = f"https://github.com/{REPO}/releases/latest/download/nlu-model.zip"
REQUIRED = ("model.onnx", "tokenizer.json", "labels.json")


def fetch(url: str, dest: Path, force: bool = False) -> bool:
    if all((dest / f).exists() for f in REQUIRED) and not force:
        print(f"model already present in {dest}")
        return True
    try:
        with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310 - fixed https URL
            data = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            print(f"no released model at {url}; the rule-based NLU backend will be used")
            return False
        raise
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = {Path(n).name: n for n in zf.namelist() if not n.endswith("/")}
        missing = [f for f in REQUIRED if f not in names]
        if missing:
            raise SystemExit(f"nlu-model.zip is missing {missing}")
        dest.mkdir(parents=True, exist_ok=True)
        for name in REQUIRED + tuple(n for n in names if n not in REQUIRED):
            (dest / name).write_bytes(zf.read(names[name]))
    print(f"model extracted to {dest} ({len(data) / 1e6:.1f} MB zip)")
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--dest", default="models/nlu")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()
    fetch(args.url, Path(args.dest), args.force)
    sys.exit(0)


if __name__ == "__main__":
    main()
