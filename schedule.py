import streamlit as st
from streamlit_calendar import calendar
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
from dateutil import tz
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

credentials = Credentials.from_service_account_info(
    st.secrets["google_service_account"], 
    scopes=SCOPES
)

gc = gspread.authorize(credentials)

SPREADSHEET_ID = "1taVkkzhIgJAsjM2IshKHsnflNAItJ7PGKlQKZqUrI0s"
sh = gc.open_by_key(SPREADSHEET_ID)

events_ws = sh.worksheet("events")
managers_ws = sh.worksheet("managers")




# -------------------------
# 기본 설정
# -------------------------
st.set_page_config(page_title="밍콩 달력", layout="wide")
st.title("📅 밍콩 달력")

DB_PATH = r"C:\Users\KIM_MINKYEONG07\Desktop\events.db"

# 채널 리스트
CHANNEL_LIST = ["스파오 공홈", "무신사", "지그재그", "에이블리", "쿠팡", "네이버", "11번가"]

# 채널별 기본 컬러 매핑
CHANNEL_COLORS = {
    "스파오 공홈": "#ff0000",  # 빨간색
    "무신사": "#000000",       # 검은색
    "지그재그": "#ff69b4",      # 분홍색
    "에이블리": "#ffff00",      # 노란색
    "쿠팡": "#ff4c00",          # 주황색
    "네이버": "#00ff00",        # 초록색
}

# 미리 정의된 컬러 칩
COLOR_CHIPS = {
    "공홈(기본)": "#ff0000",
    "무신사(기본)": "#000000",
    "지그재그(기본)": "#ff69b4",
    "에이블리(기본)": "#ffff00",
    "네이버(기본)": "#00ff00",
    "쿠팡(기본)": "#ff4c00"
}


# -------------------------
# DB 유틸
# -------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        start TEXT NOT NULL,
        end TEXT NOT NULL,
        all_day INTEGER DEFAULT 0,
        color TEXT,
        description TEXT,
        channel TEXT,
        submit_due TEXT,
        manager TEXT
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS managers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)
    # 기존 테이블에 새 컬럼 추가 (마이그레이션)
    try:
        conn.execute("ALTER TABLE events ADD COLUMN channel TEXT")
    except:
        pass  # 컬럼이 이미 존재하면 무시
    try:
        conn.execute("ALTER TABLE events ADD COLUMN submit_due TEXT")
    except:
        pass  # 컬럼이 이미 존재하면 무시
    try:
        conn.execute("ALTER TABLE events ADD COLUMN manager TEXT")
    except:
        pass  # 컬럼이 이미 존재하면 무시
    conn.commit()
    return conn

def fetch_events() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM events ORDER BY start", conn)
    conn.close()
    return df

def get_managers():
    conn = get_conn()
    df = pd.read_sql_query("SELECT name, email FROM managers ORDER BY name", conn)
    conn.close()
    return df

