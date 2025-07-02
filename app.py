import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import pytz

from dotenv import load_dotenv
import os

load_dotenv()  # .env 파일 읽기
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")



# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')

import firebase_admin
from firebase_admin import credentials, firestore

# 이미 초기화된 경우 건너뛰기
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

firestore_db = firestore.client()

def log_dwell_time_to_firebase(session):
    view_data = session.get("view_start_time")  # dict 타입
    search_id = session.get("current_search_id")
    search_keyword = session.get("current_search_keyword")  # 검색어 (문자)
    recipe_id = view_data.get("recipe_id") if view_data else None
    recipe_name = session.get("selected_recipe_name")  # 레시피명 (문자)

    if isinstance(view_data, dict) and "time" in view_data and search_id:
        view_time = view_data["time"]
        if isinstance(view_time, datetime):
            duration = (datetime.now() - view_time).total_seconds()
            now_korea = datetime.now(korea)

            firestore_db.collection("dwell_logs").add({
                "검색어_아이디": search_id,
                "검색어_이름": search_keyword or "Unknown",
                "레시피_아이디": recipe_id,
                "레시피_이름": recipe_name or "Unknown",
                "체류시간": f"{round(duration, 2)}초",
                "검색시간": now_korea
            })


from database_setup import setup_database
from search_logic import (
    load_bert_model, search_by_name_bert, search_by_ingredient,
    fetch_recipe_detail, log_search, log_recommendations, log_dwell_time, db_query
)
from utils import get_youtube_videos

# --- 페이지 기본 설정 ---
st.set_page_config(layout="wide", page_title="AI 레시피 추천 서비스")

# --- 리소스 로딩 (앱 실행 시 한 번만) ---
model = load_bert_model()
setup_database(model)

# --- 세션 상태 초기화 ---
if 'selected_recipe_id' not in st.session_state:
    st.session_state.selected_recipe_id = None
if 'view_start_time' not in st.session_state:
    st.session_state.view_start_time = None
if 'search_results' not in st.session_state:
    st.session_state.search_results = pd.DataFrame()
if 'current_search_id' not in st.session_state:
    st.session_state.current_search_id = None
if 'youtube_videos' not in st.session_state:
    st.session_state.youtube_videos = []
if 'next_page_token' not in st.session_state:
    st.session_state.next_page_token = None
if 'youtube_query' not in st.session_state:
    st.session_state.youtube_query = ""
if 'calc_ingredients' not in st.session_state:
    st.session_state.calc_ingredients = []


# --- UI 레이아웃 ---
st.title("🍳 AI 레시피 추천 및 분석 서비스")
tab1, tab2, tab3 = st.tabs(["🔍 AI 레시피 추천", "📈 트렌드 분석", "🧮 영양성분 계산기"])

