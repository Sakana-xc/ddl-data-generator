import re
import random
import string
from decimal import Decimal
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st


# =========================================
# DDL解析
# =========================================

def extract_table_name(ddl: str) -> str:
    """テーブル名取得"""
    m = re.search(r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+([^\s(]+)", ddl, re.I)
    return m.group(1) if m else "TARGET_TABLE"


def extract_columns(ddl: str):
    """カラム定義抽出"""
    start = ddl.find("(")
    end = ddl.rfind(")")
    block = ddl[start + 1:end]

    cols = []
    level = 0
    buf = []

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
    """カラム解析（簡易版）"""
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

    length = None
    precision = None
    scale = None
    ts_scale = None

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
    lines = extract_columns(ddl)

    cols = []
    for l in lines:
        c = parse_column(l)
        if c:
            cols.append(c)

    return table, cols


# =========================================
# 列名ルール
# =========================================

def detect_type(name: str):
    n = name.upper()

    if "YM" in n:
        return "YM"
    if "ID" in n or "NO" in n:
        return "ID"
    if "NAME" in n:
        return "NAME"
    if "CODE" in n:
        return "CODE"
    if "KBN" in n or "STATUS" in n:
        return "KBN"
    if "AMOUNT" in n:
        return "AMOUNT"
    return "NORMAL"


# =========================================
# 生成ロジック
# =========================================

def gen_varchar(col, mode, semantic):
    length = col["length"] or 10

    if semantic == "NAME":
        return random.choice(["TARO", "HANAKO", "SATO"])[:length]

    if semantic == "CODE":
        return f"A{random.randint(1,9999):04d}"[:length]

    if mode == "min":
        return "A"
    if mode == "max":
        return "Z" * length

    return "".join(random.choices(string.ascii_uppercase, k=min(length, 10)))


def gen_number(col, mode, semantic):
    p = col["precision"] or 10
    s = col["scale"] or 0

    if semantic == "YM":
        return random.randint(200001, 203012)

    if semantic == "ID":
        return random.randint(1, 999999)

    if semantic == "KBN":
        return random.choice([0, 1, 9])

    max_int = int("9" * (p - s))

    if mode == "min":
        return -max_int
    if mode == "max":
        return max_int

    val = random.randint(0, max_int)

    if s == 0:
        return val

    frac = random.randint(0, int("9" * s))
    return Decimal(f"{val}.{str(frac).zfill(s)}")


def gen_timestamp(col, mode):
    scale = col["ts_scale"]

    if mode == "min":
        dt = datetime(1900, 1, 1)
    elif mode == "max":
        dt = datetime(2099, 12, 31, 23, 59, 59, 999999)
    else:
        dt = datetime(2000, 1, 1) + timedelta(seconds=random.randint(0, 1_000_000_000))

    if not scale:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    micro = str(dt.microsecond).zfill(6)[:scale]
    return dt.strftime("%Y-%m-%d %H:%M:%S") + "." + micro


def gen_value(col, mode):
    semantic = detect_type(col["column_name"])
    dtype = col["data_type"]

    if dtype.startswith("VARCHAR"):
        return gen_varchar(col, mode, semantic)

    if dtype.startswith("NUMBER"):
        return gen_number(col, mode, semantic)

    if dtype.startswith("TIMESTAMP_NTZ"):
        return gen_timestamp(col, mode)


def gen_rows(cols, n):
    rows = []

    rows.append({"_pattern": "MIN", **{c["column_name"]: gen_value(c, "min") for c in cols}})
    rows.append({"_pattern": "MAX", **{c["column_name"]: gen_value(c, "max") for c in cols}})

    for i in range(n):
        rows.append({
            "_pattern": f"RANDOM_{i+1}",
            **{c["column_name"]: gen_value(c, "random") for c in cols}
        })

    return pd.DataFrame(rows)


# =========================================
# SQL生成
# =========================================

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

    return f"""INSERT INTO {table} (
    {", ".join(col_names)}
)
VALUES
{",\n".join(values)};"""


# =========================================
# UI
# =========================================

st.title("DDL テストデータ生成（簡易版）")

ddl = st.text_area("DDL", height=200)

n = st.number_input("ランダム件数", 1, 100, 5)

if st.button("生成"):
    table, cols = parse_ddl(ddl)

    df = gen_rows(cols, n)

    st.dataframe(df)

    sql = build_sql(table, cols, df.drop(columns=["_pattern"]))

    st.code(sql, language="sql")