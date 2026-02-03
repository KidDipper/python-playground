from __future__ import annotations

import io
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from wordcloud import STOPWORDS, WordCloud

try:
    from janome.tokenizer import Tokenizer
except Exception:  # pragma: no cover - handled by dependency setup
    Tokenizer = None


JAPANESE_STOPWORDS = {
    "これ",
    "それ",
    "あれ",
    "この",
    "その",
    "あの",
    "ため",
    "よう",
    "こと",
    "もの",
    "ところ",
    "とき",
    "さん",
    "する",
    "いる",
    "なる",
    "ある",
    "ます",
    "です",
    "できる",
}

DEFAULT_SAMPLE = """昨日の定例会議では、新規プロジェクトの進め方を議論しました。
特に、要件定義の精度とレビューのタイミングが重要だという意見が多かったです。
オンライン会議のコメントでは、スケジュール調整とリスク管理に関する発言が目立ちました。"""

LANG_AUTO = "Auto"
LANG_JA = "Japanese"
LANG_EN = "English"


def contains_japanese(text: str) -> bool:
    return bool(re.search(r"[ぁ-んァ-ン一-龥]", text))


def tokenize_english(
    text: str,
    min_len: int,
    include_numbers: bool,
    stopwords: set[str],
) -> list[str]:
    if include_numbers:
        pattern = r"[A-Za-z0-9][A-Za-z0-9'\-]*"
    else:
        pattern = r"[A-Za-z][A-Za-z'\-]*"
    words = re.findall(pattern, text.lower())
    return [word for word in words if len(word) >= min_len and word not in stopwords]


def tokenize_japanese(
    text: str,
    min_len: int,
    include_pos: set[str],
    stopwords: set[str],
) -> list[str]:
    if Tokenizer is None:
        return []
    tokenizer = Tokenizer()
    tokens: list[str] = []
    for token in tokenizer.tokenize(text):
        pos = token.part_of_speech.split(",")[0]
        base = token.base_form
        if base == "*":
            base = token.surface
        if pos not in include_pos:
            continue
        if len(base) < min_len:
            continue
        if base in stopwords:
            continue
        tokens.append(base)
    return tokens


def find_font_path(uploaded_font: bytes | None, filename: str | None) -> str | None:
    if uploaded_font and filename:
        suffix = Path(filename).suffix or ".ttf"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_font)
            return tmp.name

    candidate_paths = [
        "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            return path
    return None


def build_wordcloud(
    frequencies: dict[str, int],
    width: int,
    height: int,
    background_color: str,
    colormap: str,
    font_path: str | None,
) -> WordCloud:
    return WordCloud(
        width=width,
        height=height,
        background_color=background_color,
        colormap=colormap,
        font_path=font_path,
        stopwords=None,
    ).generate_from_frequencies(frequencies)


def main() -> None:
    st.set_page_config(
        page_title="AI Text Mining Word Cloud",
        page_icon="🧠",
        layout="wide",
    )

    st.title("AI Text Mining Word Cloud")
    st.write(
        "議事録やオンライン会議コメントを入力すると、頻出キーワードをワードクラウドで可視化します。"
    )

    with st.sidebar:
        st.header("Settings")
        language = st.selectbox("Language", [LANG_AUTO, LANG_JA, LANG_EN], index=0)
        min_len = st.slider("Minimum Word Length", 1, 6, 2)
        max_words = st.slider("Max Words", 20, 200, 80)
        include_numbers = st.checkbox("Include Numbers (English)", value=False)
        include_pos = st.multiselect(
            "Japanese POS",
            ["名詞", "形容詞", "動詞"],
            default=["名詞", "形容詞"],
        )
        background = st.selectbox("Background", ["white", "black"])
        colormap = st.selectbox(
            "Colormap",
            ["viridis", "plasma", "inferno", "magma", "cividis", "Set2", "tab20"],
        )
        uploaded_font = st.file_uploader("Font File (optional)", type=["ttf", "otf", "ttc"])

    text = st.text_area("Input Text", height=240, value=DEFAULT_SAMPLE)

    if st.button("Analyze", type="primary"):
        if not text.strip():
            st.error("テキストを入力してください。")
            return

        if language == LANG_AUTO:
            resolved_language = LANG_JA if contains_japanese(text) else LANG_EN
        else:
            resolved_language = language

        font_path = find_font_path(
            uploaded_font.getvalue() if uploaded_font else None,
            uploaded_font.name if uploaded_font else None,
        )

        if resolved_language == LANG_JA:
            if Tokenizer is None:
                st.error("日本語解析には janome が必要です。依存関係を確認してください。")
                return
            tokens = tokenize_japanese(
                text,
                min_len=min_len,
                include_pos=set(include_pos),
                stopwords=JAPANESE_STOPWORDS,
            )
        else:
            tokens = tokenize_english(
                text,
                min_len=min_len,
                include_numbers=include_numbers,
                stopwords=set(word.lower() for word in STOPWORDS),
            )

        if not tokens:
            st.warning("抽出された単語がありませんでした。設定を見直してください。")
            return

        counts = Counter(tokens)
        top_counts = counts.most_common(max_words)
        frequencies = dict(top_counts)

        wordcloud = build_wordcloud(
            frequencies=frequencies,
            width=1000,
            height=500,
            background_color=background,
            colormap=colormap,
            font_path=font_path,
        )

        col1, col2 = st.columns([2, 1], gap="large")
        with col1:
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.imshow(wordcloud, interpolation="bilinear")
            ax.axis("off")
            st.pyplot(fig, use_container_width=True)

            buffer = io.BytesIO()
            fig.savefig(buffer, format="png", bbox_inches="tight", dpi=150)
            st.download_button(
                "Download Word Cloud (PNG)",
                data=buffer.getvalue(),
                file_name="wordcloud.png",
                mime="image/png",
            )

        with col2:
            st.subheader("Top Keywords")
            df = pd.DataFrame(top_counts, columns=["keyword", "count"])
            st.dataframe(df, use_container_width=True, height=420)
            st.download_button(
                "Download Keywords (CSV)",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="keywords.csv",
                mime="text/csv",
            )

        if resolved_language == LANG_JA and font_path is None:
            st.info(
                "日本語フォントが見つからない場合、文字が四角く表示されることがあります。"
                "必要に応じてフォントファイルをアップロードしてください。"
            )


if __name__ == "__main__":
    main()
