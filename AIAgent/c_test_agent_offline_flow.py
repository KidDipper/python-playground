# オフライン（LLM不要）版：テスト表 + フロー図 + 行選択ハイライト
# 重要修正：生成ボタン後も選択変更で右側が消えないように session_state を使用

import re
import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple, Set
from pycparser import c_parser, c_ast

st.set_page_config(page_title="C Test Pattern + Flow (Offline)", page_icon="🧪", layout="wide")
st.title("🧪 テストケースとフロー図")

# ----------------------
# セッション状態の初期化
# ----------------------
if "generated" not in st.session_state:
    st.session_state.generated = False
if "cached_code" not in st.session_state:
    st.session_state.cached_code = ""
if "cached_mode" not in st.session_state:
    st.session_state.cached_mode = "C1（原子条件 True/False：MC/DC風）"
if "parsed_funcs" not in st.session_state:
    st.session_state.parsed_funcs = []  # [{"name", "params", "body"}]
if "tables" not in st.session_state:
    st.session_state.tables = {}        # {func_name: DataFrame}
if "flows" not in st.session_state:
    st.session_state.flows = {}         # {func_name: (nodes, edges)}

# ----------------------
# ユーティリティ
# ----------------------
def remove_comments(code: str) -> str:
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)  # /* ... */ を除去
    code = re.sub(r"//.*", "", code)                        # // ... を除去
    return code

def parse_functions(code: str):
    parser = c_parser.CParser()
    try:
        ast = parser.parse(code)
    except Exception as e:
        st.error(f"Parse error: {e}")
        return []
    funcs = []
    class V(c_ast.NodeVisitor):
        def visit_FuncDef(self, node: c_ast.FuncDef):
            decl = node.decl
            params = []
            if hasattr(decl.type, "args") and decl.type.args:
                for p in decl.type.args.params:
                    name = getattr(p, "name", None) or f"arg{len(params)}"
                    t = getattr(p.type, "type", p.type)
                    names = getattr(t, "names", ["int"])
                    params.append({"name": name, "type": " ".join(names)})
            funcs.append({"name": decl.name, "params": params, "body": node.body})
    V().visit(ast)
    return funcs

def collect_condition_roots(body) -> List[c_ast.Node]:
    roots = []
    class CV(c_ast.NodeVisitor):
        def visit_If(self, n: c_ast.If):
            if n.cond: roots.append(n.cond)
            self.generic_visit(n)
        if hasattr(c_ast, "CondExpr"):
            def visit_CondExpr(self, n: c_ast.CondExpr):  # type: ignore
                if getattr(n, "cond", None):
                    roots.append(n.cond)
                self.generic_visit(n)
    CV().visit(body)
    return roots

def flatten_predicates(expr: c_ast.Node) -> List[c_ast.BinaryOp]:
    prims: List[c_ast.BinaryOp] = []
    def rec(e):
        if isinstance(e, c_ast.BinaryOp):
            if e.op in ("&&", "||"):
                rec(e.left); rec(e.right)
            elif e.op in (">", ">=", "<", "<=", "==", "!="):
                prims.append(e)
        elif isinstance(e, c_ast.UnaryOp):
            rec(e.expr)
        else:
            for _, child in getattr(e, "children", lambda: [])():
                rec(child)
    rec(expr)
    return prims

def extract_var_const_op(expr: c_ast.BinaryOp):
    op = expr.op
    L, R = expr.left, expr.right
    if isinstance(L, c_ast.ID) and isinstance(R, c_ast.Constant) and getattr(R, "type","")=="int":
        try: return L.name, int(R.value), op
        except: return L.name, None, op
    if isinstance(R, c_ast.ID) and isinstance(L, c_ast.Constant) and getattr(L, "type","")=="int":
        try: return R.name, int(L.value), op
        except: return R.name, None, op
    if isinstance(L, c_ast.ID): return L.name, None, op
    if isinstance(R, c_ast.ID): return R.name, None, op
    return None, None, op

