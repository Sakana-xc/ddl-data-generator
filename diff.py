import pandas as pd
import streamlit as st


# =========================================
# 共通
# =========================================

def normalize(val):
    """统一处理空值"""
    if pd.isna(val):
        return ""
    return str(val).strip()


def compare_sheets_position(before_df, after_df, sheet_name):
    """
    按位置比较（方案B：一行合并）
    B列作为補正項目名
    """
    diffs = []

    # 列名
    cols = list(before_df.columns)

    max_rows = max(len(before_df), len(after_df))
    max_cols = max(len(cols), len(after_df.columns))

    for i in range(max_rows):
        row_diffs = []

        for j in range(max_cols):
            before_val = ""
            after_val = ""

            if i < len(before_df) and j < len(before_df.columns):
                before_val = normalize(before_df.iat[i, j])

            if i < len(after_df) and j < len(after_df.columns):
                after_val = normalize(after_df.iat[i, j])

            if before_val != after_val:
                col_name = cols[j] if j < len(cols) else f"COL_{j}"
                row_diffs.append(f"{col_name}:{before_val}→{after_val}")

        if row_diffs:
            # B列 = index 1
            item_name = ""
            if i < len(before_df) and len(before_df.columns) > 1:
                item_name = normalize(before_df.iat[i, 1])

            diffs.append({
                "Sheet名": sheet_name,
                "行号": i + 2,  # Excel实际行号（+2，因为header+0index）
                "補正項目名": item_name,
                "差分内容": " / ".join(row_diffs)
            })

    return pd.DataFrame(diffs)


def compare_all_sheets(before_file, after_file):
    before_xls = pd.ExcelFile(before_file)
    after_xls = pd.ExcelFile(after_file)

    common_sheets = list(set(before_xls.sheet_names) & set(after_xls.sheet_names))

    all_diffs = []

    for sheet in common_sheets:
        before_df = pd.read_excel(before_file, sheet_name=sheet)
        after_df = pd.read_excel(after_file, sheet_name=sheet)

        diff_df = compare_sheets_position(before_df, after_df, sheet)

        if not diff_df.empty:
            all_diffs.append(diff_df)

    if all_diffs:
        return pd.concat(all_diffs, ignore_index=True)
    else:
        return pd.DataFrame(columns=["Sheet名", "行号", "補正項目名", "差分内容"])


# =========================================
# UI
# =========================================

st.set_page_config(page_title="Excel差分（按位置）", layout="wide")
st.title("Excel 差分比較（按位置・行合并）")

before_file = st.file_uploader("before Excel", type=["xlsx", "xlsm"])
after_file = st.file_uploader("after Excel", type=["xlsx", "xlsm"])

if before_file and after_file:

    if st.button("差分生成", type="primary"):

        diff_df = compare_all_sheets(before_file, after_file)

        st.subheader("差分一览")

        if diff_df.empty:
            st.success("差分なし")
        else:
            st.dataframe(diff_df, use_container_width=True)

            # 下载
            st.download_button(
                "CSV下载",
                diff_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="diff_result.csv",
                mime="text/csv"
            )

            # 可复制文本（TSV）
            st.subheader("复制用（直接贴Excel）")
            tsv_text = diff_df.to_csv(index=False, sep="\t")
            st.text_area("复制这里", tsv_text, height=300)