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
        attendee or "",
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
        attendee or "",
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


ATTENDEE_LIST = ["콩", "밍깅", "밍콩콩"]

ATTENDEE_COLORS = {
    "콩": "#B4BDBD",
    "밍깅": "#FBD7ED",
    "밍콩콩": "#EC7B87",
}

COLOR_CHIPS = ATTENDEE_COLORS.copy()

ATTENDEE_TEXT_COLORS = {
    "콩": "#000000",
    "밍깅": "#1f1f1f",
    "밍콩콩": "#ffffff",
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

default_start_dt = datetime.now().replace(second=0, microsecond=0)
default_end_dt = (datetime.now() + timedelta(hours=1)).replace(second=0, microsecond=0)

with st.sidebar.form("event_form", clear_on_submit=False):
    title = st.text_input("약속명*", key="new_title")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("약속일*", value=date.today())
        start_time = st.time_input("시작 시간*", value=default_start_dt.time())
    with col2:
        end_date = st.date_input("종료일*", value=date.today())
        end_time = st.time_input("종료 시간*", value=default_end_dt.time())

    description = st.text_area("메모")

    attendee = st.selectbox("attendee", ["선택 안함"] + ATTENDEE_LIST)
    attendee = None if attendee == "선택 안함" else attendee

    # 색상
    selected_chip = st.radio("컬러 칩", list(COLOR_CHIPS.keys()), horizontal=True)
    selected_color = COLOR_CHIPS[selected_chip]
    custom_color = st.color_picker("직접 선택", value=selected_color)

    color = custom_color if custom_color != selected_color else selected_color

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
selected = st.multiselect(
    "attendee 필터",
    ATTENDEE_LIST,
    default=st.session_state.selected_attendees
)
st.session_state.selected_attendees = selected

# Fetch events
events_df = fetch_events()
events_df = events_df[events_df["attendee"].isin(selected)]

# FullCalendar용 변환
events = []
for _, r in events_df.iterrows():
    events.append({
        "id": str(r["id"]),
        "title": r["title"],
        "start": r["start"],
        "end": r["end"],
        "allDay": bool(r["all_day"]),
        "color": r["color"],
        "textColor": ATTENDEE_TEXT_COLORS.get(r["attendee"], "#ffffff"),
        "extendedProps": {
            "description": r["description"],
            "attendee": r["attendee"],
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
    st.write(f"**attendee:** {props.get('attendee','')}")
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

        description = st.text_area("메모", value=row["description"])
        attendee = st.selectbox("attendee", ATTENDEE_LIST,
                                index=ATTENDEE_LIST.index(row["attendee"]))

        # color
        selected_chip = st.radio("컬러 칩", list(COLOR_CHIPS.keys()),
                                 index=list(COLOR_CHIPS.values()).index(row["color"]),
                                 horizontal=True)
        selected_color = COLOR_CHIPS[selected_chip]
        custom_color = st.color_picker("직접 선택", value=selected_color)
        color = custom_color if custom_color != selected_color else selected_color

        save = st.form_submit_button("저장")

        if save:
            start_dt = datetime.combine(start_date, start_time)
            end_dt = datetime.combine(end_date, end_time)

            update_event(event_id, title, start_dt.isoformat(),
                         end_dt.isoformat(), False, color, description, attendee)

            st.success("수정 완료!")
            st.session_state.inline_edit_event_id = None
            st.rerun()
