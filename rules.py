import re
import pandas as pd
import streamlit as st


# =========================================
# 列名定義
# =========================================

COL_ITEM_NAME = "補正項目名"
COL_ATTR = "属性"
COL_LENGTH = "Length"
COL_SCREEN = "画面表示項目"
COL_REQUIRED = "必須チェック"


# =========================================
# 共通関数
# =========================================

def normalize_mark(val) -> bool:
    """〇/○/O/1/True系をTrue扱いにする"""
    if pd.isna(val):
        return False

    s = str(val).strip()
    return s in {"〇", "○", "O", "o", "1", "True", "TRUE", "true", "Y", "y", "有"}


def normalize_attr(val: str) -> str:
    """属性を正規化する"""
    if pd.isna(val):
        return ""

    s = str(val).strip()
    s = s.replace("　", "").replace(" ", "")
    return s


def parse_length_for_text(length_val):
    """文字列用Length解析"""
    if pd.isna(length_val):
        return None

    s = str(length_val).strip()
    s = s.replace(" ", "").replace("　", "")

    if s == "":
        return None

    if re.fullmatch(r"\d+", s):
        return int(s)

    return None


def parse_length_for_number(length_val):
    """
    数字用Length解析
    例:
      21,4 -> (21, 4)
      21   -> (21, 0)
    """
    if pd.isna(length_val):
        return None

    s = str(length_val).strip()
    s = s.replace(" ", "").replace("　", "")

    if s == "":
        return None

    m = re.fullmatch(r"(\d+),(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.fullmatch(r"(\d+)", s)
    if m:
        return int(m.group(1)), 0

    return None


def is_text_attr(attr: str) -> bool:
    """文字列属性判定"""
    attr = normalize_attr(attr)
    return attr in {"文字列", "文字"}


def is_number_attr(attr: str) -> bool:
    """数字属性判定"""
    attr = normalize_attr(attr)
    return attr in {"数字", "数値", "整数", "小数"}


def py_escape(s: str) -> str:
    """Python文字列エスケープ"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def validate_required_columns(df: pd.DataFrame):
    """必要列チェック"""
    required_cols = [COL_ITEM_NAME, COL_ATTR, COL_LENGTH, COL_SCREEN, COL_REQUIRED]
    missing = [c for c in required_cols if c not in df.columns]
    return missing


def build_rule_dict(row: pd.Series):
    """
    1行からrule dictとtodo文言を生成する
    """
    rule = {}
    todo_messages = []

    attr = normalize_attr(row.get(COL_ATTR, ""))
    length_val = row.get(COL_LENGTH, None)
    is_required = normalize_mark(row.get(COL_REQUIRED, None))

    # 必須
    if is_required:
        rule["is_required"] = True

    # 文字列
    if is_text_attr(attr):
        max_len = parse_length_for_text(length_val)
        if max_len is not None:
            rule["max_len"] = max_len
        else:
            todo_messages.append("length未定義")

    # 数字
    elif is_number_attr(attr):
        rule["type"] = "number"

        parsed = parse_length_for_number(length_val)
        if parsed is not None:
            p, s = parsed
            rule["common_check"] = f"number_{p}_{s}"
        else:
            todo_messages.append("precision/scale未定義")

    # 不明属性
    else:
        todo_messages.append(f"属性未判定:{attr if attr else '空'}")

    return rule, todo_messages


def df_to_validation_code(sheet_name: str, df: pd.DataFrame):
    """
    DataFrame -> validation_rules.py文字列
    """
    missing = validate_required_columns(df)
    if missing:
        raise ValueError(f"Sheet [{sheet_name}] に必要な列がありません: {missing}")

    # 項目名が空の行は除外
    work_df = df.copy()
    work_df[COL_ITEM_NAME] = work_df[COL_ITEM_NAME].fillna("").astype(str).str.strip()
    work_df = work_df[work_df[COL_ITEM_NAME] != ""].reset_index(drop=True)

    # config（画面表示項目のみ）
    config_items = []
    for _, row in work_df.iterrows():
        if normalize_mark(row.get(COL_SCREEN, None)):
            config_items.append(str(row[COL_ITEM_NAME]).strip())

    # validation_rule（全科目）
    rule_lines = []
    todo_list = []

    for idx, row in work_df.iterrows():
        item_name = str(row[COL_ITEM_NAME]).strip()
        rule, todos = build_rule_dict(row)

        if todos:
            todo_list.append({
                "index": idx,
                "item_name": item_name,
                "todo": " / ".join(todos)
            })

        parts = []

        if "is_required" in rule:
            parts.append('"is_required": True')
        if "max_len" in rule:
            parts.append(f'"max_len": {rule["max_len"]}')
        if "common_check" in rule:
            parts.append(f'"common_check": "{rule["common_check"]}"')
        if "type" in rule:
            parts.append(f'"type": "{rule["type"]}"')

        body = ", ".join(parts)
        comment = f"# {item_name}"
        if todos:
            comment += f"  ← TODO: {' / '.join(todos)}"

        rule_lines.append(f'            {idx}: {{{body}}},  {comment}')

    # config部分
    config_lines = []
    for item in config_items:
        config_lines.append(f'            "{py_escape(item)}",')

    code_lines = []
    code_lines.append("validation_rules = {")
    code_lines.append(f'    "{py_escape(sheet_name)}": {{')
    code_lines.append('        "config": [')

    if config_lines:
        code_lines.extend(config_lines)

    code_lines.append("        ],")
    code_lines.append('        "validation_rule": {')

    if rule_lines:
        code_lines.extend(rule_lines)

    code_lines.append("        }")
    code_lines.append("    }")
    code_lines.append("}")

    code_text = "\n".join(code_lines)

    todo_df = pd.DataFrame(todo_list)
    return code_text, work_df, todo_df


# =========================================
# Streamlit UI
# =========================================

st.set_page_config(page_title="Excel→validation_rules 生成ツール", layout="wide")
st.title("Excel → validation_rules.py 生成ツール")

uploaded_file = st.file_uploader(
    "Excelファイルをアップロード",
    type=["xlsx", "xlsm", "xls"]
)

if uploaded_file is not None:
    try:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names

        st.subheader("Sheet一覧")
        st.write(sheet_names)

        sheet_name = st.selectbox("Sheetを選択", sheet_names)

        preview_df = pd.read_excel(uploaded_file, sheet_name=sheet_name)

        st.subheader("Excelプレビュー")
        st.dataframe(preview_df, use_container_width=True)

        if st.button("コード生成", type="primary"):
            df = pd.read_excel(uploaded_file, sheet_name=sheet_name)

            code_text, work_df, todo_df = df_to_validation_code(sheet_name, df)

            st.subheader("生成コード")
            st.code(code_text, language="python")

            st.download_button(
                label="validation_rules.py ダウンロード",
                data=code_text.encode("utf-8"),
                file_name=f"validation_rules_{sheet_name}.py",
                mime="text/plain"
            )

            st.subheader("対象科目一覧（全科目）")
            show_cols = [COL_ITEM_NAME, COL_ATTR, COL_LENGTH, COL_SCREEN, COL_REQUIRED]
            st.dataframe(work_df[show_cols], use_container_width=True)

            st.subheader("TODO一覧")
            if todo_df.empty:
                st.success("TODOなし")
            else:
                st.warning(f"TODOあり: {len(todo_df)}件")
                st.dataframe(todo_df, use_container_width=True)

    except Exception as e:
        st.error(f"処理中にエラーが発生しました: {e}")
