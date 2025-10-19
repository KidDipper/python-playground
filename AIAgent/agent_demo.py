import streamlit as st
import re, io, textwrap, json, time, requests
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from asteval import Interpreter
import wikipedia
from pypdf import PdfReader

# -------------------------
# Minimal "Agent-like" App
# -------------------------
st.set_page_config(page_title="Mini AI Agent (Free Demo)", page_icon="🤖")
st.title("🤖 Mini AI Agent (Free Demo, No API Key)")

# Session memory
if "memory" not in st.session_state:
    st.session_state.memory = []
if "steps" not in st.session_state:
    st.session_state.steps = []

@dataclass
class Step:
    thought: str
    action: str
    observation: str

def add_step(thought, action, observation):
    st.session_state.steps.append(Step(thought, action, observation))

# -------- Tools (No keys) --------
def tool_calculator(expr: str) -> str:
    aeval = Interpreter()
    try:
        # 危険な名前の削除（安全側）
        for name in list(aeval.symtable.keys()):
            if not name.startswith('_'):
                del aeval.symtable[name]
        result = aeval(expr)
        return f"Result: {result}"
    except Exception as e:
        return f"Calc error: {e}"

def tool_wikipedia_search(query: str, lang="en", sentences=3) -> str:
    try:
        wikipedia.set_lang(lang)
        hits = wikipedia.search(query)
        if not hits:
            return "No results."
        page = wikipedia.page(hits[0], auto_suggest=False)
        summary = wikipedia.summary(page.title, sentences=sentences)
        return f"Top: {page.title}\n\n{summary}\n\nURL: {page.url}"
    except Exception as e:
        return f"Wikipedia error: {e}"

def tool_weather(city: str) -> str:
    try:
        # wttr.in の簡易テキスト出力
        url = f"https://wttr.in/{city}?format=3"
        r = requests.get(url, timeout=10)
        return r.text.strip()
    except Exception as e:
        return f"Weather error: {e}"

def tool_hn_news(query: str) -> str:
    try:
        url = "https://hn.algolia.com/api/v1/search"
        r = requests.get(url, params={"query": query, "tags":"story"}, timeout=10)
        data = r.json()
        hits = data.get("hits", [])[:5]
        if not hits:
            return "No related news."
        lines = []
        for h in hits:
            title = h.get("title") or "(no title)"
            url = h.get("url") or "(no url)"
            points = h.get("points", 0)
            lines.append(f"- {title}  ({points} pts)\n  {url}")
        return "Top results:\n" + "\n".join(lines)
    except Exception as e:
        return f"News error: {e}"

def tool_file_search(text: str, query: str, topk=3) -> str:
    # 超シンプルなスコア：出現回数＋近傍抜粋
    chunks = []
    q = query.lower()
    for i, para in enumerate(text.split("\n\n")):
        score = para.lower().count(q)
        if score > 0:
            snippet = textwrap.shorten(para.strip(), width=400, placeholder=" ...")
            chunks.append((score, snippet))
    if not chunks:
        return "No match in file."
    chunks.sort(key=lambda x: x[0], reverse=True)
    best = [f"- {snip}" for _, snip in chunks[:topk]]
    return "Matches:\n" + "\n".join(best)

def read_uploaded_file(file) -> str:
    if file is None:
        return ""
    if file.type == "text/plain":
        return file.getvalue().decode("utf-8", errors="ignore")
    if file.type == "application/pdf":
        reader = PdfReader(io.BytesIO(file.getvalue()))
        texts = []
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        return "\n".join(texts)
    return ""

