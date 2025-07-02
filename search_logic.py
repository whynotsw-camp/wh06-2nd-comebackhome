import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime

from database_setup import DB_FILE

@st.cache_resource
def load_bert_model():
    """SentenceTransformer 모델을 로드합니다."""
    return SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def db_query(query, params=()):
    """데이터베이스 쿼리를 실행하고 결과를 DataFrame으로 반환합니다."""
    with sqlite3.connect(DB_FILE) as conn:
        return pd.read_sql_query(query, conn, params=params)

def search_by_name_bert(query: str, model, nation_code: int = None, type_code: int = None, top_k: int = 15):
    """
    AI 검색에 카테고리 필터링 기능을 추가합니다.
    """
    sql_query = "SELECT RECIPE_ID, RECIPE_NM_KO, EMBEDDING FROM RECIPE_BASE WHERE EMBEDDING IS NOT NULL"
    params = []

    if nation_code:
        sql_query += " AND NATION_CODE = ?"
        params.append(nation_code)
    if type_code:
        sql_query += " AND TY_CODE = ?"
        params.append(type_code)

    df_base = db_query(sql_query, tuple(params))
    
    if df_base.empty:
        return pd.DataFrame()

    # --- 4. 임베딩 비교 로직 (필터링된 결과 내에서 수행) ---
    all_embeddings = np.array([np.frombuffer(e, dtype=np.float32) for e in df_base['EMBEDDING']])
    query_embedding = model.encode([query])[0]
    sim_scores = cosine_similarity([query_embedding], all_embeddings)[0]
    
    top_indices = sim_scores.argsort()[::-1][:top_k]
    
    df_similar = df_base.iloc[top_indices].copy()
    df_similar["유사도"] = sim_scores[top_indices]
    
    return df_similar.drop(columns=['EMBEDDING'])

def search_by_ingredient(keyword: str, nation_code: int = None, type_code: int = None):
    """
    재료 검색에 카테고리 필터링 기능을 추가합니다.
    """
    sql_query = """
        SELECT DISTINCT b.RECIPE_ID, b.RECIPE_NM_KO
        FROM RECIPE_BASE b
        JOIN RECIPE_INGREDIENT i ON b.RECIPE_ID = i.RECIPE_ID
        WHERE i.IRDNT_NM LIKE ?
    """
    params = [f'%{keyword}%']

    if nation_code:
        sql_query += " AND b.NATION_CODE = ?"
        params.append(nation_code)
    if type_code:
        sql_query += " AND b.TY_CODE = ?"
        params.append(type_code)

    return db_query(sql_query, tuple(params))

def fetch_recipe_detail(recipe_id: int):
    """특정 레시피 ID에 해당하는 상세 정보를 DB에서 조회합니다."""
    with sqlite3.connect(DB_FILE) as conn:
        base_query = """
            SELECT rb.*, ni.NATION_NM, ti.TY_NM
            FROM RECIPE_BASE rb
            LEFT JOIN NATION_INFO ni ON rb.NATION_CODE = ni.NATION_CODE
            LEFT JOIN TYPE_INFO ti ON rb.TY_CODE = ti.TY_CODE
            WHERE rb.RECIPE_ID = ?
        """
        base_df = pd.read_sql_query(base_query, conn, params=(recipe_id,))
        if base_df.empty:
            return None
        base = base_df.to_dict(orient="records")[0]
        ingredients = pd.read_sql_query("SELECT IRDNT_NM, IRDNT_CPCTY FROM RECIPE_INGREDIENT WHERE RECIPE_ID = ? ORDER BY IRDNT_SN", conn, params=(recipe_id,)).to_dict(orient="records")
        process = pd.read_sql_query("SELECT COOKING_DC FROM RECIPE_PROCESS WHERE RECIPE_ID = ? ORDER BY COOKING_NO", conn, params=(recipe_id,)).to_dict(orient="records")
    return {"base": base, "ingredients": ingredients, "process": process}

def log_search(srch_code: int, keyword: str, nation_code: int = None):
    """검색 기록을 SEARCH_LOG에 저장하고 생성된 SRCH_ID를 반환합니다."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO SEARCH_LOG (SRCH_CODE, SRCH_KEYWORD, NATION_CODE, SRCH_TIME) VALUES (?, ?, ?, ?)",
            (srch_code, keyword, nation_code, datetime.now())
        )
        return cursor.lastrowid

def log_recommendations(srch_id: int, results_df: pd.DataFrame):
    """추천된 레시피 목록을 RECOMMEND_LOG에 저장합니다."""
    if 'RECIPE_ID' not in results_df.columns:
        return
    with sqlite3.connect(DB_FILE) as conn:
        for recipe_id in results_df['RECIPE_ID']:
            conn.execute(
                "INSERT INTO RECOMMEND_LOG (SRCH_ID, RECIPE_ID) VALUES (?, ?)",
                (srch_id, int(recipe_id))
            )

def log_dwell_time(session_state):
    """레시피 상세 페이지 체류 시간을 DWELL_TIME_LOG에 저장합니다."""
    if 'view_start_time' in session_state and session_state.view_start_time:
        view_info = session_state.view_start_time
        dwell_seconds = (datetime.now() - view_info['time']).total_seconds()
        if dwell_seconds > 3:
            with sqlite3.connect(DB_FILE) as conn:
                conn.execute(
                    "INSERT INTO DWELL_TIME_LOG (SRCH_ID, RECIPE_ID, START_TIME, DWELL_TIME) VALUES (?, ?, ?, ?)",
                    (view_info['srch_id'], view_info['recipe_id'], view_info['time'], int(dwell_seconds))
                )