def add_manager(name, email):
    conn = get_conn()
    # 중복 체크
    existing = conn.execute("SELECT * FROM managers WHERE name=?", (name,)).fetchone()
    if existing:
        conn.close()
        return False
    conn.execute(
        "INSERT INTO managers (name, email, created_at) VALUES (?, ?, ?)",
        (name, email, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return True

def insert_event(title, start, end, all_day, color, description, channel, submit_due, managers):
    conn = get_conn()
    # managers를 콤마로 구분된 문자열로 저장
    manager_str = ",".join(managers) if managers else None
    conn.execute(
        "INSERT INTO events (title, start, end, all_day, color, description, channel, submit_due, manager) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, start, end, int(all_day), color, description, channel, submit_due, manager_str),
    )
    conn.commit()
    conn.close()

def update_event(event_id, title, start, end, all_day, color, description, channel, submit_due, managers):
    conn = get_conn()
    # managers를 콤마로 구분된 문자열로 저장
    manager_str = ",".join(managers) if managers else None
    conn.execute(
        """UPDATE events
           SET title=?, start=?, end=?, all_day=?, color=?, description=?, channel=?, submit_due=?, manager=?
           WHERE id=?""",
        (title, start, end, int(all_day), color, description, channel, submit_due, manager_str, event_id),
    )
    conn.commit()
    conn.close()

def delete_event(event_id):
    conn = get_conn()
    conn.execute("DELETE FROM events WHERE id=?", (event_id,))
    conn.commit()
    conn.close()

def send_email(to_email, subject, body):
    """이메일 발송 함수 (Gmail SMTP 사용 예시)"""
    try:
        # 이메일 설정 (사용자 환경에 맞게 수정 필요)
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        sender_email = "your_email@gmail.com"  # 발신자 이메일
        sender_password = "your_app_password"  # Gmail 앱 비밀번호
        
        # 메시지 생성
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # 서버 연결 및 메일 발송
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, to_email, text)
        server.quit()
        
        return True
    except Exception as e:
        st.error(f"이메일 발송 실패: {str(e)}")
        return False

def check_and_send_reminders():
    """기획전 오픈 알림을 발송할 이벤트 확인 및 발송"""
    now = datetime.now()
    events = fetch_events()
    
    for _, event in events.iterrows():
        if not event.get("manager") or not event.get("start"):
            continue
            
        # 시작일 파싱
        try:
            start_date = datetime.fromisoformat(event["start"])
        except:
            continue
        
        # 담당자 여러 명 파싱
        managers_str = event.get("manager", "")
        managers_list = [m.strip() for m in managers_str.split(",")] if managers_str else []
        
        # 담당자 이메일 조회
        managers_df = get_managers()
        emails = []
        for manager_name in managers_list:
            manager_info = managers_df[managers_df["name"] == manager_name]
            if not manager_info.empty:
                emails.append(manager_info.iloc[0]["email"])
        
        if not emails:
            continue
        
        # 오픈 1일 전 체크 (오전 8시에 발송)
        one_day_before = start_date - timedelta(days=1)
        if now.date() == one_day_before.date() and now.hour == 8 and now.minute < 1:
            subject = f"⏰ 기획전 오픈 1일 전 알림: {event['title']}"
            body = f"""
안녕하세요,

'{event['title']}' 기획전 오픈이 1일 전입니다.

기획전 정보:
- 제목: {event['title']}
- 시작일: {start_date.strftime('%Y년 %m월 %d일')}
- 채널: {event.get('channel', '미지정')}

확인 부탁드립니다.
            """
            for email in emails:
                send_email(email, subject, body)
        
        # 오픈 당일 체크 (오전 8시에 발송)
        if now.date() == start_date.date() and now.hour == 8 and now.minute < 1:
            subject = f"🎉 기획전 오픈 당일 알림: {event['title']}"
            body = f"""
안녕하세요,

'{event['title']}' 기획전이 오늘 오픈됩니다!

기획전 정보:
- 제목: {event['title']}
- 시작일: {start_date.strftime('%Y년 %m월 %d일')}
- 채널: {event.get('channel', '미지정')}

오늘 하루도 화이팅입니다!
            """
            for email in emails:
                send_email(email, subject, body)

# -------------------------
# 필터 (메인 상단 우측)
# -------------------------
# 드롭다운에는 항상 모든 채널을 노출
unique_channels = list(CHANNEL_LIST)
if "selected_channels" not in st.session_state:
    st.session_state.selected_channels = list(unique_channels)

# 담당자 목록 가져오기
managers_df = get_managers()
manager_options = ["선택 안함"] + managers_df["name"].tolist() if not managers_df.empty else ["선택 안함"]

# -------------------------
# 폼: 일정 등록/수정
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
    
    # 채널 선택 (검색 가능한 드롭다운)
    channel_options = ["선택 안함"] + CHANNEL_LIST
    channel = st.selectbox("채널 (선택)", channel_options, key="new_channel")
    if channel == "선택 안함":
        channel = None
    
    # 채널에 따라 기본 컬러 설정
    if channel and channel in CHANNEL_COLORS:
        default_color = CHANNEL_COLORS[channel]
    else:
        default_color = "#3174ad"
    
    st.markdown("**색상 선택**")
    
    # 컬러 칩 선택
    color_chip_options = list(COLOR_CHIPS.keys())
    selected_chip = st.radio("컬러 칩", color_chip_options, horizontal=True, key="new_color_chip")
    selected_color = COLOR_CHIPS[selected_chip]
    
    # 또는 직접 선택
    custom_color = st.color_picker("또는 직접 선택", value=selected_color, key="new_color_picker")
    
    # 사용자가 색상을 변경했는지 확인
    if custom_color != selected_color:
        color = custom_color
    else:
        color = selected_color
        
    submit_due = st.date_input("기획전 상품리스트 제출일)", value=None, key="new_submit_due")
    
    # 담당자 선택 (복수 선택 가능)
    selected_managers = st.multiselect("담당자 선택 (복수 선택 가능)", manager_options[1:] if len(manager_options) > 1 else [], key="new_manager")

    submitted = st.form_submit_button("➕ 일정 추가")
    if submitted:
        # 날짜만 사용 → ISO 문자열 (하루 종일로 처리)
        start_iso = datetime.combine(start_date, datetime.min.time()).isoformat()
        # FullCalendar에서 end가 다음날 00:00이어야 구간이 포함 표시됨
        end_iso = (datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)).isoformat()

        if not title:
            st.warning("제목은 필수입니다.")
        else:
            # submit_due를 날짜 문자열로 변환
            submit_due_str = submit_due.strftime("%Y-%m-%d") if submit_due else None
            insert_event(title, start_iso, end_iso, True, color, description, channel or None, submit_due_str, selected_managers)
            st.success("✅ 일정이 추가되었습니다.")
            st.rerun()

