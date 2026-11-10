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

# --- ЗАМАНАУИ МИНИМАЛИЗМ CSS СТИЛЬДЕРІ ---
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
        temp_df["grade"] = temp_df["grade"].astype(str).str.strip().str.lower()
        temp_df["subject"] = temp_df["subject"].astype(str).str.strip().str.lower()
        temp_df["term"] = temp_df["term"].astype(str).str.strip().str.lower()
        temp_df["type"] = temp_df["type"].astype(str).str.strip().str.lower()
        
        s_grade = str(selected_grade).strip().lower()
        s_subject = str(selected_subject).strip().lower()
        s_term = str(selected_term).strip().lower()
        s_type = str(prefix_text).strip().lower()

        filtered = temp_df[
            (temp_df["grade"] == s_grade) & 
            (temp_df["subject"] == s_subject) & 
            (temp_df["term"] == s_term) & 
            (temp_df["type"] == s_type)
        ]
        
        if prefix_text == "БЖБ" and bzhb_sub_num and "num" in temp_df.columns:
            temp_df["num"] = temp_df["num"].astype(str).str.strip().str.lower()
            s_num = str(bzhb_sub_num).strip().lower()
            sub_filtered = filtered[filtered["num"] == s_num]
            if not sub_filtered.empty:
                filtered = sub_filtered

        if not filtered.empty:
            row = filtered.iloc[0]
            default_task = str(row["task"]) if "task" in row and pd.notna(row["task"]) else default_task
            default_desc = str(row["desc"]) if "desc" in row and pd.notna(row["desc"]) else default_desc
            if "learning_objectives" in row and pd.notna(row["learning_objectives"]):
                default_learning_objectives = str(row["learning_objectives"])
            if "assessment_criteria" in row and pd.notna(row["assessment_criteria"]):
                default_assessment_criteria = str(row["assessment_criteria"])
            if "achieved_goals" in row and pd.notna(row["achieved_goals"]):
                default_achieved_goals = str(row["achieved_goals"])
            if "struggling_goals" in row and pd.notna(row["struggling_goals"]):
                default_struggling_goals = str(row["struggling_goals"])

    st.markdown("---")
    st.subheader("⚙️ Тапсырма, оқу мақсаттары, критерийлер және дескрипторлар параметрлері")
    
    col_score, col_gen_btn = st.columns([1, 2])
    with col_score:
        max_score = st.number_input(
            "Ең жоғары ұпай", 
            min_value=1.0, 
            max_value=50.0, 
            value=14.0, 
            step=1.0
        )
    with col_gen_btn:
        st.write("")
        st.write("")
        auto_gen_clicked = st.button("✨ Барлық параметрлерді автоматты генерациялау")

    task_topic = st.text_input("Тапсырма тақырыбы немесе сұрақ", value=default_task)

    if auto_gen_clicked:
        with st.spinner("Жасанды интеллект мектеп стандартына сай оқу мақсаттары мен критерийлерді дайындауда..."):
            try:
                prompt = f"""
                Сен Қазақстан Республикасының орта білім беру мазмұны, БЖБ және ТЖБ өткізу ережелерін жеткізетін тәжірибелі мектеп мұғалімі әрі әдіскерсің.
                
                Мектеп стандартының деректері:
                - Сынып және пән: {selected_grade}, {selected_subject}
                - Бағалау түрі: {assessment_type} ({selected_term})
                - Тапсырма тақырыбы/мазмұны: {task_topic}
                - Жалпы ең жоғарғы ұпай: {int(max_score)} балл.
                
                Осы деректер негізінде Қазақстан мектептеріндегі критериалды бағалау жүйесіне қатаң сәйкес келетін:
                1. Нақты тапсырма шартын немесе нұсқауын.
                2. Оқу мақсаттарын.
                3. Бағалау критерийін.
                4. {int(max_score)} балдық жүйеге дәл бөлінген бағалау дескрипторларын.
                5. "Қол жеткізілген мақсаттар".
                6. "Қиындық тудырған мақсаттар".
                
                Жауапты мына форматта бер:
                [ШАРТ] ... [/ШАРТ]
                [ОҚУ_МАҚСАТТАРЫ] ... [/ОҚУ_МАҚСАТТАРЫ]
                [БАҒАЛАУ_КРИТЕРИЙІ] ... [/БАҒАЛАУ_КРИТЕРИЙІ]
                [ДЕСКРИПТОР] ... [/ДЕСКРИПТОР]
                [МАҚСАТТАР_ҚОЛ_ЖЕТКІЗІЛГЕН] ... [/МАҚСАТТАР_ҚОЛ_ЖЕТКІЗІЛГЕН]
                [МАҚСАТТАР_ҚИЫНДЫҚ] ... [/МАҚСАТТАР_ҚИЫНДЫҚ]
                """
                
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2
                )
                res_text = response.choices[0].message.content
                
                import re
                t_match = re.search(r'[ШАРТ](.*?)\[/ШАРТ\]', res_text, re.DOTALL)
                om_match = re.search(r'\[ОҚУ_МАҚСАТТАРЫ\](.*?)\[/ОҚУ_МАҚСАТТАРЫ\]', res_text, re.DOTALL)
                bk_match = re.search(r'\[БАҒАЛАУ_КРИТЕРИЙІ\](.*?)\[/БАҒАЛАУ_КРИТЕРИЙІ\]', res_text, re.DOTALL)
                d_match = re.search(r'[ДЕСКРИПТОР](.*?)\[/ДЕСКРИПТОР\]', res_text, re.DOTALL)
                a_match = re.search(r'\[МАҚСАТТАР_ҚОЛ_ЖЕТКІЗІЛГЕН\](.*?)\[/МАҚСАТТАР_ҚОЛ_ЖЕТКІЗІЛГЕН\]', res_text, re.DOTALL)
                s_match = re.search(r'\[МАҚСАТТАР_ҚИЫНДЫҚ\](.*?)\[/МАҚСАТТАР_ҚИЫНДЫҚ\]', res_text, re.DOTALL)
                
                if t_match:
                    task_topic = t_match.group(1).strip()
                if om_match:
                    st.session_state['generated_learning_objectives'] = om_match.group(1).strip()
                if bk_match:
                    st.session_state['generated_assessment_criteria'] = bk_match.group(1).strip()
                if d_match:
                    st.session_state['generated_descriptors'] = d_match.group(1).strip()
                if a_match:
                    st.session_state['generated_achieved'] = a_match.group(1).strip()
                if s_match:
                    st.session_state['generated_struggling'] = s_match.group(1).strip()
                
                st.success("✅ Барлық параметрлер мектеп стандартына сай генерацияланды!")
                st.rerun()
            except Exception as e:
                st.error(f"Генерация қатесі: {e}")

    default_lo_text = st.session_state.get('generated_learning_objectives', default_learning_objectives)
    learning_objectives = st.text_area("📚 Оқу мақсаттары", value=default_lo_text, height=80)

    default_ac_text = st.session_state.get('generated_assessment_criteria', default_assessment_criteria)
    assessment_criteria = st.text_area("📋 Бағалау критерийі", value=default_ac_text, height=90)

    default_desc_text = st.session_state.get('generated_descriptors', default_desc)
    descriptors = st.text_area("Бағалау дескрипторлары", value=default_desc_text, height=120)
    
    default_achieved_text = st.session_state.get('generated_achieved', default_achieved_goals)
    achieved_goals = st.text_area("🎯 Қол жеткізілген мақсаттар", value=default_achieved_text, height=90)

    default_struggling_text = st.session_state.get('generated_struggling', default_struggling_goals)
    struggling_goals = st.text_area("⚠️ Қиындық тудырған мақсаттар", value=default_struggling_text, height=90)

    uploaded_files = st.file_uploader("Оқушылардың жұмыс файлдарын жүктеу (JPG, PNG, PDF)", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)
    
    if uploaded_files:
        st.success(f"Барлығы {len(uploaded_files)} файл жүктелді.")
        for idx, uploaded_file in enumerate(uploaded_files):
            with st.expander(f"📁 Жұмыс №{idx+1}: {uploaded_file.name}"):
                col_img, col_form = st.columns([1, 1])
                with col_img:
                    if uploaded_file.name.lower().endswith('.pdf'):
                        st.info("📄 PDF форматындағы документ жүктелді.")
                    else:
                        try:
                            image = Image.open(uploaded_file)
                            st.image(image, caption=uploaded_file.name, use_container_width=True)
                        except Exception:
                            st.error("Суретті ашу мүмкін болмады.")
                with col_form:
                    student_name_key = f"student_name_{idx}"
                    if student_name_key not in st.session_state:
                        st.session_state[student_name_key] = f"{selected_grade}-0{idx+1}"

                    st_code = st.text_input("Оқушы аты-жөні", value=st.session_state[student_name_key], key=f"name_input_{idx}")
                    
                    ai_res_key = f"ai_result_{idx}"
                    if ai_res_key not in st.session_state:
                        st.session_state[ai_res_key] = "Бағаны мұғалім тексеруі қажет."

                    if st.button("🔍 Тексеру", key=f"ai_btn_{idx}"):
                        current_balance = get_user_credits(current_user)
                        
                        if not is_admin and current_balance < 1.0:
                            st.error("❌ Балансыңызда кредит жеткіліксіз!")
                        else:
                            with st.spinner("ЖИ суреттен оқушының аты-жөнін оқып, әрбір тапсырманы талдап жатыр..."):
                                try:
                                    images_b64 = process_uploaded_file(uploaded_file)
                                    
                                    prompt_text = f"""
Сен Қазақстан мектептерінің тәжірибелі мұғалімі әрі сарапшысың. 
Оқушының мына жұмысын берілген оқу мақсаттары, бағалау критерийлері, дескрипторлар мен ең жоғарғы баллға ({int(max_score)}) сәйкес мұқият тексер.

ҚАТАҢ БАҒАЛАУ ШАРТЫ ЖӘНЕ ТҮС ЖҮЙЕСІ:
1. Жалпы максималды балл ДӘЛ {int(max_score)} БАЛЛ. Басқа шкала қолдануға БОЛМАЙДЫ.
2. Әр тапсырма мен тармақты тексерген кезде мына белгілеу жүйесін қатаң қолдан:
   - 🟢 [Дұрыс] — Жауап толық дұрыс.
   - 🔴 [Қате] — Жауап қате немесе дескриптор орындалмаған.
   - 🟡 [Жартылай] — Жартылай дұрыс немесе мұғалімнің қосымша тексеруін/назар аударуын талап етеді.
3. Қорытынды баллды тек 'Жиынтық балл: X/{int(max_score)}' форматында көрсет.

Тапсырма тақырыбы: {task_topic}
Оқу мақсаттары: {learning_objectives}
Бағалау критерийі: {assessment_criteria}
Дескрипторлар: {descriptors}
Қол жеткізілген мақсаттар: {achieved_goals}
Қиындық тудырған мақсаттар: {struggling_goals}

НАҚТЫ ТАЛАПТАР:
1. ФАЙЛДЫҢ ҮСТІҢГІ ТҰСЫНДА ЖАЗЫЛҒАН ОҚУШЫНЫҢ АТЫ-ЖӨНІН ТАБЫП, МЫНА ФОРМАТТА ЖАЗ:
   [ОҚУШЫ_АТЫ] Тегі Есімі [/ОҚУШЫ_АТЫ] (егер табылмаса "Белгісіз оқушы" деп көрсет).
2. Жұмыстағы әрбір тапсырманы және оның тармақтарын (1-тапсырма, 2-тапсырма, а, б, в, г т.б.) бөлек-бөлек қарастыр.
3. Соңында осы жұмыс бойынша жиынтық баллды 'Жиынтық балл: X/{int(max_score)}' түрінде көрсет.
"""
                                    messages_content = [{"type": "text", "text": prompt_text}]
                                    for img_b64 in images_b64:
                                        messages_content.append({
                                            "type": "image_url",
                                            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                                        })

                                    response = client.chat.completions.create(
                                        model="gpt-4o",
                                        messages=[
                                            {"role": "system", "content": f"Сіз оқушы жұмыстарын 🟢 [Дұрыс], 🔴 [Қате], 🟡 [Жартылай] белгілерімен тексеретін, барлық баллды қатаң түрде {int(max_score)} баллдық шкалаға сай есептейтін мұғалімсіз."},
                                            {"role": "user", "content": messages_content}
                                        ],
                                        max_tokens=1200
                                    )
                                    
                                    full_ai_resp = response.choices[0].message.content
                                    
                                    import re
                                    name_match = re.search(r'\[ОҚУШЫ_АТЫ\](.*?)\[/ОҚУШЫ_АТЫ\]', full_ai_resp, re.DOTALL)
                                    if name_match:
                                        found_name = name_match.group(1).strip()
                                        if found_name and "Белгісіз" not in found_name:
                                            st.session_state[student_name_key] = found_name
                                        full_ai_resp = re.sub(r'\[ОҚУШЫ_АТЫ\].*?\[/ОҚУШЫ_АТЫ\]', '', full_ai_resp).strip()
                                    
                                    st.session_state[ai_res_key] = full_ai_resp
                                    if not is_admin:
                                        deduct_credit(current_user, amount=1.0)
                                    st.success("✅ Тексеру сәтті аяқталды!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Қате пайда болды: {e}")

                    prop_score = st.number_input("Алдын ала ұпай", min_value=0.0, max_value=float(max_score), value=0.0, step=0.5, key=f"score_{idx}")
                    explanation = st.text_area("Кері байланыс (🟢/🔴/🟡 белгілерімен)", value=st.session_state[ai_res_key], height=200, key=f"exp_{idx}")
                    
                    if st.button("💾 Тексеруге сақтау", key=f"save_btn_{idx}"):
                        current_st_name = st_code.strip() if st_code.strip() else st.session_state[student_name_key]
                        if current_st_name:
                            full_feedback = f"Кері байланыс пен белгілер:\n{explanation.strip()}\n\n📚 Оқу мақсаттары:\n{learning_objectives.strip()}\n\n📋 Бағалау критерийі:\n{assessment_criteria.strip()}\n\n🎯 Қол жеткізілген мақсаттар:\n{achieved_goals.strip()}\n\n⚠️ Қиындық тудырған мақсаттар:\n{struggling_goals.strip()}"
                            save_pending_result(
                                current_st_name, 
                                f"[{selected_term} | {prefix_text} | {selected_grade} - {selected_subject}] {task_topic.strip()}", 
                                descriptors.strip(), 
                                float(prop_score), 
                                float(max_score), 
                                full_feedback
                            )
                            st.success("✅ Тексеруге сәтті сақталды!")
                        else:
                            st.error("❌ Оқушы аты-жөнін енгізіңіз!")

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
        st.dataframe(df_res)import streamlit as st
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