# --- 탭 1: AI 레시피 추천 ---
with tab1:
    col1, col2 = st.columns([0.4, 0.6])
    
    with col1:
        st.subheader("1. 검색 조건 선택")
        # [수정됨] 검색 옵션의 이름을 '키워드명 (영상 검색)'으로 통일
        search_by_options = {"레시피명 (AI 추천)": 1, "재료명": 2, "영상 검색": 3}
        search_by_label = st.radio("검색 기준", search_by_options.keys(), key="search_by", horizontal=True)
        
        if search_by_label == "영상 검색":
            placeholder_text = "예: 다이어트 식단, 간단한 아침"
        else:
            placeholder_text = "예: 김치찌개, 닭가슴살 등"
        keyword = st.text_input("검색어를 입력하세요:", placeholder=placeholder_text)

        # [수정됨] '키워드명 (영상 검색)'을 기준으로 올바르게 분기 처리
        is_recipe_search = search_by_label != "영상 검색"
        
        nation_df = db_query("SELECT NATION_CODE, NATION_NM FROM NATION_INFO ORDER BY NATION_CODE")
        type_df = db_query("SELECT TY_CODE, TY_NM FROM TYPE_INFO ORDER BY TY_CODE")
        nation_options = {"전체": None, **pd.Series(nation_df.NATION_CODE.values, index=nation_df.NATION_NM).to_dict()}
        type_options = {"전체": None, **pd.Series(type_df.TY_CODE.values, index=type_df.TY_NM).to_dict()}

        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            selected_nation_label = st.selectbox("나라별 음식", options=nation_options.keys(), disabled=not is_recipe_search)
            selected_nation_code = nation_options[selected_nation_label]
        with filter_col2:
            selected_type_label = st.selectbox("음식 종류", options=type_options.keys(), disabled=not is_recipe_search)
            selected_type_code = type_options[selected_type_label]

        if st.button("검색", type="primary"):
            log_dwell_time_to_firebase(st.session_state)
            if keyword:
                st.session_state.current_search_keyword = keyword
                log_dwell_time(st.session_state)
                st.session_state.selected_recipe_id = None
                st.session_state.youtube_videos = []
                st.session_state.next_page_token = None
                st.session_state.search_results = pd.DataFrame()

                srch_code = search_by_options[search_by_label]
                log_nation_code = selected_nation_code if is_recipe_search else None
                srch_id = log_search(srch_code, keyword, log_nation_code)
                st.session_state.current_search_id = srch_id

                    # ✅ Firebase에 검색 로그 저장
                firestore_db.collection("search_logs").add({
                    "키워드": keyword,
                    "검색기준": search_by_label,
                    "나라별 음식": selected_nation_label,
                    "음식 종류": selected_type_label,
                    "시간": datetime.now(korea)
                    })

                if is_recipe_search:
                    with st.spinner("AI가 레시피를 찾고 있습니다..."):
                        if search_by_label == "레시피명 (AI 추천)":
                            results = search_by_name_bert(keyword, model, selected_nation_code, selected_type_code)
                        else:
                            results = search_by_ingredient(keyword, selected_nation_code, selected_type_code)
                        st.session_state.search_results = results
                    if not results.empty:
                        log_recommendations(srch_id, results)
                else: # 키워드 영상 검색
                    st.session_state.youtube_query = keyword
                    with st.spinner("관련 영상을 찾는 중..."):
                        videos, token = get_youtube_videos(keyword, max_results=5)
                        st.session_state.youtube_videos = videos
                        st.session_state.next_page_token = token
            else:
                st.warning("검색어를 입력해주세요.")
        
        if not st.session_state.search_results.empty:
            st.divider()
            st.subheader("2. 검색 결과")
            for _, row in st.session_state.search_results.iterrows():
                recipe_name = row['RECIPE_NM_KO']
                score = f" (유사도: {row['유사도']:.2f})" if '유사도' in row else ""
                if st.button(f"{recipe_name}{score}", key=f"recipe_{row['RECIPE_ID']}"):
                    log_dwell_time(st.session_state)
                    st.session_state.selected_recipe_name = recipe_name
                    if st.session_state.selected_recipe_id != row['RECIPE_ID']:
                        st.session_state.youtube_videos = []
                        st.session_state.next_page_token = None
                    st.session_state.selected_recipe_id = row['RECIPE_ID']
                    st.session_state.view_start_time = {'srch_id': st.session_state.current_search_id, 'recipe_id': row['RECIPE_ID'], 'time': datetime.now()}
                    st.rerun()

    with col2:
        if st.session_state.selected_recipe_id:
            st.subheader("상세 정보")
            try:
                with st.spinner("레시피 상세 정보를 불러오는 중..."):
                    details = fetch_recipe_detail(st.session_state.selected_recipe_id)
                if details:
                    base, ingredients, process = details['base'], details['ingredients'], details['process']
                    st.markdown(f"### 🍽️ {base['RECIPE_NM_KO']}")
                    st.caption(base['SUMRY'])
                    
                    cols_info = st.columns(4)
                    cols_info[0].metric("분류", f"{base.get('NATION_NM', 'N/A')} / {base.get('TY_NM', 'N/A')}")
                    cols_info[1].metric("조리 시간", f"{base.get('COOKING_TIME', 0)} 분")
                    
                    # [개선됨] 칼로리가 0일 경우 "정보 없음"으로 표시
                    calorie_value = base.get('CALORIE', 0)
                    calorie_display = f"{calorie_value} Kcal" if calorie_value > 0 else "정보 없음"
                    cols_info[2].metric("칼로리", calorie_display)
                    
                    cols_info[3].metric("분량", f"{base.get('QNT', 0)} 인분")

                    st.subheader("🥕 재료")
                    for ing in ingredients:
                        st.markdown(f"- **{ing.get('IRDNT_NM', '')}**: {ing.get('IRDNT_CPCTY', '')}")

                    st.subheader("👨‍🍳 조리 과정")
                    for i, step in enumerate(process, 1):
                        st.markdown(f"**{i}.** {step.get('COOKING_DC', '')}")
                    
                    st.divider()
                    st.subheader("🎥 관련 유튜브 영상")
                    st.session_state.youtube_query = base['RECIPE_NM_KO']
                    
                    if not st.session_state.youtube_videos:
                        with st.spinner("관련 영상을 찾는 중..."):
                            videos, token = get_youtube_videos(st.session_state.youtube_query, max_results=2)
                            st.session_state.youtube_videos = videos
                            st.session_state.next_page_token = token
                        
                        # YouTube API 키가 없거나 오류가 발생한 경우 안내 메시지 표시
                        if not st.session_state.youtube_videos:
                            st.warning("YouTube API 키가 설정되지 않았습니다. 관련 영상을 보려면 .env 파일에 YOUTUBE_API_KEY를 설정해주세요.")
                            st.info("YouTube Data API v3 키는 https://console.cloud.google.com/apis/credentials 에서 생성할 수 있습니다.")
            except Exception as e:
                st.error(f"상세 정보를 불러오는 중 오류가 발생했습니다: {e}")
                st.session_state.selected_recipe_id = None
                st.rerun()

        if st.session_state.youtube_videos:
            if not st.session_state.selected_recipe_id:
                st.subheader(f"🎥 '{st.session_state.youtube_query}' 영상 검색 결과")
            for video in st.session_state.youtube_videos:
                st.write(f"**{video['title']}**")
                st.video(f"https://www.youtube.com/watch?v={video['video_id']}")
            if st.session_state.next_page_token:
                if st.button("추천 영상 더보기 🔄"):
                    with st.spinner("추가 영상을 찾는 중..."):
                        new_videos, new_token = get_youtube_videos(st.session_state.youtube_query, max_results=2, page_token=st.session_state.next_page_token)
                        st.session_state.youtube_videos.extend(new_videos)
                        st.session_state.next_page_token = new_token
                    st.rerun()
        elif st.session_state.youtube_query and not st.session_state.youtube_videos:
            st.warning("YouTube API 키가 설정되지 않았습니다. 영상 검색 기능을 사용하려면 .env 파일에 YOUTUBE_API_KEY를 설정해주세요.")
            st.info("YouTube Data API v3 키는 https://console.cloud.google.com/apis/credentials 에서 생성할 수 있습니다.")

        if not st.session_state.selected_recipe_id and not st.session_state.youtube_videos:
            st.info("왼쪽에서 검색 조건을 선택하고 검색어를 입력해주세요.")

