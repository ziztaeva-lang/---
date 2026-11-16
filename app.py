import streamlit as st
from PIL import Image
import base64
import pandas as pd
import io
import os
import re
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

# --- ЗАМАНАУИ МИНИМАЛИЗМ CSS СТИЛЬДЕРІ МЕН БЕЛГІЛЕР ---
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
        padding: 10px 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #065f46;
        font-weight: 500;
    }
    .incorrect-card {
        background-color: #fef2f2;
        border-left: 5px solid #ef4444;
        padding: 10px 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #991b1b;
        font-weight: 500;
    }
    .warning-card {
        background-color: #fffbeb;
        border-left: 5px solid #f59e0b;
        padding: 10px 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #92400e;
        font-weight: 500;
    }
    .analysis-box {
        background-color: #ffffff;
        border: 1px solid #cbd5e1;
        border-left: 6px solid #3b82f6;
        border-radius: 10px;
        padding: 20px;
        margin-top: 15px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
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
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=90)
            b64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            images_b64.append(b64_str)
        except Exception:
            b64_str = base64.b64encode(file_bytes).decode('utf-8')
            images_b64.append(b64_str)
        
    return images_b64

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

st.title("📄 SmartTest — Автоматты түрде тексеру жүйесі")

if menu == "Басты бет":
    st.write("Оқушы жұмыстарын ҚР білім беру стандартына сай автоматты түрде тексеруге арналған платформа.")
    c1, c2 = st.columns(2)
    c1.metric("Мұғалім тексеруін күтуде", len(get_pending_results()))
    c2.metric("Бекітілген жұмыс", len(get_approved_results()))

