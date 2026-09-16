import json
import socket
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class InstrumentMasterDownloadError(RuntimeError):
    """Raised when Angel One's broker-provided instrument master cannot be read."""


class AngelOneInstrumentMasterClient:
    """Read-only downloader for the official Angel One instrument-master file."""

    URL = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
    source = "ANGEL_ONE_INSTRUMENT_MASTER"

    def __init__(self, timeout=15, opener=urlopen, clock=None):
        self.timeout = timeout
        self._opener = opener
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def fetch_records(self):
        request = Request(self.URL, headers={"Accept": "application/json"})
        try:
            with self._opener(request, timeout=self.timeout) as response:
                status = getattr(response, "status", response.getcode())
                if status < 200 or status >= 300:
                    raise InstrumentMasterDownloadError(f"Instrument-master request failed with HTTP {status}.")
                payload = response.read()
        except HTTPError as error:
            raise InstrumentMasterDownloadError(f"Instrument-master request failed with HTTP {error.code}.") from error
        except (URLError, socket.timeout, TimeoutError) as error:
            raise InstrumentMasterDownloadError(f"Instrument-master request failed: {error}.") from error

        if not payload:
            raise InstrumentMasterDownloadError("Instrument-master response was empty.")
        try:
            records = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InstrumentMasterDownloadError("Instrument-master response was not valid JSON.") from error
        if not isinstance(records, list):
            raise InstrumentMasterDownloadError("Instrument-master JSON payload must be a list.")
        if not records:
            raise InstrumentMasterDownloadError("Instrument-master payload contained no records.")

        timestamp = self._utc_timestamp()
        return [
            {**record, "source": record.get("source", self.source), "timestamp": record.get("timestamp", timestamp), "is_fresh": True}
            for record in records
            if isinstance(record, dict)
        ]

    def _utc_timestamp(self):
        timestamp = self._clock()
        return timestamp.astimezone(timezone.utc) if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)