def suggest_values(op: str, k: Optional[int]) -> List[int]:
    if k is None:
        return [-1, 0, 1]
    if op in (">", ">="):  return [k-1, k, k+1]
    if op in ("<", "<="):  return [k-1, k, k+1]
    if op in ("==", "!="): return [k, k+1]
    return [0, k, k+1]

def eval_atom_truth(op: str, x: int, k: Optional[int]) -> Optional[bool]:
    if k is None: return None
    try:
        if op == ">":  return x >  k
        if op == ">=": return x >= k
        if op == "<":  return x <  k
        if op == "<=": return x <= k
        if op == "==": return x == k
        if op == "!=": return x != k
        return None
    except: return None

def eval_cond_ast(e, inputs: Dict[str, int]) -> Optional[bool]:
    if isinstance(e, c_ast.BinaryOp):
        op = e.op
        if op in ("&&", "||"):
            lt = eval_cond_ast(e.left, inputs)
            rt = eval_cond_ast(e.right, inputs)
            if lt is None or rt is None:
                if op == "&&":
                    if lt is False or rt is False: return False
                    if lt is True and rt is True:  return True
                    return None
                else:
                    if lt is True or rt is True:   return True
                    if lt is False and rt is False:return False
                    return None
            else:
                return (lt and rt) if op=="&&" else (lt or rt)
        if op in (">", ">=", "<", "<=", "==", "!="):
            def val_of(node):
                if isinstance(node, c_ast.ID): return inputs.get(node.name, None)
                if isinstance(node, c_ast.Constant) and getattr(node, "type","")=="int":
                    try: return int(node.value)
                    except: return None
                return None
            lv = val_of(e.left); rv = val_of(e.right)
            if lv is None or rv is None: return None
            return eval_atom_truth(op, int(lv), int(rv))
        return None
    if isinstance(e, c_ast.UnaryOp) and e.op == "!":
        inner = eval_cond_ast(e.expr, inputs)
        return (not inner) if inner is not None else None
    for _, child in getattr(e, "children", lambda: [])():
        r = eval_cond_ast(child, inputs)
        if r is not None: return r
    return None

def gen_c0(params: List[Dict[str,str]]) -> List[Dict[str,Any]]:
    base = {p["name"]: 0 for p in params}
    return [{"inputs": base, "reason":"C0 baseline"}]

def gen_c1_mcdc_like(params: List[Dict[str,str]], cond_roots: List[c_ast.Node]) -> List[Dict[str,Any]]:
    base = {p["name"]: 0 for p in params}
    cases: List[Dict[str,Any]] = []
    seen = set()
    def push(assign: Dict[str,int], reason: str):
        key = tuple(sorted(assign.items()))
        if key in seen: return
        seen.add(key); cases.append({"inputs": assign.copy(), "reason": reason})
    push(base, "baseline")
    for root in cond_roots:
        atoms = flatten_predicates(root)
        if not atoms:
            for p in params:
                a = base.copy(); a[p["name"]] += 1
                push(a, f"vary {p['name']} (no primitive cmp)")
            continue
        for expr in atoms:
            var, k, op = extract_var_const_op(expr)
            if not var or var not in base:
                for p in params:
                    a = base.copy(); a[p["name"]] += 1
                    push(a, f"vary {p['name']} for {op}")
                continue
            tv = next((c for c in suggest_values(op,k) if eval_atom_truth(op,c,k) is True), None)
            fv = next((c for c in suggest_values(op,k) if eval_atom_truth(op,c,k) is False), None)
            if tv is not None:
                a = base.copy(); a[var] = tv
                push(a, f"{var} {op} {k} -> True ({tv})")
            if fv is not None:
                a = base.copy(); a[var] = fv
                push(a, f"{var} {op} {k} -> False ({fv})")
    return cases

