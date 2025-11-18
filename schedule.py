import streamlit as st
from streamlit_calendar import calendar
import pandas as pd
from datetime import datetime, date, timedelta
from dateutil import tz
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import gspread
from google.oauth2.service_account import Credentials


# -------------------------
# Google Sheets 연결 설정
# -------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = "1taVkkzhIgJAsjM2IshKHsnflNAItJ7PGKlQKZqUrI0s"  # 웅니 ID 그대로 사용

EVENT_COLUMNS = [
    "id",
    "title",
    "start",
    "end",
    "all_day",
    "color",
    "description",
    "channel",
    "submit_due",
    "manager",
]

MANAGER_COLUMNS = ["name", "email", "created_at"]


@st.cache_resource
def get_sheets():
    """구글 시트 인증 & events / managers 워크시트 가져오기"""
    credentials = Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=SCOPES,
    )

    gc = gspread.authorize(credentials)
    sh = gc.open_by_key(SPREADSHEET_ID)

    events_ws = sh.worksheet("events")
    managers_ws = sh.worksheet("managers")

    return events_ws, managers_ws


# -------------------------
# Google Sheets 기반 DB 함수들
# -------------------------

def fetch_events() -> pd.DataFrame:
    events_ws, _ = get_sheets()
    rows = events_ws.get_all_records()

    if not rows:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    df = pd.DataFrame(rows)

    for col in EVENT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    try:
        df["id"] = df["id"].astype(int)
    except Exception:
        pass

    return df[EVENT_COLUMNS]


def get_managers() -> pd.DataFrame:
    _, managers_ws = get_sheets()
    rows = managers_ws.get_all_records()

    if not rows:
        return pd.DataFrame(columns=MANAGER_COLUMNS)

    df = pd.DataFrame(rows)

    for col in MANAGER_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[MANAGER_COLUMNS]


def add_manager(name, email):
    """이름 중복 체크 후 추가"""
    _, managers_ws = get_sheets()
    rows = managers_ws.get_all_records()

    for r in rows:
        if r.get("name") == name:
            return False

    managers_ws.append_row(
        [name, email, datetime.now().isoformat()],
        value_input_option="USER_ENTERED",
    )
    return True


def _get_new_event_id(events_ws):
    """id 자동 증가"""
    col = events_ws.col_values(1)
    if len(col) <= 1:
        return 1
    ids = []
    for v in col[1:]:
        try:
            ids.append(int(v))
        except:
            pass
    if not ids:
        return 1
    return max(ids) + 1


def insert_event(title, start, end, all_day, color, description, channel, submit_due, managers):
    events_ws, _ = get_sheets()

    new_id = _get_new_event_id(events_ws)
    manager_str = ",".join(managers) if managers else ""

    row = [
        new_id,
        title,
        start,
        end,
        int(all_day),
        color,
        description or "",
        channel or "",
        submit_due or "",
        manager_str,
    ]

    events_ws.append_row(row, value_input_option="USER_ENTERED")


def update_event(event_id, title, start, end, all_day, color, description, channel, submit_due, managers):
    events_ws, _ = get_sheets()

    try:
        cell = events_ws.find(str(event_id))
    except:
        return

    row_idx = cell.row
    manager_str = ",".join(managers) if managers else ""

    row = [
        event_id,
        title,
        start,
        end,
        int(all_day),
        color,
        description or "",
        channel or "",
        submit_due or "",
        manager_str,
    ]

    events_ws.update(f"A{row_idx}:J{row_idx}", [row])


def delete_event(event_id):
    events_ws, _ = get_sheets()
    try:
        cell = events_ws.find(str(event_id))
    except:
        return

    events_ws.delete_row(cell.row)


# -------------------------
# 기본 UI 설정
# -------------------------

st.set_page_config(page_title="밍콩 달력", layout="wide")
st.title("📅 밍콩 달력")


CHANNEL_LIST = ["스파오 공홈", "무신사", "지그재그", "에이블리", "쿠팡", "네이버", "11번가"]

