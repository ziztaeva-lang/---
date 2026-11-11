import streamlit as st
from PIL import Image
import base64
import pandas as pd
import io
import os
import fitz  # PyMuPDF кітапханасы (PDF-ті суретке айналдыру үшін)
from openai import OpenAI
from security_layer import (
    init_db, save_pending_result, get_pending_results, 
    approve_result, get_approved_results, external_ai_is_enabled,
    get_user_credits, deduct_credit, verify_user, add_payment_record,
    get_user_role, get_user_subject
)

st.set_page_config(page_title="SmartTest БЖБ–ТЖБ", layout="wide")
init_db()

# --- ЗАМАНАУИ МИНИМАЛИЗМ CSS СТИЛЬДЕРІ МЕН КАРТОЧКАЛАР ---
st.markdown("""
<style>
    .stApp {
        background-color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
    div.stExpander, div.stForm {
        background-color: #ffffff;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
        padding: 10px;
    }
    .stButton > button {
        background-color: #10b981;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        box-shadow: 0 2px 4px rgba(16, 185, 129, 0.2);
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #059669;
        color: white;
    }
    [data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
    }
    .correct-card {
        background-color: #ecfdf5;
        border-left: 5px solid #10b981;
        padding: 12px 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #065f46;
        font-size: 15px;
        font-weight: 500;
    }
    .incorrect-card {
        background-color: #fef2f2;
        border-left: 5px solid #ef4444;
        padding: 12px 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #991b1b;
        font-size: 15px;
        font-weight: 500;
    }
    .warning-card {
        background-color: #fffbeb;
        border-left: 5px solid #f59e0b;
        padding: 12px 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #92400e;
        font-size: 15px;
        font-weight: 500;
    }
</style>
""", unsafe_allow_html=True)

# --- ФАЙЛДАРДЫ ЖИ-ГЕ ДАЙЫНДАУ ФУНКЦИЯСЫ ---
def process_uploaded_file(uploaded_file):
    images_b64 = []
    file_bytes = uploaded_file.getvalue()
    
    if uploaded_file.name.lower().endswith(".pdf"):
        pdf_document = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            b64_str = base64.b64encode(img_bytes).decode('utf-8')
            images_b64.append(b64_str)
    else:
        b64_str = base64.b64encode(file_bytes).decode('utf-8')
        images_b64.append(b64_str)
        
    return images_b64

# --- СПЕЦИФИКАЦИЯ ФАЙЛЫН ОҚУ ---
@st.cache_data
def load_specs():
    possible_files = [
        "specs.xlsx", "specs.xls", "specs.csv", "specs",
        "./specs.xlsx", "./specs.xls", "./specs.csv",
        "data/specs.xlsx", "data/specs.csv"
    ]
    debug_messages = []
    for file_path in possible_files:
        if os.path.exists(file_path):
            if file_path.endswith(('.xlsx', '.xls')) or not file_path.endswith('.csv'):
                try:
                    df = pd.read_excel(file_path)
                    df.columns = df.columns.str.strip().str.lower()
                    required_cols = ["grade", "subject", "term", "type", "num", "task", "desc"]
                    if not [col for col in required_cols if col not in df.columns]:
                        return df, "Сәтті оқылды (Excel)"
                except Exception as e:
                    debug_messages.append(f"Excel қатесі: {e}")
            for enc in ["utf-8-sig", "utf-8", "cp1251", "latin1"]:
                try:
                    df = pd.read_csv(file_path, encoding=enc)
                    df.columns = df.columns.str.strip().str.lower()
                    required_cols = ["grade", "subject", "term", "type", "num", "task", "desc"]
                    if not [col for col in required_cols if col not in df.columns]:
                        return df, "Сәтті оқылды (CSV)"
                except Exception:
                    continue
    return pd.DataFrame(), debug_messages

specs_df, load_logs = load_specs()

# --- АУТЕНТИФИКАЦИЯ ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = ""

if not st.session_state.authenticated:
    st.title("🔐 SmartTest — Мұғалімнің жеке кабинетіне кіру")
    st.write("Платформаға кіру үшін логиніңіз бен құпия сөзіңізді енгізіңіз.")
    
    with st.form("login_form"):
        username_input = st.text_input("Логин (Username)", placeholder="Мысалы: zoya")
        password_input = st.text_input("Құпия сөз (Password)", type="password", placeholder="Құпия сөз...")
        if st.form_submit_button("Кіру"):
            user = verify_user(username_input, password_input)
            if not user:
                secrets_passwords = st.secrets.get("passwords", {})
                clean_username = username_input.strip().lower()
                if clean_username in secrets_passwords and secrets_passwords[clean_username] == password_input:
                    user = {"username": clean_username, "full_name": clean_username.capitalize()}
            if user:
                st.session_state.authenticated = True
                st.session_state.username = user["username"]
                st.success(f"Қош келдіңіз, {user.get('full_name', user['username'])}!")
                st.rerun()
            else:
                st.error("Логин немесе құпия сөз қате!")
    st.stop()

# --- НЕГІЗГІ ҚОСЫМША ---
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

current_user = st.session_state.get("username", "teacher")
user_balance = get_user_credits(current_user)
price_per_credit = 100  
total_tenge = user_balance * price_per_credit

user_role = get_user_role(current_user)
is_admin = (user_role == "admin" or current_user.lower() in ["zoya", "admin"])