def to_dataframe(func_name: str, params: List[Dict[str,str]], tests: List[Dict[str,Any]]) -> pd.DataFrame:
    cols = [p["name"] for p in params]
    if not cols:
        df = pd.DataFrame([[t["reason"]] for t in tests], columns=["reason"])
    else:
        rows = []
        for t in tests:
            rows.append([t["inputs"].get(c, "") for c in cols] + [t["reason"]])
        df = pd.DataFrame(rows, columns=cols + ["reason"])
    df.insert(0, "function", func_name)
    return df

class Node:
    def __init__(self, label:str, kind:str="stmt", cond_ast=None):
        self.id = None
        self.label = label
        self.kind = kind
        self.cond_ast = cond_ast

class Edge:
    def __init__(self, s:int, t:int, label:str=""):
        self.s = s; self.t = t; self.label = label

def expr_to_text(e) -> str:
    if isinstance(e, c_ast.BinaryOp):
        return f"({expr_to_text(e.left)} {e.op} {expr_to_text(e.right)})"
    if isinstance(e, c_ast.ID): return e.name
    if isinstance(e, c_ast.Constant): return e.value
    if isinstance(e, c_ast.UnaryOp): return f"{e.op}{expr_to_text(e.expr)}"
    return type(e).__name__

def build_flow_for_compound(cmpd: c_ast.Compound):
    nodes: List[Node] = []
    edges: List[Edge] = []
    def new_node(label:str, kind="stmt", cond_ast=None) -> int:
        n = Node(label, kind, cond_ast); n.id = len(nodes); nodes.append(n); return n.id
    start = new_node("Start", "start")
    prev_tail_ids = [start]
    def seq_connect(tails: List[int], nid:int, label:str=""):
        for t in tails: edges.append(Edge(t, nid, label))
    def make_branch_entry(parent_if_id:int, branch_label:str) -> int:
        bid = new_node(f"{branch_label}", "stmt")
        edges.append(Edge(parent_if_id, bid, branch_label))
        return bid
    def walk_stmt(stmt, tails: List[int]) -> List[int]:
        if isinstance(stmt, c_ast.If):
            if_id = new_node(expr_to_text(stmt.cond), "if", cond_ast=stmt.cond)
            seq_connect(tails, if_id, "")
            then_entry = make_branch_entry(if_id, "True")
            then_tails = [then_entry]
            then_end_tails = walk_block(stmt.iftrue, then_tails) if stmt.iftrue else then_tails
            else_entry = make_branch_entry(if_id, "False")
            else_tails = [else_entry]
            else_end_tails = walk_block(stmt.iffalse, else_tails) if stmt.iffalse else else_tails
            return then_end_tails + else_end_tails
        elif isinstance(stmt, c_ast.Return):
            rid = new_node("return " + (expr_to_text(stmt.expr) if stmt.expr else ""), "stmt")
            seq_connect(tails, rid, ""); return []
        else:
            sid = new_node(type(stmt).__name__, "stmt")
            seq_connect(tails, sid, ""); return [sid]
    def walk_block(block, incoming: List[int]) -> List[int]:
        tails = incoming
        if isinstance(block, c_ast.Compound):
            for item in (block.block_items or []):
                tails = walk_stmt(item, tails)
            return tails
        else:
            return walk_stmt(block, tails)
    end_tails = walk_block(cmpd, prev_tail_ids)
    if end_tails:
        end = new_node("End", "end")
        for t in end_tails: edges.append(Edge(t, end, ""))
    return nodes, edges

