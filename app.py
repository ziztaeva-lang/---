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

# --- ЗАМАНАУИ МИНИМАЛИЗМ CSS СТИЛЬДЕРІ МЕН БЕЛГІЛЕР —
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
Сен — Қазақстан Республикасының орта білім беру стандарты мен критериалды бағалау жүйесін жеткіді білетін тәжірибелі сарапшы-ұстазсың. 
Суреттегі оқушының жазбаша жұмысын өте мұқият оқып шық. Жұмыстағы барлық тапсырмалар мен тармақтарды (1-тапсырма, 2-тапсырма, а, б, в т.б.) анықтап, жеке-жеке тексер.

СТАНДАРТҚА САЙ ТЕКСЕРУ ЕРЕЖЕЛЕРІ:
1. Әрбір тапсырманы және оның тармақтарын жеке тізбектеп көрсет.
2. Әр тармаққа міндетті түрде мына белгілердің бірін қой:
   - 🟢 [Дұрыс] — жауап толық дұрыс болса.
   - 🔴 [Қате] — жауап қате немесе орындалмаған болса.
   - 🟡 [Жартылай] — жартылай дұрыс болса.
3. Әр бағалаудың себебін қысқаша түсіндіріп жаз.
4. Барлық жиналған ұпайды есептеп, соңында міндетті түрде мына форматта жаз:
   Жиынтық балл: X/{int(max_score)}

ФОРМАТ ТАЛАБЫ:
1. Оқушының аты-жөнін жұмыс бетінен тауып жаз:
   [ОҚУШЫ_АТЫ] Аты Жөні [/ОҚУШЫ_АТЫ] (егер табылмаса "Белгісіз оқушы").
2. Барлық тапсырмаларды жеке жолдармен сипаттап шық.
3. Соңында міндетті түрде 'Жиынтық балл: X/{int(max_score)}' түрінде көрсет.
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
                                            {"role": "system", "content": f"Сіз ҚР білім беру стандартына сай оқушы жұмыстарын қатаң әрі әділ тексеретін, әр тапсырманы бөлек бағалайтын және қорытынды ұпайды {int(max_score)} баллдық шкаламен есептейтін мұғалімсіз."},
                                            {"role": "user", "content": messages_content}
                                        ],
                                        max_tokens=2500,
                                        temperature=0.1
                                    )
                                    
                                    full_ai_resp = response.choices[0].message.content
                                    
                                    import re
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
                                    if not is_admin:
                                        deduct_credit(current_user, amount=1.0)
                                    st.success("✅ Жұмыс стандарқа сай сәтті тексерілді!")
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
                    
                    # Мұғалім өз пікірін қоса алатын етіп атауы толықтырылды
                    explanation = st.text_area(
                        "Толық кері байланыс мәтіні (Қажет болған жағдайда мұғалім өз пікірін қоса алады)", 
                        value=current_ai_text, 
                        height=250, 
                        key=f"exp_{idx}"
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
    st.subheader("Статистика")
    rows = get_approved_results()
    if not rows:
        st.info("Әзірге статистика жоқ.")
    else:
        df_stat = pd.DataFrame(rows)
        st.bar_chart(df_stat.set_index('student_code')[['teacher_score']])

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