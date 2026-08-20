import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import urllib.parse
import requests
import os

st.set_page_config(
    page_title="긴급출동 소화전 탐색기",
    page_icon="🚒",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
    }
    .block-container { padding-top: 2rem; }
    h1 { font-size: clamp(1.4rem, 4vw, 2.5rem) !important; }
    h3 { font-size: clamp(1rem, 3vw, 1.5rem) !important; }
</style>
""", unsafe_allow_html=True)

EXCEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "용수.xlsx")

@st.cache_data
def load_data():
    df = pd.read_excel(EXCEL_FILE, engine="openpyxl", header=1)
    df.columns = [
        "연번", "시설번호", "수리형식", "시도명", "시군구명", "시군구코드",
        "도로명주소", "지번주소", "위도", "경도", "상세위치",
        "안전센터명", "보호틀유무", "사용가능여부", "설치연도",
        "배관깊이", "출수압력", "배관지름", "관할소방서명",
        "소방서전화번호", "표지설치여부", "설치주체", "적색노면표시", "비고"
    ]
    df["도로명주소"] = df["도로명주소"].fillna(df["지번주소"])
    df = df.dropna(subset=["위도", "경도"])
    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")
    df = df.dropna(subset=["위도", "경도"])
    return df

@st.cache_data
def calc_distances(fire_lat, fire_lng, lats, lngs):
    R = 6371000
    lat1 = np.radians(fire_lat)
    lat2 = np.radians(lats)
    dlat = np.radians(lats - fire_lat)
    dlng = np.radians(lngs - fire_lng)
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlng/2)**2
    return (R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))).astype(int)

try:
    hydrant_df = load_data()
except Exception as e:
    st.error(f"엑셀 파일을 읽을 수 없습니다: {e}")
    st.stop()

st.title("🚒 소화전 탐색")
st.caption(f"충청북도 소화전 {len(hydrant_df)}개 데이터 로드 완료")

fire_lat = None
fire_lng = None
fire_name = ""

query_params = st.query_params
if "gps_lat" in query_params and "gps_lng" in query_params:
    try:
        fire_lat = float(query_params["gps_lat"])
        fire_lng = float(query_params["gps_lng"])
        fire_name = f"GPS 위치 ({fire_lat:.6f}, {fire_lng:.6f})"
        st.success(f"GPS 위치 설정됨: {fire_lat:.6f}, {fire_lng:.6f}")
    except ValueError:
        pass

KAKAO_REST_KEY = "f0eebc52520c7ff58f091ec8cfd3b32e"

def kakao_geocode(addr):
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_KEY}"}

    resp = requests.get(
        "https://dapi.kakao.com/v2/local/search/keyword.json",
        headers=headers, params={"query": addr}, timeout=5
    )
    if resp.ok:
        docs = resp.json().get("documents")
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"])

    resp = requests.get(
        "https://dapi.kakao.com/v2/local/search/address.json",
        headers=headers, params={"query": addr}, timeout=5
    )
    if resp.ok:
        docs = resp.json().get("documents")
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"])

    return None, None

col_input1, col_input2 = st.columns(2)

with col_input1:
    st.subheader("화재 현장 주소 입력")
    fire_addr = st.text_input("화재 현장 주소를 입력하세요", placeholder="예: 충청북도 진천군 진천읍 교성리 1-1")
    if fire_addr:
        try:
            fire_lat, fire_lng = kakao_geocode(fire_addr)
            if fire_lat:
                fire_name = fire_addr
                st.success(f"좌표: {fire_lat:.6f}, {fire_lng:.6f}")
            else:
                st.warning("주소를 찾을 수 없습니다.")
        except Exception as e:
            st.warning(f"주소 변환 오류: {e}")

with col_input2:
    st.subheader("GPS 현재 위치 사용")
    from streamlit_geolocation import streamlit_geolocation
    location = streamlit_geolocation()
    if location and location.get("latitude") and location.get("longitude"):
        lat = location["latitude"]
        lng = location["longitude"]
        st.query_params["gps_lat"] = str(lat)
        st.query_params["gps_lng"] = str(lng)
        st.rerun()
    st.caption("버튼을 누르면 GPS 위치가 자동으로 설정됩니다.")

st.divider()

if fire_lat is not None and fire_lng is not None:
    lats = hydrant_df["위도"].values
    lngs = hydrant_df["경도"].values
    distances = calc_distances(fire_lat, fire_lng, lats, lngs)

    hydrant_df = hydrant_df.copy()
    hydrant_df["거리(m)"] = distances
    top_hydrants = hydrant_df.sort_values(by="거리(m)").head(10).reset_index(drop=True)

    st.subheader("인근 소화전 Top 10")
    col_map, col_list = st.columns([3, 2])

    with col_map:
        result_map = folium.Map(location=[fire_lat, fire_lng], zoom_start=15)
        folium.Marker(
            [fire_lat, fire_lng],
            popup="소방펌프차 위치",
            icon=folium.Icon(color="red", icon="truck", prefix="fa"),
            tooltip="소방펌프차 위치"
        ).add_to(result_map)

        for i, row in top_hydrants.iterrows():
            popup_html = f"""
            <div style='min-width:200px'>
                <b>{i+1}순위: {row['시설번호']}</b><br>
                거리: {row['거리(m)']:,}m<br>
                주소: {row['도로명주소']}<br>
                상세: {row['상세위치']}
            </div>
            """
            folium.Marker(
                [row["위도"], row["경도"]],
                popup=folium.Popup(popup_html, max_width=300),
                icon=folium.Icon(color="blue", icon="tint", prefix="fa"),
                tooltip=f"{i+1}순위 {row['거리(m)']:,}m"
            ).add_to(result_map)

        st_folium(result_map, width=None, height=450)

    with col_list:
        for i, row in top_hydrants.iterrows():
            rank = i + 1
            name = row["시설번호"]
            addr = row["도로명주소"]
            detail = row["상세위치"] if pd.notna(row["상세위치"]) else ""
            dist = row["거리(m)"]
            lat = row["위도"]
            lng = row["경도"]
            usable = row["사용가능여부"]
            guard = row["보호틀유무"]

            badge = "🟢" if usable == "Y" else "🔴"

            with st.expander(
                f"**{rank}순위** {badge} {name} — **{dist:,}m**",
                expanded=(rank == 1)
            ):
                st.markdown(f"""
                | 항목 | 내용 |
                |---|---|
                | 주소 | {addr} |
                | 상세 | {detail} |
                | 거리 | **{dist:,}m** |
                | 사용가능 | {badge} {usable} |
                | 보호틀 | {guard} |
                """)

                st.markdown("**내비게이션으로 이동**")

                kakao_app_url = f"kakaomap://route?sp={fire_lat},{fire_lng}&ep={lat},{lng}&by=CAR"
                naver_app_url = f"nmap://route/car?slat={fire_lat}&slng={fire_lng}&sname=%EC%B6%9C%EB%B0%9C%EC%A7%80&dlat={lat}&dlng={lng}&dname={urllib.parse.quote(name)}&appname=com.fire.hydrant"
                tmap_app_url = f"tmap://route?startx={fire_lng}&starty={fire_lat}&goalx={lng}&goaly={lat}&reqCoordType=WGS84&resCoordType=WGS84"

                nav_col1, nav_col2, nav_col3 = st.columns(3)
                with nav_col1:
                    st.link_button("카카오맵", kakao_app_url, use_container_width=True)
                with nav_col2:
                    st.link_button("네이버지도", naver_app_url, use_container_width=True)
                with nav_col3:
                    st.link_button("티맵", tmap_app_url, use_container_width=True)

                kakao_url = f"https://map.kakao.com/link/to/{urllib.parse.quote(name)},{lat},{lng}"
                naver_url = f"http://map.naver.com/index.nhn?slng={fire_lng}&slat={fire_lat}&stext=%EC%B6%9C%EB%B0%9C%EC%A7%80&elng={lng}&elat={lat}&etext={urllib.parse.quote(name)}&menu=route&pathType=1"

                web_col1, web_col2 = st.columns(2)
                with web_col1:
                    st.link_button("웹 카카오맵", kakao_url, use_container_width=True)
                with web_col2:
                    st.link_button("웹 네이버지도", naver_url, use_container_width=True)

    st.divider()
    st.subheader("소화전 요약")
    summary_cols = st.columns(4)
    with summary_cols[0]:
        st.metric("가장 가까운 거리", f"{top_hydrants.iloc[0]['거리(m)']:,}m")
    with summary_cols[1]:
        st.metric("10순위 거리", f"{top_hydrants.iloc[-1]['거리(m)']:,}m")
    with summary_cols[2]:
        usable_count = len(top_hydrants[top_hydrants["사용가능여부"] == "Y"])
        st.metric("사용가능 소화전", f"{usable_count}개")
    with summary_cols[3]:
        guard_count = len(top_hydrants[top_hydrants["보호틀유무"] == "Y"])
        st.metric("보호틀 설치", f"{guard_count}개")

else:
    st.info("화재 현장 주소를 입력하거나 GPS 버튼을 눌러주세요.")

st.divider()
st.caption("소화전 탐색 시스템 | 충청북도 소방용수시설 데이터")
