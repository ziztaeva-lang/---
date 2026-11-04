import streamlit as st
from PIL import Image
import base64
import pandas as pd
import io
import os
from openai import OpenAI
from security_layer import (
    init_db, save_pending_result, get_pending_results, 
    approve_result, get_approved_results, external_ai_is_enabled,
    get_user_credits, deduct_credit, verify_user
)

st.set_page_config(page_title="SmartTest БЖБ–ТЖБ", layout="wide")
init_db()

# --- ЗАМАНАУИ МИНИМАЛИЗМ CSS СТИЛЬДЕРІ ---
st.markdown("""
<style>
    /* Негізгі фон мен қаріп */
    .stApp {
        background-color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    
    /* Бүйірлік мәзір (Sidebar) */
    [data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }

    /* Карточкалар бен контейнерлерді әдемілеу */
    div.stExpander, div.stForm {
        background-color: #ffffff;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.02);
        padding: 10px;
    }

    /* Батырмалардың заманауи жасыл стилі */
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

    /* Метрикалар мен көрсеткіштер блогы */
    [data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.02);
    }
</style>
""", unsafe_allow_html=True)

# --- ФАЙЛДЫ ДЕБАГГИНГ ЖӘНЕ ҚАУІПСІЗ ОҚУ ЖҮЙЕСІ ---
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
                    missing_cols = [col for col in required_cols if col not in df.columns]
                    
                    if not missing_cols:
                        return df, "Сәтті оқылды (Excel)"
                    else:
                        debug_messages.append(f"Файл табылды ({file_path}), бірақ мына бағандар жетіспеді: {missing_cols}.")
                except Exception as e:
                    debug_messages.append(f"Excel оқу қатесі ({file_path}): {e}")
            
            for enc in ["utf-8-sig", "utf-8", "cp1251", "latin1"]:
                try:
                    df = pd.read_csv(file_path, encoding=enc)
                    df.columns = df.columns.str.strip().str.lower()
                    required_cols = ["grade", "subject", "term", "type", "num", "task", "desc"]
                    missing_cols = [col for col in required_cols if col not in df.columns]
                    
                    if not missing_cols:
                        return df, "Сәтті оқылды (CSV)"
                except Exception:
                    continue
            
    return pd.DataFrame(), debug_messages

specs_df, load_logs = load_specs()

# --- АУТЕНТИФИКАЦИЯ (ЛОГИН ЖӘНЕ ПАРОЛЬ МЕНЕН КІРУ) ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = ""

if not st.session_state.authenticated:
    st.title("🔐 SmartTest — Мұғалімнің жеке кабинетіне кіру")
    st.write("Платформаға кіру үшін логиніңіз бен құпия сөзіңізді енгізіңіз.")
    
    with st.form("login_form"):
        username_input = st.text_input("Логин (Username)", placeholder="Мысалы: gulnar")
        password_input = st.text_input("Құпия сөз (Password)", type="password", placeholder="Құпия сөзіңізді енгізіңіз...")
        login_submitted = st.form_submit_button("Кіру")
        
        if login_submitted:
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
                st.error("Логин немесе құпия сөз қате! Қайта көріңіз.")
    
    st.stop()

# --- НЕГІЗГІ ҚОСЫМША (КІРГЕННЕН КЕЙІН) ---
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

current_user = st.session_state.get("username", "teacher")
user_balance = get_user_credits(current_user)

price_per_credit = 50 
total_tenge = user_balance * price_per_credit

st.sidebar.title("SmartTest")
st.sidebar.markdown(f"👤 **Қолданушы:** {current_user}")
st.sidebar.metric(label="💳 Сіздің балансыңыз", value=f"{user_balance} кредит", delta=f"{total_tenge:,.0f} ₸")
st.sidebar.markdown("---")

