import pandas as pd
import requests

def fetch_all_data(fetch_function, total, step=1000):
    """
    주어진 fetch 함수를 여러 번 호출하여 전체 데이터를 가져오는 헬퍼 함수입니다.
    """
    dfs = []
    for start in range(1, total + 1, step):
        end = start + step - 1
        if end > total:
            end = total
        try:
            print(f"Fetching data from {start} to {end}...")
            df = fetch_function(start, end)
            dfs.append(df)
        except Exception as e:
            print(f"Error fetching data from {start} to {end}: {e}")
            break
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)

def _fetch_from_api(endpoint, start, end):
    """API 호출을 위한 내부 헬퍼 함수"""
    api_key = '7a23a3b51fd97cd3f70d137e5d0a64bb3aff4d746dcad2424b3ee8b5421fe3d3'
    url = f"http://211.237.50.150:7080/openapi/{api_key}/json/{endpoint}/{start}/{end}"
    response = requests.get(url, timeout=30) # 타임아웃 시간 증가
    response.raise_for_status()
    data = response.json()
    if endpoint not in data or 'row' not in data[endpoint]:
        return pd.DataFrame() # 데이터가 없는 경우 빈 데이터프레임 반환
    return pd.DataFrame(data[endpoint]['row'])

def fetch_basic_list(start=1, end=5):
    """레시피 기본 정보 리스트를 API로부터 가져옵니다."""
    return _fetch_from_api("Grid_20150827000000000226_1", start, end)

def fetch_ingr_list(start=1, end=5):
    """레시피 재료 정보 리스트를 API로부터 가져옵니다."""
    return _fetch_from_api("Grid_20150827000000000227_1", start, end)

def fetch_prc_list(start=1, end=5):
    """레시피 과정 정보 리스트를 API로부터 가져옵니다."""
    return _fetch_from_api("Grid_20150827000000000228_1", start, end)

def load_nutrition(file_path, sheet_name):
    """
    Excel 파일에서 영양 정보를 로드하고 전처리합니다.
    """
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=1)
        df.columns = df.columns.str.strip()
        
        # 필요한 컬럼과 새 컬럼명 매핑
        required_cols = {
            '식품군': 'FOOD_GROUP', '식품명': 'FOOD_NAME', '에너지(kcal)': 'ENERGY',
            '단백질(g)': 'PROTEIN', '지방(g)': 'FAT', '탄수화물(g)': 'CH', '총당류(g)': 'SUGAR'
        }
        
        # 실제 파일에 있는 컬럼만 선택
        existing_cols = {k: v for k, v in required_cols.items() if k in df.columns}
        if not existing_cols:
            raise ValueError("필요한 영양성분 컬럼을 Excel 파일에서 찾을 수 없습니다.")

        df_filtered = df[list(existing_cols.keys())].copy()
        df_filtered.rename(columns=existing_cols, inplace=True)
        
        # 숫자형으로 변환
        numeric_cols = ['ENERGY', 'PROTEIN', 'FAT', 'CH', 'SUGAR']
        for col in numeric_cols:
            if col in df_filtered.columns:
                df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce').fillna(0)
        
        df_filtered.drop_duplicates(subset='FOOD_NAME', keep='first', inplace=True)
        return df_filtered
    except FileNotFoundError:
        print(f"Error: 영양 정보 파일 '{file_path}'를 찾을 수 없습니다.")
        return pd.DataFrame()
    except Exception as e:
        print(f"Error loading nutrition data: {e}")
        return pd.DataFrame()