# -------------------------
# 담당자 관리 (사이드바 최하단)
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
# 메인: 캘린더 표시
# -------------------------
st.markdown("---")
st.subheader("📆 캘린더")

# 상단 우측: 채널 필터 (드롭다운 체크리스트 +)
top_left, top_right = st.columns([0.6, 0.4])
with top_right:
    prev_selected = st.session_state.selected_channels
    prev_all = len(CHANNEL_LIST) > 0 and len(prev_selected) == len(CHANNEL_LIST)

    # 전체 선택 상태일 때만 '전체' 옵션을 노출 (해제 기능만 제공)
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

    # 선택 결과 해석
    if "전체" not in current_selection and prev_all:
        # 전체가 체크된 상태에서 전체를 해제하면 모두 해제
        st.session_state.selected_channels = []
        st.rerun()
    else:
        # 일반적인 체크/해제
        st.session_state.selected_channels = [x for x in current_selection if x in CHANNEL_LIST]

# 필터 적용
events_df = fetch_events()
if "channel" in events_df.columns:
    if len(st.session_state.selected_channels) > 0:
        events_df = events_df[events_df["channel"].isin(st.session_state.selected_channels)]
    else:
        # 전체 해제 시 결과 없음
        events_df = events_df[events_df["channel"].isin([])]

