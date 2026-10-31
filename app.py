import streamlit as st
from PIL import Image
from openai import OpenAI
from security_layer import init_db, save_pending_result, get_pending_results, approve_result, get_approved_results, external_ai_is_enabled

st.set_page_config(page_title="SmartTest БЖБ–ТЖБ", layout="wide")
init_db()

# Streamlit secrets арқылы OpenAI клиентін қауіпсіз баптау
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.sidebar.title("SmartTest")
menu = st.sidebar.selectbox("Бөлім", ["Басты бет", "Жұмысты тексеру", "Мұғалім бекітуі", "Нәтижелер", "Қауіпсіздік"])
st.title("📄 SmartTest — БЖБ / ТЖБ")

if menu == "Басты бет":
    st.write("Оқушы жұмыстарын тексеруге және мұғалімнің қорытынды бағасын бекітуге арналған жергілікті прототип.")
    st.info("Сыртқы ЖИ көмегімен алдын ала бағалау және визуалды индикаторлар қосылды.")
    c1, c2 = st.columns(2)
    c1.metric("Мұғалім тексеруін күтуде", len(get_pending_results()))
    c2.metric("Бекітілген жұмыс", len(get_approved_results()))

elif menu == "Жұмысты тексеру":
    st.subheader("Жұмысты тіркеу және бағалауға дайындау")
    student_code = st.text_input("Анонимді оқушы коды", placeholder="Мысалы: ST-0001")
    task_text = st.text_area("Тапсырма және/немесе жауап мәтіні", placeholder="Оқушының аты-жөнін, мектебін, сыныбын енгізбеңіз.")
    descriptors = st.text_area("Бағалау дескрипторлары", "1. Тапсырманың шартын дұрыс жазады (2 балл)\n2. Есептеулерді қатесіз орындайды (3 балл)")
    max_score = st.number_input("Ең жоғары ұпай", min_value=0.5, max_value=100.0, value=5.0, step=0.5)
    
    uploaded_file = st.file_uploader("Жұмыс суреті", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        try:
            st.image(Image.open(uploaded_file), caption="Жүктелген жұмыс суреті", use_container_width=True)
        except Exception:
            st.error("Сурет файлын оқу мүмкін болмады.")

    # --- ЖИ көмегімен бағалауды ұсыну функциясы ---
    ai_suggested_score = 0.0
    ai_explanation = ""

    if st.button("🤖 OpenAI (GPT-4o) арқылы талдау жасау"):
        if not task_text.strip() or not descriptors.strip():
            st.error("Тапсырма мәтіні мен дескрипторларды толтырыңыз.")
        else:
            with st.spinner("ЖИ жұмысты талдап жатыр..."):
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": "Сіз мектеп мұғалімісіз. Берілген дескрипторлар мен оқушының жауабын салыстырып, әділ ұпай мен қысқаша түсіндірме беріңіз."
                            },
                            {
                                "role": "user",
                                "content": f"Тапсырма/Жауап: {task_text}\nДескрипторлар: {descriptors}\nЕң жоғары ұпай: {max_score}"
                            }
                        ]
                    )
                    ai_explanation = response.choices[0].message.content
                    st.success("ЖИ талдауы дайын!")
                    st.write(ai_explanation)
                except Exception as e:
                    st.error(f"ЖИ қатесі: {e}")

    with st.form("save_pending_form"):
        proposed_score = st.number_input("Алдын ала ұпай (мұғалім тексереді)", min_value=0.0, max_value=float(max_score), value=float(ai_suggested_score), step=0.5)
        explanation = st.text_area("Түсіндірме", value=ai_explanation if ai_explanation else "Бағаны мұғалім тексеруі қажет.")
        submitted = st.form_submit_button("Тексеруге сақтау")
        if submitted:
            if not student_code.strip() or not task_text.strip():
                st.error("Анонимді код пен тапсырма/жауап мәтінін енгізіңіз.")
            else:
                try:
                    rid = save_pending_result(student_code.strip(), task_text.strip(), descriptors.strip(), float(proposed_score), float(max_score), explanation.strip())
                    st.success("Жұмыс жергілікті дерекқорға сақталды. Мұғалім бекіткенге дейін қорытынды баға қабылданбайды.")
                    st.code(rid)
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
        # Алдын ала ұпайға қарай түс белгісін таңдау (50% немесе одан жоғары болса жасыл, төмен болса қызыл)
        icon = "🟢" if prop_score >= (max_s * 0.5) else "🔴"
        
        with st.expander(f"{icon} Жұмыс: {item['student_code']} — Алдын ала ұпай: {prop_score} / {max_s} ({item['created_at']})"):
            st.write("Жауап/мәтін:", item["task_text"])
            st.write("Дескрипторлар:", item["descriptors"])
            st.write("Алдын ала ұпай:", f"**{prop_score} / {max_s}**")
            st.write("Түсіндірме:", item["explanation"])
            
            score = st.number_input("Мұғалім бекітетін ұпай", min_value=0.0, max_value=float(max_s), value=float(prop_score), step=0.5, key="score_" + item["id"])
            comment = st.text_area("Мұғалім ескертпесі", key="comment_" + item["id"])
            
            if st.button("Бағаны бекіту", key="approve_" + item["id"]):
                if not teacher_id.strip():
                    st.error("Мұғалім ID-ін енгізіңіз.")
                else:
                    try:
                        approve_result(item["id"], score, teacher_id.strip(), comment.strip())
                        st.success("Баға бекітілді және журналға жазылды.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Бекіту қатесі: {e}")

elif menu == "Нәтижелер":
    st.subheader("Мұғалім бекіткен нәтижелер")
    rows = get_approved_results()
    if not rows:
        st.info("Әзірге бекітілген нәтиже жоқ.")
        
    for item in rows:
        score = item['teacher_score']
        max_s = item['max_score']
        
        # Ұпай деңгейіне қарай жасыл немесе қызыл белгі қою
        if score >= (max_s * 0.5):
            status_icon = "🟢"
            status_text = "Тапсырма сәтті орындалды"
        else:
            status_icon = "🔴"
            status_text = "Қосымша жұмыс қажет"

        with st.expander(f"{status_icon} Оқушы: {item['student_code']} — {score} / {max_s} балл ({status_text})"):
            st.write("Жауап/мәтін:", item["task_text"])
            st.write("Дескрипторлар:", item["descriptors"])
            st.write("Мұғалім бекіткен ұпай:", f"**{score} / {max_s}**")
            st.write("Бекіткен мұғалім:", item["approved_by"])
            st.write("Бекітілген уақыты:", item["approved_at"])
            st.write("Ескертпе:", item["teacher_comment"] or "—")

elif menu == "Қауіпсіздік":
    st.subheader("Қауіпсіздік күйі")
    st.write("Дерекқор: компьютердегі data/smarttest.db")
    st.write("Сыртқы ЖИ режимі: Қосулы (OpenAI GPT-4o арқылы талдау қосылған)")