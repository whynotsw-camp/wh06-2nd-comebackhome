import streamlit as st
import re

# --- 세션 초기화 ---
if "bookmarks" not in st.session_state:
    st.session_state["bookmarks"] = set()
if "ingredient_count" not in st.session_state:
    st.session_state["ingredient_count"] = 1

# --- 레시피 데이터 ---
recipes = [
    {
        "title": "계란말이",
        "ingredients": ["계란", "소금", "당근"],
        "calorie": "약 180 kcal",
        "img_url": "https://via.placeholder.com/150",
        "link": "https://www.10000recipe.com/recipe/6838011",
        "youtube_links": [
            "https://www.youtube.com/watch?v=T7YJviWhquo"
        ]
    },
    {
        "title": "우유 팬케이크",
        "ingredients": ["우유", "밀가루", "계란"],
        "calorie": "약 250 kcal",
        "img_url": "https://via.placeholder.com/150",
        "link": "https://www.10000recipe.com/recipe/6903801",
        "youtube_links": [
            "https://www.youtube.com/watch?v=hNfcXgYNS84"
        ]
    },
    {
        "title": "파 계란국",
        "ingredients": ["계란", "파", "국간장"],
        "calorie": "약 120 kcal",
        "img_url": "https://via.placeholder.com/150",
        "link": "https://www.10000recipe.com/recipe/6908268",
        "youtube_links": [
            "https://www.youtube.com/watch?v=pwBD7OIaeu8"
        ]
    },
    {
        "title": "제육볶음",
        "ingredients": ["돼지고기", "고추장", "양파", "간장"],
        "calorie": "약 500 kcal",
        "img_url": "https://via.placeholder.com/150",
        "link": "https://www.10000recipe.com/recipe/6845428",
        "youtube_links": [
            "https://www.youtube.com/watch?v=gWHWUj5AzvU"
        ]
    },
    {
        "title": "김치찌개",
        "ingredients": ["김치", "돼지고기", "두부", "고춧가루"],
        "calorie": "약 350 kcal",
        "img_url": "https://via.placeholder.com/150",
        "link": "https://www.10000recipe.com/recipe/6835685",
        "youtube_links": [
            "https://www.youtube.com/watch?v=tDlw8yMg9NY"
        ]
    },
]

# --- 칼로리 DB (100g 기준) ---
CALORIE_DB = {
    "계란": 155,
    "소금": 0,
    "당근": 41,
    "우유": 42,
    "고추장": 200,
    "김치": 28,
    "돼지고기": 290,
    "양파": 40,
    "밀가루": 365,
    "두부": 76,
    "파": 31,
    "국간장": 50,
}

# --- 사이드바 메뉴 ---
category = st.sidebar.radio("카테고리 선택", ("레시피", "칼로리", "마이페이지"))

# --- 레시피 추천 기능 ---
if category == "레시피":
    st.title("🍳 재료 또는 음식명 기반 레시피 추천기")

    query = st.text_input("재료 또는 음식명을 입력하세요 (예: 계란, 김치찌개, 제육볶음)")

    if st.button("레시피 추천 받기") and query.strip():
        input_terms = re.split(r"[,\s]+", query.strip())
        input_terms = [term for term in input_terms if term]

        st.markdown(f"🔍 **검색 키워드**: {', '.join(input_terms)}")

        matched_recipes = []
        for recipe in recipes:
            if all(
                term == recipe["title"] or term in recipe["ingredients"]
                for term in input_terms
            ):
                matched_recipes.append(recipe)

        if matched_recipes:
            st.success(f"{len(matched_recipes)}개의 레시피를 찾았습니다.")
            for recipe in matched_recipes:
                st.markdown(f"### {recipe['title']}")
                st.image(recipe["img_url"], width=150)
                st.markdown(f"📄 [만개의레시피 보기]({recipe['link']})")
                st.markdown(f"🔥 **칼로리 정보**: {recipe['calorie']}")
                st.markdown("🎥 **유튜브 레시피 영상:**")
                for link in recipe["youtube_links"]:
                    st.video(link)

                # 북마크 버튼
                with st.form(key=f"form_{recipe['title']}"):
                    submitted = st.form_submit_button("⭐ 북마크 추가")
                    if submitted:
                        if recipe["title"] not in st.session_state["bookmarks"]:
                            st.session_state["bookmarks"].add(recipe["title"])
                            st.session_state["bookmark_added"] = recipe["title"]
                            st.rerun()

                # 북마크 완료 표시
                if (
                    "bookmark_added" in st.session_state
                    and st.session_state["bookmark_added"] == recipe["title"]
                ):
                    st.success(f"✅ '{recipe['title']}' 북마크 완료!")

                st.markdown("---")
        else:
            st.warning("입력한 재료나 음식명과 관련된 레시피가 없습니다.")