# --- 탭 2: 트렌드 분석 ---
with tab2:
    import plotly.express as px
    import pandas as pd

    st.header("📈 트렌드 데이터 분석")
    st.info("사용자 행동 로그를 기반으로 한 심층 분석입니다.")

    # 🔹 Firestore에서 데이터프레임으로 가져오는 함수 정의
    def get_collection_df(collection_name):
        docs = firestore_db.collection(collection_name).stream()
        data = [doc.to_dict() for doc in docs]
        return pd.DataFrame(data)

    # 🔹 데이터 로딩
    df_search = get_collection_df("search_logs")
    df_dwell = get_collection_df("dwell_logs")
    df_recipe = get_collection_df("recipe_base")

    col1, col2 = st.columns(2)

    # -----------------------------
    # 🔹 인기 검색 키워드
    # -----------------------------
    with col1:
        st.subheader("인기 검색 키워드")
        if not df_search.empty and "키워드" in df_search.columns:
            top_keywords = df_search["키워드"].value_counts().nlargest(10).reset_index()
            top_keywords.columns = ["키워드", "검색 수"]
            fig1 = px.bar(top_keywords, x="키워드", y="검색 수", title="TOP 10 검색 키워드", text_auto=True)
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("검색 기록이 없습니다.")

    # -----------------------------
    # 🔹 가장 많이 본 레시피
    # -----------------------------
    with col2:
        st.subheader("가장 많이 본 레시피")
        if not df_dwell.empty and not df_recipe.empty:
            if "레시피_아이디" in df_dwell.columns and "RECIPE_ID" in df_recipe.columns:
                merged = pd.merge(df_dwell, df_recipe, left_on="레시피_아이디", right_on="RECIPE_ID", how="left")
                if "RECIPE_NM_KO" in merged.columns:
                    top_recipes = merged["RECIPE_NM_KO"].value_counts().nlargest(10).reset_index()
                    top_recipes.columns = ["레시피명", "조회 수"]
                    fig2 = px.bar(top_recipes, x="레시피명", y="조회 수", title="TOP 10 조회수 레시피", text_auto=True)
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.warning("병합 후 RECIPE_NM_KO 필드가 존재하지 않습니다.")
            else:
                st.warning("레시피 ID 컬럼이 누락되었습니다.")
        else:
            st.info("조회 기록이 없습니다.")

    # -----------------------------
    # 🔹 검색어별 평균 체류시간
    # -----------------------------
    st.divider()
    st.subheader("검색어별 평균 레시피 체류시간")
    if not df_search.empty and not df_dwell.empty:
        try:
            # ✅ '체류시간' 문자열 처리 → 숫자형 초
            if "체류시간" in df_dwell.columns:
                df_dwell = df_dwell[df_dwell["체류시간"].notnull()]
                df_dwell["체류시간_초"] = df_dwell["체류시간"].str.replace("초", "").astype(float)
                df_dwell = df_dwell[df_dwell["체류시간_초"] < 1800]  # 30분 이상 제거
            else:
                st.warning("체류시간 컬럼이 없습니다.")
                df_dwell["체류시간_초"] = 0

            # ✅ 병합 키: 검색어_이름 (from dwell) vs 키워드 (from search)
            if "검색어_이름" in df_dwell.columns and "키워드" in df_search.columns:
                merged = pd.merge(df_dwell, df_search, left_on="검색어_이름", right_on="키워드", how="inner")

                group = merged.groupby("검색어_이름").agg(
                    평균체류시간=("체류시간_초", "mean"),
                    조회수=("레시피_아이디", "count")
                ).reset_index()

                group = group[group["조회수"] > 2].sort_values("평균체류시간", ascending=False).head(10)
                group["평균체류시간"] = group["평균체류시간"].round(1)

                fig3 = px.bar(
                    group,
                    x="검색어_이름",
                    y="평균체류시간",
                    title="검색어별 평균 체류시간 (단위: 초)",
                    text_auto=True,
                    labels={"평균체류시간": "평균 체류시간(초)"}
                )
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.warning("병합을 위한 검색어 컬럼이 누락되었습니다.")

        except Exception as e:
            st.error(f"데이터 처리 중 오류 발생: {e}")
    else:
        st.info("분석할 체류 시간 데이터가 부족합니다.")





