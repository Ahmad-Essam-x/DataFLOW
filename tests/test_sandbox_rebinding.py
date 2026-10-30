"""Round-2 review: rebinding a trusted name (re, datetime, pd, np, df, builtins) must not widen what code can reach."""
import pandas as pd
import pytest

from backend.engine.sandbox import SandboxError, run_pandas_code, validate_code

REBINDING = [
    "re = pd\ndf = re.read_csv('C:/Windows/win.ini', sep='~', header=None, engine='python')",
    "datetime = df\ndatetime.to_csv('leak.txt')",
    "re = pd\nre.read_pickle('x.pkl')",
    "re = pd\nre.read_csv('http://127.0.0.1:1/x')",
    "pd = df\npd.to_csv('x.csv')",
    "np = pd",
    "for re in [pd]:\n    re.read_csv('x.csv')",
    "x = [datetime for datetime in [df]]",
    "f = lambda re: re.read_csv('x')",
    "f = lambda pd: pd.to_csv('x')",
    "f = lambda _x: _x",
    "len = pd\nlen.read_csv('x')",
    "str = df\nstr.to_csv('x')",
    "(re := pd)",
    "df, re = df, pd",
    "[pd, np] = [df, df]",
]

MEMBERS = [
    "re.read_csv('x')",
    "datetime.to_csv('x')",
    "re.__dict__",
    "datetime.sys",
    "re.enum",
    "re.functools",
    "datetime.os",
    "df = pd.read_csv('x.csv')",
]


@pytest.mark.parametrize("code", REBINDING)
def test_reserved_names_cannot_be_rebound(code):
    with pytest.raises(SandboxError):
        validate_code(code)


@pytest.mark.parametrize("code", MEMBERS)
def test_only_listed_members_of_re_and_datetime(code):
    with pytest.raises(SandboxError):
        validate_code(code)


def test_df_may_still_be_reassigned():
    validate_code("df = df.rename(columns={'a': 'b'})\ndf = df[['b']]")


def test_ordinary_loop_and_lambda_variables_are_fine():
    validate_code("for c in list(df.columns):\n    df[c] = df[c].astype(str)")
    validate_code("df['x'] = df['a'].apply(lambda v: v * 2)")
    validate_code("df['y'] = [n for n in df['a']]")


def test_nothing_is_written_or_read_when_rebinding_is_attempted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({"a": [1]})
    out, err = run_pandas_code(frame, "datetime = df\ndatetime.to_csv('leak.txt')")
    assert err and out is frame
    assert list(tmp_path.iterdir()) == []


def test_allowed_re_and_datetime_members_still_work():
    validate_code("df['x'] = df['a'].astype(str).apply(lambda s: re.sub(r'[^0-9]', '', s))")
    validate_code("df['d'] = datetime.datetime(2024, 1, 1)")
    validate_code("p = re.compile('[a-z]+')\ndf['m'] = df['a'].astype(str).apply(lambda s: bool(p.match(s)))")
