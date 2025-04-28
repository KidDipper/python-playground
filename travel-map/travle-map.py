import streamlit as st
import pandas as pd
import pydeck as pdk

# ランダムな国のリストを定義
COUNTRIES = [
    "Japan",
    "United States",
    "Brazil",
    "India",
    "Germany",
    "Australia",
    "Canada",
    "France",
    "Italy",
    "South Africa",
]


def main():
    st.title("旅行履歴の地図可視化アプリ")

    # 初期化
    if "travel_data" not in st.session_state:
        st.session_state.travel_data = []

    # ユーザー入力
    st.subheader("旅行履歴を入力してください")
    col1, col2, col3 = st.columns(3)
    with col1:
        year = st.selectbox("年", list(range(1990, 2024)))  # 年を選択
    with col2:
        month = st.selectbox("月", list(range(1, 13)))  # 月を選択
    with col3:
        country = st.selectbox("国名", COUNTRIES)

    if st.button("確定"):
        st.session_state.travel_data.append(
            {"年月": f"{year}-{month:02}", "国名": country}
        )

    # 旅行履歴の表示
    st.subheader("入力された旅行履歴")
    for i, entry in enumerate(
        sorted(st.session_state.travel_data, key=lambda x: x["年月"])
    ):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"{entry['年月']} - {entry['国名']}")
        with col2:
            if st.button("削除", key=f"delete_{i}"):
                st.session_state.travel_data.pop(i)

    # 地図の作成
    if st.button("地図作成"):
        if st.session_state.travel_data:
            # データ準備
            df = pd.DataFrame(st.session_state.travel_data)
            df["latitude"] = df["国名"].apply(lambda x: get_latitude(x))
            df["longitude"] = df["国名"].apply(lambda x: get_longitude(x))
            df = df.sort_values(by="年月")

            # アークのためのデータ準備
            arcs = []
            for i in range(len(df) - 1):
                start = [df.iloc[i]["longitude"], df.iloc[i]["latitude"]]
                end = [df.iloc[i + 1]["longitude"], df.iloc[i + 1]["latitude"]]
                arcs.append({"start": start, "end": end})

            # 地図プロット
            st.pydeck_chart(
                pdk.Deck(
                    map_style="mapbox://styles/mapbox/light-v10",
                    initial_view_state=pdk.ViewState(
                        latitude=0,
                        longitude=0,
                        zoom=1,
                    ),
                    layers=[
                        pdk.Layer(
                            "ScatterplotLayer",
                            data=df,
                            get_position="[longitude, latitude]",
                            get_color="[255, 0, 0]",  # 赤色表示
                            get_radius=100000,
                        ),
                        pdk.Layer(
                            "ArcLayer",
                            data=arcs,
                            get_source_position="start",
                            get_target_position="end",
                            get_source_color="[0, 255, 0]",  # 緑色表示
                            get_target_color="[0, 0, 255]",  # 青色表示
                            get_width=5,
                        ),
                    ],
                )
            )


def get_latitude(country):
    # 仮のデータを使用
    lat_dict = {
        "Japan": 36.2048,
        "United States": 37.0902,
        "Brazil": -14.2350,
        "India": 20.5937,
        "Germany": 51.1657,
        "Australia": -25.2744,
        "Canada": 56.1304,
        "France": 46.6034,
        "Italy": 41.8719,
        "South Africa": -30.5595,
    }
    return lat_dict.get(country, 0)


def get_longitude(country):
    # 仮のデータを使用
    lon_dict = {
        "Japan": 138.2529,
        "United States": -95.7129,
        "Brazil": -51.9253,
        "India": 78.9629,
        "Germany": 10.4515,
        "Australia": 133.7751,
        "Canada": -106.3468,
        "France": 1.8883,
        "Italy": 12.5674,
        "South Africa": 22.9375,
    }
    return lon_dict.get(country, 0)


if __name__ == "__main__":
    main()
