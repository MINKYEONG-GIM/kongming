import streamlit as st
from streamlit_calendar import calendar
import pandas as pd
from datetime import datetime, date, timedelta
import time
from dateutil import tz

import gspread
from google.oauth2.service_account import Credentials
import requests

# =========================================
# 보안 설정 (로컬에서는 config.py, 클라우드에서는 st.secrets 사용)
# =========================================
try:
    from config import SCOPES, SPREADSHEET_ID, LOVE_START_DATE
except ImportError:
    # Streamlit Cloud 환경에서 실행될 때 또는 config.py가 없을 때
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    SPREADSHEET_ID = st.secrets.get("spreadsheet_id", "")
    LOVE_START_DATE = st.secrets.get("love_start_date", "2025-09-06")

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
SPREADSHEET_ID = "1taVkkzhIgJAsjM2IshKHsnflNAItJ7PGKlQKZqUrI0s"

@st.cache_resource
def get_events_sheet():
    try:
        credentials = Credentials.from_service_account_info(
            st.secrets["google_service_account"],
            scopes=SCOPES,
        )

        gc = gspread.authorize(credentials)
        sh = gc.open_by_key(SPREADSHEET_ID)
        return sh.worksheet("events")
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("❌ 스프레드시트를 찾을 수 없습니다.")
        st.error(f"스프레드시트 ID: `{SPREADSHEET_ID}`")
        st.info("💡 해결 방법:\n"
                "1. 스프레드시트 ID가 올바른지 확인하세요\n"
                "2. 스프레드시트가 삭제되지 않았는지 확인하세요\n"
                "3. 서비스 계정 이메일(`mingging@kongmingcalendar.iam.gserviceaccount.com`)을\n"
                "   스프레드시트에 공유하고 편집 권한을 부여하세요")
        st.stop()
    except gspread.exceptions.APIError as e:
        # APIError에서 상태 코드 추출 시도
        error_code = 'Unknown'
        error_str = str(e)
        if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
            error_code = e.response.status_code
        elif '404' in error_str:
            error_code = 404
        elif '403' in error_str:
            error_code = 403
        
        if error_code == 404:
            st.error("❌ 스프레드시트를 찾을 수 없습니다 (404 오류).")
            st.error(f"스프레드시트 ID: `{SPREADSHEET_ID}`")
            st.info("💡 해결 방법:\n"
                    "1. 스프레드시트 ID가 올바른지 확인하세요\n"
                    "2. 서비스 계정 이메일(`mingging@kongmingcalendar.iam.gserviceaccount.com`)을\n"
                    "   스프레드시트에 공유하고 편집 권한을 부여하세요\n"
                    "3. 스프레드시트가 삭제되지 않았는지 확인하세요")
        elif error_code == 403:
            st.error("❌ 스프레드시트 접근 권한이 없습니다 (403 오류).")
            st.info("💡 해결 방법:\n"
                    "1. 서비스 계정 이메일(`mingging@kongmingcalendar.iam.gserviceaccount.com`)을\n"
                    "   스프레드시트에 공유하고 편집 권한을 부여하세요\n"
                    "2. Google Cloud Console에서 API가 활성화되어 있는지 확인하세요")
        else:
            st.error(f"❌ Google Sheets API 오류: {str(e)}")
            st.error(f"오류 코드: {error_code}")
        st.stop()
    except gspread.exceptions.WorksheetNotFound:
        st.error("❌ 'events' 워크시트를 찾을 수 없습니다.")
        st.info("💡 해결 방법:\n"
                f"1. 스프레드시트(`{SPREADSHEET_ID}`)에 'events'라는 이름의 워크시트가 있는지 확인하세요\n"
                "2. 워크시트 이름이 정확히 'events'인지 확인하세요 (대소문자 구분)")
        st.stop()
    except requests.exceptions.ConnectionError as e:
        st.error(f"❌ 네트워크 연결 오류: Google Sheets API에 연결할 수 없습니다.")
        st.error(f"오류 상세: {str(e)}")
        st.info("💡 해결 방법:\n"
                "1. 인터넷 연결을 확인하세요\n"
                "2. 회사/학교 네트워크에서 Google API 접근이 차단되었을 수 있습니다\n"
                "3. VPN을 사용하거나 다른 네트워크에서 시도해보세요\n"
                "4. 방화벽이나 프록시 설정을 확인하세요")
        st.stop()
    except Exception as e:
        error_str = str(e)
        if "404" in error_str or "not found" in error_str.lower():
            st.error("❌ 스프레드시트를 찾을 수 없습니다.")
            st.error(f"스프레드시트 ID: `{SPREADSHEET_ID}`")
            st.info("💡 해결 방법:\n"
                    "1. 스프레드시트 ID가 올바른지 확인하세요\n"
                    "2. 서비스 계정 이메일(`mingging@kongmingcalendar.iam.gserviceaccount.com`)을\n"
                    "   스프레드시트에 공유하고 편집 권한을 부여하세요")
        else:
            st.error(f"❌ Google Sheets 연결 오류: {str(e)}")
        st.stop()