# -------- Simple Router (Rule-based) --------
def choose_tools(user_task: str) -> List[Dict[str, Any]]:
    t = user_task.lower()
    actions = []

    # 電卓
    if re.search(r"(calc|計算|[0-9\)\( \+\-\*\/\.\^]+)\s*=", t):
        expr = re.split(r"=", user_task, maxsplit=1)[-1].strip() if "=" in user_task else user_task
        actions.append({"tool":"calculator", "args":{"expr":expr}})

    # Wikipedia
    if any(k in t for k in ["とは", "what is", "who is", "について", "wiki", "wikipedia", "解説"]):
        q = re.sub(r"(とは|について|を教えて|って何|とは何か)", "", user_task).strip()
        actions.append({"tool":"wikipedia", "args":{"query": q or user_task, "lang":"ja"}})

    # 天気
    m = re.search(r"(天気|weather)\s*[:： ]\s*([A-Za-z\u3040-\u30FF\u4E00-\u9FFF\s\-]+)", user_task)
    if m:
        city = m.group(2).strip()
        actions.append({"tool":"weather", "args":{"city": city}})

    # ニュース
    if any(k in t for k in ["ニュース", "news", "最近の話題", "トレンド"]):
        q = re.sub(r"(ニュース|news|最近の話題|トレンド)", "", user_task).strip() or user_task
        actions.append({"tool":"news", "args":{"query": q}})

    # デフォルトでWikipediaを最後にフォールバック
    if not actions:
        actions.append({"tool":"wikipedia", "args":{"query": user_task, "lang":"ja"}})

    return actions

# -------- UI --------
with st.sidebar:
    st.header("🧠 Agent Memory")
    st.write("過去の指示・結果を保持します（簡易）。")
    if st.button("メモリをクリア"):
        st.session_state.memory.clear()
        st.session_state.steps.clear()
        st.success("メモリをクリアしました。")

user_task = st.text_input("やってほしいことを書いてください（例：'東京の天気: Tokyo' / 'ニュース AI Agent' / 'スクラムとは？' / 'calc= (2+3)*4'）")

uploaded = st.file_uploader("任意：TXTやPDFをアップロードするとファイルQ&Aが使えます", type=["txt","pdf"])
file_text = read_uploaded_file(uploaded)

if st.button("実行") and user_task.strip():
    st.session_state.steps.clear()
    add_step("ユーザー意図を解析", "Router", f"Task='{user_task}'")

    plan = choose_tools(user_task)
    add_step("タスク分解・ツール選択", "Plan", json.dumps(plan, ensure_ascii=False))

    results = []
    for i, act in enumerate(plan, 1):
        tool = act["tool"]
        args = act["args"]
        if tool == "calculator":
            add_step("数式評価", "Calculator", f"expr={args['expr']}")
            obs = tool_calculator(args["expr"])
        elif tool == "wikipedia":
            add_step("一般知識の取得", "Wikipedia", f"query={args['query']}")
            obs = tool_wikipedia_search(**args)
        elif tool == "weather":
            add_step("天気取得", "Weather", f"city={args['city']}")
            obs = tool_weather(**args)
        elif tool == "news":
            add_step("ニュース検索", "HackerNews", f"query={args['query']}")
            obs = tool_hn_news(**args)
        else:
            obs = "Unknown tool."
        results.append(f"### Step {i}: {tool}\n{obs}")

    # ファイルQ&A（あれば）
    if file_text and any(k in user_task.lower() for k in ["ファイル", "資料", "document", "pdf", "txt", "この文書", "このファイル"]):
        add_step("ファイル探索", "FileQnA", f"query={user_task}")
        results.append("### File Q&A\n" + tool_file_search(file_text, user_task))

    final_answer = "\n\n".join(results)
    st.markdown(final_answer)

    # メモリ保存
    st.session_state.memory.append({"task": user_task, "answer": final_answer, "steps":[s.__dict__ for s in st.session_state.steps]})

# Steps log
with st.expander("🪜 思考ログ（擬似）"):
    for s in st.session_state.steps:
        st.markdown(f"**Thought:** {s.thought}\n\n**Action:** {s.action}\n\n**Observation:** {s.observation}\n---")

# Memory log
with st.expander("📜 メモリ（履歴）"):
    for i, m in enumerate(st.session_state.memory[::-1], 1):
        st.markdown(f"**{i}.** {m['task']}")