menu = st.sidebar.selectbox("Бөлім", ["Басты бет", "Жұмысты тексеру", "Мұғалім бекітуі", "Нәтижелер", "Статистика", "Қауіпсіздік"])

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

    if not specs_df.empty:
        csv_grades = specs_df["grade"].dropna().astype(str).unique().tolist()
        csv_subjects = specs_df["subject"].dropna().astype(str).unique().tolist()
        all_grades = sorted(list(set(default_grades + csv_grades)))
        all_subjects = sorted(list(set(default_subjects + csv_subjects)))
    else:
        all_grades = default_grades
        all_subjects = default_subjects

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        selected_grade = st.selectbox("📌 Сыныпты таңдаңыз", all_grades)
    with col_s2:
        selected_subject = st.selectbox("📌 Пәнді таңдаңыз", all_subjects)

    prefix_text = "БЖБ" if "БЖБ" in assessment_type else "ТЖБ"
    bzhb_sub_num = ""
    if prefix_text == "БЖБ":
        bzhb_sub_num = st.selectbox("📌 БЖБ нөмірін таңдаңыз:", ["БЖБ 1", "БЖБ 2", "БЖБ 3"])

    default_task = f"{selected_grade}. {selected_term}. {selected_subject} пәні бойынша {prefix_text} тапсырмасы."
    default_desc = "1. Тапсырма шартын толық түсініп, талапқа сай орындайды (2 балл);\n2. Жауабын жүйелі түрде негіздеп, қатесіз жазады (3 балл)."

    if not specs_df.empty:
        filtered = specs_df[
            (specs_df["grade"].astype(str).str.strip() == str(selected_grade).strip()) & 
            (specs_df["subject"].astype(str).str.strip() == str(selected_subject).strip()) & 
            (specs_df["term"].astype(str).str.strip() == str(selected_term).strip()) & 
            (specs_df["type"].astype(str).str.strip() == str(prefix_text).strip())
        ]
        if prefix_text == "БЖБ" and bzhb_sub_num:
            filtered = filtered[filtered["num"].astype(str).str.strip() == str(bzhb_sub_num).strip()]
            
        if not filtered.empty:
            row = filtered.iloc[0]
            default_task = str(row["task"])
            default_desc = str(row["desc"])

    task_text = st.text_area("Тапсырма тақырыбы немесе сұрақ", value=default_task)
    descriptors = st.text_area("Бағалау дескрипторлары", value=default_desc)
    max_score = st.number_input("Ең жоғары ұпай", min_value=0.5, max_value=100.0, value=10.0 if prefix_text == "ТЖБ" else 5.0, step=0.5)
    
    uploaded_files = st.file_uploader("Оқушылардың жұмыс суреттерін жүктеу", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    
    if uploaded_files:
        st.success(f"Барлығы {len(uploaded_files)} жұмыс жүктелді.")
        for idx, uploaded_file in enumerate(uploaded_files):
            with st.expander(f"📁 Жұмыс №{idx+1}: {uploaded_file.name}"):
                col_img, col_form = st.columns([1, 1])
                with col_img:
                    try:
                        image = Image.open(uploaded_file)
                        st.image(image, caption=uploaded_file.name, use_container_width=True)
                    except Exception:
                        st.error("Суретті ашу мүмкін болмады.")
                with col_form:
                    st_code = st.text_input("Анонимді оқушы коды", value=f"{selected_grade}-0{idx+1}", key=f"code_{idx}")
                    def encode_image(file_obj):
                        return base64.b64encode(file_obj.getvalue()).decode('utf-8')
                    ai_exp = "Бағаны мұғалім тексеруі қажет."

                    if st.button("🔍 ЖИ арқылы талдау", key=f"ai_btn_{idx}"):
                        current_balance = get_user_credits(current_user)
                        if current_balance < 1.0:
                            st.error("❌ Балансыңызда кредит жеткіліксіз! Жұмысты талдау үшін балансты толықтырыңыз.")
                        else:
                            with st.spinner("ЖИ талдап жатыр..."):
                                try:
                                    b64_img = encode_image(uploaded_file)
                                    response = client.chat.completions.create(
                                        model="gpt-4o",
                                        messages=[
                                            {"role": "system", "content": "Сіз тәжірибелі мектеп мұғалімісіз."},
                                            {"role": "user", "content": [
                                                {"type": "text", "text": f"Тапсырма: {task_text}\nДескрипторлар: {descriptors}"},
                                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                                            ]}
                                        ],
                                        max_tokens=600
                                    )
                                    ai_exp = response.choices[0].message.content
                                    deduct_credit(current_user, amount=1.0)
                                    st.success("Талдау сәтті жасалды (-1 кредит)!")
                                    st.write(ai_exp)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Қате: {e}")

                    with st.form(key=f"form_{idx}"):
                        prop_score = st.number_input("Алдын ала ұпай", min_value=0.0, max_value=float(max_score), value=0.0, step=0.5, key=f"score_{idx}")
                        explanation = st.text_area("Кері байланыс", value=ai_exp, key=f"exp_{idx}")
                        if st.form_submit_button("Тексеруге сақтау"):
                            if st.strip(): # fixed logical error check
                                save_pending_result(st_code.strip(), f"[{selected_term} | {prefix_text} | {selected_grade} - {selected_subject}] {task_text.strip()}", descriptors.strip(), float(prop_score), float(max_score), explanation.strip())
                                st.success("Сақталды!")

elif menu == "Мұғалім бекітуі":
    st.subheader("Мұғалімнің қорытынды бағасын бекіту")
    pending = get_pending_results()
    if not pending:
        st.info("Бекітуді күтіп тұрған жұмыс жоқ.")
    for item in pending:
        with st.expander(f"Жұмыс: {item['student_code']} — {item['proposed_score']} балл"):
            score = st.number_input("Бекітілетін ұпай", value=float(item['proposed_score']), key="app_" + item["id"])
            comment = st.text_area("Ескертпе", key="com_" + item["id"])
            if st.button("Бекіту", key="btn_" + item["id"]):
                approve_result(item["id"], score, current_user, comment)
                st.rerun()

elif menu == "Нәтижелер":
    st.subheader("Мұғалім бекіткен нәтижелер")
    rows = get_approved_results()
    if not rows:
        st.info("Әзірге нәтиже жоқ.")
    else:
        df_res = pd.DataFrame(rows)
        st.dataframe(df_res)

elif menu == "Статистика":
    st.subheader("📊 Статистика")
    rows = get_approved_results()
    if not rows:
        st.info("Әзірге статистика жоқ.")
    else:
        df_stat = pd.DataFrame(rows)
        st.bar_chart(df_stat.set_index('student_code')[['teacher_score']])

elif menu == "Қауіпсіздік":
    st.subheader("Қауіпсіздік және файл күйі (Диагностика)")
    st.write(f"Ағымдағы пайдаланушы: **{current_user}** | Баланс: **{user_balance} кредит** ({total_tenge:,.0f} ₸)")
    st.markdown("---")
    
    if not specs_df.empty:
        st.success(f"✅ Спецификация файлы сәтті оқылды! Жалпы жолдар саны: **{len(specs_df)}**")
        st.write("**Файлдағы табылған бағандар:**", list(specs_df.columns))
        st.dataframe(specs_df.head(5))
    else:
        st.error("❌ Спецификация файлы табылмады немесе баған атаулары қате.")
        st.markdown("### 🔍 Диагностикалық логтар:")
        for log in load_logs:
            st.warning(log)