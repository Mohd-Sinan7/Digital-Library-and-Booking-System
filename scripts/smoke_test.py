"""Smoke test for a running app (DLBS-42): wait until GET /health answers {"status": "ok"}.

    python scripts/smoke_test.py http://localhost:8000
    python scripts/smoke_test.py https://<app>.onrender.com --version <commit> --timeout 900

With --version it also waits until the X-App-Version header names that commit, so a
deploy only passes once the new version is serving. Exits with 1 if the time runs out.
Uses only the standard library, so it runs on a CI runner without installing anything.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request


def check(base_url: str, version: str | None = None, timeout: float = 10.0) -> tuple[bool, str]:
    """One GET /health. Returns (healthy, message)."""
    url = base_url.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = json.load(response)
            served = response.headers.get("X-App-Version", "")
    except (OSError, ValueError) as error:  # URLError, HTTPError, timeouts, bad JSON
        return False, f"{url}: no healthy answer yet ({error})"
    if body != {"status": "ok"}:
        return False, f"{url}: unexpected answer {body}"
    if version and served != version:
        return False, f"{url}: still serving version {served or 'unknown'}, waiting for {version}"
    return True, f"{url}: healthy, version {served or 'unknown'}"


def wait_until_healthy(
    base_url: str,
    version: str | None = None,
    timeout: float = 300,
    interval: float = 10,
    probe=check,
    sleep=time.sleep,
    clock=time.monotonic,
) -> bool:
    """Call probe until it reports healthy or timeout seconds have passed."""
    deadline = clock() + timeout
    while True:
        healthy, message = probe(base_url, version)
        print(message, flush=True)
        if healthy:
            return True
        if clock() + interval > deadline:
            return False
        sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait until the app's /health answers ok.")
    parser.add_argument("base_url", help="for example http://localhost:8000")
    parser.add_argument("--version", help="commit that X-App-Version must name")
    parser.add_argument("--timeout", type=float, default=300, help="seconds (default 300)")
    parser.add_argument("--interval", type=float, default=10, help="seconds between tries")
    args = parser.parse_args(argv)

    if wait_until_healthy(args.base_url, args.version, args.timeout, args.interval):
        return 0
    wanted = f" on version {args.version}" if args.version else ""
    print(f"Smoke test failed: the app was not healthy{wanted} within {args.timeout:.0f} "
          "seconds.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
