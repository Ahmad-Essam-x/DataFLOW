"""Schema Fit sandbox: escape attempts must be rejected, legitimate pandas transformations must still work."""
import os

import numpy as np
import pandas as pd
import pytest

from backend.engine.sandbox import SandboxError, run_pandas_code, validate_code


@pytest.fixture
def df():
    return pd.DataFrame({"cust_id": [1, 2], "cust_name": ["a", "b"], "amount": ["$1,000", "$2,500"]})


# Payloads from the original design review plus the bypasses found by the independent security review.
ESCAPES = [
    "x = ().__class__.__bases__[0].__subclasses__()",
    "df = df.__class__",
    "import os",
    "from os import system",
    "__import__('os').system('echo hi')",
    "getattr(df, 'to_csv')('x.csv')",
    "eval('1+1')",
    "exec('x = 1')",
    "open('x.txt', 'w').write('hi')",
    "pd.read_csv('some.csv')",
    "pd.io.common.os.system('echo hi')",
    "df.to_csv('leak.csv')",
    "df.to_pickle('leak.pkl')",
    "df.query('cust_id > @x')",
    "df.eval('z = cust_id + 1')",
    "np.load('x.npy')",
    "np.save('x.npy', df.values)",
    "np.ctypeslib.load_library('a', '.')",
    "s = 'x'.__class__",
    "df['__class__'] = 1",
    "df = (lambda: __builtins__)()",
    "type(df)",
    "[c for c in ().__class__.__mro__]",
    # --- found by the security review ---
    "m = re.enum.sys.modules['subprocess']\ndf = pd.DataFrame({'x': [str(m.check_output(['cmd', '/c', 'echo', 'RCE']))]})",
    "m = re.functools.sys.modules['os']",
    "df['x'] = '{0.read_csv.__globals__[os].environ}'.format(pd)",
    "df['x'] = f'{pd.read_csv.__globals__}'",
    "np.lib.npyio.DataSource(None).open('C:/Windows/win.ini').read()",
    "np.lib.format.open_memmap('pwn.npy', mode='w+', shape=(2,))",
    "df = df.pipe(lambda d: d.agg('to_csv', 0, 'pwn.csv'))",
    "df = df.apply('to_json', axis=0)",
    "df = df.agg('to_csv')",
    "df.to_numpy().dump('pwn.bin')",
    "np.ma.dump(df, 'pwn.bin')",
    "pd.ExcelWriter('pwn.xlsx')",
    "pd.HDFStore('pwn.h5')",
    "np.f2py.compile('x')",
    "df.style.to_html()",
    "df.plot()",
    "pd.eval('1+1')",
    "x = [d for d in globals()]",
    "class A:\n    pass",
    "def f():\n    pass",
    "with open('x') as f:\n    pass",
    "try:\n    pass\nexcept Exception:\n    pass",
    "while True:\n    pass",
    "assert True",
    "del df",
    "x = lambda *a: a",
    "df.apply(**{'func': 'to_csv'})",
    "x = b'bytes'",
    "df = df.__getitem__('cust_id')",
    "x = df.cust_id.__dict__",
    "(x := 5)",
]


@pytest.mark.parametrize("code", ESCAPES)
def test_escape_attempts_are_rejected_by_static_gate(code):
    with pytest.raises(SandboxError):
        validate_code(code)


