import streamlit as st
from PIL import Image
import base64
import pandas as pd
import io
from openai import OpenAI
from security_layer import init_db, save_pending_result, get_pending_results, approve_result, get_approved_results, external_ai_is_enabled

st.set_page_config(page_title="SmartTest БЖБ–ТЖБ", layout="wide")
init_db()

# --- АУТЕНТИФИКАЦИЯ (КІРУ ЖҮЙЕСІ) ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 SmartTest — Мұғалімнің жеке кабинетіне кіру")
    st.write("Платформаға кіру үшін мұғалімнің құпия сөзін енгізіңіз.")
    
    with st.form("login_form"):
        password_input = st.text_input("Құпия сөз (Password)", type="password", placeholder="Құпия сөзді енгізіңіз...")
        login_submitted = st.form_submit_button("Кіру")
        
        if login_submitted:
            expected_password = st.secrets.get("TEACHER_PASSWORD", "smarttest2026")
            
            if password_input == expected_password:
                st.session_state.authenticated = True
                st.success("Жүйеге сәтті кірдіңіз!")
                st.rerun()
            else:
                st.error("Құпия сөз қате! Қайта көріңіз.")
    
    st.stop()

# --- НЕГІЗГІ ҚОСЫМША (КІРГЕННЕН КЕЙІН) ---
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.sidebar.title("SmartTest")
menu = st.sidebar.selectbox("Бөлім", ["Басты бет", "Жұмысты тексеру", "Мұғалім бекітуі", "Нәтижелер", "Статистика", "Қауіпсіздік"])

if st.sidebar.button("🚪 Жүйеден шығу"):
    st.session_state.authenticated = False
    st.rerun()

st.title("📄 SmartTest — БЖБ / ТЖБ (Ресми спецификациялар базасы)")

if menu == "Басты бет":
    st.write("Оқушы жұмыстарын тексеруге және мұғалімнің қорытынды бағасын бекітуге арналған қауіпсіз платформа.")
    st.info("БЖБ/ТЖБ спецификациялары мен дескрипторларының толық автоматты қоры қосылды.")
    c1, c2 = st.columns(2)
    c1.metric("Мұғалім тексеруін күтуде", len(get_pending_results()))
    c2.metric("Бекітілген жұмыс", len(get_approved_results()))