# -------------------------
# Google Sheets 기반 DB 함수
# -------------------------

def fetch_events() -> pd.DataFrame:
    try:
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
    except Exception as e:
        # StopException은 get_events_sheet()에서 st.stop()이 호출되었을 때 발생
        # 앱을 중단하기 위해 다시 발생시킴
        # StopException의 모듈 경로로 확인 (streamlit.runtime.scriptrunner 관련)
        exception_type = type(e)
        exception_module = getattr(exception_type, '__module__', '')
        exception_name = exception_type.__name__
        
        # Streamlit의 StopException인지 확인
        if 'streamlit' in exception_module and 'Stop' in exception_name:
            raise
        st.error(f"일정을 불러오는 중 오류가 발생했습니다: {str(e)}")
        return pd.DataFrame(columns=EVENT_COLUMNS)


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

st.image("https://drive.google.com/uc?export=view&id=1Q5w3pBROSLyb5B91T5cC6DhPykAe2IjA", use_column_width=True)

# st.title("🥰 밍콩콩 일정관리")  # 타이틀 제거


# -------------------------
# 참석자 정보
# -------------------------
ATTENDEE_LIST = ["밍콩콩", "콩", "밍깅"]

ATTENDEE_COLORS = {
    "콩": "#474747",
    "밍깅": "#4b8ee5",
    "밍콩콩": "#EC7B87",
}

ATTENDEE_TEXT_COLORS = {
    "콩": "#ffffff",
    "밍깅": "#ffffff",
    "밍콩콩": "#ffffff",
}

