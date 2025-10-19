import os
import json
import re
import streamlit as st
import pandas as pd

# --- OpenAI SDK ---
try:
    from openai import OpenAI
except Exception as e:
    OpenAI = None

st.set_page_config(page_title="C Test Pattern Agent (LLM)", page_icon="🧪", layout="wide")
st.title("🧪 C Test Pattern Agent（LLM版 / 最小）")

# ============ LLM 呼び出しユーティリティ ============
def call_llm_for_tests(code: str, coverage: str = "C1", model: str = "gpt-4o-mini") -> list[dict]:
    """
    LLMにCコードからテストパターン(JSON)を生成させる。
    期待出力: [{"inputs": {"x": 1, "y": 0}, "expected": 1, "reason": "..."}, ...]
    """
    if OpenAI is None:
        raise RuntimeError("openai パッケージが見つかりません。'uv pip install openai' を実行してください。")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY が未設定です。環境変数を設定してください。")

    client = OpenAI(api_key=api_key)

    system = (
        "あなたは組み込みソフトウェアのテスト設計の専門家です。"
        "与えられたC関数の入出力仕様をコードから読み取り、指定カバレッジに適した最小限のテストケースを設計します。"
        "出力は**厳密なJSON**のみで返し、Markdownや説明文は出力しないでください。"
        "JSONは配列で、各要素は {\"inputs\": <引数名→値の辞書>, \"expected\": <整数または数値>, \"reason\": <日本語の短い説明>} の形にします。"
        "unknownな期待値は推論して良いが自信が低い場合はexpectedをnullにし、その理由をreasonに明記してください。"
        "安全第一で境界・充足/否充足が分かる値を選びます。"
    )

    user = f"""
【カバレッジ】{coverage}
【タスク】
- 次のC関数について、{coverage} カバレッジを満たす最小のテストセットをJSONで返してください。
- 関数シグネチャから引数名を正しく抽出してください。
- expected（期待結果）は可能な限り推定してください。難しい場合は null でも構いません（理由は reason に明記）。
- JSON以外の文字を一切含めないでください（コードブロックや先頭の説明文も禁止）。

【Cコード】
{code}

【出力フォーマット（例）】
[
  {{"inputs": {{"x": 1, "y": 0}}, "expected": 1, "reason": "両条件成立"}},
  {{"inputs": {{"x": -1, "y": 0}}, "expected": -1, "reason": "x<0 分岐"}},
  {{"inputs": {{"x": 0, "y": 1}}, "expected": 0, "reason": "else 分岐"}}
]
    """.strip()

    resp = client.chat.completions.create(
        model=model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    content = resp.choices[0].message.content.strip()

    # ```json ... ``` の囲いを剥がす保険
    content = re.sub(r"^```json\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE|re.DOTALL)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        # JSONでない場合は簡易修復の試み（最終手段）
        content2 = re.sub(r"^[^{\[]*", "", content, flags=re.DOTALL)  # 先頭の余白/説明を落とす
        content2 = re.sub(r"[^}\]]*$", "", content2, flags=re.DOTALL) # 末尾の余白/説明を落とす
        data = json.loads(content2)

    if not isinstance(data, list):
        raise ValueError("LLMから配列(JSON)が返りませんでした。")

    # 軽いバリデーション
    normalized = []
    for item in data:
        if not isinstance(item, dict):
            continue
        inputs = item.get("inputs", {})
        expected = item.get("expected", None)
        reason = item.get("reason", "")
        if not isinstance(inputs, dict):
            continue
        normalized.append({"inputs": inputs, "expected": expected, "reason": reason})
    return normalized

def tests_to_dataframe(func_name: str, tests: list[dict]) -> pd.DataFrame:
    # 列を安定化（inputs のキーを全て集約）
    all_keys = set()
    for t in tests:
        all_keys.update(t.get("inputs", {}).keys())
    ordered_cols = sorted(all_keys)

    rows = []
    for t in tests:
        row = {k: t.get("inputs", {}).get(k, "") for k in ordered_cols}
        row["expected"] = t.get("expected", "")
        row["reason"] = t.get("reason", "")
        rows.append(row)

    df = pd.DataFrame(rows, columns=ordered_cols + ["expected", "reason"])
    df.insert(0, "function", func_name)
    return df

# ============ UI ============
left, right = st.columns([1, 1.4], gap="large")

with left:
    st.subheader("入力")
    code = st.text_area(
        "C関数を貼り付けてください（複数関数でも可。LLMが識別します）",
        height=260,
        placeholder="例:\nint foo(int x, int y){ if(x>0 && y==0) return 1; else if(x<0) return -1; else return 0; }"
    )
    coverage = st.radio("カバレッジ", ["C0", "C1"], index=1, horizontal=True)
    model = st.selectbox("モデル", ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"], index=0)
    go = st.button("LLMでテスト作成", type="primary")

with right:
    st.subheader("テストケース（LLM生成）")
    if go:
        if not code.strip():
            st.info("Cコードを貼り付けてください。")
        else:
            try:
                tests = call_llm_for_tests(code, coverage=coverage, model=model)
                if not tests:
                    st.warning("テストが返りませんでした。プロンプトやコードを見直してください。")
                else:
                    # 関数名はLLMに依存せず、便宜上 'auto' 表示（ハイブリッド化時にASTから埋められます）
                    df = tests_to_dataframe(func_name="auto", tests=tests)
                    st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"LLM呼び出しでエラー: {e}")
                st.caption("OPENAI_API_KEY、ネットワーク、モデル名などをご確認ください。")
