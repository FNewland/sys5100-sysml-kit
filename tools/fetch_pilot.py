#!/usr/bin/env python3
"""Download the OMG SysML v2 Pilot Implementation (jupyter-sysml-kernel, EPL-2.0) from
conda-forge and unpack the all-in-one jar plus the standard library. No conda needed.

usage: python tools/fetch_pilot.py [--version 0.62.0] [--dest ext/kernel] [--sha256 HEX]
Prints the kernel directory (contains jupyter-sysml-kernel-<ver>-all.jar and sysml.library/).
Requires: pip install zstandard   (Python >= 3.14 can use compression.zstd instead)

The download (~124 MB) is streamed to disk and resumed with HTTP Range requests if the
connection drops, then checked against Content-Length (and --sha256 if given).
"""
import argparse
import hashlib
import io
import pathlib
import sys
import tarfile
import time
import urllib.error
import urllib.request
import zipfile

ap = argparse.ArgumentParser()
ap.add_argument("--version", default="0.62.0")
ap.add_argument("--build", default="pyhd8ed1ab_0")
ap.add_argument("--dest", default="ext/kernel")
ap.add_argument("--sha256", help="expected SHA-256 of the .conda file (pin it per term)")
ap.add_argument("--retries", type=int, default=6)
a = ap.parse_args()

dest = pathlib.Path(a.dest)
kdir = dest / "pkg" / "share" / "jupyter" / "kernels" / "sysml"
jar = kdir / f"jupyter-sysml-kernel-{a.version}-all.jar"


def download(url: str, out: pathlib.Path) -> None:
    total = None
    for attempt in range(1, a.retries + 1):
        have = out.stat().st_size if out.exists() else 0
        req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                if have and r.status != 206:          # server ignored Range: start again
                    have = 0
                    out.unlink(missing_ok=True)
                length = r.headers.get("Content-Length")
                if length is not None:
                    total = have + int(length)
                with out.open("ab") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
            size = out.stat().st_size
            if total is None or size >= total:
                print(f"downloaded {size / 1e6:.1f} MB", flush=True)
                return
            print(f"short read ({size}/{total} bytes); resuming (attempt {attempt})", flush=True)
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            print(f"download interrupted ({e.__class__.__name__}); resuming (attempt {attempt})", flush=True)
        time.sleep(min(2 ** attempt, 20))
    sys.exit(f"could not download {url} after {a.retries} attempts")


if not jar.exists():
    url = (f"https://conda.anaconda.org/conda-forge/noarch/"
           f"jupyter-sysml-kernel-{a.version}-{a.build}.conda")
    dest.mkdir(parents=True, exist_ok=True)
    pkg_file = dest / f"jupyter-sysml-kernel-{a.version}-{a.build}.conda"
    print(f"downloading {url}", flush=True)
    download(url, pkg_file)
    if a.sha256:
        h = hashlib.sha256(pkg_file.read_bytes()).hexdigest()
        if h != a.sha256.lower():
            pkg_file.unlink()
            sys.exit(f"SHA-256 mismatch: got {h}, expected {a.sha256}")
    with zipfile.ZipFile(pkg_file) as z:
        inner = next(n for n in z.namelist() if n.startswith("pkg-") and n.endswith(".tar.zst"))
        raw = z.read(inner)
    try:
        from compression import zstd  # Python 3.14+
        stream = io.BytesIO(zstd.decompress(raw))
    except ImportError:
        import zstandard
        stream = zstandard.ZstdDecompressor().stream_reader(io.BytesIO(raw))
    with tarfile.open(fileobj=stream, mode="r|") as t:
        t.extractall(dest / "pkg", filter="data")
    pkg_file.unlink()                                  # keep only the unpacked kernel
print(kdir.resolve())
