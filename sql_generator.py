import re
import random
import string
from decimal import Decimal
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st


def extract_table_name(ddl: str) -> str:
    m = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+([^\s(]+)", ddl, re.I)
    return m.group(1) if m else "TARGET_TABLE"


def extract_columns(ddl: str):
    start = ddl.find("(")
    end = ddl.rfind(")")
    block = ddl[start + 1:end]
    cols, buf, level = [], [], 0

    for ch in block:
        if ch == "(":
            level += 1
        elif ch == ")":
            level -= 1

        if ch == "," and level == 0:
            cols.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)

    if buf:
        cols.append("".join(buf).strip())
    return cols


def parse_column(line: str):
    pattern = re.compile(
        r"""
        (?P<col>\w+)\s+
        (?P<type>
            VARCHAR\(\d+\)
            |NUMBER(?:\(\d+(?:,\d+)?\))?
            |TIMESTAMP_NTZ(?:\(\d+\))?
        )
        """,
        re.I | re.X,
    )
    m = pattern.search(line)
    if not m:
        return None

    col = m.group("col")
    dtype = m.group("type").upper()
    length = precision = scale = ts_scale = None

    if dtype.startswith("VARCHAR"):
        length = int(re.findall(r"\d+", dtype)[0])
    elif dtype.startswith("NUMBER"):
        nums = re.findall(r"\d+", dtype)
        if len(nums) >= 1:
            precision = int(nums[0])
        if len(nums) >= 2:
            scale = int(nums[1])
    elif dtype.startswith("TIMESTAMP_NTZ"):
        nums = re.findall(r"\d+", dtype)
        if nums:
            ts_scale = int(nums[0])

    return {
        "column_name": col,
        "data_type": dtype,
        "length": length,
        "precision": precision,
        "scale": scale,
        "ts_scale": ts_scale,
    }


def parse_ddl(ddl: str):
    table = extract_table_name(ddl)
    cols = [c for c in (parse_column(l) for l in extract_columns(ddl)) if c]
    return table, cols


def normalize_name(name: str) -> str:
    return str(name).upper().replace("_", "").replace(" ", "").replace("　", "")


def detect_semantic(name: str) -> str:
    n = normalize_name(name)

    if any(k in n for k in ["年月", "YM"]):
        return "DATE_YM"
    if any(k in n for k in ["日付", "基準日", "対象日", "DATE", "YMD"]):
        return "DATE"
    if any(k in n for k in ["TIMESTAMP", "UPDATETS", "CREATETS"]):
        return "DATE_TIME"

    if any(k in n for k in ["ID", "KEY", "NO", "SEQ", "番号"]):
        return "KEY"
    if any(k in n for k in ["CODE", "CD", "KBN", "区分", "種別", "通貨"]):
        return "CODE"
    if any(k in n for k in ["AMOUNT", "金額", "残高", "額面", "利息"]):
        return "AMOUNT"
    if any(k in n for k in ["RATE", "利率", "パーセント"]):
        return "RATE"
    if any(k in n for k in ["NAME", "名称", "名"]):
        return "NAME"
    return "NORMAL"


def fit_text(s: str, length: int) -> str:
    if length is None:
        return s
    return s[:length].ljust(min(length, max(1, len(s))), "X")


def gen_varchar(col, semantic: str, row_idx: int):
    length = col["length"] or 10
    if semantic == "KEY":
        return fit_text(f"K{row_idx + 1:0>5}", length)
    if semantic == "CODE":
        return fit_text(random.choice(["01", "02", "A1", "JPY", "USD"]), length)
    if semantic == "DATE_YM":
        return fit_text("202604", length)
    if semantic == "DATE":
        return fit_text("20260414", length)
    if semantic == "NAME":
        return fit_text(random.choice(["TOKYO", "OSAKA", "NAGOYA"]), length)
    return fit_text("".join(random.choices(string.ascii_uppercase, k=min(length, 8))), length)


