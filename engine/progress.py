"""Live progress of a running search, for the dashboard's progress bar.

The engine writes one small file, data/search-progress.json, on a side branch so the main
branch (and the published site) is not rebuilt every few seconds. The file is encrypted with
RADAR_KEY like the rest of the data, so the public repository shows nothing about a search.
Progress is optional: any failure here is ignored and never interrupts the search.
"""

import base64
import json
import os
import time
import urllib.request

import store

BRANCH = "radar-live"
PATH = "data/search-progress.json"
MIN_INTERVAL = 7  # seconds between two updates, unless forced


class Progress:
    def __init__(self, run_id, key=None):
        self.run_id = run_id
        self.key = key or os.getenv("RADAR_KEY")
        self.token = os.getenv("RADAR_PROGRESS_TOKEN")
        self.repo = os.getenv("GITHUB_REPOSITORY")
        self.sha = None
        self.last = 0.0
        self.discovery_done = 0
        self.discovery_total = 0

    @property
    def enabled(self):
        return bool(self.token and self.repo and self.key)

    def _call(self, path, method="GET", data=None):
        req = urllib.request.Request(
            f"https://api.github.com/repos/{self.repo}{path}", method=method,
            data=json.dumps(data).encode() if data else None,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)

    def _ensure_branch(self):
        try:
            self._call("/git/ref/heads/" + BRANCH)
        except Exception:  # noqa: BLE001 - the branch does not exist yet
            self._call("/git/refs", "POST", {"ref": "refs/heads/" + BRANCH, "sha": os.environ["GITHUB_SHA"]})
        try:
            self.sha = self._call(f"/contents/{PATH}?ref={BRANCH}")["sha"]
        except Exception:  # noqa: BLE001 - first write creates the file
            self.sha = None

    def update(self, phase, done=0, total=0, force=False):
        if not self.enabled or (not force and time.monotonic() - self.last < MIN_INTERVAL):
            return
        self.last = time.monotonic()
        try:
            if self.sha is None:
                self._ensure_branch()
            payload = {"run_id": self.run_id, "phase": phase, "done": done, "total": total, "at": int(time.time())}
            sealed = store.encrypt_bytes(json.dumps(payload).encode(), self.key)
            data = {"message": "radar: progress [skip ci]", "branch": BRANCH,
                    "content": base64.b64encode(sealed.encode()).decode()}
            if self.sha:
                data["sha"] = self.sha
            self.sha = self._call(f"/contents/{PATH}", "PUT", data)["content"]["sha"]
        except Exception:  # noqa: BLE001 - progress is optional
            self.sha = None