def predict_path_edges(nodes: List[Node], edges: List[Edge], inputs: Dict[str,int]) -> Set[Tuple[int,int]]:
    chosen: Set[Tuple[int,int]] = set()
    out_map: Dict[int, List[Edge]] = {}
    for e in edges: out_map.setdefault(e.s, []).append(e)
    def find_edge(src:int, label:str) -> Optional[Edge]:
        for e in out_map.get(src, []):
            if e.label == label: return e
        return None
    visited: Set[int] = set()
    def walk(nid:int):
        if nid in visited: return
        visited.add(nid)
        n = nodes[nid]
        if n.kind == "if":
            truth = eval_cond_ast(n.cond_ast, inputs) if n.cond_ast is not None else None
            if truth is True:
                e = find_edge(nid, "True")
                if e: chosen.add((e.s, e.t)); walk(e.t)
            elif truth is False:
                e = find_edge(nid, "False")
                if e: chosen.add((e.s, e.t)); walk(e.t)
            else:
                e1 = find_edge(nid, "True")
                e0 = find_edge(nid, "False")
                if e1: chosen.add((e1.s, e1.t)); walk(e1.t)
                if e0: chosen.add((e0.s, e0.t)); walk(e0.t)
        else:
            for e in out_map.get(nid, []):
                chosen.add((e.s, e.t)); walk(e.t)
    start_id = next((n.id for n in nodes if n.kind=="start"), 0)
    walk(start_id); return chosen

def to_dot(nodes: List[Node], edges: List[Edge], highlight: Set[Tuple[int,int]] = set()) -> str:
    lines = ['digraph G {', 'rankdir=LR', 'node [shape=box, fontname="Arial"];']
    for n in nodes:
        shape = "box"
        if n.kind == "start": shape = "oval"
        if n.kind == "end":   shape = "oval"
        if n.kind == "if":    shape = "diamond"
        label = n.label.replace('"','\\"')
        lines.append(f'{n.id} [label="{label}", shape={shape}];')
    for e in edges:
        color = "grey"; penw = "1"
        if (e.s, e.t) in highlight: color = "red"; penw = "3"
        lab = f' [label="{e.label}"]' if e.label else ""
        lines.append(f"{e.s} -> {e.t}{lab} [color={color}, penwidth={penw}];")
    lines.append("}"); return "\n".join(lines)

# ----------------------
# UI（左：入力、右：結果）
# ----------------------
left, right = st.columns([1, 1.5], gap="large")

with left:
    st.subheader("入力")
    code = st.text_area(
        "C関数を貼り付け（コメントOK：自動除去）",
        height=260,
        placeholder="例:\nint foo(int x,int y){ if(x>0 && y==0) return 1; else return 0; }"
    )
    mode = st.radio("テスト生成モード", ["C0（最小）", "C1（原子条件 True/False：MC/DC風）"], index=1)
    if st.button("生成", type="primary"):
        clean = remove_comments(code or "")
        funcs = parse_functions(clean)
        if not funcs:
            st.warning("関数定義が見つかりません。`int f(int x){...}` の形で貼り付けてください。")
            st.session_state.generated = False
        else:
            # 解析＆キャッシュ
            st.session_state.generated = True
            st.session_state.cached_code = clean
            st.session_state.cached_mode = mode
            st.session_state.parsed_funcs = funcs
            st.session_state.tables = {}
            st.session_state.flows = {}
            # 関数ごとに表とフローを構築して保存
            for f in funcs:
                cond_roots = collect_condition_roots(f["body"])
                tests = gen_c0(f["params"]) if "C0" in mode else gen_c1_mcdc_like(f["params"], cond_roots)
                st.session_state.tables[f["name"]] = to_dataframe(f["name"], f["params"], tests)
                st.session_state.flows[f["name"]] = build_flow_for_compound(f["body"])