CHANNEL_COLORS = {
    "스파오 공홈": "#ff0000",
    "무신사": "#000000",
    "지그재그": "#ff69b4",
    "에이블리": "#ffff00",
    "쿠팡": "#ff4c00",
    "네이버": "#00ff00",
}

COLOR_CHIPS = {
    "공홈(기본)": "#ff0000",
    "무신사(기본)": "#000000",
    "지그재그(기본)": "#ff69b4",
    "에이블리(기본)": "#ffff00",
    "네이버(기본)": "#00ff00",
    "쿠팡(기본)": "#ff4c00",
}


# -------------------------
# 필터 기본값 설정
# -------------------------

unique_channels = list(CHANNEL_LIST)
if "selected_channels" not in st.session_state:
    st.session_state.selected_channels = list(unique_channels)

managers_df = get_managers()
manager_options = ["선택 안함"] + managers_df["name"].tolist() if not managers_df.empty else ["선택 안함"]


# -------------------------
# 일정 등록 UI
# -------------------------

st.sidebar.header("📝 일정 등록")

with st.sidebar.form("event_form", clear_on_submit=False):
    title = st.text_input("제목*", key="new_title")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("시작일*", value=date.today(), key="new_start_date")
    with col2:
        end_date = st.date_input("종료일*", value=date.today(), key="new_end_date")

    description = st.text_area("메모", key="new_desc")

    channel_options = ["선택 안함"] + CHANNEL_LIST
    channel = st.selectbox("채널 (선택)", channel_options, key="new_channel")
    if channel == "선택 안함":
        channel = None

    if channel and channel in CHANNEL_COLORS:
        default_color = CHANNEL_COLORS[channel]
    else:
        default_color = "#3174ad"

    st.markdown("**색상 선택**")
    color_chip_options = list(COLOR_CHIPS.keys())
    selected_chip = st.radio("컬러 칩", color_chip_options, horizontal=True, key="new_color_chip")
    selected_color = COLOR_CHIPS[selected_chip]
    custom_color = st.color_picker("또는 직접 선택", value=selected_color, key="new_color_picker")

    if custom_color != selected_color:
        color = custom_color
    else:
        color = selected_color

    submit_due = st.date_input("기획전 상품리스트 제출일)", value=None, key="new_submit_due")

    selected_managers = st.multiselect("담당자 선택 (복수 선택 가능)", manager_options[1:] if len(manager_options) > 1 else [], key="new_manager")

    submitted = st.form_submit_button("➕ 일정 추가")
    if submitted:
        start_iso = datetime.combine(start_date, datetime.min.time()).isoformat()
        end_iso = (datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)).isoformat()

        if not title:
            st.warning("제목은 필수입니다.")
        else:
            submit_due_str = submit_due.strftime("%Y-%m-%d") if submit_due else None
            insert_event(title, start_iso, end_iso, True, color, description, channel or None, submit_due_str, selected_managers)
            st.success("✅ 일정이 추가되었습니다.")
            st.rerun()


# -------------------------
# 담당자 관리
# -------------------------

st.sidebar.markdown("---")
st.sidebar.header("👤 담당자 관리")

with st.sidebar.expander("새 담당자 추가", expanded=False):
    new_manager_name = st.text_input("담당자 이름", key="new_manager_name")
    new_manager_email = st.text_input("담당자 이메일", key="new_manager_email")

    if st.button("➕ 담당자 추가", key="add_manager_btn"):
        if new_manager_name and new_manager_email:
            if add_manager(new_manager_name, new_manager_email):
                st.success("✅ 담당자가 추가되었습니다.")
                st.rerun()
            else:
                st.error("이미 존재하는 담당자입니다.")
        else:
            st.warning("담당자 이름과 이메일을 모두 입력해주세요.")


# -------------------------
# 캘린더 화면
# -------------------------

st.markdown("---")
st.subheader("📆 캘린더")

