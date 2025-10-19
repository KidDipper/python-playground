import streamlit as st
import pandas as pd
from pycparser import c_parser, c_ast

st.set_page_config(page_title="C Test Pattern Agent", page_icon="🧪", layout="wide")
st.title("🧪 C Test Pattern Agent（表表示のみ / No LLM）")

# ---- Cコード解析 ----
def extract_functions(code: str):
    parser = c_parser.CParser()
    try:
        ast = parser.parse(code)
    except Exception as e:
        st.error(f"Parse error: {e}")
        return []

    functions = []
    class FuncVisitor(c_ast.NodeVisitor):
        def visit_FuncDef(self, node: c_ast.FuncDef):
            decl = node.decl
            func = {"name": decl.name, "params": [], "body": node.body}
            if hasattr(decl.type, "args") and decl.type.args:
                for p in decl.type.args.params:
                    # 型名の抽出は簡易（実務では強化推奨）
                    t = getattr(p.type, "type", p.type)
                    type_name = getattr(t, "names", ["int"])[0]
                    func["params"].append({"name": p.name or f"arg", "type": type_name})
            functions.append(func)
    FuncVisitor().visit(ast)
    return functions

def collect_conditions(node):
    """If文などから条件式ノードを集める（上位の式）"""
    cond_roots = []
    class CondVisitor(c_ast.NodeVisitor):
        def visit_If(self, n: c_ast.If):
            if n.cond:
                cond_roots.append(n.cond)
            self.generic_visit(n)
        # CondExpr (?:) は環境にあれば拾う
        if hasattr(c_ast, "CondExpr"):
            def visit_CondExpr(self, n: c_ast.CondExpr):  # type: ignore
                if getattr(n, "cond", None):
                    cond_roots.append(n.cond)
                self.generic_visit(n)
    CondVisitor().visit(node)
    return cond_roots

def flatten_primitive_conditions(expr):
    """
    論理式を分解して、原子的な比較 (>, >=, <, <=, ==, !=) の BinaryOp をリスト化。
    例: (x>0 && y==0) || z!=1  ->  [x>0, y==0, z!=1]
    """
    prims = []
    def rec(e):
        if isinstance(e, c_ast.BinaryOp):
            if e.op in ("&&", "||"):
                rec(e.left)
                rec(e.right)
            elif e.op in (">", ">=", "<", "<=", "==", "!="):
                prims.append(e)
            else:
                # +, -, &, | などは原子比較ではないのでスキップ
                pass
        elif isinstance(e, c_ast.UnaryOp):
            # ! (not) の中に BinaryOp があれば掘る
            rec(e.expr)
        elif isinstance(e, (c_ast.ID, c_ast.Constant, c_ast.FuncCall, c_ast.Cast, c_ast.Paren)):
            # さらに内側があれば掘る
            for child_name, child in e.children():
                rec(child)
        else:
            # その他ノードも子供を探索
            for _, child in getattr(e, 'children', lambda: [])():
                rec(child)
    rec(expr)
    return prims

def extract_var_and_const(expr):
    """BinaryOp から (変数名, 定数, 演算子) を取り出す。定数が無ければ None。"""
    if not isinstance(expr, c_ast.BinaryOp):
        return None, None, None
    op = expr.op
    L, R = expr.left, expr.right

    # var <op> const
    if isinstance(L, c_ast.ID) and isinstance(R, c_ast.Constant) and getattr(R, "type", "") == "int":
        try:
            return L.name, int(R.value), op
        except:
            return L.name, None, op

    # const <op> var
    if isinstance(R, c_ast.ID) and isinstance(L, c_ast.Constant) and getattr(L, "type", "") == "int":
        try:
            return R.name, int(L.value), op
        except:
            return R.name, None, op

    # どちらかが変数なら変数名だけ返す
    if isinstance(L, c_ast.ID): return L.name, None, op
    if isinstance(R, c_ast.ID): return R.name, None, op
    return None, None, op

def suggest_values(op, val):
    # 定数境界の典型パターン
    if val is None:
        return [-1, 0, 1]  # フォールバック
    if op in (">", ">="):  return [val - 1, val, val + 1]
    if op in ("<", "<="):  return [val - 1, val, val + 1]
    if op in ("==", "!="): return [val, val + 1]
    return [0, val, val + 1]

def gen_tests(params, cond_roots, coverage="C1"):
    # ベースライン
    base = {p["name"]: 0 for p in params}
    if coverage == "C0":
        return [{"inputs": base.copy(), "reason": "C0 baseline"}]

    tests, seen = [], set()
    def push(assign, reason):
        key = tuple(sorted(assign.items()))
        if key not in seen:
            seen.add(key)
            tests.append({"inputs": assign.copy(), "reason": reason})

    push(base, "baseline")

    # 各If条件の“原子比較”に分解して個別に当てる（ゆるいC1）
    for root in cond_roots:
        prims = flatten_primitive_conditions(root)
        if not prims:
            # 比較が取れない場合は全引数を少し揺らす
            for p in params:
                a = base.copy()
                a[p["name"]] = a[p["name"]] + 1
                push(a, f"vary {p['name']} (no primitive cmp)")
            continue

        for cmp_expr in prims:
            var, val, op = extract_var_and_const(cmp_expr)
            if var and var in base:
                for v in suggest_values(op, val):
                    a = base.copy()
                    a[var] = v
                    # できれば True/False を意識したいが、ここでは簡易に境界を並べる
                    push(a, f"{var} {op} {val} ≈ {v}")
            else:
                # 変数が特定できない場合のフォールバック
                for p in params:
                    a = base.copy()
                    a[p["name"]] = a[p["name"]] + 1
                    push(a, f"vary {p['name']} for complex cmp")

    return tests or [{"inputs": base.copy(), "reason": "no condition"}]

def to_dataframe(func, params, tests):
    df = pd.DataFrame([{**t["inputs"], "reason": t["reason"]} for t in tests])
    # 引数がゼロの関数対策
    if df.empty:
        df = pd.DataFrame([{"reason":"no inputs"}])
    df.insert(0, "function", func["name"])
    return df

# ---- UI ----
left, right = st.columns([1, 1.2], gap="large")

with left:
    code = st.text_area(
        "ここにC関数を貼り付け：",
        height=240,
        placeholder="例：\nint foo(int x, int y){ if(x>0 && y==0) return 1; else return 0; }"
    )
    coverage = st.radio("カバレッジ方式", ["C0", "C1"], horizontal=True, index=1)
    go = st.button("テストパターン生成", type="primary")

with right:
    st.subheader("テストケース")
    if go:
        if not code.strip():
            st.info("Cコードを貼り付けてください。")
        else:
            funcs = extract_functions(code)
            if not funcs:
                st.warning("関数定義が見つかりませんでした。`int foo(int x){...}` の形を貼ってください。")
            else:
                for f in funcs:
                    conds = collect_conditions(f["body"])
                    tests = gen_tests(f["params"], conds, coverage)
                    df = to_dataframe(f, f["params"], tests)
                    st.markdown(f"**関数 `{f['name']}`（{coverage}）**")
                    st.dataframe(df, use_container_width=True)