with right:
    st.subheader("テストケースとフロー図")
    if st.session_state.generated and st.session_state.parsed_funcs:
        for f in st.session_state.parsed_funcs:
            fname = f["name"]
            df = st.session_state.tables.get(fname)
            nodes, edges = st.session_state.flows.get(fname, ([], []))

            st.markdown(f"**関数 `{fname}` — {st.session_state.cached_mode}**")
            if df is not None:
                st.dataframe(df, use_container_width=True)

                # 行選択（安全：selectbox）
                if len(df) > 0:
                    input_cols = [p["name"] for p in f["params"]]
                    idx = st.selectbox(
                        f"ハイライトするテスト行（{fname}）",
                        options=list(range(len(df))),
                        index=0,
                        key=f"{fname}_row_sel"
                    )
                    # 数値化を頑健に
                    try:
                        row = df.iloc[idx][input_cols] if input_cols else pd.Series(dtype=float)
                        row_num = pd.to_numeric(row, errors="coerce").fillna(0)
                        inputs = {c: int(float(row_num.get(c, 0))) for c in input_cols}
                    except Exception:
                        inputs = {c: 0 for c in input_cols}

                    # 例外が出てもUIが消えないように保護
                    try:
                        highlight = predict_path_edges(nodes, edges, inputs)
                        dot = to_dot(nodes, edges, highlight)
                        st.graphviz_chart(dot, use_container_width=True)
                    except Exception as e:
                        st.warning("フロー図の生成で問題が発生しました。入力や条件式をご確認ください。")
                        st.exception(e)
                        st.graphviz_chart(to_dot(nodes, edges, set()), use_container_width=True)
            else:
                st.info("テーブルが生成できませんでした。コードをご確認ください。")
    else:
        st.caption("左でコードを貼って「生成」を押すと表示されます。")


# int foo(int x, int y) {
#     if (x > 0 && y == 0)
#         return 1;
#     else
#         return 0;
# }


# // ① 速度違反レベル判定（複合条件・入れ子）
# int classify_speed(int speed, int isRain, int schoolZone) {
#     // 異常値
#     if (speed <= 0) return -1;

#     // 学校ゾーンは厳しめ、または極端な速度
#     if (speed > 80 || (speed > 60 && schoolZone == 1)) {
#         return 3; // 最重度
#     }
#     // 雨天時の高速走行
#     else if (speed > 60 && isRain == 1) {
#         return 2; // 重度
#     }
#     // 軽度の超過
#     else if (speed > 50 && isRain == 0 && schoolZone == 0) {
#         return 1; // 軽度
#     }
#     // 問題なし
#     return 0;
# }

# // ② 料金計算の割引ロジック（段階条件・複合条件）
# int calc_fee(int base, int age, int isMember, int dayOfWeek, int hour) {
#     // ベースチェック
#     if (base <= 0) return -1;

#     // 深夜割（平日かつ深夜帯）
#     if ((dayOfWeek >= 1 && dayOfWeek <= 5) && (hour < 6 || hour >= 23)) {
#         base = base - 20;
#     }

#     // 会員割 or 高齢者割
#     if (isMember == 1 || age >= 65) {
#         base = base - 30;
#     }
#     // 学生割（非会員・若年）
#     else if (age <= 22 && isMember == 0) {
#         base = base - 10;
#     }

#     // 最低料金の下限
#     if (base < 0) base = 0;

#     return base;
# }

# // ③ 温度・バッテリ・故障フラグから制御モード決定（入れ子＆複合）
# int decide_mode(int tempC, int soc, int fault) {
#     // 故障優先
#     if (fault != 0) {
#         if (soc < 20 || tempC > 90) {
#             return -2; // 緊急停止
#         } else {
#             return -1; // セーフモード
#         }
#     }

#     // 正常系
#     if ((tempC >= 10 && tempC <= 45) && (soc >= 40 && soc <= 90)) {
#         return 2; // ハイパフォーマンス
#     } else if ((tempC >= 0 && tempC < 10) || (tempC > 45 && tempC <= 60)) {
#         if (soc >= 30) {
#             return 1; // 通常
#         } else {
#             return 0; // 省電力
#         }
#     } else {
#         // 温度が極端 or SOCが極端
#         if (tempC < 0 || tempC > 60 || soc < 15 || soc > 95) {
#             return -1; // セーフモード
#         }
#         return 0; // 省電力
#     }
# }