# --- 칼로리 기능 ---
elif category == "칼로리":
    st.title("🔥 칼로리 기능")

    mode = st.radio("기능 선택", ("음식 칼로리 조회", "칼로리 계산기"))

    if mode == "음식 칼로리 조회":
        food_name = st.text_input("음식명을 입력하세요 (예: 제육볶음, 김치찌개)")
        if st.button("칼로리 조회") and food_name.strip():
            found = False
            for recipe in recipes:
                if recipe["title"] == food_name:
                    st.success(f"'{food_name}'의 예상 칼로리는 {recipe['calorie']}입니다.")
                    found = True
                    break
            if not found:
                st.warning(f"'{food_name}'의 칼로리 정보를 찾을 수 없습니다.")

    elif mode == "칼로리 계산기":
        st.markdown("### 🧮 재료별 칼로리 계산기")

        ingredients = []
        for i in range(st.session_state.ingredient_count):
            cols = st.columns([3, 2])
            with cols[0]:
                name = st.text_input(f"재료명 {i+1}", key=f"name_{i}")
            with cols[1]:
                gram = st.number_input(f"그램(g) {i+1}", min_value=0.0, step=1.0, key=f"gram_{i}")
            ingredients.append((name, gram))

        if st.button("➕ 입력칸 추가"):
            st.session_state.ingredient_count += 1

        if st.button("🔥 최종 칼로리 계산!"):
            total_cal = 0
            st.markdown("### 📦 계산 결과:")
            for name, gram in ingredients:
                if name.strip() == "" or gram == 0:
                    continue
                kcal_per_100g = CALORIE_DB.get(name.strip())
                if kcal_per_100g is not None:
                    kcal = kcal_per_100g * gram / 100
                    total_cal += kcal
                    st.write(f"- {name.strip()} {gram:.1f}g → {kcal:.1f} kcal")
                else:
                    st.write(f"- {name.strip()} {gram:.1f}g → ❗ 알 수 없음 (DB 없음)")
            st.success(f"🥗 총 칼로리: **{total_cal:.1f} kcal**")

        if st.button("🧹 전부 초기화"):
            st.session_state.ingredient_count = 1
            for key in list(st.session_state.keys()):
                if key.startswith("name_") or key.startswith("gram_"):
                    del st.session_state[key]

# --- 마이페이지 ---
elif category == "마이페이지":
    st.title("📁 마이페이지 - 즐겨찾기한 레시피")

    bookmark_titles = st.session_state["bookmarks"]
    if bookmark_titles:
        bookmarked_recipes = [r for r in recipes if r["title"] in bookmark_titles]
        st.success(f"총 {len(bookmarked_recipes)}개의 레시피가 저장되어 있습니다.")
        for i, recipe in enumerate(bookmarked_recipes):
            st.markdown(f"### {recipe['title']}")
            st.image(recipe["img_url"], width=150)
            st.markdown(f"📄 [만개의레시피 보기]({recipe['link']})")
            st.markdown(f"🔥 **칼로리 정보**: {recipe['calorie']}")
            st.markdown("🎥 **유튜브 레시피 영상:**")
            for link in recipe["youtube_links"]:
                st.video(link)

            if st.button("🗑️ 북마크 삭제", key=f"delete_{i}"):
                st.session_state["bookmarks"].remove(recipe["title"])
                st.experimental_rerun()

            st.markdown("---")
    else:
        st.warning("아직 북마크된 레시피가 없습니다.")