top_left, top_right = st.columns([0.6, 0.4])
with top_right:
    prev_selected = st.session_state.selected_channels
    prev_all = len(CHANNEL_LIST) > 0 and len(prev_selected) == len(CHANNEL_LIST)

    if prev_all:
        options_for_ui = ["전체"] + list(CHANNEL_LIST)
        default_selection = options_for_ui[:]
    else:
        options_for_ui = list(CHANNEL_LIST)
        default_selection = prev_selected

    current_selection = st.multiselect(
        "채널 필터",
        options=options_for_ui,
        default=default_selection,
        key="channel_filter",
    )

    if "전체" not in current_selection and prev_all:
        st.session_state.selected_channels = []
        st.rerun()
    else:
        st.session_state.selected_channels = [x for x in current_selection if x in CHANNEL_LIST]


events_df = fetch_events()
if "channel" in events_df.columns:
    if len(st.session_state.selected_channels) > 0:
        events_df = events_df[events_df["channel"].isin(st.session_state.selected_channels)]
    else:
        events_df = events_df[events_df["channel"].isin([])]

events = []
for _, r in events_df.iterrows():
    events.append({
        "id": str(r["id"]),
        "title": r["title"],
        "start": r["start"],
        "end": r["end"],
        "allDay": bool(r["all_day"]),
        "color": r["color"] or "#3174ad",
        "extendedProps": {
            "description": r.get("description", "") or "",
            "channel": r.get("channel", "") or "",
            "submit_due": r.get("submit_due", "") or "",
            "manager": r.get("manager", "") or ""
        }
    })

calendar_options = {
    "initialView": "dayGridMonth",
    "headerToolbar": {
        "left": "prev,next today",
        "center": "title",
        "right": "dayGridMonth,timeGridWeek,timeGridDay",
    },
    "locale": "ko",
    "selectable": True,
    "editable": False,
    "height": "auto",
}

st.markdown(
    """
    <style>
    .fc .fc-button, .fc .fc-button-primary {
        background-color: #ff0000 !important;
        border: none !important;
        box-shadow: none !important;
        color: #ffffff !important;
    }
    .fc { --fc-border-color: transparent; }
    </style>
    """,
    unsafe_allow_html=True,
)

state = calendar(events=events, options=calendar_options)


# -------------------------
# 일정 상세 + 인라인 수정
# -------------------------

