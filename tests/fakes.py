"""Small stand-ins for the Hermes plugin context."""
from __future__ import annotations

import json
from pathlib import Path


class FakeState:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self._d = {}

    def get(self, key, default=None):
        return json.loads(json.dumps(self._d.get(key, default)))

    def set(self, key, value):
        self._d[key] = json.loads(json.dumps(value))


class FakeCtx:
    """Plugin context with config, state and an in-memory cron. Any other ctx call is recorded."""

    def __init__(self, settings: dict, data_dir):
        self._s = dict(settings)
        self.state = FakeState(data_dir)
        self.cron: dict[str, dict] = {}
        self.calls: list[tuple[str, tuple, dict]] = []
        self.profile_name = "test"

    def get_config(self, key, default=None):
        return self._s.get(key, default)

    def set_config(self, key, value):
        self._s[key] = value

    def dispatch_tool(self, name, args):
        assert name == "cronjob_manage"
        if args["action"] == "create":
            jid = f"job{len(self.cron) + 1}"
            self.cron[jid] = dict(args)
            return json.dumps({"success": True, "job_id": jid})
        if args["action"] == "list":
            return json.dumps({"jobs": [{**v, "job_id": k} for k, v in self.cron.items()]})
        if args["action"] == "update":
            self.cron[args["job_id"]].update({k: v for k, v in args.items() if k not in ("action", "job_id")})
            return json.dumps({"success": True, "job_id": args["job_id"]})
        if args["action"] == "remove":
            self.cron.pop(args["job_id"], None)
            return json.dumps({"success": True})
        raise AssertionError(args)

    def __getattr__(self, name):
        if not name.startswith(("register_", "on_")):
            raise AttributeError(name)

        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return record