def gen_number(col, semantic: str, row_idx: int):
    p = col["precision"] or 10
    s = col["scale"] or 0
    int_digits = max(1, p - s)
    max_int = min(10 ** min(int_digits, 9) - 1, 999_999_999)

    if semantic == "KEY":
        base = row_idx + 1
        return min(base, max_int)

    if semantic == "CODE":
        return random.choice([1, 2, 3, 9])

    if semantic == "AMOUNT":
        int_val = random.randint(1_000, min(max_int, 9_999_999))
        if s == 0:
            return int_val
        frac = random.randint(0, 10**s - 1 if s <= 6 else 999999)
        return Decimal(f"{int_val}.{str(frac).zfill(s)}")

    if semantic == "RATE":
        if s == 0:
            return random.randint(1, min(max_int, 100))
        frac = random.randint(0, 10**s - 1 if s <= 6 else 999999)
        return Decimal(f"{random.randint(0, 99)}.{str(frac).zfill(s)}")

    val = random.randint(1, max_int)
    if s == 0:
        return val
    frac = random.randint(0, 10**s - 1 if s <= 6 else 999999)
    return Decimal(f"{val}.{str(frac).zfill(s)}")


def gen_timestamp(col, semantic: str):
    base = datetime(2026, 4, 1, 9, 0, 0)
    if semantic in {"DATE", "DATE_YM"}:
        dt = datetime(2026, 4, 14, 0, 0, 0)
    else:
        dt = base + timedelta(minutes=random.randint(0, 20_000))

    scale = col["ts_scale"] or 0
    if scale <= 0:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    micro = str(dt.microsecond).zfill(6)[:scale]
    return dt.strftime("%Y-%m-%d %H:%M:%S") + "." + micro


def gen_value(col, row_idx: int):
    semantic = detect_semantic(col["column_name"])
    dtype = col["data_type"]
    if dtype.startswith("VARCHAR"):
        return gen_varchar(col, semantic, row_idx)
    if dtype.startswith("NUMBER"):
        return gen_number(col, semantic, row_idx)
    if dtype.startswith("TIMESTAMP_NTZ"):
        return gen_timestamp(col, semantic)
    return None


def gen_rows(cols, n: int):
    return pd.DataFrame([{c["column_name"]: gen_value(c, i) for c in cols} for i in range(n)])


def to_sql(v):
    if isinstance(v, str):
        return f"'{v}'"
    return str(v)


def build_sql(table, cols, df):
    col_names = [c["column_name"] for c in cols]
    values = []
    for _, r in df.iterrows():
        vals = [to_sql(r[c]) for c in col_names]
        values.append("(" + ", ".join(vals) + ")")
    values_sql = ",\n".join(values)
    return f"""INSERT INTO {table} (
    {", ".join(col_names)}
)
VALUES
{values_sql};"""


def build_field_value_text(df: pd.DataFrame, cols):
    col_names = [c["column_name"] for c in cols]
    blocks = []
    for i, row in df.iterrows():
        lines = [f"{c}: {row[c]}" for c in col_names]
        blocks.append(f"[ROW {i+1}]\n" + "\n".join(lines))
    return "\n\n".join(blocks)


st.title("DDL 実務寄りテストデータ生成（正常データのみ）")
ddl = st.text_area("DDL", height=220)
row_count = st.number_input("生成件数（1〜10）", min_value=1, max_value=10, value=5, step=1)

if st.button("正常データ生成", type="primary"):
    table, cols = parse_ddl(ddl)
    if not cols:
        st.error("DDL解析失敗")
        st.stop()

    df = gen_rows(cols, int(row_count))
    st.subheader("生成結果")
    st.dataframe(df, use_container_width=True)

    sql = build_sql(table, cols, df)
    st.subheader("INSERT SQL")
    st.code(sql, language="sql")

    field_value_text = build_field_value_text(df, cols)
    st.subheader("科目: 値（コピー用）")
    st.text_area("コピーして使う", field_value_text, height=260)
