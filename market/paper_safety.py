"""Durable paper-only stop state. Corrupt state fails closed."""
import json
import os
from pathlib import Path
import tempfile
from threading import RLock


class PaperSafetySwitch:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self._halted = False
        self._write_failed = False
        self._lock = RLock()

    @property
    def halted(self):
        with self._lock:
            if self._write_failed:
                return True
            if self.path and self.path.exists():
                try:
                    data = json.loads(self.path.read_text())
                    if type(data.get("halted")) is not bool:
                        raise ValueError
                    self._halted = data["halted"]
                except (ValueError, OSError, TypeError, AttributeError):
                    self._halted = True
            return self._halted

    def set(self, halted):
        if type(halted) is not bool:
            raise ValueError("halted must be boolean")
        with self._lock:
            if halted:
                self._halted = True
            if self.path:
                name = None
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as stream:
                        name = stream.name
                        json.dump({"halted": halted}, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(name, self.path)
                except OSError as error:
                    self._halted = True
                    self._write_failed = True
                    raise ValueError("Could not persist paper safety state; execution remains halted.") from error
                finally:
                    if name and os.path.exists(name):
                        os.unlink(name)
            self._write_failed = False
            self._halted = halted