st.sidebar.title("SmartTest")
st.sidebar.markdown(f"👤 **Қолданушы:** {current_user}")
st.sidebar.metric(label="💳 Сіздің балансыңыз", value=f"{user_balance} кредит", delta=f"{total_tenge:,.0f} ₸")
st.sidebar.markdown("---")

if is_admin:
    menu_options = ["Басты бет", "Жұмысты тексеру", "Мұғалім бекітуі", "Нәтижелер", "Статистика", "Балансты толтыру", "Қауіпсіздік"]
else:
    menu_options = ["Басты бет", "Жұмысты тексеру", "Мұғалім бекітуі", "Нәтижелер", "Статистика", "Балансты толтыру"]

menu = st.sidebar.selectbox("Бөлім", menu_options)

if st.sidebar.button("🚪 Жүйеден шығу"):
    st.session_state.authenticated = False
    st.session_state.username = ""
    st.rerun()

st.title("📄 SmartTest — БЖБ / ТЖБ (Тоқсандар бойынша автоматты жүйе)")

if menu == "Басты бет":
    st.write("Оқушы жұмыстарын тексеруге және мұғалімнің қорытынды бағасын бекітуге арналған қауіпсіз платформа.")
    if not specs_df.empty:
        st.success(f"✅ Спецификация файлы сәтті жүктелді! Барлығы **{len(specs_df)}** жазба танылды.")
    else:
        st.warning("⚠️ Спецификация файлы табылмады немесе форматы қате.")
        
    c1, c2 = st.columns(2)
    c1.metric("Мұғалім тексеруін күтуде", len(get_pending_results()))
    c2.metric("Бекітілген жұмыс", len(get_approved_results()))

elif menu == "Жұмысты тексеру":
    st.subheader("Жұмыстарды тіркеу және ЖИ арқылы кері байланыспен бағалау")
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        assessment_type = st.radio("📌 Бағалау түрі:", ["БЖБ (Бөлім бойынша)", "ТЖБ (Тоқсандық)"], horizontal=True)
    with col_t2:
        selected_term = st.selectbox("📌 Оқу тоқсаны:", ["1-тоқсан", "2-тоқсан", "3-тоқсан", "4-тоқсан"])

    default_grades = ["5-сынып", "6-сынып", "7-сынып", "8-сынып", "9-сынып", "10-сынып", "11-сынып"]
    default_subjects = [
        "Қазақ тілі", "Қазақ әдебиеті", "Алгебра", "Геометрия", "Физика", "Химия", 
        "Биология", "География", "Жаратылыстану", "Цифрлық сауаттылық және жасанды интеллект", 
        "Информатика және жасанды интеллект", "Қазақстан тарихы", "Дүние жүзі тарихы"
    ]

    assigned_subject = get_user_subject(current_user)

    if not is_admin and assigned_subject:
        st.info(f"🔒 Сізге бекітілген пән: **{assigned_subject}**")
        all_subjects = [assigned_subject]
    else:
        if not specs_df.empty:
            csv_grades = specs_df["grade"].dropna().astype(str).unique().tolist()
            csv_subjects = specs_df["subject"].dropna().astype(str).unique().tolist()
            all_grades = sorted(list(set(default_grades + csv_grades)))
            all_subjects = sorted(list(set(default_subjects + csv_subjects)))
        else:
            all_grades = default_grades
            all_subjects = default_subjects

    if not specs_df.empty:
        csv_grades = specs_df["grade"].dropna().astype(str).unique().tolist()
        all_grades = sorted(list(set(default_grades + csv_grades)))
    else:
        all_grades = default_grades

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        selected_grade = st.selectbox("📌 Сыныпты таңдаңыз", all_grades)
    with col_s2:
        if not is_admin and assigned_subject:
            selected_subject = st.selectbox("📌 Пәнді таңдаңыз", all_subjects, disabled=True)
        else:
            selected_subject = st.selectbox("📌 Пәнді таңдаңыз", all_subjects)

    prefix_text = "БЖБ" if "БЖБ" in assessment_type else "ТЖБ"
    bzhb_sub_num = ""
    if prefix_text == "БЖБ":
        bzhb_sub_num = st.selectbox("📌 БЖБ нөмірін таңдаңыз:", ["БЖБ 1", "БЖБ 2", "БЖБ 3"])

    default_task = f"{selected_grade}, {selected_term}. {selected_subject} пәні бойынша {prefix_text} тапсырмасы."
    default_learning_objectives = "9.2.1.2 — Бірқалыпты және бірқалыпты емес қозғалыстағы жылдамдық пен орын ауыстыруды анықтау."
    default_assessment_criteria = "1. Кілттік формуланы дұрыс қолданады;\n2. Графикті шартқа сай салады;\n3. Теориялық тұжырымды жүйелі жазады."
    default_desc = "1. Тапсырма шартын түсініп орындайды;\n2. Жауабын жүйелі түрде негіздеп жазады."
    default_achieved_goals = f"Оқушы {selected_subject} пәні бойынша {selected_term} бағдарламасындағы негізгі ұғымдарды түсініп меңгергенін көрсетеді."
    default_struggling_goals = "Формулаларды қолдануда немесе есептеу барысында жіберілетін ұсақ қателіктерді түзету."

    if not specs_df.empty:
        temp_df = specs_df.copy()
        temp_df["grade"] = temp_df["grade"].astype(