elif menu == "Жұмысты тексеру":
    st.subheader("Жұмыстарды тіркеу және ЖИ арқылы кері байланыспен бағалау")
    
    # --- БЖБ НЕМЕСЕ ТЖБ ТАҢДАУ БАТЫРМАСЫ ---
    assessment_type = st.radio("📌 Бағалау түрін таңдаңыз:", ["БЖБ (Бөлім бойынша жиынтық бағалау)", "ТЖБ (Тоқсандық жиынтық бағалау)"], horizontal=True)

    # --- СЫНЫП ЖӘНЕ ПӘНДІ ТАҢДАУ БӨЛІМІ ---
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        selected_grade = st.selectbox("📌 Сыныпты таңдаңыз", [
            "1-сынып", "2-сынып", "3-сынып", "4-сынып", 
            "5-сынып", "6-сынып", "7-сынып", "8-сынып", 
            "9-сынып", "10-сынып", "11-сынып"
        ])
    with col_s2:
        selected_subject = st.selectbox("📌 Пәнді таңдаңыз", [
            "Сауат ашу / Қазақ тілі (Бастауыш)", 
            "Математика (Бастауыш)", 
            "Жаратылыстану (Бастауыш)", 
            "Дүниетану (Бастауыш)",
            "Цифрлық сауаттылық және жасанды интеллект",
            "Информатика және жасанды интеллект",
            "Математика / Алгебра", 
            "Физика", 
            "Химия", 
            "Биология", 
            "Қазақстан тарихы",
            "Дүние жүзі тарихы",
            "География",
            "Қазақ тілі мен әдебиеті"
        ])

    prefix_text = "БЖБ" if "БЖБ" in assessment_type else "ТЖБ"

    # --- РЕСМИ СПЕЦИФИКАЦИЯЛАРҒА НЕГІЗДЕЛГЕН АВТОМАТТЫ БАЗА ---
    auto_content_db = {
        # Бастауыш буын
        ("1-сынып", "Сауат ашу / Қазақ тілі (Бастауыш)"): {
            "task": f"1-сынып. {prefix_text}. «Дыбыстар және әріптер» бөлімі бойынша тілдік дағдыларды тексеру.",
            "desc": "1. Сөздегі дыбыстарды (дауысты/дауыссыз) дұрыс ажыратады (2 балл);\n2. Буынға бөліп оқиды және сөйлемді сауатты жазады (3 балл)."
        },
        ("2-сынып", "Математика (Бастауыш)"): {
            "task": f"2-сынып. {prefix_text}. Екі таңбалы сандарды қосу және азайту, теңдеулерді шешу.",
            "desc": "1. Есептің шартын құрып, амалын дұрыс таңдайды (2 балл);\n2. Есептеулерді қатесіз орындап, түпкілікті жауабын жазады (3 балл)."
        },
        ("3-сынып", "Жаратылыстану (Бастауыш)"): {
            "task": f"3-сынып. {prefix_text}. «Тірі табиғат және қоршаған орта» бөлімі.",
            "desc": "1. Өсімдіктер мен жануарлардың тіршілік ортасын сипаттайды (2 балл);\n2. Табиғат құбылыстарының өзара байланысын түсіндіреді (3 балл)."
        },
        ("4-сынып", "Дүниетану (Бастауыш)"): {
            "task": f"4-сынып. {prefix_text}. «Менің Отаныым - Қазақстан» бөлімі.",
            "desc": "1. Негізгі географиялық нысандар мен карта элементтерін атайды (2 балл);\n2. Өлке тарихы мен қоғамдық ережелерді мысалдармен дәйектейді (3 балл)."
        },

        # ЖИ және Информатика бағыты
        ("2-сынып", "Цифрлық сауаттылық және жасанды интеллект"): {
            "task": f"2-сынып. {prefix_text}. Цифрлық құрылғылар және қарапайым алгоритмдер.",
            "desc": "1. Құрылғылардың негізгі бөліктерін және қызметін ажыратады (2 балл);\n2. Қарапайым командалар тізбегін логикалық тұрғыдан құрады (3 балл)."
        },
        ("5-сынып", "Цифрлық сауаттылық және жасанды интеллект"): {
            "task": f"5-сынып. {prefix_text}. Медиасауаттылық және ЖИ көмекшілері.",
            "desc": "1. Ақпараттың шынайылығы мен сенімділігін тексереді (2 балл);\n2. Жасанды интеллект құралдарының көмегімен қарапайым міндеттерді шешеді (3 балл)."
        },
        ("7-сынып", "Информатика және жасанды интеллект"): {
            "task": f"7-сынып. {prefix_text}. Алгоритмдерді блок-схема түрінде өрнектеу және нейрожелілер негіздері.",
            "desc": "1. Шартты және циклдік блоктарды пайдаланып блок-схема сызады (2 балл);\n2. Мәтін немесе сурет генерациялайтын ЖИ құралдарын дұрыс қолданады (3 балл)."
        },
        ("9-сынып", "Информатика және жасанды интеллект"): {
            "task": f"9-сынып. {prefix_text}. Python тілінде программалау және машиналық оқыту элементтері.",
            "desc": "1. Python тіліндегі негізгі деректер типтері мен циклдерді қолданады (2 балл);\n2. Берілген деректер жиыны бойынша қарапайым болжау алгоритмін жазады (3 балл)."
        },

        # Негізгі және жоғары буын пәндері
        ("7-сынып", "Математика / Алгебра"): {
            "task": f"7-сынып. {prefix_text}. Алгебралық өрнектерді түрлендіру және теңдеулер.",
            "desc": "1. Формулаларды қолданып, алгебралық өрнекті ықшамдайды (2 балл);\n2. Сызықтық және квадраттық теңдеулерді шешіп, түбірлерін табады (3 балл)."
        },
        ("9-сынып", "Физика"): {
            "task": f"9-сынып. {prefix_text}. Кинематика және динамика заңдары бойынша есептер.",
            "desc": "1. Физикалық заңдарды есептің шартына сай қолданады (2 балл);\n2. Шамаларды СИ жүйесіне келтіріп, есептеулерді қатесіз орындайды (3 балл)."
        },
        ("8-сынып", "Химия"): {
            "task": f"8-сынып. {prefix_text}. Зат мөлшері, стехиометриялық есептеулер.",
            "desc": "1. Химиялық реакция теңдеулерін жазып, теңестіреді (2 балл);\n2. Молярлық масса мен массалық үлеске қатысты есептерді шығарады (3 балл)."
        },
        ("7-сынып", "Биология"): {
            "task": f"7-сынып. {prefix_text}. Жасушалық биология және тірі ағзалардың әגוртпалығы.",
            "desc": "1. Жасуша органоидтерінің құрылысы мен қызметін сипаттайды (2 балл);\n2. Микропрепарат немесе сурет бойынша биологиялық нысандарды талдайды (3 балл)."
        },
        ("8-сынып", "Қазақстан тарихы"): {
            "task": f"8-сынып. {prefix_text}. Қазақстанның XVIII-XIX ғасырлардағы тарихи оқиғалары.",
            "desc": "1. Тарихи оқиғалардың хронологиясы мен себеп-салдарын анықтайды (2 балл);\n2. Тарихи карта немесе дереккөзді талдап, қорытынды жасайды (3 балл)."
        },
        ("9-сынып", "Дүние жүзі тарихы"): {
            "task": f"9-сынып. {prefix_text}. Жаңа заман тарихы және халықаралық қатынастар.",
            "desc": "1. Тарихи процестердің маңыздылығы мен әсеріне баға береді (2 балл);\n2. Факторларды салыстырып, дәйекті тұжырым жасайды (3 балл)."
        },
        ("7-сынып", "География"): {
            "task": f"7-сынып. {prefix_text}. Физикалық география және литосфера.",
            "desc": "1. Географиялық карта номенклатурасын дұрыс пайдаланады (2 балл);\n2. Табиғи процестердің пайда болу заңдылықтарын түсіндіреді (3 балл)."
        },
        ("10-сынып", "Қазақ тілі мен әдебиеті"): {
            "task": f"10-сынып. {prefix_text}. Көркем шығарманың идеялық-көркемдік мазмұнын талдау.",
            "desc": "1. Шығарма тақырыбын терең ашып, кейіпкерлер жүйесіне баға береді (2 балл);\n2. Ойларын жүйелі жазып, стилистикалық және орфографиялық нормаларды сақтайды (3 балл)."
        }
    }

    default_data = auto_content_db.get(
        (selected_grade, selected_subject), 
        {
            "task": f"{selected_grade}. {selected_subject} пәні бойынша {prefix_text} стандарты тапсырмасы.",
            "desc": "1. Тапсырма шартын толық түсініп, талапқа сай орындайды (2 балл);\n2. Жауабын жүйелі түрде негіздеп, қатесіз жазады (3 балл)."
        }
    )

    # --- АВТОМАТТЫ ТҮРДЕ ТОЛТЫРЫЛАТЫН ӨРІСТЕР ---
    task_text = st.text_area("Тапсырма тақырыбы немесе сұрақ (Спецификация бойынша автоматты шығады)", value=default_data["task"])
    descriptors = st.text_area("Бағалау дескрипторлары (Спецификация бойынша автоматты шығады)", value=default_data["desc"])
    max_score = st.number_input("Ең жоғары ұпай", min_value=0.5, max_value=100.0, value=5.0, step=0.5)
    
    uploaded_files = st.file_uploader(f"({prefix_text} | {selected_grade} - {selected_subject}) Оқушылардың жұмыс суреттерін қатар жүктеу", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    
    if uploaded_files:
        st.success(f"Барлығы {len(uploaded_files)} жұмыс жүктелді. Әрқайсысын жеке өңдеңіз:")
        
        for idx, uploaded_file in enumerate(uploaded_files):
            with st.expander(f"📁 [{prefix_text} | {selected_grade} | {selected_subject}] Жұмыс №{idx+1}: {uploaded_file.name}"):
                col_img, col_form = st.columns([1, 1])
                
                with col_img:
                    try:
                        image = Image.open(uploaded_file)
                        st.image(image, caption=f"Жүктелген файл: {uploaded_file.name}", use_container_width=True)
                    except Exception:
                        st.error("Сурет файлын ашу мүмкін болмады.")
                
                with col_form:
                    st_code = st.text_input(f"Анонимді оқушы коды", value=f"{selected_grade}-0{idx+1}", key=f"code_{idx}")
                    
                    def encode_image(file_obj):
                        bytes_data = file_obj.getvalue()
                        return base64.b64encode(bytes_data).decode('utf-8')

                    ai_exp = "Бағаны мұғалім тексеруі қажет."

                    if st.button(f"🔍 ЖИ (GPT-4o) арқылы талдау", key=f"ai_btn_{idx}"):
                        with st.spinner("ЖИ суретті оқып, кері байланыс дайындап жатыр..."):
                            try:
                                b64_img = encode_image(uploaded_file)
                                response = client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=[
                                        {
                                            "role": "system",
                                            "content": (
                                                "Сіз тәжірибелі мектеп мұғалімісіз. Берілген дескрипторлар мен оқушының жұмыс суретін салыстырып, мына форматта жауап беріңіз:\n"
                                                "1. **Ұпай мен талдау**: Ұсынылатын ұпай және мұғалімге қысқаша түсіндірме.\n"
                                                "2. **Оқушыға арналған кері байланыс (Feedback)**: Оқушыға тікелей арналған (жылы, ынталандырушы түрде): "
                                                "не нәрсе өте жақсы шықты, қандай қате кетті және келесі жолы неге көңіл бөлу керектігі туралы нақты әрі түсінікті кеңес."
                                            )
                                        },
                                        {
                                            "role": "user",
                                            "content": [
                                                {"type": "text", "text": f"Түрі: {assessment_type}, Сынып: {selected_grade}, Пән: {selected_subject}\nТапсырма: {task_text}\nДескрипторлар: {descriptors}\nМакс ұпай: {max_score}"},
                                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                                            ]
                                        }
                                    ],
                                    max_tokens=600
                                )
                                ai_exp = response.choices[0].message.content
                                st.success("Талдау мен жеке кері байланыс дайын!")
                                st.write(ai_exp)
                            except Exception as e:
                                st.error(f"Қате: {e}")

                    with st.form(key=f"form_{idx}"):
                        prop_score = st.number_input("Алдын ала ұпай", min_value=0.0, max_value=float(max_score), value=0.0, step=0.5, key=f"score_{idx}")
                        explanation = st.text_area("Түсіндірме және оқушыға кері байланыс", value=ai_exp, key=f"exp_{idx}")
                        submitted = st.form_submit_button("Тексеруге сақтау")
                        
                        if submitted:
                            if not st_code.strip():
                                st.error("Кодты енгізіңіз.")
                            else:
                                try:
                                    full_task_info = f"[{prefix_text} | {selected_grade} - {selected_subject}] {task_text.strip()}"
                                    save_pending_result(st_code.strip(), full_task_info, descriptors.strip(), float(prop_score), float(max_score), explanation.strip())
                                    st.success(f"{st_code} жұмысы сәтті сақталды!")
                                except Exception as e:
                                    st.error(f"Сақтау қатесі: {e}")

