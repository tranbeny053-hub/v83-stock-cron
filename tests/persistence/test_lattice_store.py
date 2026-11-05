from crypto_probability_engine.persistence.lattice_store import LatticeStore


class Cursor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return (self.result,)


class Connection:
    def __init__(self, result):
        self.cursor_obj = Cursor(result)
        self.transactions = 0

    def __enter__(self):
        self.transactions += 1
        return self

    def __exit__(self, *_):
        pass

    def cursor(self):
        return self.cursor_obj


def test_parameterized_one_transaction_per_operation() -> None:
    connection = Connection("INSERTED")
    store = LatticeStore(lambda: connection)
    assert store.record_row({"key": "value"}) == "INSERTED"
    assert connection.transactions == 1
    sql, params = connection.cursor_obj.calls[0]
    assert sql == "SELECT ucpe_lattice.record_lattice_row(%s::jsonb)"
    assert params == ('{"key": "value"}',)


def test_unknown_status_is_refused_without_connection_details() -> None:
    store = LatticeStore(lambda: Connection("SECRET-DSN"))
    try:
        store.record_row({})
    except RuntimeError as exc:
        assert "SECRET-DSN" not in str(exc)
    else:
        raise AssertionError("unknown status accepted")
