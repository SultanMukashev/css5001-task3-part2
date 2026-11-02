"""The three provided Sink subclasses that break the contract (kept for the tests)."""
from d2_2_sources_sinks.solution import Sink


class BatchSink(Sink):
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size
        self.stored: list[dict] = []

    def write(self, records):
        records = list(records)
        if len(records) < self.batch_size:
            raise ValueError(f"need at least {self.batch_size} records")
        self.stored.extend(records)
        return len(records)


class DryRunSink(Sink):
    def write(self, records):
        for r in records:
            print("would write", r)
        return None


class WarehouseSink(Sink):
    def __init__(self):
        self.staged: list[dict] = []

    def write(self, records):
        before = len(self.staged)
        self.staged.extend(records)
        return len(self.staged) - before

    def flush(self):
        raise NotImplementedError("warehouse flush not supported")