@pytest.mark.parametrize("code", ESCAPES[:30])
def test_escape_attempts_do_not_execute(df, code, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out, err = run_pandas_code(df, code)
    assert err
    assert out is df
    assert list(tmp_path.iterdir()) == []  # nothing written


LEGIT = [
    "df = df.rename(columns={'cust_id': 'CustomerID', 'cust_name': 'CustomerName'})",
    "df['Revenue'] = df['amount'].str.replace('$', '', regex=False).str.replace(',', '', regex=False).astype(float)",
    "df['SignupDate'] = pd.to_datetime('2024-01-01')",
    "df['IsActive'] = df['cust_name'].str.lower() == 'a'",
    "df['Missing'] = np.nan",
    "df = df[['cust_id', 'amount']]",
    "df['n'] = pd.to_numeric(df['amount'].astype(str).str.replace(r'[^0-9.-]', '', regex=True), errors='coerce')",
    "df['flag'] = df['cust_name'].astype(str).str.strip().str.lower().isin(['true', '1', 'yes', 't', 'y'])",
    "df['L'] = [len(str(v)) for v in df['cust_name']]",
    "df['u'] = df['cust_name'].str.upper().str.title()",
    "df['d'] = pd.to_datetime(df['cust_id'], errors='coerce').dt.strftime('%Y-%m-%d')",
    "df['y'] = pd.to_datetime('2024-03-05').year + df['cust_id']",
    "df['x'] = df['cust_id'].apply(lambda v: v * 2)",
    "df['c'] = np.where(df['cust_id'] > 1, 'big', 'small')",
    "df['r'] = df['amount'].apply(lambda s: re.sub(r'[^0-9]', '', s))",
    "df['f'] = df['cust_name'].map({'a': 'Alpha', 'b': 'Beta'})",
    "df['full'] = df['cust_name'] + ' #' + df['cust_id'].astype(str)",
    "df['fs'] = [f'{n}-{i}' for n, i in zip(df['cust_name'], df['cust_id'])]",
    "df = df.drop(columns=['amount'])",
    "df = df.fillna(0).reset_index(drop=True)",
    "df['t'] = df['cust_name'].str.split(' ').str[0]",
    "df['ok'] = pd.api.types.is_numeric_dtype(df['cust_id'])",
    "for c in list(df.columns):\n    df[c] = df[c].astype(str)",
    "if 'amount' in df.columns:\n    df['has'] = True",
    "df['dt'] = datetime.datetime(2024, 1, 1)",
    "df = df.sort_values('cust_id', ascending=False)",
    "df['ex'] = df['amount'].str.extract(r'(\\d+)')[0]",
]


@pytest.mark.parametrize("code", LEGIT)
def test_legitimate_transformations_pass_the_gate(code):
    validate_code(code)


@pytest.mark.parametrize("code", LEGIT[:12])
def test_legitimate_transformations_still_run(df, code):
    out, err = run_pandas_code(df, code)
    assert err is None, err
    assert isinstance(out, pd.DataFrame)


def test_result_is_returned_and_input_untouched(df):
    out, err = run_pandas_code(df, "df['x'] = df['cust_id'] * 10")
    assert err is None
    assert list(out["x"]) == [10, 20]
    assert "x" not in df.columns


def test_datatypes_survive_the_round_trip(df):
    out, err = run_pandas_code(df, "df['d'] = pd.to_datetime('2024-01-02')\ndf['f'] = df['cust_id'] / 4")
    assert err is None
    assert str(out["d"].dtype).startswith("datetime64")
    assert out["f"].tolist() == [0.25, 0.5]


def test_infinite_loop_is_killed_by_timeout(df):
    # `while` is rejected statically, so use a comprehension that never finishes in time
    out, err = run_pandas_code(df, "x = [i for i in range(10**12)]", timeout=2)
    assert err and ("time limit" in err or "memory" in err.lower() or "unexpectedly" in err)
    assert out is df


def test_runtime_error_is_reported(df):
    out, err = run_pandas_code(df, "df['x'] = df['does_not_exist'] + 1")
    assert err and "KeyError" in err
    assert out is df


def test_code_must_leave_a_dataframe(df):
    out, err = run_pandas_code(df, "df = 5")
    assert err and "DataFrame" in err


def test_child_environment_is_scrubbed(df, monkeypatch):
    monkeypatch.setenv("DATAFLOW_SECRET_PROBE", "should-not-leak")
    # os is unreachable from generated code; verify the scrub directly at the child entry point
    import backend.engine.sandbox as sb
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        inp, outp = os.path.join(tmp, "i.feather"), os.path.join(tmp, "o.feather")
        df.to_feather(inp)
        saved = dict(os.environ)
        try:
            sb._child_main(inp, outp, "df['x'] = 1", 2 * 1024 ** 3)
            assert "DATAFLOW_SECRET_PROBE" not in os.environ
        finally:
            os.environ.clear()
            os.environ.update(saved)
        assert json.load(open(outp + ".status"))["ok"] is True


def test_no_leftover_temp_files(df, tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    run_pandas_code(df, "df['x'] = 1")
    assert [p for p in os.listdir(tmp_path) if p.startswith("dataflow_sandbox_")] == []