if state.get("eventClick"):
    clicked = state["eventClick"]["event"]
    props = clicked.get("extendedProps", {})

    st.markdown("### 📌 선택한 일정 상세 정보")

    st.markdown(
        """
        <style>
        .detail-container * { font-size: 16px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    event_id = int(clicked.get("id")) if clicked.get("id") else None

    st.markdown(
        f"""
        <div class="detail-container">
            <p><b>제목:</b> {clicked.get('title','')}</p>
            <p><b>시작일:</b> {clicked.get('start','')[:10]}</p>
            <p><b>종료일:</b> {clicked.get('end','')[:10]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    detail_lines = []

    if props.get("channel"):
        detail_lines.append(f"<p><b>채널:</b> {props['channel']}</p>")

    manager_display = None
    managers_str = props.get("manager", "") or ""

    if managers_str and not managers_df.empty:
        name_to_email = {r["name"]: r["email"] for _, r in managers_df.iterrows()}
        manager_names = [m.strip() for m in managers_str.split(",") if m.strip()]
        pairs = [f"{name} ({name_to_email.get(name, '이메일 없음')})" for name in manager_names]
        manager_display = ", ".join(pairs)

    if manager_display:
        detail_lines.append(f"<p><b>담당자:</b> {manager_display}</p>")

    if props.get("submit_due"):
        detail_lines.append(f"<p><b>Submit Due:</b> {props['submit_due']}</p>")
    if props.get("description"):
        detail_lines.append(f"<p><b>메모:</b> {props['description']}</p>")

    if detail_lines:
        st.markdown("<div class=\"detail-container\">" + "\n".join(detail_lines) + "</div>", unsafe_allow_html=True)


    # --------------- 인라인 수정 ---------------

    if "inline_edit_event_id" not in st.session_state:
        st.session_state.inline_edit_event_id = None

    if st.session_state.inline_edit_event_id == event_id:
        st.markdown("---")
        st.markdown("**인라인 수정**")

        full_df = fetch_events()
        current_row = full_df[full_df["id"] == event_id]

        if not current_row.empty:
            current_row = current_row.iloc[0]

            try:
                sdt = datetime.fromisoformat(str(current_row["start"])).astimezone(tz.tzlocal())
                edt = datetime.fromisoformat(str(current_row["end"])).astimezone(tz.tzlocal())
            except:
                sdt = edt = datetime.now()

            cur_title = str(current_row.get("title", ""))
            cur_desc = str(current_row.get("description", "") or "")
            cur_channel = str(current_row.get("channel", "") or "")
            cur_color = str(current_row.get("color", "") or "#3174ad")

            submit_due_str = str(current_row.get("submit_due", "") or "")
            submit_due_val = None
            if submit_due_str:
                try:
                    submit_due_val = datetime.strptime(submit_due_str, "%Y-%m-%d").date()
                except:
                    submit_due_val = None

            cur_managers_str = str(current_row.get("manager", "") or "")
            cur_managers = [m.strip() for m in cur_managers_str.split(",") if m.strip()]

            with st.form(f"inline_edit_form_{event_id}"):

                title_val = st.text_input("제목*", value=cur_title)

                col_a, col_b = st.columns(2)
                with col_a:
                    start_date_val = st.date_input("시작일*", value=sdt.date())
                with col_b:
                    end_date_val = st.date_input("종료일*", value=edt.date())

                desc_val = st.text_area("메모", value=cur_desc)

                channel_opts = ["선택 안함"] + CHANNEL_LIST
                default_idx = channel_opts.index(cur_channel) if cur_channel in CHANNEL_LIST else 0
                channel_val = st.selectbox("채널 (선택)", channel_opts, index=default_idx)
                if channel_val == "선택 안함":
                    channel_val = None

                st.markdown("**색상 선택**")
                chip_names = list(COLOR_CHIPS.keys())

                chip_index = 0
                for i, (chip_name, chip_color) in enumerate(COLOR_CHIPS.items()):
                    if chip_color.lower() == cur_color.lower():
                        chip_index = i
                        break

                chip_selected = st.radio("컬러 칩", chip_names, index=chip_index, horizontal=True)
                chip_color_val = COLOR_CHIPS[chip_selected]

                use_custom = st.checkbox("직접 색상 선택 사용", value=False)
                if use_custom:
                    custom_color_val = st.color_picker("색상 선택", value=chip_color_val)
                    color_val = custom_color_val
                else:
                    color_val = chip_color_val

                submit_due_val = st.date_input("Submit Due (선택)", value=submit_due_val)

                manager_list_opts = managers_df["name"].tolist() if not managers_df.empty else []
                managers_val = st.multiselect("담당자 선택 (복수 선택 가능)", manager_list_opts, default=cur_managers)

                col_save, col_delete = st.columns(2)

                with col_save:
                    save_btn = st.form_submit_button("💾 변경 저장")

                with col_delete:
                    del_btn = st.form_submit_button("🗑 삭제")

                if save_btn:
                    if not title_val:
                        st.warning("제목은 필수입니다.")
                    else:
                        start_iso = datetime.combine(start_date_val, datetime.min.time()).isoformat()
                        end_iso = (datetime.combine(end_date_val, datetime.min.time()) + timedelta(days=1)).isoformat()
                        submit_due_out = submit_due_val.strftime("%Y-%m-%d") if submit_due_val else None

                        update_event(
                            event_id,
                            title_val,
                            start_iso,
                            end_iso,
                            True,
                            color_val,
                            desc_val,
                            channel_val or None,
                            submit_due_out,
                            managers_val,
                        )

                        st.success("✅ 일정이 수정되었습니다.")
                        st.session_state.inline_edit_event_id = None
                        st.rerun()

                if del_btn:
                    delete_event(event_id)
                    st.warning("⚠️ 일정이 삭제되었습니다.")
                    st.session_state.inline_edit_event_id = None
                    st.rerun()

        if st.button("취소"):
            st.session_state.inline_edit_event_id = None
            st.rerun()

    else:
        if st.button("✏️ 여기서 수정"):
            st.session_state.inline_edit_event_id = event_id
            st.experimental_rerun()
