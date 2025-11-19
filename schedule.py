import streamlit as st
from streamlit_calendar import calendar
import pandas as pd
from datetime import datetime, date, timedelta
from dateutil import tz

import gspread
from google.oauth2.service_account import Credentials


# -------------------------
# Google Sheets 연결 설정
# -------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = "1taVkkzhIgJAsjM2IshKHsnflNAItJ7PGKlQKZqUrI0s"

EVENT_COLUMNS = [
    "id",
    "title",
    "start",
    "end",
    "all_day",
    "color",
    "description",
    "attendee",
]


@st.cache_resource
def get_events_sheet():
    credentials = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=SCOPES,
    )

    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SPREADSHEET_ID)
    return sh.worksheet("events")


# -------------------------
# Google Sheets 기반 DB 함수
# -------------------------

def fetch_events() -> pd.DataFrame:
    events_ws = get_events_sheet()
    rows = events_ws.get_all_records()

    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    df = pd.DataFrame(rows)

    # 빠진 컬럼 자동 생성
    for col in EVENT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    try:
        df["id"] = df["id"].astype(int)
    except:
        pass

    return df[EVENT_COLUMNS]


def _get_new_event_id(events_ws):
    col = events_ws.col_values(1)
    if len(col) <= 1:
        return 1

    ids = []
    for v in col[1:]:
        try:
            ids.append(int(v))
        except:
            pass

    return max(ids) + 1 if ids else 1


def insert_event(title, start, end, all_day, color, description, attendee):
    events_ws = get_events_sheet()

    new_id = _get_new_event_id(events_ws)

    row = [
        new_id,
        title,
        start,
        end,
        int(all_day),
        color,
        description or "",
        attendee,
    ]

    events_ws.append_row(row, value_input_option="USER_ENTERED")


def update_event(event_id, title, start, end, all_day, color, description, attendee):
    events_ws = get_events_sheet()

    try:
        cell = events_ws.find(str(event_id))
    except:
        return

    row_idx = cell.row

    row = [
        event_id,
        title,
        start,
        end,
        int(all_day),
        color,
        description or "",
        attendee,
    ]

    events_ws.update(f"A{row_idx}:H{row_idx}", [row])


def delete_event(event_id):
    events_ws = get_events_sheet()
    try:
        cell = events_ws.find(str(event_id))
        events_ws.delete_row(cell.row)
    except:
        return


# -------------------------
# 기본 UI 설정
# -------------------------

st.set_page_config(page_title="밍콩콩 달력", layout="wide")
st.title("🥰 밍콩콩 일정관리")


ATTENDEE_LIST = ["밍콩콩", "콩", "밍깅"]

ATTENDEE_COLORS = {
    "콩": "#474747",
    "밍깅": "#4b8ee5",
    "밍콩콩": "#EC7B87",
}

COLOR_CHIPS = ATTENDEE_COLORS.copy()

ATTENDEE_TEXT_COLORS = {
    "콩": "#ffffff",
    "밍깅": "#ffffff",
    "밍콩콩": "#ffffff",
}

ATTENDEE_EMOJIS = {
    "콩": "🫛",
    "밍깅": "👻",
    "밍콩콩": "❤️",
}


# -------------------------
# 필터 기본값
# -------------------------

if "selected_attendees" not in st.session_state:
    st.session_state.selected_attendees = list(ATTENDEE_LIST)


# -------------------------
# 일정 등록 UI
# -------------------------

st.sidebar.header("📝 약속 등록")

# 한국시간 기준 현재 시간 가져오기
korea_tz = tz.gettz("Asia/Seoul")
now_korea = datetime.now(korea_tz)
today_korea = now_korea.date()

# 시작시간 기본값: 18:00
default_start_time = datetime.strptime("18:00:00", "%H:%M:%S").time()
# 종료시간 기본값: 24:00 (23:59:59)
default_end_time = datetime.strptime("23:59:59", "%H:%M:%S").time()

with st.sidebar.form("event_form", clear_on_submit=False):
    title = st.text_input("약속명*", key="new_title")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("약속일", value=today_korea)
        start_time = st.time_input("시작 시간", value=default_start_time)
    with col2:
        end_date = st.date_input("종료일", value=today_korea)
        end_time = st.time_input("종료 시간", value=default_end_time)

    # 이모지가 포함된 참석자 옵션 리스트
    attendee_options = [f"{ATTENDEE_EMOJIS.get(a, '')} {a}" for a in ATTENDEE_LIST]
    selected_attendee_display = st.radio("참석자", attendee_options, horizontal=True)
    # 선택된 값에서 이모지 제거하여 실제 attendee 값 추출
    attendee = selected_attendee_display.split(" ", 1)[1] if " " in selected_attendee_display else selected_attendee_display
    # 참석자에 따라 컬러 자동 설정
    color = ATTENDEE_COLORS.get(attendee, ATTENDEE_COLORS[ATTENDEE_LIST[0]])

    description = st.text_area("메모")

    submitted = st.form_submit_button("➕ 약속 추가")

    if submitted:
        if not title:
            st.warning("약속명은 필수입니다.")
        else:
            start_dt = datetime.combine(start_date, start_time)
            end_dt = datetime.combine(end_date, end_time)

            if end_dt <= start_dt:
                st.warning("종료 시간은 약속 시작 이후여야 합니다.")
            else:
                insert_event(title, start_dt.isoformat(), end_dt.isoformat(),
                             False, color, description, attendee)
                st.success("약속이 추가되었습니다!")
                st.rerun()