# --- ЗАМАНАУИ МИНИМАЛИЗМ CSS СТИЛЬДЕРІ ---
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
        temp_df["grade"] = temp_df["grade"].astype(str).str.strip().str.lower()
        temp_df["subject"] = temp_df["subject"].astype(str).str.strip().str.lower()
        temp_df["term"] = temp_df["term"].astype(str).str.strip().str.lower()
        temp_df["type"] = temp_df["type"].astype(str).str.strip().str.lower()
        
        s_grade = str(selected_grade).strip().lower()
        s_subject = str(selected_subject).strip().lower()
        s_term = str(selected_term).strip().lower()
        s_type = str(prefix_text).strip().lower()

        filtered = temp_df[
            (temp_df["grade"] == s_grade) & 
            (temp_df["subject"] == s_subject) & 
            (temp_df["term"] == s_term) & 
            (temp_df["type"] == s_type)
        ]
        
        if prefix_text == "БЖБ" and bzhb_sub_num and "num" in temp_df.columns:
            temp_df["num"] = temp_df["num"].astype(str).str.strip().str.lower()
            s_num = str(bzhb_sub_num).strip().lower()
            sub_filtered = filtered[filtered["num"] == s_num]
            if not sub_filtered.empty:
                filtered = sub_filtered

        if not filtered.empty:
            row = filtered.iloc[0]
            default_task = str(row["task"]) if "task" in row and pd.notna(row["task"]) else default_task
            default_desc = str(row["desc"]) if "desc" in row and pd.notna(row["desc"]) else default_desc

elif menu == "Статистика":
    st.subheader("📊