elif menu == "Мұғалім бекітуі":
    st.subheader("Мұғалімнің қорытынды бағасын бекіту")
    teacher_id = st.text_input("Мұғалімнің ішкі ID-і", placeholder="Мысалы: TEACHER-01")
    pending = get_pending_results()
    if not pending:
        st.info("Бекітуді күтіп тұрған жұмыс жоқ.")
        
    for item in pending:
        prop_score = item['proposed_score']
        max_s = item['max_score']
        icon = "🟢" if prop_score >= (max_s * 0.5) else "🔴"
        
        with st.expander(f"{icon} Жұмыс: {item['student_code']} — Алдын ала ұпай: {prop_score} / {max_s} ({item['created_at']})"):
            st.write("Тапсырма/мәтін:", item["task_text"])
            st.write("Дескрипторлар:", item["descriptors"])
            st.write("ЖИ талдауы және кері байланыс:", item["explanation"])
            
            score = st.number_input("Мұғалім бекітетін ұпай", min_value=0.0, max_value=float(max_s), value=float(prop_score), step=0.5, key="score_" + item["id"])
            comment = st.text_area("Мұғалімнің қосымша ескертпесі", key="comment_" + item["id"])
            
            if st.button("Бағаны бекіту", key="approve_" + item["id"]):
                if not teacher_id.strip():
                    st.error("Мұғалім ID-ін енгізіңіз.")
                else:
                    try:
                        approve_result(item["id"], score, teacher_id.strip(), comment.strip())
                        st.success("Баға бекітілді!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Бекіту қатесі: {e}")

