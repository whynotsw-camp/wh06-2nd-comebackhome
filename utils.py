import streamlit as st
import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# .env 파일에서 환경 변수를 로드합니다.
# 이 코드는 스크립트가 임포트될 때 한 번 실행됩니다.
load_dotenv()
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

def get_youtube_videos(query: str, max_results: int = 2, page_token: str = None):
    """
    YouTube 영상을 검색하고 외부 재생 가능 여부를 확인하여 반환합니다.
    페이지네이션(더보기)을 위해 page_token을 사용합니다.

    Args:
        query (str): 검색할 키워드 (예: '김치찌개').
        max_results (int): 한 번에 가져올 영상의 최대 개수.
        page_token (str, optional): 다음 페이지를 요청하기 위한 토큰. 
                                     None이면 첫 페이지부터 검색합니다. Defaults to None.

    Returns:
        tuple: (영상 리스트, 다음 페이지 토큰) 형태의 튜플을 반환합니다.
               - 영상 리스트 (list): 제목과 ID를 담은 딕셔너리의 리스트.
               - 다음 페이지 토큰 (str or None): 다음 페이지가 있으면 토큰 문자열, 없으면 None.
               API 키가 없거나 오류 발생 시 ([], None)을 반환합니다.
    """
    # 1. YouTube API 키 유효성 검사
    if not YOUTUBE_API_KEY:
        # 터미널에 경고를 출력하고, UI에는 영향을 주지 않음
        print("Warning: YOUTUBE_API_KEY is not set in .env file. YouTube search is disabled.")
        st.warning("YouTube API 키가 설정되지 않았습니다. .env 파일에 YOUTUBE_API_KEY를 설정해주세요.")
        return [], None

    try:
        # 2. YouTube API 서비스 객체 생성
        youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

        # 3. 관련 영상을 넉넉하게 검색
        # 'embeddable' 영상을 필터링해야 하므로, 요청하는 영상 개수에 여유를 둡니다.
        # 예를 들어 max_results가 2이면, 8개 정도를 검색해서 그 중에서 2개를 찾습니다.
        search_count = max_results * 4

        search_response = youtube.search().list(
            part='snippet',
            q=f"{query} 레시피",
            type='video',
            maxResults=search_count,
            order='relevance',        # 관련성 순서로 정렬
            regionCode="KR",          # 한국 지역 결과 우선
            relevanceLanguage="ko",   # 한국어 영상 우선
            pageToken=page_token      # [핵심] 페이지 토큰을 사용하여 다음 결과 요청
        ).execute()

        # 4. 다음 페이지를 위한 토큰과 영상 ID 리스트 추출
        next_page_token = search_response.get('nextPageToken')
        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]

        # 검색 결과가 없으면 즉시 빈 리스트와 None 토큰 반환
        if not video_ids:
            return [], None

        # 5. 검색된 영상들의 상세 정보('status' 포함)를 다시 조회하여 'embeddable' 여부 확인
        videos_response = youtube.videos().list(
            part='snippet,status',
            id=','.join(video_ids)
        ).execute()

        # 6. 외부 재생이 가능한(embeddable=True) 영상만 필터링
        embeddable_videos = []
        for video in videos_response.get('items', []):
            # 'status' 객체와 그 안의 'embeddable' 키가 존재하는지 안전하게 확인
            if video.get('status', {}).get('embeddable'):
                video_info = {
                    "title": video["snippet"]["title"],
                    "video_id": video["id"]
                }
                embeddable_videos.append(video_info)
            
            # 원하는 개수(max_results)만큼 찾았으면 더 이상 확인하지 않고 루프 종료
            if len(embeddable_videos) >= max_results:
                break
        
        # 7. 최종적으로 (영상 리스트, 다음 페이지 토큰)을 튜플로 반환
        return embeddable_videos, next_page_token

    except HttpError as e:
        # API 관련 HTTP 오류 처리 (할당량 초과, 잘못된 키 등)
        error_content = e.content.decode('utf-8', 'ignore')
        if "quotaExceeded" in error_content:
            st.error("YouTube API 일일 할당량을 초과했습니다. 내일 다시 시도해주세요.")
        elif "API key not valid" in error_content:
            st.error("YouTube API 키가 유효하지 않습니다. .env 파일을 확인해주세요.")
        else:
            st.warning("YouTube 영상을 불러오는 중 일시적인 오류가 발생했습니다.")
        # 터미널에 상세 오류 기록
        print(f"An HTTP error {e.resp.status} occurred:\n{error_content}")
        return [], None
        
    except Exception as e:
        # 기타 모든 예외 처리
        st.warning("YouTube 영상을 불러오는 중 예상치 못한 오류가 발생했습니다.")
        print(f"An unexpected error occurred: {e}")
        return [], None