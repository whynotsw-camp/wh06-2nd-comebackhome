import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import plotly.express as px
import re
# <<< 수정된 부분: 유튜브 API 연동을 위한 라이브러리 임포트 >>>
from dotenv import load_dotenv
from googleapiclient.discovery import build

# --- 1. 데이터베이스 설정 및 관리 ---
DB_FILE = "recipe_service.db"

def setup_database():
    """앱 실행 시 한 번만 호출되어 DB 및 테이블, 샘플 데이터를 생성합니다."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 테이블 생성 (기존 + 영양성분 계산기용 테이블 추가)
    cursor.execute('''CREATE TABLE IF NOT EXISTS recipes (RECIPE_ID INTEGER PRIMARY KEY, RECIPE_NM_KO TEXT, NATION_NM TEXT, TY_NM TEXT, CALORIE REAL, PROTEIN REAL, FAT REAL, CARBOHYDRATE REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ingredients (INGREDIENT_ID INTEGER PRIMARY KEY AUTOINCREMENT, RECIPE_ID INTEGER, INGREDIENT_NAME TEXT, FOREIGN KEY (RECIPE_ID) REFERENCES recipes (RECIPE_ID))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS steps (STEP_ID INTEGER PRIMARY KEY AUTOINCREMENT, RECIPE_ID INTEGER, STEP_DESCRIPTION TEXT, FOREIGN KEY (RECIPE_ID) REFERENCES recipes (RECIPE_ID))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS search_logs (LOG_ID INTEGER PRIMARY KEY AUTOINCREMENT, KEYWORD TEXT, SEARCH_TIME TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS dwell_time_logs (LOG_ID INTEGER PRIMARY KEY AUTOINCREMENT, RECIPE_ID INTEGER, RECIPE_NM_KO TEXT, DWELL_SECONDS REAL, LOG_TIME TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS ingredient_nutrition (INGREDIENT_NAME TEXT PRIMARY KEY, CALORIE_PER_100G REAL, PROTEIN_PER_100G REAL, FAT_PER_100G REAL, CARBS_PER_100G REAL)''')

    # 샘플 데이터가 없는 경우에만 삽입
    if cursor.execute("SELECT COUNT(*) FROM recipes").fetchone()[0] == 0:
        recipe_data = [{'RECIPE_ID': 1, 'RECIPE_NM_KO': '닭볶음탕', 'NATION_NM': '한식', 'TY_NM': '메인요리', 'CALORIE': 550, 'PROTEIN': 45, 'FAT': 25, 'CARBOHYDRATE': 35},
                       {'RECIPE_ID': 2, 'RECIPE_NM_KO': '김치찌개', 'NATION_NM': '한식', 'TY_NM': '찌개', 'CALORIE': 350, 'PROTEIN': 25, 'FAT': 18, 'CARBOHYDRATE': 15},
                       {'RECIPE_ID': 3, 'RECIPE_NM_KO': '토마토 스파게티', 'NATION_NM': '양식', 'TY_NM': '면요리', 'CALORIE': 650, 'PROTEIN': 20, 'FAT': 15, 'CARBOHYDRATE': 80}]
        pd.DataFrame(recipe_data).to_sql('recipes', conn, if_exists='append', index=False)

    if cursor.execute("SELECT COUNT(*) FROM ingredient_nutrition").fetchone()[0] == 0:
        nutrition_data = [
            ('닭고기', 230, 27, 14, 0), ('감자', 77, 2, 0.1, 17), ('양파', 40, 1.1, 0.1, 9),
            ('김치', 34, 2, 0.5, 5), ('돼지고기', 242, 27, 14, 0), ('토마토 소스', 29, 1.3, 0.2, 5),
            ('스파게티면', 158, 5.5, 0.8, 31), ('두부', 76, 8, 4.8, 1.9), ('양상추', 15, 0.9, 0.2, 3),
            ('계란', 155, 13, 11, 1.1), ('쌀밥', 130, 2.7, 0.3, 28)
        ]
        cursor.executemany("INSERT INTO ingredient_nutrition VALUES (?, ?, ?, ?, ?)", nutrition_data)
    
    conn.commit()
    conn.close()

# --- 2. 헬퍼 함수 (DB 쿼리, 로그, API) ---
def db_query(query, params=()):
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query(query, conn, params=params)

def end_current_view_log(): # 체류시간 기록 함수
    if 'current_view' in st.session_state and st.session_state.current_view:
        dwell_time = (datetime.now() - st.session_state.current_view['start_time']).total_seconds()
        if dwell_time > 3:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute("INSERT INTO dwell_time_logs (RECIPE_ID, RECIPE_NM_KO, DWELL_SECONDS, LOG_TIME) VALUES (?, ?, ?, ?)",
                             (st.session_state.current_view['id'], st.session_state.current_view['name'], round(dwell_time, 2), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        st.session_state.current_view = None

def search_by_recipe_name(keyword, nation):
    query = "SELECT RECIPE_ID, RECIPE_NM_KO FROM recipes WHERE RECIPE_NM_KO LIKE ? AND (? = '전체' OR NATION_NM = ?)"
    return db_query(query, (f'%{keyword}%', nation, nation))

###########################################################################
# --- 영양성분 계산기 함수 --- @@@@
CSV_FILE_PATH = 'nutrition_info.CSV'
SEARCH_COLUMN = '식품명'
NUTRITION_COLUMNS = ['에너지', '탄수화물', '단백질', '지방 ', '당류']

@st.cache_data
def load_nutrition_data(file_path):
    """CSV에서 영양성분 데이터를 로드하고 캐시합니다."""
    try:
        df = pd.read_csv(file_path, encoding='utf-8-sig')
        df = df.iloc[2:].reset_index(drop=True) # 불필요한 행 제거
        # 숫자형으로 변환, 변환 불가 시 0으로 처리
        for col in NUTRITION_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                df[col] = df[col].fillna(0)
        return df
    except FileNotFoundError:
        st.error(f"오류: '{file_path}' 파일을 찾을 수 없습니다.")
        return None

@st.cache_data
def build_keywords(df):
    """데이터프레임에서 검색을 위한 키워드와 동의어 사전을 만듭니다."""
    all_food_names = df[SEARCH_COLUMN].dropna().unique()
    keywords = set(p for name in all_food_names for p in re.split(r'[,\s]+', name) if p)
    synonyms = {'닭': '닭고기', '돼지': '돼지고기', '소': '쇠고기', '계란': '달걀', '생': '생것', '구운': '구이', '삶은': '삶기', '튀긴': '튀김', '가슴': '가슴살'}
    return keywords, synonyms

def find_best_match(search_query: str, df: pd.DataFrame, keywords: set, synonyms: dict):
    """사용자 입력에 가장 잘 맞는 항목을 점수 기반으로 찾습니다."""
    search_query_parts = set(re.split(r'[,\s]+', search_query))
    extracted_keywords = keywords.intersection(search_query_parts)
    
    normalized_keywords = {synonyms.get(key, key) for key in extracted_keywords}
    for syn, real_key in synonyms.items():
        if syn in search_query:
            normalized_keywords.add(real_key)

    if not normalized_keywords:
        return None

    def calculate_score(row_food_name):
        return sum(1 for key in normalized_keywords if key in row_food_name)

    df['match_score'] = df[SEARCH_COLUMN].apply(calculate_score)
    relevant_results = df[df['match_score'] > 0]

    if relevant_results.empty:
        return None

    # 최대 점수를 가진 행 찾기
    max_score = relevant_results['match_score'].max()
    best_match_row = relevant_results[relevant_results['match_score'] == max_score].iloc[0]
    return best_match_row

# 세션 상태 초기화
if 'current_view' not in st.session_state: st.session_state.current_view = None
if 'calculator_ingredients' not in st.session_state: st.session_state.calculator_ingredients = []

#################################################################################



# .env에서 API 키 불러오기
load_dotenv()
api_key = os.getenv("YOUTUBE_API_KEY")

# <<< 실제 YouTube API 호출 함수 >>>
def get_youtube_videos(query, max_results=2):
    st.info(f"🔍 유튜브에서 '{query}'(을)를 검색합니다...")

    if not api_key:
        st.error("❗ 유튜브 API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        return []

    try:
        # 유튜브 API 클라이언트 생성
        youtube = build("youtube", "v3", developerKey=api_key)
        
        # 검색 요청
        request = youtube.search().list(
            part="snippet",
            q=f"{query} 레시피",  # 검색어를 더 구체적으로
            maxResults=max_results,
            type="video",
            order="viewCount" # 조회수 순으로 정렬
        )
        response = request.execute()

        videos = []
        for item in response.get("items", []):
            video = {
                "title": item["snippet"]["title"],
                "video_id": item["id"]["videoId"]
            }
            videos.append(video)
        
        if not videos:
            st.warning("관련 유튜브 영상을 찾지 못했습니다.")
        return videos

    except Exception as e:
        st.error(f"❗ 유튜브 API 호출 중 오류가 발생했습니다: {e}")
        return []

def get_youtube_trends(): # 유튜브 트렌드 분석 (가상임)
    trends_df = pd.DataFrame({
        'trend_keyword': ['마라탕', '탕후루', '약과', '제로 음료', '단백질 쉐이크'],
        'search_volume': [1200, 1150, 980, 850, 700]
    })
    return trends_df

# <<< 실제 공공데이터 레시피 API 호출 함수 >>>

# <<< 실제  API 호출 함수 >>>

# --- 3. Streamlit UI ---
st.set_page_config(layout="wide", page_title="레시피 추천 서비스")
setup_database()

if 'current_view' not in st.session_state:
    st.session_state.current_view = None

st.title("�� 레시피 추천 및 분석 서비스")

tab1, tab2, tab3 = st.tabs(["📊 레시피 검색", "📈 트렌드 분석", "🧮 영양성분 계산기"])

# --- 탭 1: 레시피 검색 ---
with tab1:
    col1, col2 = st.columns([0.4, 0.6])
    with col1:
        st.subheader("1. 검색 유형 선택")
        search_mode = st.radio("어떤 레시피를 찾으시나요?", ["일반 검색 (음식/재료명)", "테마별 검색 (비건, 다이어트 등)"], horizontal=True)
        st.divider()

        # 검색 로직 (기존과 동일)
        if search_mode == "일반 검색 (음식/재료명)":
            st.subheader("2. 검색 조건 입력")
            keyword = st.text_input("음식명 또는 재료명을 입력하세요:")
            nation_filter = st.selectbox("음식 종류", ["전체", "한식", "중식", "양식"])

            if st.button("레시피 검색", key="normal_search"):
                end_current_view_log()
                if keyword:
                    with sqlite3.connect(DB_FILE) as conn:
                         conn.execute("INSERT INTO search_logs (KEYWORD, SEARCH_TIME) VALUES (?, ?)", (keyword, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                    st.session_state.search_results = search_by_recipe_name(keyword, nation_filter)
                    st.session_state.selected_recipe_id = None
                else:
                    st.warning("검색어를 입력해주세요.")
            
            if 'search_results' in st.session_state and not st.session_state.search_results.empty:
                st.subheader("3. 검색 결과")
                recipe_options = pd.Series(st.session_state.search_results.RECIPE_NM_KO.values, index=st.session_state.search_results.RECIPE_ID).to_dict()
                selected_recipe_id = st.selectbox("레시피 선택:", options=recipe_options.keys(), format_func=lambda x: recipe_options.get(x, "선택"), index=None)
                
                if selected_recipe_id:
                    if not st.session_state.current_view or st.session_state.current_view['id'] != selected_recipe_id:
                        end_current_view_log()
                        st.session_state.current_view = {'id': selected_recipe_id, 'name': recipe_options[selected_recipe_id], 'start_time': datetime.now()}
                    st.session_state.selected_recipe_id = selected_recipe_id

        if search_mode == "테마별 검색 (비건, 다이어트 등)":
            st.subheader("2. 테마 선택")
            theme_keyword = st.selectbox("원하는 테마를 선택하세요.", ["비건 요리", "고단백질 다이어트", "저탄수화물 식단"])
            if st.button("테마로 영상 검색", key="theme_search"):
                st.session_state.theme_videos = get_youtube_videos(theme_keyword, max_results=5)
                st.session_state.selected_recipe_id = None
                end_current_view_log()

    with col2:
        st.subheader("결과 보기")
        if 'selected_recipe_id' in st.session_state and st.session_state.selected_recipe_id:
            info = db_query("SELECT * FROM recipes WHERE RECIPE_ID = ?", (st.session_state.selected_recipe_id,)).iloc[0]
            st.markdown(f"### 🍽️ {info['RECIPE_NM_KO']}")
            # 유튜브 영상 출력
            videos = get_youtube_videos(info['RECIPE_NM_KO'])
            if videos:
                for video in videos:
                    st.write(f"**{video['title']}**")
                    st.video(f"https://www.youtube.com/watch?v={video['video_id']}")

        elif 'theme_videos' in st.session_state and st.session_state.theme_videos:
             st.markdown(f"### 🎥 '{theme_keyword}' 추천 유튜브 영상")
             for video in st.session_state.theme_videos:
                 st.write(f"**{video['title']}**")
                 st.video(f"https://www.youtube.com/watch?v={video['video_id']}")
        else:
            st.info("왼쪽에서 레시피를 검색하거나 테마를 선택해주세요.")

# --- 탭 2: 트렌드 분석 ---
with tab2:
    st.header("트렌드 데이터 분석")
    st.subheader("1. 내부 검색어 트렌드 분석")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**키워드별 검색 빈도**")
        keyword_df = db_query("SELECT KEYWORD, COUNT(*) as count FROM search_logs GROUP BY KEYWORD ORDER BY count DESC")
        st.dataframe(keyword_df, use_container_width=True)
        if not keyword_df.empty:
            fig1 = px.bar(keyword_df.head(10), x='KEYWORD', y='count', title='인기 검색어 TOP 10')
            st.plotly_chart(fig1, use_container_width=True)
            
    with col2:
        st.markdown("**레시피별 평균 체류 시간(초)**")
        dwell_df = db_query("SELECT RECIPE_NM_KO, ROUND(AVG(DWELL_SECONDS), 2) as avg_dwell_sec FROM dwell_time_logs GROUP BY RECIPE_ID, RECIPE_NM_KO ORDER BY avg_dwell_sec DESC")
        st.dataframe(dwell_df, use_container_width=True)
        if not dwell_df.empty:
            fig2 = px.bar(dwell_df.head(10), x='RECIPE_NM_KO', y='avg_dwell_sec', title='평균 체류 시간이 긴 레시피 TOP 10')
            st.plotly_chart(fig2, use_container_width=True)

    # st.divider()
    # st.subheader("2. 유튜브 API 활용 트렌드 분석 (가상)")
    # yt_trends = get_youtube_trends()
    # st.markdown("최근 대중적으로 관심있는 음식 키워드입니다. (주기적 수집 데이터 예시)")
    # st.dataframe(yt_trends, use_container_width=True)
    # fig3 = px.pie(yt_trends, names='trend_keyword', values='search_volume', title='유튜브 인기 음식 키워드 점유율')
    # st.plotly_chart(fig3, use_container_width=True)

# --- 탭 3: 영양성분 계산기 ---
with tab3:
    st.header("영양성분 계산기")
    st.info("재료명을 검색하여 목록에 추가하고 그램(g)을 입력하면 총 영양성분이 계산됩니다.")

    main_df = load_nutrition_data(CSV_FILE_PATH)

    if main_df is not None:
        keyword_vocab, synonym_map = build_keywords(main_df)

        # 1. 재료 검색 및 추가
        search_query = st.text_input("재료명을 검색하세요 (예: '삶은계란'):")
        
        if search_query:
            best_match = find_best_match(search_query, main_df.copy(), keyword_vocab, synonym_map)
            if best_match is not None:
                st.write(f"**검색 결과:** {best_match[SEARCH_COLUMN]}")
                if st.button("목록에 추가하기", key=f"add_{search_query}"):
                    # 중복 추가 방지
                    if not any(d['name'] == best_match[SEARCH_COLUMN] for d in st.session_state.calculator_ingredients):
                        st.session_state.calculator_ingredients.append({
                            'name': best_match[SEARCH_COLUMN],
                            'nutrients_per_100g': best_match[NUTRITION_COLUMNS],
                            'grams': 100  # 기본값 100g
                        })
                    else:
                        st.warning("이미 목록에 있는 항목입니다.")
            else:
                st.warning("일치하는 항목을 찾을 수 없습니다.")
        
        st.divider()

        # 2. 선택된 재료 목록 및 총 영양성분 계산
        total_nutrition = {col: 0.0 for col in NUTRITION_COLUMNS}
        
        if st.session_state.calculator_ingredients:
            st.subheader("계산 목록")
            
            # 목록의 각 항목을 삭제하기 위한 로직
            indices_to_remove = []
            for i, item in enumerate(st.session_state.calculator_ingredients):
                col1, col2, col3 = st.columns([4, 2, 1])
                with col1:
                    st.write(item['name'])
                with col2:
                    item['grams'] = st.number_input(f"그램(g)", min_value=0, value=item['grams'], step=10, key=f"grams_{i}")
                with col3:
                    if st.button("삭제", key=f"del_{i}"):
                        indices_to_remove.append(i)

                # 총 영양성분 계산
                for col in NUTRITION_COLUMNS:
                    total_nutrition[col] += (item['nutrients_per_100g'][col] * item['grams'] / 100)

            # 삭제할 항목들을 역순으로 제거
            for i in sorted(indices_to_remove, reverse=True):
                st.session_state.calculator_ingredients.pop(i)
                st.rerun()

            st.divider()
            st.subheader("총 영양성분 합계")
            kpi_cols = st.columns(5)
            kpi_cols[0].metric("총 에너지 (kcal)", f"{total_nutrition.get('에너지', 0):.1f}")
            kpi_cols[1].metric("총 탄수화물 (g)", f"{total_nutrition.get('탄수화물', 0):.1f}")
            kpi_cols[2].metric("총 단백질 (g)", f"{total_nutrition.get('단백질', 0):.1f}")
            kpi_cols[3].metric("총 지방 (g)", f"{total_nutrition.get('지방 ', 0):.1f}")
            kpi_cols[4].metric("총 당류 (g)", f"{total_nutrition.get('당류', 0):.1f}")
        else:
            st.write("계산할 재료를 검색하여 추가해주세요.") 