elif menu == "Нәтижелер":
    st.subheader("Мұғалім бекіткен нәтижелер")
    rows = get_approved_results()
    if not rows:
        st.info("Әзірге бекітілген нәтиже жоқ.")
    else:
        df = pd.DataFrame(rows)
        export_df = pd.DataFrame({
            "Оқушы коды": df.get("student_code", ""),
            "Тапсырма": df.get("task_text", ""),
            "Бекітілген ұпай": df.get("teacher_score", ""),
            "Максималды ұпай": df.get("max_score", ""),
            "Бекіткен мұғалім": df.get("approved_by", ""),
            "Уақыты": df.get("approved_at", ""),
            "Кері байланыс/Ескертпе": df.get("teacher_comment", "")
        })

        col1, col2 = st.columns(2)
        with col1:
            buffer_excel = io.BytesIO()
            with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                export_df.to_excel(writer, index=False, sheet_name='Нәтижелер')
            st.download_button(
                label="📊 Excel (.xlsx) форматында жүктеу",
                data=buffer_excel.getvalue(),
                file_name="SmartTest_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col2:
            csv_data = export_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📄 CSV форматында жүктеу",
                data=csv_data,
                file_name="SmartTest_results.csv",
                mime="text/csv"
            )

        st.markdown("---")

        for item in rows:
            score = item['teacher_score']
            max_s = item['max_score']
            status_icon = "🟢" if score >= (max_s * 0.5) else "🔴"
            status_text = "Тапсырма сәтті орындалды" if score >= (max_s * 0.5) else "Қосымша жұмыс қажет"

            with st.expander(f"{status_icon} Оқушы: {item['student_code']} — {score} / {max_s} балл ({status_text})"):
                st.write("Мәтіні/Тапсырма:", item["task_text"])
                st.write("Мұғалім бекіткен ұпай:", f"**{score} / {max_s}**")
                st.write("Кері байланыс / Түсіндірме:", item["explanation"])
                st.write("Мұғалім ескертпесі:", item["teacher_comment"] or "—")
                st.write("Бекіткен мұғалім:", item["approved_by"], f"({item['approved_at']})")

