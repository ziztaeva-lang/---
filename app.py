import streamlit as st
from PIL import Image
import base64
import pandas as pd
import io
import os
from openai import OpenAI
from security_layer import init_db, save_pending_result, get_pending_results, approve_result, get_approved_results, external_ai_is_enabled

st.set_page_config(page_title="SmartTest БЖБ–ТЖБ", layout="wide")
init_db()

# --- ФАЙЛДЫ ФОРМАТЫНА ҚАРАМАСТАН ҚАУІПСІЗ ОҚУ ЖҮЙЕСІ (Excel немесе CSV) ---
@st.cache_data
def load_specs():
    possible_files = [
        "specs.xlsx", "specs.xls", "specs.csv", "specs",
        "./specs.xlsx", "./specs.xls", "./specs.csv",
        "data/specs.xlsx", "data/specs.csv"
    ]
    
    for file_path in possible_files:
        if os.path.exists(file_path):
            # 1. Егер файл Excel форматында болса (.xlsx немесе .xls)
            if file_path.endswith(('.xlsx', '.xls')) or not file_path.endswith('.csv'):
                try:
                    df = pd.read_excel(file_path)
                    df.columns = df.columns.str.strip().str.lower()
                    required_cols = ["grade", "subject", "term", "type", "num", "task", "desc"]
                    if all(col in df.columns for col in required_cols):
                        return df
                except Exception:
                    pass
            
            # 2. Егер файл CSV форматында болса
            for enc in ["utf-8-sig", "utf-8", "cp1251", "latin1"]:
                try:
                    df = pd.read_csv(file_path, encoding=enc)
                    df.columns = df.columns.str.strip().str.lower()
                    required_cols = ["grade", "subject", "term", "type", "num", "task", "desc"]
                    if all(col in df.columns for col in required_cols):
                        return df
                except Exception:
                    continue
                    
    return pd.DataFrame(columns=["grade", "subject", "term", "type", "num", "task", "desc"])

specs_df = load_specs()

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
    if not specs_df.empty:
        st.success(f"✅ Спецификация файлы сәтті оқылды! Барлығы **{len(specs_df)}** жазба танылды.")
    else:
        st.warning("⚠️ Спецификация файлы табылмады немесе форматы қате. 'Қауіпсіздік' бөлімінен тексеріңіз.")
        
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

    # --- СЫНЫП ЖӘНЕ ПӘНДЕР ТІЗІМІН ДИНАМИКАЛЫҚ ҚҰРУ ---
    default_grades = ["5-сынып", "6-сынып", "7-сынып", "8-сынып", "9-сынып", "10-сынып", "11-сынып"]
    default_subjects = [
        "Қазақ тілі", "Қазақ әдебиеті", "Алгебра", "Геометрия", "Физика", "Химия", 
        "Биология", "География", "Жаратылыстану", "Цифрлық сауаттылық және жасанды интеллект", 
        "Информатика және жасанды интеллект", "Қазақстан тарихы", "Дүние жүзі тарихы", 
        "Құқық негіздері", "Орыс тілі мен әдебиеті", "Ағылшын тілі"
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

    # --- ДЕРЕКТЕРДІ ІЗДЕУ ЖӘНЕ СҮЗУ (LOOKUP) ---
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

    task_text = st.text_area("Тапсырма тақырыбы немесе сұрақ (Автоматты түрде шығады, қажет болса өңдеңіз)", value=default_task)
    descriptors = st.text_area("Бағалау дескрипторлары (Спецификация бойынша автоматты шығады)", value=default_desc)
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
            "Оқушы коды": df.get("student_code", pd.Series()),
            "Тапсырма": df.get("task_text", pd.Series()),
            "Бекітілген ұпай": df.get("teacher_score", pd.Series()),
            "Максималды ұпай": df.get("max_score", pd.Series()),
            "Бекіткен мұғалім": df.get("approved_by", pd.Series()),
            "Уақыты": df.get("approved_at", pd.Series()),
            "Кері байланыс/Ескертпе": df.get("teacher_comment", pd.Series())
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
    st.subheader("Қауіпсіздік және файл күйі")
    st.write("Дерекқор: компьютердегі data/smarttest.db")
    st.markdown("---")
    if not specs_df.empty:
        st.success(f"✅ Спецификация файлы сәтті оқылды! Жалпы жолдар саны: **{len(specs_df)}**")
        st.write("**Файлдағы табылған алғашқы жазбалар:**")
        st.dataframe(specs_df.head(5))
    else:
        st.error("❌ Спецификация файлы табылмады немесе іші бос.")
        st.info("💡 **Кеңес:** `app.py` файлымен бір папкада `specs.xlsx` (немесе `specs.csv`) файлы тұрғанына және бағандары (`grade, subject, term, type, num, task, desc`) дұрыс жазылғанына көз жеткізіңіз.")