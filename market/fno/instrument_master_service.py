from market.fno.instrument_master import AngelOneInstrumentMasterAdapter
from market.fno.universe import FNOUniverse
from market.providers.angel_one_instrument_master import AngelOneInstrumentMasterClient


class AngelOneFNOUniverseService:
    """Fetches raw master records, then delegates F&O decisions to the normalizer."""

    def __init__(self, client=None, adapter=None):
        self.client = client or AngelOneInstrumentMasterClient()
        self.adapter = adapter or AngelOneInstrumentMasterAdapter()

    def load_universe(self):
        raw_records = self.client.fetch_records()
        instruments = self.adapter.normalize_records(raw_records)
        return FNOUniverse(instruments)