# --- 탭 3: 영양성분 계산기 ---
with tab3:
    # (탭3 코드는 변경 없음)
    st.header("🧮 나만의 레시피 영양성분 계산기")
    st.info("재료와 무게(g)를 입력하면 총 영양성분을 계산해줍니다.")

    try:
        all_ingredients = db_query("SELECT FOOD_NAME FROM NUTRITION_INFO ORDER BY FOOD_NAME")['FOOD_NAME'].tolist()
    except Exception:
        all_ingredients = []

    if not all_ingredients:
        st.warning("영양성분 데이터가 없습니다. DB 파일을 확인해주세요.")
    else:
        if not st.session_state.calc_ingredients:
            st.session_state.calc_ingredients = [{"name": all_ingredients[0], "weight": 100}]

        for i, item in enumerate(st.session_state.calc_ingredients):
            cols = st.columns([0.6, 0.3, 0.1])
            try:
                current_index = all_ingredients.index(item.get('name', all_ingredients[0]))
            except ValueError:
                current_index = 0
            
            item['name'] = cols[0].selectbox(f"재료 {i+1}", all_ingredients, key=f"name_{i}", index=current_index)
            item['weight'] = cols[1].number_input("무게(g)", min_value=0, value=item.get('weight', 100), key=f"weight_{i}", step=10)
            if cols[2].button("➖", key=f"del_{i}"):
                if len(st.session_state.calc_ingredients) > 1:
                    st.session_state.calc_ingredients.pop(i)
                    st.rerun()

        if st.button("➕ 재료 추가"):
            st.session_state.calc_ingredients.append({"name": all_ingredients[0], "weight": 100})
            st.rerun()
            
        st.divider()

        if st.button("영양성분 계산하기", type="primary"):
            total_nutrition = {'ENERGY': 0.0, 'PROTEIN': 0.0, 'FAT': 0.0, 'CH': 0.0, 'SUGAR': 0.0}
            
            ingredient_list = [item['name'] for item in st.session_state.get('calc_ingredients', []) if item.get('name') and item.get('weight', 0) > 0]

            if ingredient_list:
                placeholders = ', '.join('?' for _ in ingredient_list)
                query = f"SELECT * FROM NUTRITION_INFO WHERE FOOD_NAME IN ({placeholders})"
                
                with st.spinner("영양성분 정보를 조회하는 중..."):
                    all_nut_info_df = db_query(query, ingredient_list)
                
                if not all_nut_info_df.empty:
                    all_nut_info_df.set_index('FOOD_NAME', inplace=True)
                    for item in st.session_state.get('calc_ingredients', []):
                        if item.get('name') in all_nut_info_df.index and item.get('weight', 0) > 0:
                            info = all_nut_info_df.loc[item['name']]
                            ratio = item['weight'] / 100.0
                            total_nutrition['ENERGY'] += info.get('ENERGY', 0) * ratio
                            total_nutrition['PROTEIN'] += info.get('PROTEIN', 0) * ratio
                            total_nutrition['FAT'] += info.get('FAT', 0) * ratio
                            total_nutrition['CH'] += info.get('CH', 0) * ratio
                            total_nutrition['SUGAR'] += info.get('SUGAR', 0) * ratio
            
            st.subheader("📈 총 영양성분")
            cols_nut = st.columns(5)
            cols_nut[0].metric("에너지", f"{total_nutrition['ENERGY']:.1f} kcal")
            cols_nut[1].metric("탄수화물", f"{total_nutrition['CH']:.1f} g")
            cols_nut[2].metric("단백질", f"{total_nutrition['PROTEIN']:.1f} g")
            cols_nut[3].metric("지방", f"{total_nutrition['FAT']:.1f} g")
            cols_nut[4].metric("당류", f"{total_nutrition['SUGAR']:.1f} g")