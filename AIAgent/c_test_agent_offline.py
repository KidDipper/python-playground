import streamlit as st
import pandas as pd
import re
from typing import List, Dict, Any, Optional, Tuple
from pycparser import c_parser, c_ast

st.set_page_config(page_title="C Test Pattern Agent (Offline)", page_icon="🧪", layout="wide")
st.title("🧪 C Test Pattern Agent（オフライン / ルールベース強化）")

# ----------------------
# 解析ユーティリティ
# ----------------------
def remove_comments(code: str) -> str:
    # /* ... */ と // ... の両方を削除
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    code = re.sub(r"//.*", "", code)
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
                    # 簡易な型名抽出（実務で強化推奨）
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
        # CondExpr (?:) はある環境だけ拾う
        if hasattr(c_ast, "CondExpr"):
            def visit_CondExpr(self, n: c_ast.CondExpr):  # type: ignore
                if getattr(n, "cond", None):
                    roots.append(n.cond)
                self.generic_visit(n)
    CV().visit(body)
    return roots

def flatten_predicates(expr: c_ast.Node) -> List[c_ast.BinaryOp]:
    """
    (x>0 && y==0) || z!=1  →  [x>0, y==0, z!=1]
    """
    prims: List[c_ast.BinaryOp] = []
    def rec(e):
        if isinstance(e, c_ast.BinaryOp):
            if e.op in ("&&", "||"):
                rec(e.left); rec(e.right)
            elif e.op in (">", ">=", "<", "<=", "==", "!="):
                prims.append(e)
            else:
                # 算術等はスキップ
                pass
        elif isinstance(e, c_ast.UnaryOp):
            rec(e.expr)
        else:
            for _, child in getattr(e, "children", lambda: [])():
                rec(child)
    rec(expr)
    return prims

def extract_var_const_op(expr: c_ast.BinaryOp) -> Tuple[Optional[str], Optional[int], str]:
    op = expr.op
    L, R = expr.left, expr.right
    # var op const
    if isinstance(L, c_ast.ID) and isinstance(R, c_ast.Constant) and getattr(R, "type", "") == "int":
        try: return L.name, int(R.value), op
        except: return L.name, None, op
    # const op var
    if isinstance(R, c_ast.ID) and isinstance(L, c_ast.Constant) and getattr(L, "type", "") == "int":
        try: return R.name, int(L.value), op
        except: return R.name, None, op
    # どちらかがIDなら変数名のみ
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

def eval_atom_truth(op: str, x: int, k: Optional[int], aim_true: bool) -> bool:
    if k is None:
        return False  # 評価できない場合はFalseで
    try:
        if op == ">":  v = (x >  k)
        elif op == ">=": v = (x >= k)
        elif op == "<":  v = (x <  k)
        elif op == "<=": v = (x <= k)
        elif op == "==": v = (x == k)
        elif op == "!=": v = (x != k)
        else: return False
        return v if aim_true else (not v)
    except:
        return False

# ----------------------
# テスト生成
# ----------------------
def gen_c0(params: List[Dict[str,str]]) -> List[Dict[str,Any]]:
    base = {p["name"]: 0 for p in params}
    return [{"inputs": base, "reason":"C0 baseline"}]

def gen_c1_mcdc_like(params: List[Dict[str,str]], cond_roots: List[c_ast.Node]) -> List[Dict[str,Any]]:
    """
    原子条件ごとに True/False ケースを作る（他はベースライン維持）。
    厳密なMC/DC最小化ではないが、実務で役立つ“各項の寄与が見える”セット。
    """
    base = {p["name"]: 0 for p in params}
    cases: List[Dict[str,Any]] = []
    seen = set()

    def push(assign: Dict[str,int], reason: str):
        key = tuple(sorted(assign.items()))
        if key in seen: return
        seen.add(key)
        cases.append({"inputs": assign.copy(), "reason": reason})

    push(base, "baseline")

    for root in cond_roots:
        atoms = flatten_predicates(root)
        if not atoms:
            # 比較が抽出できない場合は軽く揺らす
            for p in params:
                a = base.copy(); a[p["name"]] = a[p["name"]] + 1
                push(a, f"vary {p['name']} (no primitive cmp)")
            continue

        # 各原子条件を独立に True / False にする
        for expr in atoms:
            var, k, op = extract_var_const_op(expr)
            if not var or var not in base:
                # 変数特定できない → 全引数を軽く揺らす
                for p in params:
                    a = base.copy(); a[p["name"]] += 1
                    push(a, f"vary {p['name']} for {op}")
                continue

            # Trueにする候補
            true_val = None
            for cand in suggest_values(op, k):
                if eval_atom_truth(op, cand, k, aim_true=True):
                    true_val = cand; break
            # Falseにする候補
            false_val = None
            for cand in suggest_values(op, k):
                if eval_atom_truth(op, cand, k, aim_true=False):
                    false_val = cand; break

            if true_val is not None:
                a = base.copy(); a[var] = true_val
                push(a, f"{var} {op} {k} -> True ({true_val})")
            if false_val is not None:
                a = base.copy(); a[var] = false_val
                push(a, f"{var} {op} {k} -> False ({false_val})")

    return cases

def to_dataframe(func_name: str, params: List[Dict[str,str]], tests: List[Dict[str,Any]]) -> pd.DataFrame:
    cols = [p["name"] for p in params]
    rows = []
    for t in tests:
        row = [t["inputs"].get(c, "") for c in cols] + [t["reason"]]
        rows.append(row)
    if not cols:  # 引数なし関数の表示対策
        df = pd.DataFrame([[t["reason"]] for t in tests], columns=["reason"])
    else:
        df = pd.DataFrame(rows, columns=cols + ["reason"])
    df.insert(0, "function", func_name)
    return df

# ----------------------
# UI
# ----------------------
left, right = st.columns([1, 1.4], gap="large")

with left:
    st.subheader("入力")
    code = st.text_area(
        "C関数を貼り付けてください（複数可）",
        height=260,
        placeholder="例:\nint foo(int x,int y){ if(x>0 && y==0) return 1; else if(x<0) return -1; else return 0; }"
    )
    mode = st.radio("モード", ["C0（最小）", "C1（原子条件 True/False：MC/DC風）"], index=1, horizontal=False)
    go = st.button("テストパターン生成", type="primary")

with right:
    st.subheader("生成結果")
    if go:
        if not code.strip():
            st.info("Cコードを貼り付けてください。")
        else:
            code = remove_comments(code)
            funcs = parse_functions(code)
            if not funcs:
                st.warning("関数定義が見つかりません。`int f(int x){...}` のような形で貼り付けてください。")
            else:
                for f in funcs:
                    cond_roots = collect_condition_roots(f["body"])
                    if "C0" in mode:
                        tests = gen_c0(f["params"])
                    else:
                        tests = gen_c1_mcdc_like(f["params"], cond_roots)
                    df = to_dataframe(f["name"], f["params"], tests)
                    st.markdown(f"**関数 `{f['name']}` — {mode}**")
                    st.dataframe(df, use_container_width=True)




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



