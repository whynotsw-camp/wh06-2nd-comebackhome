import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
import pytz

# 한국 시간대 설정
korea = pytz.timezone('Asia/Seoul')

import firebase_admin
from firebase_admin import credentials, firestore

# 이미 초기화된 경우 건너뛰기
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase_key.json")
    firebase_admin.initialize_app(cred)

firestore_db = firestore.client()

# --- Firebase 로그 저장 함수 (ERD 컬럼명에 맞게) ---
def log_search_to_firebase(srch_id, srch_code, srch_keyword, nation_code):
    now_korea = datetime.now(korea)
    firestore_db.collection("SEARCH_LOG").add({
        "SRCH_ID": srch_id,
        "SRCH_CODE": srch_code,
        "SRCH_KEYWORD": srch_keyword,
        "NATION_CODE": nation_code,
        "SRCH_TIME": now_korea
    })

def log_recommend_to_firebase(rec_id, srch_id, recipe_id):
    firestore_db.collection("RECOMMEND_LOG").add({
        "REC_ID": rec_id,
        "SRCH_ID": srch_id,
        "RECIPE_ID": recipe_id
    })

def log_dwell_to_firebase(view_id, srch_id, rec_id, start_time, dwell_time):
    firestore_db.collection("DWELL_TIME_LOG").add({
        "VIEW_ID": view_id,
        "SRCH_ID": srch_id,
        "REC_ID": rec_id,
        "START_TIME": start_time,
        "DWELL_TIME": dwell_time
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

def save_dwell_log_if_needed():
    view_info = st.session_state.get('view_start_time')
    if view_info and 'time' in view_info:
        dwell_seconds = (datetime.now() - view_info['time']).total_seconds()
        if dwell_seconds > 3:
            view_id = None
            srch_id = view_info['srch_id']
            rec_id = None
            start_time = view_info['time']
            dwell_time = int(dwell_seconds)
            log_dwell_to_firebase(view_id, srch_id, rec_id, start_time, dwell_time)
    st.session_state.view_start_time = None

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
            save_dwell_log_if_needed()  # 새 검색 시 이전 상세 체류 로그 저장
            if keyword:
                st.session_state.current_search_keyword = keyword
                st.session_state.selected_recipe_id = None
                st.session_state.youtube_videos = []
                st.session_state.next_page_token = None
                st.session_state.search_results = pd.DataFrame()

                srch_code = search_by_options[search_by_label]
                log_nation_code = selected_nation_code if is_recipe_search else None
                srch_id = log_search(srch_code, keyword, log_nation_code)
                st.session_state.current_search_id = srch_id

                # ✅ Firebase에 검색 로그 저장 (ERD 컬럼명)
                log_search_to_firebase(srch_id, srch_code, keyword, log_nation_code)

                if is_recipe_search:
                    with st.spinner("AI가 레시피를 찾고 있습니다..."):
                        if search_by_label == "레시피명 (AI 추천)":
                            results = search_by_name_bert(keyword, model, selected_nation_code, selected_type_code)
                        else:
                            results = search_by_ingredient(keyword, selected_nation_code, selected_type_code)
                        st.session_state.search_results = results
                    if not results.empty:
                        log_recommendations(srch_id, results)
                        # ✅ Firebase에 추천 로그 저장 (ERD 컬럼명)
                        for idx, row in results.iterrows():
                            rec_id = None  # Firestore는 자동 증가 없음, 필요시 None 또는 row index 사용
                            log_recommend_to_firebase(rec_id, srch_id, int(row['RECIPE_ID']))
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
                    save_dwell_log_if_needed()  # 다른 레시피 클릭 시 이전 상세 체류 로그 저장
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

        if not st.session_state.selected_recipe_id and not st.session_state.youtube_videos:
            st.info("왼쪽에서 검색 조건을 선택하고 검색어를 입력해주세요.")

# --- 탭 2: 트렌드 분석 ---
with tab2:
    # (탭2 코드는 변경 없음)
    st.header("📈 트렌드 데이터 분석")
    st.info("사용자 행동 로그를 기반으로 한 심층 분석입니다.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("인기 검색 키워드")
        q1 = "SELECT SRCH_KEYWORD, COUNT(*) as count FROM SEARCH_LOG GROUP BY SRCH_KEYWORD ORDER BY count DESC LIMIT 10"
        df1 = db_query(q1)
        if not df1.empty:
            fig1 = px.bar(df1, x='SRCH_KEYWORD', y='count', title='TOP 10 검색 키워드', text_auto=True)
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("검색 기록이 없습니다.")

    with col2:
        st.subheader("가장 많이 본 레시피")
        q2 = """
            SELECT r.RECIPE_NM_KO, COUNT(d.VIEW_ID) as view_count
            FROM DWELL_TIME_LOG d
            JOIN RECIPE_BASE r ON d.RECIPE_ID = r.RECIPE_ID
            GROUP BY d.RECIPE_ID, r.RECIPE_NM_KO
            ORDER BY view_count DESC LIMIT 10
        """
        df2 = db_query(q2)
        if not df2.empty:
            fig2 = px.bar(df2, x='RECIPE_NM_KO', y='view_count', title='TOP 10 조회수 레시피', text_auto=True)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("조회 기록이 없습니다.")

    st.divider()
    st.subheader("검색어별 평균 레시피 체류시간")
    st.caption("단위: 초")
    q3 = """
        SELECT s.SRCH_KEYWORD, AVG(d.DWELL_TIME) as avg_dwell
        FROM DWELL_TIME_LOG d
        JOIN SEARCH_LOG s ON d.SRCH_ID = s.SRCH_ID
        WHERE d.DWELL_TIME IS NOT NULL AND d.DWELL_TIME < 1800 -- 30분 이상은 이상치로 간주
        GROUP BY s.SRCH_KEYWORD
        HAVING COUNT(d.VIEW_ID) > 2 
        ORDER BY avg_dwell DESC LIMIT 10
    """
    df3 = db_query(q3)
    if not df3.empty:
        df3['avg_dwell'] = df3['avg_dwell'].round(1)
        fig3 = px.bar(df3, x='SRCH_KEYWORD', y='avg_dwell', title='검색어별 평균 체류시간 (초)', text_auto=True, labels={'avg_dwell': '평균 체류시간(초)'})
        st.plotly_chart(fig3, use_container_width=True)
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