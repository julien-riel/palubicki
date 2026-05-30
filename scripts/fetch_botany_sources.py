"""Download the free source documents listed in the literature manifest.

Reads ``src/palubicki/configs/literature.yaml``, downloads every entry whose
``availability: free`` carries a ``url`` into a gitignored cache, and prints a
recap table. Paywalled entries are skipped with their DOI so you know where to
look manually.

The cache is provenance, not source: it is gitignored (see .gitignore), so a
reviewer regenerates it on demand rather than pulling binaries from git.

Usage:
    .venv/bin/python scripts/fetch_botany_sources.py
    .venv/bin/python scripts/fetch_botany_sources.py --out-dir docs/botany/sources
    .venv/bin/python scripts/fetch_botany_sources.py --only wood_handbook silvics
"""
from __future__ import annotations

import argparse
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path

import yaml

_UA = "palubicki-fetch-botany/0.1 (+https://github.com/julien-riel/palubicki)"


def _load_sources() -> dict:
    text = resources.files("palubicki.configs").joinpath("literature.yaml").read_text()
    return (yaml.safe_load(text) or {}).get("sources", {})


def _ext_for(fmt: str | None) -> str:
    return {"pdf": ".pdf", "csv": ".csv"}.get(fmt or "", ".bin")


def _download(url: str, dest: Path) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (trusted manifest URLs)
        data = resp.read()
    dest.write_bytes(data)
    return len(data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=Path("docs/botany/sources"),
                    help="Cache directory for downloaded sources (gitignored).")
    ap.add_argument("--only", nargs="*", default=None,
                    help="Restrict to these source keys (default: all free entries).")
    ap.add_argument("--force", action="store_true",
                    help="Re-download even if the cached file already exists.")
    args = ap.parse_args()

    sources = _load_sources()
    keys = args.only if args.only else sorted(sources)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[tuple[str, str, str]] = []
    for key in keys:
        entry = sources.get(key)
        if entry is None:
            rows.append((key, "—", "unknown key"))
            continue
        if entry.get("availability") != "free" or not entry.get("url"):
            doi = entry.get("doi") or "no DOI"
            rows.append((key, "—", f"skipped (paywall; doi:{doi})"))
            continue

        dest = args.out_dir / f"{key}{_ext_for(entry.get('format'))}"
        if dest.exists() and not args.force:
            rows.append((key, _human_size(dest.stat().st_size), "cached (skip; --force to redo)"))
            continue
        try:
            n = _download(entry["url"], dest)
            rows.append((key, _human_size(n), "downloaded"))
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            rows.append((key, "—", f"FAILED: {type(e).__name__}: {e}"))

    print(f"{'source':16s} {'size':>10s}  status")
    print("-" * 64)
    for key, size, status in rows:
        print(f"{key:16s} {size:>10s}  {status}")
    return 0


def _human_size(n: int) -> str:
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024 or unit == "GB":
            return f"{f:.0f}{unit}" if unit == "B" else f"{f:.1f}{unit}"
        f /= 1024
    return f"{f:.1f}GB"


if __name__ == "__main__":
    raise SystemExit(main())
