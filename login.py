# login.py
import streamlit as st
import json
import os
import uuid

USER_FILE = "users.json"
ACTIVE_USER_FILE = "active_users.json"

# --- 사용자 저장소 초기화 ---
if not os.path.exists(USER_FILE):
    with open(USER_FILE, "w") as f:
        json.dump({}, f)

if not os.path.exists(ACTIVE_USER_FILE):
    with open(ACTIVE_USER_FILE, "w") as f:
        json.dump([], f)

# --- 사용자 JSON 로딩/저장 ---
def load_users():
    with open(USER_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USER_FILE, "w") as f:
        json.dump(users, f, indent=2)

def load_active_users():
    with open(ACTIVE_USER_FILE, "r") as f:
        return json.load(f)

def save_active_users(user_list):
    with open(ACTIVE_USER_FILE, "w") as f:
        json.dump(user_list, f, indent=2)

# --- 회원가입 ---
def signup():
    st.subheader("회원가입")
    new_id = st.text_input("아이디")
    check = st.button("✅ 아이디 중복확인")

    users = load_users()
    if check:
        if new_id in users:
            st.error("이미 사용 중인 아이디입니다.")
        elif new_id == "":
            st.warning("아이디를 입력하세요.")
        else:
            st.success("사용 가능한 아이디입니다.")

    new_pw = st.text_input("비밀번호", type="password")
    new_pw_confirm = st.text_input("비밀번호 확인", type="password")

    if st.button("회원가입"):
        if new_id in users:
            st.error("이미 등록된 아이디입니다.")
        elif new_pw != new_pw_confirm:
            st.error("비밀번호가 일치하지 않습니다.")
        elif new_id == "" or new_pw == "":
            st.warning("모든 항목을 입력하세요.")
        else:
            token = str(uuid.uuid4())
            users[new_id] = {"password": new_pw, "token": token}
            save_users(users)
            st.success("회원가입 완료! 로그인 해주세요.")

# --- 로그인 ---
def login():
    st.subheader("로그인")
    user_id = st.text_input("아이디")
    user_pw = st.text_input("비밀번호", type="password")

    if st.button("로그인"):
        users = load_users()
        if user_id in users and users[user_id]["password"] == user_pw:
            st.success(f"{user_id}님 환영합니다!")
            st.session_state["logged_in"] = True
            st.session_state["user_id"] = user_id
            st.session_state["user_token"] = users[user_id]["token"]

            # ✅ 로그인 유저 등록
            active_users = load_active_users()
            if user_id not in active_users:
                active_users.append(user_id)
                save_active_users(active_users)
        else:
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

# --- 로그아웃 ---
def logout():
    user_id = st.session_state.get("user_id")
    active_users = load_active_users()
    updated_users = [u for u in active_users if u != user_id]
    save_active_users(updated_users)
    st.session_state.clear()
    # 실행 즉시 페이지 리로드
    st.experimental_rerun()


# --- 메인 ---
st.title("🔐 로그인 / 회원가입")

menu = st.radio("선택", ("로그인", "회원가입"))

if menu == "로그인":
    login()
else:
    signup()

# --- 로그인된 경우 표시 ---
if st.session_state.get("logged_in"):
    st.markdown("---")
    st.success(f"현재 로그인 중: **{st.session_state['user_id']}**")
    st.code(f"토큰: {st.session_state['user_token']}")

    # ✅ 현재 로그인한 전체 유저 보여주기
    st.markdown("### 👥 현재 로그인된 사용자 목록")
    active_users = load_active_users()
    for u in active_users:
        st.markdown(f"- {u}")

    # ✅ 로그아웃 버튼
    if st.button("로그아웃"):
        logout()