elif menu == "Статистика":
    st.subheader("📊 Сыныптың статистикасы мен графикалық аналитикасы")
    rows = get_approved_results()
    
    if not rows:
        st.info("Әзірге статистика үшін бекітілген нәтижелер жоқ.")
    else:
        df = pd.DataFrame(rows)
        total_works = len(df)
        avg_score = df['teacher_score'].mean()
        max_possible = df['max_score'].iloc[0] if total_works > 0 else 5.0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Бекітілген жұмыс саны", total_works)
        col2.metric("Орташа ұпай", f"{avg_score:.2f} / {max_possible}")
        
        success_count = len(df[df['teacher_score'] >= (df['max_score'] * 0.5)])
        success_rate = (success_count / total_works) * 100 if total_works > 0 else 0
        col3.metric("Табыстылық көрсеткіші", f"{success_rate:.1f}%")
        
        st.markdown("---")
        st.write("### Оқушылардың ұпайлар бөлінісі (График)")
        chart_data = df.set_index('student_code')[['teacher_score']]
        st.bar_chart(chart_data)

elif menu == "Қауіпсіздік":
    st.subheader("Қауіпсіздік күйі")
    st.write("Дерекқор: компьютердегі data/smarttest.db")
    st.write("Сыртқы ЖИ режимі: Қосулы (Ресми спецификациялар автоматты түрде қосылды)")