# -------------------------
# 캘린더 화면
# -------------------------

st.markdown("---")
st.subheader("📆 일정 보기")

# 필터 UI
# 이모지가 포함된 참석자 옵션 리스트
attendee_filter_options = [f"{ATTENDEE_EMOJIS.get(a, '')} {a}" for a in ATTENDEE_LIST]
selected_display = st.multiselect(
    "참석자 필터",
    attendee_filter_options,
    default=[f"{ATTENDEE_EMOJIS.get(a, '')} {a}" for a in st.session_state.selected_attendees if a in ATTENDEE_LIST]
)
# 선택된 값에서 이모지 제거하여 실제 attendee 값 추출
selected = [s.split(" ", 1)[1] if " " in s else s for s in selected_display]
st.session_state.selected_attendees = selected

# Fetch events
events_df = fetch_events()
events_df = events_df[events_df["attendee"].isin(selected)]

# FullCalendar용 변환
events = []
for _, r in events_df.iterrows():
    attendee = r["attendee"]
    emoji = ATTENDEE_EMOJIS.get(attendee, "")
    
    # 제목에 이모티콘 추가
    if attendee == "콩":
        # 콩: 제목 앞에 🫛
        display_title = f"🫛 {r['title']}"
    elif attendee == "밍깅":
        # 밍깅: 제목 앞에 👻
        display_title = f"👻 {r['title']}"
    elif attendee == "밍콩콩":
        # 밍콩콩: 제목 앞에 ❤️
        display_title = f"❤️ {r['title']}"
    else:
        display_title = r["title"]
    
    events.append({
        "id": str(r["id"]),
        "title": display_title,
        "start": r["start"],
        "end": r["end"],
        "allDay": bool(r["all_day"]),
        "color": r["color"],
        "textColor": ATTENDEE_TEXT_COLORS.get(attendee, "#ffffff"),
        "extendedProps": {
            "description": r["description"],
            "attendee": attendee,
        }
    })

calendar_options = {
    "initialView": "dayGridMonth",
    "locale": "ko",
    "selectable": True,
    "editable": False,
    "height": "auto",
    # 이벤트 전체 배경에 색상이 차도록 블록 형태로 표시
    "eventDisplay": "block",
}

state = calendar(events=events, options=calendar_options)

# -------------------------
# 일정 상세 + 인라인 수정
# -------------------------

if state.get("eventClick"):
    clicked = state["eventClick"]["event"]
    props = clicked.get("extendedProps", {})

    event_id = int(clicked.get("id"))

    st.markdown("### 📌 상세 정보")
    st.write(f"**약속명:** {clicked['title']}")
    st.write(f"**시작:** {clicked['start']}")
    st.write(f"**종료:** {clicked['end']}")
    st.write(f"**참석자:** {props.get('attendee','')}")
    st.write(f"**메모:** {props.get('description','')}")

    # 수정
    if st.button("✏ 수정하기"):
        st.session_state.inline_edit_event_id = event_id
        st.rerun()

    # 삭제
    if st.button("🗑 삭제"):
        delete_event(event_id)
        st.success("삭제되었습니다.")
        st.rerun()

# -------------------------
# 인라인 수정 창
# -------------------------

if st.session_state.get("inline_edit_event_id"):
    event_id = st.session_state.inline_edit_event_id
    df = fetch_events()
    row = df[df["id"] == event_id].iloc[0]

    st.markdown("---")
    st.markdown("### ✏ 인라인 수정")

    with st.form("edit_form"):
        title = st.text_input("약속명", value=row["title"])
        sdt = datetime.fromisoformat(row["start"])
        edt = datetime.fromisoformat(row["end"])

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("약속일", value=sdt.date())
            start_time = st.time_input("시작 시간", value=sdt.time())
        with col2:
            end_date = st.date_input("종료일", value=edt.date())
            end_time = st.time_input("종료 시간", value=edt.time())
        
        # attendee chip selector
        current_attendee = row.get("attendee") or ATTENDEE_LIST[0]
        if current_attendee in ATTENDEE_LIST:
            attendee_index = ATTENDEE_LIST.index(current_attendee)
        else:
            attendee_index = 0
        # 이모지가 포함된 참석자 옵션 리스트
        attendee_options = [f"{ATTENDEE_EMOJIS.get(a, '')} {a}" for a in ATTENDEE_LIST]
        selected_attendee_display = st.radio("참석자*", attendee_options, 
                           index=attendee_index, horizontal=True)
        # 선택된 값에서 이모지 제거하여 실제 attendee 값 추출
        attendee = selected_attendee_display.split(" ", 1)[1] if " " in selected_attendee_display else selected_attendee_display
        # 참석자에 따라 컬러 자동 설정
        color = ATTENDEE_COLORS.get(attendee, ATTENDEE_COLORS[ATTENDEE_LIST[0]])

        description = st.text_area("메모", value=row["description"])

        save = st.form_submit_button("저장")

        if save:
            start_dt = datetime.combine(start_date, start_time)
            end_dt = datetime.combine(end_date, end_time)

            update_event(event_id, title, start_dt.isoformat(),
                         end_dt.isoformat(), False, color, description, attendee)

            st.success("수정 완료!")
            st.session_state.inline_edit_event_id = None
            st.rerun()
