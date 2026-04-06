import pandas as pd
import streamlit as st


# =========================================
# 共通
# =========================================

IGNORE_COLS = {"項目説明"}
SPECIAL_KEYWORDS = {"更新対象項目"}


def normalize(val):
    """空值统一处理"""
    if pd.isna(val):
        return ""
    return str(val).strip()


def is_special_diff(col_name: str) -> bool:
    """是否属于要单独输出的特殊差分"""
    for kw in SPECIAL_KEYWORDS:
        if kw in str(col_name):
            return True
    return False


def compare_sheets_position(before_df, after_df, sheet_name):
    """
    按位置比较
    - B列作为補正項目名
    - 項目説明不比较
    - 特殊差分单独输出
    - 普通差分一格一行
    """
    normal_diffs = []
    special_diffs = []

    before_cols = list(before_df.columns)
    after_cols = list(after_df.columns)

    max_rows = max(len(before_df), len(after_df))
    max_cols = max(len(before_cols), len(after_cols))

    for i in range(max_rows):
        # B列 = index 1
        item_name = ""
        if i < len(before_df) and len(before_df.columns) > 1:
            item_name = normalize(before_df.iat[i, 1])
        elif i < len(after_df) and len(after_df.columns) > 1:
            item_name = normalize(after_df.iat[i, 1])

        for j in range(max_cols):
            col_name = before_cols[j] if j < len(before_cols) else (
                after_cols[j] if j < len(after_cols) else f"COL_{j+1}"
            )

            if col_name in IGNORE_COLS:
                continue

            before_val = ""
            after_val = ""

            if i < len(before_df) and j < len(before_df.columns):
                before_val = normalize(before_df.iat[i, j])

            if i < len(after_df) and j < len(after_df.columns):
                after_val = normalize(after_df.iat[i, j])

            if before_val == after_val:
                continue

            row_data = {
                "Sheet名": sheet_name,
                "行号": i + 2,   # Excel实际行号
                "補正項目名": item_name,
                "列名": col_name,
                "変更前": before_val,
                "変更後": after_val,
            }

            if is_special_diff(col_name):
                row_data["差分内容"] = f"{col_name}: {before_val}→{after_val}"
                special_diffs.append(row_data)
            else:
                normal_diffs.append(row_data)

    normal_df = pd.DataFrame(
        normal_diffs,
        columns=["Sheet名", "行号", "補正項目名", "列名", "変更前", "変更後"]
    )

    special_df = pd.DataFrame(
        special_diffs,
        columns=["Sheet名", "行号", "補正項目名", "列名", "変更前", "変更後", "差分内容"]
    )

    return normal_df, special_df


def compare_all_sheets(before_file, after_file):
    """全共通sheet比较"""
    before_xls = pd.ExcelFile(before_file)
    after_xls = pd.ExcelFile(after_file)

    common_sheets = sorted(list(set(before_xls.sheet_names) & set(after_xls.sheet_names)))

    all_normal = []
    all_special = []

    for sheet in common_sheets:
        before_df = pd.read_excel(before_file, sheet_name=sheet)
        after_df = pd.read_excel(after_file, sheet_name=sheet)

        normal_df, special_df = compare_sheets_position(before_df, after_df, sheet)

        if not normal_df.empty:
            all_normal.append(normal_df)

        if not special_df.empty:
            all_special.append(special_df)

    final_normal = pd.concat(all_normal, ignore_index=True) if all_normal else pd.DataFrame(
        columns=["Sheet名", "行号", "補正項目名", "列名", "変更前", "変更後"]
    )

    final_special = pd.concat(all_special, ignore_index=True) if all_special else pd.DataFrame(
        columns=["Sheet名", "行号", "補正項目名", "列名", "変更前", "変更後", "差分内容"]
    )

    return final_normal, final_special


# =========================================
# UI
# =========================================

st.set_page_config(page_title="Excel差分比較", layout="wide")
st.title("Excel 差分比較（按位置）")

before_file = st.file_uploader("before Excel", type=["xlsx", "xlsm"], key="before")
after_file = st.file_uploader("after Excel", type=["xlsx", "xlsm"], key="after")

if before_file and after_file:
    if st.button("差分生成", type="primary"):
        normal_df, special_df = compare_all_sheets(before_file, after_file)

        st.subheader("通常差分")
        if normal_df.empty:
            st.success("通常差分なし")
        else:
            st.dataframe(normal_df, use_container_width=True)

            st.download_button(
                "通常差分 CSV下载",
                normal_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="normal_diff.csv",
                mime="text/csv"
            )

            st.subheader("通常差分（复制用）")
            normal_tsv = normal_df.to_csv(index=False, sep="\t")
            st.text_area("复制这里（通常差分）", normal_tsv, height=250)

        st.subheader("更新対象項目差分（单独）")
        if special_df.empty:
            st.success("更新対象項目差分なし")
        else:
            st.dataframe(special_df, use_container_width=True)

            st.download_button(
                "更新対象項目差分 CSV下载",
                special_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="special_diff.csv",
                mime="text/csv"
            )

            st.subheader("更新対象項目差分（复制用）")
            special_tsv = special_df.to_csv(index=False, sep="\t")
            st.text_area("复制这里（更新対象項目差分）", special_tsv, height=250)