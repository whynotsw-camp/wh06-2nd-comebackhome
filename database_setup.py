import streamlit as st
import sqlite3
import pandas as pd
import os
import re
import numpy as np

# 머신러닝 관련 라이브러리
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.metrics import r2_score

# 실제 프로젝트에서는 data_load_func.py에서 이 함수들을 가져옵니다.
from data_load_func import fetch_basic_list, fetch_ingr_list, fetch_prc_list, fetch_all_data

DB_FILE = os.path.join("data", "recipe_app.db")
os.makedirs("data", exist_ok=True)


# --- 칼로리 예측을 위한 헬퍼 함수들 ---
def clean_and_evaluate(expr: str):
    if pd.isna(expr): return np.nan
    expr = str(expr).replace(' ', '').replace('과', '+').replace('와', '+')
    expr = re.sub(r'[^0-9\+\-\*/\.]', '', expr)
    if not expr: return np.nan
    try:
        return round(eval(expr), 3)
    except:
        return np.nan

def clean_ingredient_name(name: str) -> str:
    if pd.isna(name): return ""
    name = re.sub(r'\([^)]*\)', '', str(name)).strip()
    name = re.sub(r'[^ㄱ-ㅎ가-힣a-zA-Z0-9\s]', '', name)
    return name.strip()

# --- 칼로리 예측 및 DB 업데이트 메인 함수 ---
def predict_and_update_calories(conn):
    """DB에서 데이터를 로드하여 칼로리가 0인 레시피의 칼로리를 예측하고 DB를 업데이트합니다."""
    st.info("AI 모델을 사용하여 누락된 칼로리 정보를 예측합니다...")

    df_recipe = pd.read_sql("SELECT RECIPE_ID, CALORIE FROM RECIPE_BASE", conn)
    df_ingr = pd.read_sql("SELECT RECIPE_ID, IRDNT_NM, IRDNT_CPCTY FROM RECIPE_INGREDIENT", conn)

    df_ingr["IRDNT_CPCTY"] = df_ingr["IRDNT_CPCTY"].apply(clean_and_evaluate).fillna(0)
    df_ingr["IRDNT_NM"] = df_ingr["IRDNT_NM"].apply(clean_ingredient_name)
    df_ingr['IRDNT_FULL'] = df_ingr['IRDNT_NM'].astype(str) + ' ' + df_ingr['IRDNT_CPCTY'].astype(str)
    
    df_ingr_grouped = df_ingr.groupby("RECIPE_ID")['IRDNT_FULL'].apply(lambda x: ', '.join(x)).reset_index()

    df = pd.merge(df_recipe, df_ingr_grouped, on="RECIPE_ID", how="left").fillna({'IRDNT_FULL': ''})
    df['CALORIE'] = pd.to_numeric(df['CALORIE'], errors='coerce').fillna(0)
    
    train_df = df[df['CALORIE'] > 0].copy()
    predict_df = df[df['CALORIE'] == 0].copy()

    # --- [핵심 수정] 디버깅을 위한 데이터 확인 코드 ---
    # 터미널에 칼로리가 낮은 순서대로 레시피 20개를 출력하여 데이터 품질 문제 확인
    print("\n" + "="*50)
    print("      AI 모델 학습 데이터 품질 확인 (DEBUGGING)      ")
    print("="*50)
    print("아래는 '칼로리가 낮은 상위 20개 레시피' 목록입니다.")
    print("재료(IRDNT_FULL)에 비해 칼로리가 비정상적으로 낮다면, 해당 데이터의 전처리에 문제가 있을 수 있습니다.")
    print(train_df[['RECIPE_ID', 'CALORIE', 'IRDNT_FULL']].sort_values('CALORIE').head(20))
    print("="*50 + "\n")
    # ----------------------------------------------------

    if predict_df.empty:
        st.toast("✅ 모든 레시피에 칼로리 정보가 있어 예측을 건너뜁니다.", icon="👍")
        return

    pipeline = make_pipeline(
        TfidfVectorizer(),
        RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    )
    pipeline.fit(train_df['IRDNT_FULL'], train_df['CALORIE'])
    
    train_r2 = r2_score(train_df['CALORIE'], pipeline.predict(train_df['IRDNT_FULL']))
    print(f"Calorie Prediction Model Training R² Score: {train_r2:.4f}")

    predicted_calories = pipeline.predict(predict_df['IRDNT_FULL'])
    predict_df['PREDICTED_CALORIE'] = np.round(predicted_calories, 0).astype(int)
    
    update_data = predict_df[['PREDICTED_CALORIE', 'RECIPE_ID']].values.tolist()
    
    cursor = conn.cursor()
    cursor.executemany("UPDATE RECIPE_BASE SET CALORIE = ? WHERE RECIPE_ID = ?", update_data)
    
    st.toast(f"✅ AI가 {len(update_data)}개 레시피의 칼로리를 예측하여 저장했습니다.", icon="🤖")