ATTENDEE_EMOJIS = {
    "콩": "🫛",
    "밍깅": "👸",
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

# 일정 입력 기본 날짜 (세션 유지)
if "form_start_date" not in st.session_state:
    st.session_state.form_start_date = today_korea
if "form_end_date" not in st.session_state:
    st.session_state.form_end_date = today_korea
if "last_date_click_date" not in st.session_state:
    st.session_state.last_date_click_date = None
if "last_date_click_ts" not in st.session_state:
    st.session_state.last_date_click_ts = None

# 시작시간 기본값: 18:00
default_start_time = datetime.strptime("18:00:00", "%H:%M:%S").time()
# 종료시간 기본값: 24:00 (23:59:59)
default_end_time = datetime.strptime("23:59:59", "%H:%M:%S").time()

def parse_time_string(value: str):
    if not value:
        return None
    value = value.strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None

def parse_calendar_date(value: str):
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        try:
            return datetime.strptime(normalized, "%Y-%m-%d").date()
        except ValueError:
            return None

with st.sidebar.form("event_form", clear_on_submit=False):
    title = st.text_input("약속명*", key="new_title")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("약속일", value=st.session_state.form_start_date)
        start_time_str = st.text_input(
            "시작 시간 (HH:MM)",
            value=default_start_time.strftime("%H:%M"),
        )
    with col2:
        end_date = st.date_input("종료일", value=st.session_state.form_end_date)
        end_time_str = st.text_input(
            "종료 시간 (HH:MM)",
            value=default_end_time.strftime("%H:%M"),
        )

    st.session_state.form_start_date = start_date
    st.session_state.form_end_date = end_date

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
            start_time = parse_time_string(start_time_str)
            end_time = parse_time_string(end_time_str)

            if not start_time or not end_time:
                st.warning("시간은 HH:MM 형식으로 입력해주세요.")
            else:
                start_dt = datetime.combine(start_date, start_time)
                end_dt = datetime.combine(end_date, end_time)

                if end_dt <= start_dt:
                    st.warning("종료 시간은 약속 시작 이후여야 합니다.")
                else:
                    insert_event(
                        title,
                        start_dt.isoformat(),
                        end_dt.isoformat(),
                        False,
                        color,
                        description,
                        attendee,
                    )
                    st.success("약속이 추가되었습니다!")
                    st.rerun()


# -------------------------
# 캘린더 화면
# -------------------------

st.markdown("---")


# 밍콩콩 NNN일 💕
love_start_date = datetime.strptime(LOVE_START_DATE, "%Y-%m-%d").date()
now_korea = datetime.now(tz=tz.gettz("Asia/Seoul")).date()
love_days = (now_korea - love_start_date).days + 1
st.markdown(f"<span style='font-size:2.5rem;font-weight:bold;color:#EC7B87;'>밍콩콩 {love_days}일 💕</span>", unsafe_allow_html=True)

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
        # 밍깅: 제목 앞에 👸
        display_title = f"👸 {r['title']}"
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
# -------------------------
# 이벤트 우선순위 정렬 (밍콩콩 → 콩 → 밍깅)
# -------------------------

priority = {
    "밍콩콩": 1,
    "콩": 2,
    "밍깅": 3
}

events.sort(key=lambda e: priority.get(e["extendedProps"]["attendee"], 99))


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

if state.get("dateClick"):
    click_payload = state["dateClick"]
    raw_date = (
        click_payload.get("date")
        or click_payload.get("dateStr")
        or click_payload.get("start")
    )
    clicked_date = parse_calendar_date(raw_date)

    if clicked_date:
        prev_date = st.session_state.get("last_date_click_date")
        prev_ts = st.session_state.get("last_date_click_ts")
        now_ts = time.time()

        double_clicked = (
            prev_date == clicked_date
            and prev_ts is not None
            and now_ts - prev_ts <= 0.8
        )

        if double_clicked:
            st.session_state.form_start_date = clicked_date
            st.session_state.form_end_date = clicked_date
            st.session_state.last_date_click_date = None
            st.session_state.last_date_click_ts = None
            st.rerun()
        else:
            st.session_state.last_date_click_date = clicked_date
            st.session_state.last_date_click_ts = now_ts

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
            start_time_str = st.text_input(
                "시작 시간 (HH:MM)",
                value=sdt.strftime("%H:%M"),
            )
        with col2:
            end_date = st.date_input("종료일", value=edt.date())
            end_time_str = st.text_input(
                "종료 시간 (HH:MM)",
                value=edt.strftime("%H:%M"),
            )
        
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
            start_time = parse_time_string(start_time_str)
            end_time = parse_time_string(end_time_str)

            if not start_time or not end_time:
                st.warning("시간은 HH:MM 형식으로 입력해주세요.")
            else:
                start_dt = datetime.combine(start_date, start_time)
                end_dt = datetime.combine(end_date, end_time)

                update_event(
                    event_id,
                    title,
                    start_dt.isoformat(),
                    end_dt.isoformat(),
                    False,
                    color,
                    description,
                    attendee,
                )

                st.success("수정 완료!")
                st.session_state.inline_edit_event_id = None
                st.rerun()
