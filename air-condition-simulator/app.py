import streamlit as st

# セッションステートに初期値を設定
if 'ac_state' not in st.session_state:
    st.session_state.ac_state = False  # エアコン停止中
if 'target_temp' not in st.session_state:
    st.session_state.target_temp = 24   # 初期設定温度
if 'mode' not in st.session_state:
    st.session_state.mode = "Auto"        # 運転モード
if 'fan_speed' not in st.session_state:
    st.session_state.fan_speed = 3        # 風量

# タイトルと説明
st.title("リモートエアコン 簡易操作シミュレーター")
st.write("エアコンの設定を変更して、リモートでエアコンを起動／停止するシミュレーションです。")

# エアコン設定の入力欄
st.subheader("エアコン設定")
mode = st.radio("運転モードを選択", options=["Cool", "Heat", "Auto"], index=["Cool", "Heat", "Auto"].index(st.session_state.mode))
target_temp = st.slider("設定温度 (℃)", 18, 29, st.session_state.target_temp)
fan_speed = st.slider("風量 (1〜5)", 1, 5, st.session_state.fan_speed)

# エアコン起動ボタン
if st.button("エアコン起動"):
    st.session_state.ac_state = True
    st.session_state.mode = mode
    st.session_state.target_temp = target_temp
    st.session_state.fan_speed = fan_speed
    st.success("エアコンが起動しました！")

# エアコン停止ボタン
if st.button("エアコン停止"):
    st.session_state.ac_state = False
    st.success("エアコンが停止しました。")

# 現在のエアコン状態の表示
st.subheader("エアコン状態")
if st.session_state.ac_state:
    st.write("### エアコンは **動作中** です。")
    st.write(f"- **設定温度**： {st.session_state.target_temp}℃")
    st.write(f"- **運転モード**： {st.session_state.mode}")
    st.write(f"- **風量**： {st.session_state.fan_speed}")
else:
    st.write("### エアコンは **Stop** です。")