# --- 메인 DB 설정 함수 ---
def setup_database(model):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS NATION_INFO (
                NATION_CODE INTEGER PRIMARY KEY,
                NATION_NM VARCHAR
            );
            CREATE TABLE IF NOT EXISTS TYPE_INFO (
                TY_CODE INTEGER PRIMARY KEY,
                TY_NM VARCHAR
            );
            CREATE TABLE IF NOT EXISTS RECIPE_BASE (
                RECIPE_ID INTEGER PRIMARY KEY,
                RECIPE_NM_KO VARCHAR,
                SUMRY VARCHAR,
                NATION_CODE INTEGER,
                TY_CODE INTEGER,
                COOKING_TIME INTEGER,
                CALORIE INTEGER,
                QNT INTEGER,
                EMBEDDING BLOB,
                FOREIGN KEY (NATION_CODE) REFERENCES NATION_INFO(NATION_CODE),
                FOREIGN KEY (TY_CODE) REFERENCES TYPE_INFO(TY_CODE)
            );
            CREATE TABLE IF NOT EXISTS RECIPE_INGREDIENT (
                RECIPE_ID INTEGER,
                IRDNT_SN INTEGER,
                IRDNT_NM VARCHAR,
                IRDNT_CPCTY VARCHAR,
                PRIMARY KEY (RECIPE_ID, IRDNT_SN),
                FOREIGN KEY (RECIPE_ID) REFERENCES RECIPE_BASE(RECIPE_ID)
            );
            CREATE TABLE IF NOT EXISTS RECIPE_PROCESS (
                RECIPE_ID INTEGER,
                COOKING_NO INTEGER,
                COOKING_DC TEXT,
                PRIMARY KEY (RECIPE_ID, COOKING_NO),
                FOREIGN KEY (RECIPE_ID) REFERENCES RECIPE_BASE(RECIPE_ID)
            );
            CREATE TABLE IF NOT EXISTS NUTRITION_INFO (
                FOOD_GROUP VARCHAR,
                FOOD_NAME VARCHAR PRIMARY KEY,
                ENERGY INTEGER,
                PROTEIN FLOAT,
                FAT FLOAT,
                CH FLOAT,
                SUGAR FLOAT
            );
            CREATE TABLE IF NOT EXISTS SEARCH_LOG (
                SRCH_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                SRCH_CODE INTEGER,
                SRCH_KEYWORD VARCHAR,
                NATION_CODE INTEGER,
                SRCH_TIME DATETIME
            );
            CREATE TABLE IF NOT EXISTS RECOMMEND_LOG (
                REC_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                SRCH_ID INTEGER,
                RECIPE_ID INTEGER,
                FOREIGN KEY (SRCH_ID) REFERENCES SEARCH_LOG(SRCH_ID),
                FOREIGN KEY (RECIPE_ID) REFERENCES RECIPE_BASE(RECIPE_ID)
            );
            CREATE TABLE IF NOT EXISTS DWELL_TIME_LOG (
                VIEW_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                SRCH_ID INTEGER,
                RECIPE_ID INTEGER,
                START_TIME DATETIME,
                DWELL_TIME INTEGER,
                FOREIGN KEY (SRCH_ID) REFERENCES SEARCH_LOG(SRCH_ID),
                FOREIGN KEY (RECIPE_ID) REFERENCES RECIPE_BASE(RECIPE_ID)
            );
        """)
        conn.commit()

        is_recipe_empty = cursor.execute("SELECT COUNT(*) FROM RECIPE_BASE").fetchone()[0] == 0
        if is_recipe_empty:
            with st.spinner('최초 실행: DB 설정 및 AI 모델링 중... (약 3-5분 소요)'):
                try:
                    # 1. API 데이터 로드 및 저장
                    df_basic_raw = fetch_all_data(fetch_basic_list, total=1000, step=100)
                    df_ingr_raw = fetch_all_data(fetch_ingr_list, total=6200, step=100)
                    df_prc_raw = fetch_all_data(fetch_prc_list,  total=3100, step=100)
                    
                    df_basic = df_basic_raw.copy()
                    df_ingr = df_ingr_raw.copy()
                    
                    df_basic['NATION_NM'] = df_basic['NATION_NM'].replace({'일본':'일식', '중국':'중식', '이탈리아':'양식', '서양':'양식', '동남아시아':'기타', '퓨전':'기타'})
                    df_basic['NATION_CODE'] = df_basic['NATION_CODE'].replace({'3020009':'3020005', '3020006':'3020002'})
                    for col in ['CALORIE', 'COOKING_TIME', 'QNT']:
                        df_basic[col] = pd.to_numeric(df_basic[col].str.replace(r'[^\d.]', '', regex=True), errors='coerce').fillna(0).astype(int)
                    df_ingr.loc[:, 'IRDNT_SN'] = df_ingr.groupby('RECIPE_ID').cumcount() + 1

                    RECIPE_BASE_df = df_basic[['RECIPE_ID', 'RECIPE_NM_KO', 'SUMRY', 'NATION_CODE', 'TY_CODE', 'COOKING_TIME', 'CALORIE', 'QNT']].copy()
                    recipe_names = RECIPE_BASE_df["RECIPE_NM_KO"].fillna("").tolist()
                    embeddings = model.encode(recipe_names, show_progress_bar=True)
                    RECIPE_BASE_df.loc[:, 'EMBEDDING'] = [e.tobytes() for e in embeddings]

                    NATION_INFO_df = df_basic[['NATION_CODE', 'NATION_NM']].drop_duplicates().sort_values(by='NATION_CODE').reset_index(drop=True)
                    TYPE_INFO_df = df_basic[['TY_CODE', 'TY_NM']].drop_duplicates().sort_values(by='TY_CODE').reset_index(drop=True)
                    RECIPE_INGREDIENT_df = df_ingr[['RECIPE_ID', 'IRDNT_SN', 'IRDNT_NM', 'IRDNT_CPCTY']]
                    RECIPE_PROCESS_df = df_prc_raw[['RECIPE_ID', 'COOKING_NO', 'COOKING_DC']]

                    NATION_INFO_df.to_sql('NATION_INFO', conn, if_exists='replace', index=False)
                    TYPE_INFO_df.to_sql('TYPE_INFO', conn, if_exists='replace', index=False)
                    RECIPE_BASE_df.to_sql('RECIPE_BASE', conn, if_exists='replace', index=False)
                    RECIPE_INGREDIENT_df.to_sql('RECIPE_INGREDIENT', conn, if_exists='replace', index=False)
                    RECIPE_PROCESS_df.to_sql('RECIPE_PROCESS', conn, if_exists='replace', index=False)
                    
                    st.toast("✅ API 레시피 및 AI 임베딩 저장 완료!", icon="🚀")

                    # 2. 누락된 칼로리 예측 및 업데이트
                    predict_and_update_calories(conn)

                    # 3. 영양 정보 로드 및 저장
                    is_nutrition_empty = cursor.execute("SELECT COUNT(*) FROM NUTRITION_INFO").fetchone()[0] == 0
                    if is_nutrition_empty:
                        NUTRITION_FILE_PATH = './data/nutrition_info.csv'
                        if os.path.exists(NUTRITION_FILE_PATH):
                            df_nutrition_raw = pd.read_csv(NUTRITION_FILE_PATH, encoding='utf-8-sig', skiprows=[1])
                            df_nutrition_raw.columns = df_nutrition_raw.columns.str.strip()
                            df_nutrition = df_nutrition_raw[['식품군', '식품명', '에너지', '탄수화물', '단백질', '지방', '당류']].rename(columns={'식품군':'FOOD_GROUP', '식품명':'FOOD_NAME', '에너지':'ENERGY', '탄수화물':'CH', '단백질':'PROTEIN', '지방':'FAT', '당류':'SUGAR'})
                            for col in df_nutrition.columns.drop(['FOOD_GROUP', 'FOOD_NAME']):
                                df_nutrition[col] = pd.to_numeric(df_nutrition[col], errors='coerce').fillna(0)
                            df_nutrition.to_sql('NUTRITION_INFO', conn, if_exists='replace', index=False)
                            st.toast(f"✅ CSV 영양 정보 {len(df_nutrition)}개 저장 완료!", icon="📊")
                        else:
                            st.warning(f"'{NUTRITION_FILE_PATH}' 파일을 찾을 수 없습니다.")

                    # 4. 모든 작업이 성공하면 최종 커밋
                    conn.commit()

                except Exception as e:
                    if conn: conn.rollback()
                    st.error(f"초기 데이터 구축 중 오류 발생. DB 변경사항이 롤백되었습니다: {e}")
                    import traceback
                    traceback.print_exc()
    
    finally:
        if conn:
            conn.close()