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

st.title("📄 SmartTest — БЖБ / ТЖБ (Тоқсандар бойынша автоматты жүйе)")

if menu == "Басты бет":
    st.write("Оқушы жұмыстарын тексеруге және мұғалімнің қорытынды бағасын бекітуге арналған қауіпсіз платформа.")
    st.info("5-сынып Қазақ тілі пәнінің 1-тоқсандық БЖБ/ТЖБ кестесі автоматты базаға қосылды[cite: 6].")
    c1, c2 = st.columns(2)
    c1.metric("Мұғалім тексеруін күтуде", len(get_pending_results()))
    c2.metric("Бекітілген жұмыс", len(get_approved_results()))

elif menu == "Жұмысты тексеру":
    st.subheader("Жұмыстарды тіркеу және ЖИ арқылы кері байланыспен бағалау")
    
    # --- ТОҚСАН ЖӘНЕ БАҒАЛАУ ТҮРІН ТАҢДАУ ---
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        assessment_type = st.radio("📌 Бағалау түрі:", ["БЖБ (Бөлім бойынша)", "ТЖБ (Тоқсандық)"], horizontal=True)
    with col_t2:
        selected_term = st.selectbox("📌 Оқу тоқсаны:", ["1-тоқсан", "2-тоқсан", "3-тоқсан", "4-тоқсан"])

    # --- СЫНЫП ЖӘНЕ ПӘНДІ ТАҢДАУ ---
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        selected_grade = st.selectbox("📌 Сыныпты таңдаңыз", [
            "5-сынып", "6-сынып", "7-сынып", "8-сынып", 
            "9-сынып", "10-сынып", "11-сынып"
        ])
    with col_s2:
        selected_subject = st.selectbox("📌 Пәнді таңдаңыз", [
            "Қазақ тілі",
            "Қазақ әдебиеті",
            "Алгебра",
            "Геометрия",
            "Физика",
            "Химия",
            "Биология",
            "География",
            "Жаратылыстану",
            "Цифрлық сауаттылық және жасанды интеллект",
            "Информатика және жасанды интеллект",
            "Қазақстан тарихы",
            "Дүние жүзі тарихы",
            "Құқық негіздері",
            "Орыс тілі мен әдебиеті",
            "Ағылшын тілі"
        ])

    prefix_text = "БЖБ" if "БЖБ" in assessment_type else "ТЖБ"

    # Егер БЖБ таңдалса, қай БЖБ екенін қосымша нақтылау үшін selectbox қосамыз
    bzhb_sub_num = ""
    if prefix_text == "БЖБ" and selected_grade == "5-сынып" and selected_subject == "Қазақ тілі" and selected_term == "1-тоқсан":
        bzhb_sub_num = st.selectbox("📌 БЖБ нөмірін таңдаңыз:", ["БЖБ 1", "БЖБ 2", "БЖБ 3"])

    # --- ТОҚСАН ЖӘНЕ ПӘН БОЙЫНША АВТОМАТТЫ СПЕЦИФИКАЦИЯ БАЗАСЫ (5-сынып Қазақ тілі, 1-тоқсан) ---
    auto_content_db = {
        ("5-сынып", "Қазақ тілі", "1-тоқсан", "БЖБ 1"): {
            "task": "5-сынып. 1-тоқсан. БЖБ 1. «Мәдениет: тіл және қарым-қатынас. Фонетика».",
            "desc": "1. Тілдік бірліктерді коммуникативті жағдаятқа сай қолданады (2 балл);\n2. Фонетикалық ерекшеліктерді ажыратып, дұрыс талдайды (3 балл)."
        },
        ("5-сынып", "Қазақ тілі", "1-тоқсан", "БЖБ 2"): {
            "task": "5-сынып. 1-тоқсан. БЖБ 2. «Киіну. Сән. Талғам. Фонетика».",
            "desc": "1. Мәтін мазмұны бойынша негізгі ойды анықтайды (2 балл);\n2. Фонетикалық заңдылықтарға сай сөздерді түрлендіреді (3 балл)."
        },
        ("5-сынып", "Қазақ тілі", "1-тоқсан", "БЖБ 3"): {
            "task": "5-сынып. 1-тоқсан. БЖБ 3. «Отбасылық дәстүрлер мен мерекелер. Лексика».",
            "desc": "1. Лексикалық мағынаны мәнмәтінге сүйене отырып түсіндіреді (2 балл);\n2. Синоним, антоним, омонимдерді орынды қолданады (3 балл)."
        },
        ("5-сынып", "Қазақ тілі", "1-тоқсан", "ТЖБ"): {
            "task": "5-сынып. 1-тоқсан. ТЖБ. «Тоқсанның барлық бөлімі бойынша жиынтық бағалау».",
            "desc": "1. Тыңдалған/оқылған мәтіннің негізгі идеясын түсінеді (3 балл);\n2. Тілдік нормаларды сақтап, сауатты жазады (4 балл);\n3. Лексика-грамматикалық тапсырмаларды орындайды (3 балл)."
        }
    }

    # Кілтті құрастыру (БЖБ болса нөмірімен, ТЖБ болса тікелей)
    lookup_key = (selected_grade, selected_subject, selected_term, bzhb_sub_num if prefix_text == "БЖБ" else "ТЖБ")
    
    default_data = auto_content_db.get(
        lookup_key, 
        {
            "task": f"{selected_grade}. {selected_term}. {selected_subject} пәні бойынша {prefix_text} стандарты тапсырмасы.",
            "desc": "1. Тапсырма шартын толық түсініп, талапқа сай орындайды (2 балл);\n2. Жауабын жүйелі түрде негіздеп, қатесіз жазады (3 балл)."
        }
    )

    task_text = st.text_area("Тапсырма тақырыбы немесе сұрақ (Автоматты түрде шығады, қажет болса өңдеңіз)", value=default_data["task"])
    descriptors = st.text_area("Бағалау дескрипторлары (Спецификация бойынша автоматты шығады)", value=default_data["desc"])
    max_score = st.number_input("Ең жоғары ұпай", min_value=0.5, max_value=100.0, value=10.0 if prefix_text == "ТЖБ" else 5.0, step=0.5)
    
    uploaded_files = st.file_uploader(f"[{selected_term} | {prefix_text} | {selected_grade} - {selected_subject}] Оқушылардың жұмыс суреттерін жүктеу", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    
    if uploaded_files:
        st.success(f"Барлығы {len(uploaded_files)} жұмыс жүктелді. Әрқайсысын жеке өңдеңіз:")
        
        for idx, uploaded_file in enumerate(uploaded_files):
            with st.expander(f"📁 [{selected_term} | {prefix_text} | {selected_grade}] Жұмыс №{idx+1}: {uploaded_file.name}"):
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
                                                {"type": "text", "text": f"Тоқсан: {selected_term}, Түрі: {assessment_type}, Сынып: {selected_grade}, Пән: {selected_subject}\nТапсырма: {task_text}\nДескрипторлар: {descriptors}\nМакс ұпай: {max_score}"},
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
                                    full_task_info = f"[{selected_term} | {prefix_text} | {selected_grade} - {selected_subject}] {task_text.strip()}"
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
    st.write("Сыртқы ЖИ режимі: Қосулы (5-сынып Қазақ тілі БЖБ-1,2,3 және ТЖБ тақырыптары қосылды)")