# FullCalendar용 이벤트 변환
events = []
for _, r in events_df.iterrows():
    events.append({
        "id": str(r["id"]),
        "title": r["title"],
        "start": r["start"],  # ISO string
        "end": r["end"],      # ISO string
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
    "initialView": "dayGridMonth",  # month/week/day 전환 가능: dayGridMonth, timeGridWeek, timeGridDay
    "headerToolbar": {
        "left": "prev,next today",
        "center": "title",
        "right": "dayGridMonth,timeGridWeek,timeGridDay"
    },
    "locale": "ko",
    "selectable": True,
    "editable": False,  # True로 바꾸면 드래그로 이동/리사이즈 가능(그 경우 후처리도 구현 필요)
    "height": "auto",
}

# FullCalendar UI 커스텀: 버튼 색상 및 테두리 제거
st.markdown(
    """
    <style>
    /* 월/주/일 전환 버튼을 빨간색으로, 테두리 제거 */
    .fc .fc-button, .fc .fc-button-primary {
        background-color: #ff0000 !important;
        border: none !important;
        box-shadow: none !important;
        color: #ffffff !important;
    }
    .fc .fc-button:hover, .fc .fc-button-primary:hover,
    .fc .fc-button:focus, .fc .fc-button-primary:focus,
    .fc .fc-button:active, .fc .fc-button-primary:active {
        background-color: #ff0000 !important;
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }

    /* 캘린더 전체 테두리/그리드 라인 제거 */
    .fc { --fc-border-color: transparent; }
    .fc-theme-standard td, .fc-theme-standard th, .fc-theme-standard .fc-scrollgrid {
        border-color: transparent !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

state = calendar(events=events, options=calendar_options)

# 캘린더 클릭/선택 후 상태 활용 예 (필요 시 확장)
if state.get("eventClick"):
    clicked = state["eventClick"]["event"]
    props = clicked.get("extendedProps", {})

    st.markdown("### 📌 선택한 일정 상세 정보")

    # 모든 상세 정보 동일한 글씨 크기 적용
    st.markdown(
        """
        <style>
        .detail-container * { font-size: 16px !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    event_id = int(clicked.get("id")) if clicked.get("id") else None

    # 텍스트 형태로 동일한 크기 정보 표시
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

    # 채널/담당자/Submit Due/메모
    detail_lines = []
    if props.get("channel"):
        detail_lines.append(f"<p><b>채널:</b> {props['channel']}</p>")

    # 담당자 이름 + 이메일 표시
    manager_display = None
    managers_str = props.get("manager", "") or ""
    if managers_str:
        manager_names = [m.strip() for m in managers_str.split(",") if m.strip()]
        if not managers_df.empty:
            name_to_email = {r["name"]: r["email"] for _, r in managers_df.iterrows()}
            pairs = [f"{name} ({name_to_email.get(name, '이메일 없음')})" for name in manager_names]
            manager_display = ", ".join(pairs)
        else:
            manager_display = ", ".join(manager_names)
    if manager_display:
        detail_lines.append(f"<p><b>담당자:</b> {manager_display}</p>")

    if props.get("submit_due"):
        detail_lines.append(f"<p><b>Submit Due:</b> {props['submit_due']}</p>")
    if props.get("description"):
        detail_lines.append(f"<p><b>메모:</b> {props['description']}</p>")

    if detail_lines:
        st.markdown("<div class=\"detail-container\">" + "\n".join(detail_lines) + "</div>", unsafe_allow_html=True)

    # 인라인 수정 토글 및 폼
    if "inline_edit_event_id" not in st.session_state:
        st.session_state.inline_edit_event_id = None

    if st.session_state.inline_edit_event_id == event_id:
        # 현재 이벤트 인라인 편집 중
        st.markdown("---")
        st.markdown("**인라인 수정**")

        # DB에서 현재 이벤트 로드
        full_df = fetch_events()
        current_row = full_df[full_df["id"] == event_id]
        if current_row.empty:
            st.warning("선택한 일정을 찾을 수 없습니다.")
        else:
            current_row = current_row.iloc[0]

            # 기본 값 준비
            try:
                sdt = datetime.fromisoformat(str(current_row["start"]).replace("Z", "+00:00")).astimezone(tz.tzlocal())
                edt = datetime.fromisoformat(str(current_row["end"]).replace("Z", "+00:00")).astimezone(tz.tzlocal())
            except Exception:
                sdt = datetime.now()
                edt = datetime.now()

            cur_title = str(current_row.get("title", ""))
            cur_desc = str(current_row.get("description", "") or "")
            cur_channel = str(current_row.get("channel", "") or "")
            cur_color = str(current_row.get("color", "") or "#3174ad")

            submit_due_str = str(current_row.get("submit_due", "") or "")
            submit_due_val = None
            if submit_due_str:
                try:
                    submit_due_val = datetime.strptime(submit_due_str, "%Y-%m-%d").date()
                except Exception:
                    submit_due_val = None

            cur_managers_str = str(current_row.get("manager", "") or "")
            cur_managers = [m.strip() for m in cur_managers_str.split(",") if m.strip()]

            with st.form(f"inline_edit_form_{event_id}"):
                title_val = st.text_input("제목*", value=cur_title, key=f"inline_title_{event_id}")
                col_a, col_b = st.columns(2)
                with col_a:
                    start_date_val = st.date_input("시작일*", value=sdt.date(), key=f"inline_start_{event_id}")
                with col_b:
                    end_date_val = st.date_input("종료일*", value=edt.date(), key=f"inline_end_{event_id}")

                desc_val = st.text_area("메모", value=cur_desc, key=f"inline_desc_{event_id}")

                channel_opts = ["선택 안함"] + CHANNEL_LIST
                default_idx = channel_opts.index(cur_channel) if cur_channel in CHANNEL_LIST else 0
                channel_val = st.selectbox("채널 (선택)", channel_opts, index=default_idx, key=f"inline_channel_{event_id}")
                if channel_val == "선택 안함":
                    channel_val = None

                # 색상 선택 (컬러 칩 또는 직접 선택)
                st.markdown("**색상 선택**")
                chip_names = list(COLOR_CHIPS.keys())
                chip_index = 0
                for i, (chip_name, chip_color) in enumerate(COLOR_CHIPS.items()):
                    if chip_color.lower() == cur_color.lower():
                        chip_index = i
                        break
                chip_selected = st.radio("컬러 칩", chip_names, index=chip_index, horizontal=True, key=f"inline_chip_{event_id}")
                chip_color_val = COLOR_CHIPS[chip_selected]
                use_custom = st.checkbox("직접 색상 선택 사용", value=False, key=f"inline_use_custom_{event_id}")
                if use_custom:
                    custom_color_val = st.color_picker("색상 선택", value=chip_color_val, key=f"inline_color_{event_id}")
                    color_val = custom_color_val
                else:
                    color_val = chip_color_val

                submit_due_val = st.date_input("Submit Due (선택)", value=submit_due_val, key=f"inline_submit_due_{event_id}")

                manager_list_opts = managers_df["name"].tolist() if not managers_df.empty else []
                managers_val = st.multiselect("담당자 선택 (복수 선택 가능)", manager_list_opts, default=cur_managers, key=f"inline_managers_{event_id}")

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
                        update_event(event_id, title_val, start_iso, end_iso, True, color_val, desc_val, channel_val or None, submit_due_out, managers_val)
                        st.success("✅ 일정이 수정되었습니다.")
                        st.session_state.inline_edit_event_id = None
                        st.rerun()

                if 'del_btn' in locals() and del_btn:
                    delete_event(event_id)
                    st.warning("⚠️ 일정이 삭제되었습니다.")
                    st.session_state.inline_edit_event_id = None
                    st.rerun()

        if st.button("취소", key=f"inline_cancel_{event_id}"):
            st.session_state.inline_edit_event_id = None
            st.rerun()
    else:
        if st.button("✏️ 여기서 수정", key=f"inline_edit_btn_{event_id}"):
            st.session_state.inline_edit_event_id = event_id
            st.experimental_rerun()