elif menu == "Жұмысты тексеру":
    st.subheader("Оқушы жұмыстарын жүктеу және автоматты тексеру")
    
    max_score = st.number_input(
        "Ең жоғары балл (Шкала)", 
        min_value=1.0, 
        max_value=50.0, 
        value=10.0, 
        step=1.0
    )

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
                        st.session_state[student_name_key] = f"Оқушы-0{idx+1}"

                    st_code = st.text_input("Оқушы аты-жөні", value=st.session_state[student_name_key], key=f"name_input_{idx}")
                    
                    ai_res_key = f"ai_result_{idx}"
                    if ai_res_key not in st.session_state:
                        st.session_state[ai_res_key] = ""

                    # ЖИ ТЕКСЕРУ БАТЫРМАСЫ
                    if st.button("🟢 Автоматты тексеру", key=f"ai_btn_{idx}"):
                        current_balance = get_user_credits(current_user)
                        
                        if not is_admin and current_balance < 1.0:
                            st.error("❌ Балансыңызда кредит жеткіліксіз!")
                        else:
                            with st.spinner("ЖИ ҚР білім стандартына сәйкес жұмысты толық талдап жатыр..."):
                                try:
                                    images_b64 = process_uploaded_file(uploaded_file)
                                    
                                    prompt_text = f"""
Сен — Қазақстан Республикасының орта білім беру стандарты мен критериалды бағалау жүйесін жеттік білетін тәжірибелі сарапшы-ұстазсың. №399, №125 және №348 бұйрықтардың талаптары мен дескрипторларды қатаң басшылыққа ал.
Суреттегі оқушының жазбаша жұмысын өте мұқият оқып шық. Жұмыстағы барлық тапсырмалар мен тармақтарды анықтап, жеке-жеке тексер.

ТАРМАҚТАРДЫ БЕЛГІЛЕУ ЕРЕЖЕСІ:
1. Жұмыста қалай жазылған болса, сол форматты қолдан: қазақша әріптер (а, ә, б, в, г) немесе латын әріптері (a, b, c, d).
2. Әрбір тапсырманың тақырыбын немесе оқу мақсатын (егер бетте жазылған болса немесе мазмұнынан анықталса) қысқаша көрсетіп, сәйкес белгі қой:
   - 🟢 [Дұрыс] — жауап толық дұрыс болса.
   - 🔴 [Қате] — жауап қате немесе орындалмаған болса.
   - 🟡 [Жартылай] — жартылай дұрыс болса.
3. Әр бағалаудың себебін қысқаша түсіндіріп жаз.
4. Соңында міндетті түрде мына форматта жаз:
   Жиынтық балл: X/{int(max_score)}

ФОРМАТ ТАЛАБЫ:
1. Оқушының аты-жөнін жұмыс бетінен тауып жаз:
   [ОҚУШЫ_АТЫ] Аты Жөні [/ОҚУШЫ_АТЫ] (егер табылмаса "Белгісіз оқушы").
2. Барлық тапсырмаларды жеке жолдармен сипаттап шық.
3. Соңында 'Жиынтық балл: X/{int(max_score)}' түрінде көрсет.
"""
                                    messages_content = [{"type": "text", "text": prompt_text}]
                                    for img_b64 in images_b64:
                                        messages_content.append({
                                            "type": "image_url",
                                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                                        })

                                    response = client.chat.completions.create(
                                        model="gpt-4o",
                                        messages=[
                                            {"role": "system", "content": "Сіз ҚР білім беру стандартына сай оқушы жұмыстарын тексеретін ұстазсыз."},
                                            {"role": "user", "content": messages_content}
                                        ],
                                        max_tokens=2500,
                                        temperature=0.1
                                    )
                                    
                                    full_ai_resp = response.choices[0].message.content
                                    
                                    name_match = re.search(r'\[ОҚУШЫ_АТЫ\](.*?)\[/ОҚУШЫ_АТЫ\]', full_ai_resp, re.DOTALL)
                                    if name_match:
                                        found_name = name_match.group(1).strip()
                                        if found_name and "Белгісіз" not in found_name:
                                            st.session_state[student_name_key] = found_name
                                        full_ai_resp = re.sub(r'\[ОҚУШЫ_АТЫ\].*?\[/ОҚУШЫ_АТЫ\]', '', full_ai_resp).strip()
                                    
                                    score_match = re.search(r'Жиынтық балл:\s*([\d\.]+)', full_ai_resp, re.IGNORECASE)
                                    if score_match:
                                        try:
                                            extracted_score = float(score_match.group(1))
                                            if extracted_score <= float(max_score):
                                                st.session_state[f"score_{idx}"] = extracted_score
                                        except:
                                            pass

                                    st.session_state[ai_res_key] = full_ai_resp
                                    st.session_state[f"exp_text_{idx}"] = full_ai_resp
                                    
                                    if not is_admin:
                                        deduct_credit(current_user, amount=1.0)
                                    st.success("✅ Жұмыс стандартқа сай сәтті тексерілді!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Қате пайда болды: {e}")

                    current_ai_text = st.session_state.get(ai_res_key, "")
                    
                    if current_ai_text:
                        st.markdown("### 🎨 Талдау нәтижесі:")
                        lines = current_ai_text.split('\n')
                        for line in lines:
                            if any(k in line for k in ['🟢', '[Дұрыс]', 'дұрыс']):
                                st.markdown(f"<div class='correct-card'>{line}</div>", unsafe_allow_html=True)
                            elif any(k in line for k in ['🔴', '[Қате]', 'қате', 'орындалмаған']):
                                st.markdown(f"<div class='incorrect-card'>{line}</div>", unsafe_allow_html=True)
                            elif any(k in line for k in ['🟡', '[Жартылай]', 'жартылай']):
                                st.markdown(f"<div class='warning-card'>{line}</div>", unsafe_allow_html=True)
                            elif line.strip():
                                st.write(line)
                    else:
                        st.info("ℹ️ Тексеру үшін жоғарыдағы **🟢 Автоматты тексеру** батырмасын басыңыз.")

                    prop_score = st.number_input(
                        "Жалпы жинаған ұпай саны", 
                        min_value=0.0, 
                        max_value=float(max_score), 
                        value=st.session_state.get(f"score_{idx}", 0.0), 
                        step=0.5, 
                        key=f"score_{idx}"
                    )
                    
                    exp_key = f"exp_text_{idx}"
                    if exp_key not in st.session_state:
                        st.session_state[exp_key] = current_ai_text

                    explanation = st.text_area(
                        "Толық кері байланыс мәтіні", 
                        value=st.session_state[exp_key], 
                        height=250, 
                        key=exp_key
                    )
                    
                    if st.button("💾 Нәтижені сақтау", key=f"save_btn_{idx}"):
                        current_st_name = st_code.strip() if st_code.strip() else st.session_state[student_name_key]
                        if current_st_name:
                            full_feedback = f"Кері байланыс:\n{explanation.strip()}"
                            save_pending_result(
                                current_st_name, 
                                f"[Автоматты тексеру] Оқушы жұмысы", 
                                "ҚР стандарттары бойынша критериалды бағалау", 
                                float(prop_score), 
                                float(max_score), 
                                full_feedback
                            )
                            st.success("✅ Нәтиже сәтті сақталды!")
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
            comment = st.text_area("Ескертпе (міндетті емес)", placeholder="Қажет болса, қосымша пікір қалдырыңыз...", key="com_" + item["id"])
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
    st.subheader("📊 Сыныптың статистикасы мен педагогикалық талдау")
    rows = get_approved_results()
    if not rows:
        st.info("Әзірге бекітілген нәтижелер жоқ. Статистика шығару үшін жұмыстарды тексеріп, бекітіңіз.")
    else:
        df_stat = pd.DataFrame(rows)
        
        # Егер дерекқордан tuple/list келсе (бағандар 0, 1, 2... деп нөмірленген болса)
        if all(isinstance(c, int) for c in df_stat.columns):
            num_cols = []
            str_cols = []
            for c in df_stat.columns:
                converted = pd.to_numeric(df_stat[c], errors='coerce')
                if converted.notna().sum() == len(df_stat) and c != 0:
                    num_cols.append(c)
                else:
                    str_cols.append(c)
            
            # Оқушы аты-жөні бағанын табу (әдетте 1-баған)
            student_col = 1 if 1 in df_stat.columns else (str_cols[0] if str_cols else 0)
            
            # Ұпай мен максималды балл бағандарын анықтау
            if len(num_cols) >= 3:
                score_col = num_cols[-1]
                max_col = num_cols[1]
            elif len(num_cols) == 2:
                score_col = num_cols[0]
                max_col = num_cols[1]
            elif len(num_cols) == 1:
                score_col = num_cols[0]
                max_col = None
            else:
                st.error("Кестеден сандық ұпай деректері табылмады.")
                st.stop()
                
            # Ең ұзын мәтінді бағанды кері байланыс (feedback) ретінде алу
            fb_col = max(str_cols, key=lambda c: df_stat[c].astype(str).str.len().mean()) if str_cols else None
            
            # Excel-ге әдемі шығуы үшін баған атауларын реттеу
            rename_map = {student_col: "Оқушы аты-жөні", score_col: "Бекітілген ұпай"}
            if max_col is not None:
                rename_map[max_col] = "Максималды балл"
            if fb_col is not None and fb_col != student_col:
                rename_map[fb_col] = "Кері байланыс"
                
            df_stat = df_stat.rename(columns=rename_map)
            student_col = "Оқушы аты-жөні"
            score_col = "Бекітілген ұпай"
            max_col_name = "Максималды балл" if max_col is not None else None
            fb_col_name = "Кері байланыс" if (fb_col is not None and fb_col != student_col) else None
        else:
            # Егер сөздік (dict) түрінде келсе
            score_col = next((c for c in ['teacher_score', 'final_score', 'approved_score', 'score', 'proposed_score'] if c in df_stat.columns), None)
            student_col = next((c for c in ['student_code', 'student_name', 'student'] if c in df_stat.columns), None)
            max_col_name = 'max_score' if 'max_score' in df_stat.columns else None
            fb_col_name = next((c for c in ['feedback', 'explanation', 'rubric', 'teacher_comment'] if c in df_stat.columns), None)

        if not score_col or score_col not in df_stat.columns:
            st.error("Кестеден ұпай бағаны табылмады.")
            st.stop()

        df_stat[score_col] = pd.to_numeric(df_stat[score_col], errors='coerce').fillna(0.0)
        
        # Негізгі көрсеткіштерді есептеу
        total_students = len(df_stat)
        avg_score = df_stat[score_col].mean()
        
        if max_col_name and max_col_name in df_stat.columns:
            df_stat[max_col_name] = pd.to_numeric(df_stat[max_col_name], errors='coerce').fillna(10.0)
            max_possible = df_stat[max_col_name].mean()
            df_stat['Пайыздық көрсеткіш (%)'] = (df_stat[score_col] / df_stat[max_col_name].replace(0, 10.0)) * 100
        else:
            max_possible = 10.0
            df_stat['Пайыздық көрсеткіш (%)'] = (df_stat[score_col] / max_possible) * 100

        # ҚР стандарты бойынша бағалау шкаласы (40%+ үлгерім, 65%+ сапа)
        passing_count = len(df_stat[df_stat['Пайыздық көрсеткіш (%)'] >= 40])
        quality_count = len(df_stat[df_stat['Пайыздық көрсеткіш (%)'] >= 65])
            
        passing_rate = (passing_count / total_students) * 100
        quality_rate = (quality_count / total_students) * 100

        # Метрикалар панелі
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Оқушы саны", f"{total_students}")
        col2.metric("Орташа балл", f"{avg_score:.1f} / {max_possible:.0f}")
        col3.metric("Үлгерім пайызы", f"{passing_rate:.1f}%")
        col4.metric("Сапа пайызы", f"{quality_rate:.1f}%")

        st.markdown("---")
        st.write("### 📈 Оқушылардың ұпайларының графигі")
        if student_col and student_col in df_stat.columns:
            st.bar_chart(df_stat.set_index(student_col)[score_col])
        else:
            st.bar_chart(df_stat[score_col])

        st.markdown("---")
        st.write("### 🧠 Оқу мақсаттары бойынша автоматты педагогикалық талдау")
        st.write("БЖБ / ТЖБ қорытынды анықтамасына арналған дайын талдау мәтінін құрастыру:")

        if "class_ai_analysis" not in st.session_state:
            st.session_state.class_ai_analysis = ""

        if st.button("🤖 Қол жеткізген және қиындық туғызған мақсаттарды талдау"):
            with st.spinner("ЖИ барлық оқушылардың қателері мен жетістіктерін қорытындылап жатыр..."):
                try:
                    # Барлық оқушылардың кері байланыс деректерін жинақтау
                    feedback_records = []
                    for idx_r, r in df_stat.iterrows():
                        st_name = r.get(student_col, f'Оқушы-{idx_r+1}') if student_col else f'Оқушы-{idx_r+1}'
                        sc = r.get(score_col, 0)
                        mx = r.get(max_col_name, max_possible) if max_col_name else max_possible
                        fb = r.get(fb_col_name, '') if fb_col_name else ''
                        feedback_records.append(f"Оқушы: {st_name} | Балл: {sc}/{mx}\nТалдауы:\n{fb}\n---")
                    
                    combined_data = "\n".join(feedback_records)

                    analysis_prompt = f"""
Сен — Қазақстан Республикасы мектептеріндегі БЖБ және ТЖБ қорытындылары бойынша аналитикалық анықтама дайындайтын тәжірибелі әдіскер-ұстазсың.
Төмендегі сынып оқушыларының тексерілген жұмыстарының нәтижелері мен статистикасына сүйене отырып, ресми педагогикалық талдау жаз.

СЫНЫП СТАТИСТИКАСЫ:
- Барлық оқушы саны: {total_students}
- Орташа балл: {avg_score:.1f} / {max_possible:.0f}
- Үлгерім пайызы: {passing_rate:.1f}%
- Білім сапасы: {quality_rate:.1f}%

ОҚУШЫЛАРДЫҢ ЖҰМЫС НӘТИЖЕЛЕРІ МЕН ҚАТЕЛЕРІ:
{combined_data[:12000]}

ТАЛАП ЕТІЛЕТІН ҚҰРЫЛЫМ (Қазақ тілінде, ресми іскерлік-педагогикалық стильде):
1. **Қол жеткізген оқу мақсаттары:** Оқушылардың басым бөлігі (🟢 белгіленген) сәтті меңгерген тақырыптар, дағдылар мен оқу мақсаттары.
2. **Қиындық туғызған оқу мақсаттары:** Оқушылар жиі қате жіберген (🔴 және 🟡 белгіленген) тапсырмалар, тақырыптар мен оқу мақсаттары (нақты неден қателескенін көрсет).
3. **Түзету (коррекциялық) жұмыстары бойынша ұсыныстар:** Қиындық туғызған мақсаттарды жою үшін мұғалімге арналған нақты әдістемелік ұсыныстар.
"""
                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "Сіз ҚР білім беру стандарты бойынша БЖБ/ТЖБ талдауын жасайтын әдіскерсіз."},
                            {"role": "user", "content": analysis_prompt}
                        ],
                        max_tokens=1800,
                        temperature=0.2
                    )
                    st.session_state.class_ai_analysis = resp.choices[0].message.content
                except Exception as e:
                    st.error(f"Талдау жасау кезінде қате шықты: {e}")

        if st.session_state.class_ai_analysis:
            st.markdown(f"<div class='analysis-box'>{st.session_state.class_ai_analysis}</div>", unsafe_allow_html=True)
            st.text_area(
                "Көшіріп алуға ыңғайлы мәтін (Word / Kundelik / BilimClass үшін):",
                value=st.session_state.class_ai_analysis,
                height=260
            )

        st.markdown("---")
        st.write("### 📥 Есепті жүктеп алу")
        
        # Excel файлына экспорттау (Статистика + Педагогикалық талдау жеке парақта)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_stat.to_excel(writer, index=False, sheet_name='Оқушылар_нәтижесі')
            
            summary_df = pd.DataFrame({
                "Көрсеткіш": ["Оқушы саны", "Орташа балл", "Үлгерім пайызы (%)", "Білім сапасы (%)", "Педагогикалық талдау"],
                "Мәні": [
                    total_students, 
                    round(avg_score, 1), 
                    round(passing_rate, 1), 
                    round(quality_rate, 1),
                    st.session_state.class_ai_analysis if st.session_state.class_ai_analysis else "Талдау жасалмаған"
                ]
            })
            summary_df.to_excel(writer, index=False, sheet_name='Қорытынды_анализ')
            
        excel_data = output.getvalue()

        st.download_button(
            label="📊 Толық есепті Excel форматында жүктеу (.xlsx)",
            data=excel_data,
            file_name="SmartTest_Cynip_Analiz.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

elif menu == "Балансты толтыру":
    st.subheader("💳 Кредит сатып алу және балансты толтыру")
    st.write("1 кредит = 100 ₸. Қалаған кредит санын енгізіп, төлем жасаңыз.")
    
    credits_to_buy = st.number_input("Сатып алғыңыз келетін кредит саны:", min_value=1, max_value=1000, value=10, step=1)
    amount = credits_to_buy * 100
    
    st.markdown(f"**Төленетін жалпы сома:** <span style='color: #10b981; font-size: 20px; font-weight: bold;'>{amount:,.0f} ₸</span>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.info("📱 **Төлем жасау қадамдары:**\n1. Төмендегі QR кодтардың бірін сканерлеңіз;\n2. Соманы аударыңыз;\n3. Төлем чегіндегі транзакция / чек нөмірін енгізіңіз.")
    
    qr_col1, qr_col2 = st.columns(2)
    with qr_col1:
        st.write("### 🟡 Kaspi QR арқылы төлеу")
        if os.path.exists("kaspi_qr_ИЗС.png"):
            st.image("kaspi_qr_ИЗС.png", caption="SmartTest — Kaspi Pay QR", width=260)
        else:
            st.warning("⚠️ `kaspi_qr_ИЗС.png` файлы табылмады.")
            
    with qr_col2:
        st.write("### 🟢 Halyk QR арқылы төлеу")
        if os.path.exists("halyk_qr_ЫРЫС.png"):
            st.image("halyk_qr_ЫРЫС.png", caption="SmartTest — Halyk QR", width=260)
        else:
            st.warning("⚠️ `halyk_qr_ЫРЫС.png` суретін жоба папкасына салыңыз.")
    
    with st.form("payment_verification_form"):
        st.write("### Төлемді растау үшін деректерді енгізіңіз:")
        txn_id = st.text_input("Транзакция / чек нөмірі", placeholder="Операция нөмірін жазыңыз...")
        
        submit_payment = st.form_submit_button("📤 Төлем туралы хабарлау")
        
        if submit_payment:
            if not txn_id.strip():
                st.error("❌ Дұрыс транзакция нөмірін енгізіңіз!")
            else:
                try:
                    add_payment_record(current_user, amount, float(credits_to_buy), txn_id.strip())
                    st.success(f"✅ Өтінім қабылданды! Тексерілгеннен кейін балансыңызға {credits_to_buy} кредит қосылады.")
                except Exception as e:
                    st.error(f"Қате орын алды: {e}")

elif menu == "Қауіпсіздік":
    if not is_admin:
        st.error("⛔ Бұл бетке тек әкімші (admin) ғана кіре алады!")
        st.stop()

    st.subheader("Қауіпсіздік және жүйе күйі")
    st.write(f"Ағымдағы пайдаланушы: **{current_user}** | Баланс: **{user_balance} кредит** ({total_tenge:,.0f} ₸)")