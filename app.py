import streamlit as st
from PIL import Image
import base64
import pandas as pd
import io
from openai import OpenAI
from security_layer import init_db, save_pending_result, get_pending_results, approve_result, get_approved_results, external_ai_is_enabled

st.set_page_config(page_title="SmartTest БЖБ–ТЖБ", layout="wide")
init_db()

# Streamlit secrets арқылы OpenAI клиентін баптау
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.sidebar.title("SmartTest")
menu = st.sidebar.selectbox("Бөлім", ["Басты бет", "Жұмысты тексеру", "Мұғалім бекітуі", "Нәтижелер", "Статистика", "Қауіпсіздік"])
st.title("📄 SmartTest — БЖБ / ТЖБ")

if menu == "Басты бет":
    st.write("Оқушы жұмыстарын тексеруге және мұғалімнің қорытынды бағасын бекітуге арналған жергілікті прототип.")
    st.info("GPT-4o Vision, Excel/CSV экспорт және Графикалық аналитика функциялары қосылды.")
    c1, c2 = st.columns(2)
    c1.metric("Мұғалім тексеруін күтуде", len(get_pending_results()))
    c2.metric("Бекітілген жұмыс", len(get_approved_results()))

elif menu == "Жұмысты тексеру":
    st.subheader("Жұмысты тіркеу және суретті ЖИ арқылы бағалау")
    student_code = st.text_input("Анонимді оқушы коды", placeholder="Мысалы: ST-0001")
    task_text = st.text_area("Тапсырма тақырыбы немесе сұрақ", placeholder="Мысалы: 1-БЖБ. Есепті шығарыңыз.")
    descriptors = st.text_area("Бағалау дескрипторлары", "1. Шартын дұрыс жазады (2 балл)\n2. Есептеулерді қатесіз орындайды (3 балл)")
    max_score = st.number_input("Ең жоғары ұпай", min_value=0.5, max_value=100.0, value=5.0, step=0.5)
    
    uploaded_file = st.file_uploader("Оқушы жұмысының суретін жүктеу", type=["jpg", "jpeg", "png"])
    
    ai_suggested_score = 0.0
    ai_explanation = ""

    if uploaded_file:
        try:
            image = Image.open(uploaded_file)
            st.image(image, caption="Жүктелген оқушы жұмысы", use_container_width=True)
            
            def encode_uploaded_image(uploaded_file):
                bytes_data = uploaded_file.getvalue()
                return base64.b64encode(bytes_data).decode('utf-8')

            if st.button("🔍 Суретті ЖИ (GPT-4o) арқылы оқып, талдау жасау"):
                with st.spinner("ЖИ суретті оқып, жауапты тексеріп жатыр..."):
                    try:
                        base64_image = encode_uploaded_image(uploaded_file)
                        
                        response = client.chat.completions.create(
                            model="gpt-4o",
                            messages=[
                                {
                                    "role": "system",
                                    "content": "Сіз мектеп мұғалімісіз. Берілген дескрипторлар мен оқушының жұмыс суретін мұқият қарап шығып, орындалу барысын талдаңыз, әділ ұпай ұсыныңыз және түсіндірме беріңіз."
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"Тапсырма: {task_text}\nДескрипторлар: {descriptors}\nЕң жоғары ұпай: {max_score}"
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/jpeg;base64,{base64_image}"
                                            }
                                        }
                                    ]
                                }
                            ],
                            max_tokens=500
                        )
                        ai_explanation = response.choices[0].message.content
                        st.success("Сурет сәтті оқылып, ЖИ талдауы дайын болды!")
                        st.write(ai_explanation)
                    except Exception as e:
                        st.error(f"ЖИ суретті оқу кезінде қате шықты: {e}")
        except Exception:
            st.error("Сурет файлын ашу мүмкін болмады.")

    with st.form("save_pending_form"):
        proposed_score = st.number_input("Алдын ала ұпай (мұғалім тексереді)", min_value=0.0, max_value=float(max_score), value=float(ai_suggested_score), step=0.5)
        explanation = st.text_area("Түсіндірме", value=ai_explanation if ai_explanation else "Бағаны мұғалім тексеруі қажет.")
        submitted = st.form_submit_button("Тексеруге сақтау")
        if submitted:
            if not student_code.strip():
                st.error("Анонимді кодты енгізіңіз.")
            else:
                try:
                    rid = save_pending_result(student_code.strip(), task_text.strip() or "Сурет түріндегі жұмыс", descriptors.strip(), float(proposed_score), float(max_score), explanation.strip())
                    st.success("Жұмыс дерекқорға сақталды. Мұғалім бекітуін күтуде.")
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
        icon = "🟢" if prop_score >= (max_s * 0.5) else "🔴"
        
        with st.expander(f"{icon} Жұмыс: {item['student_code']} — Алдын ала ұпай: {prop_score} / {max_s} ({item['created_at']})"):
            st.write("Тапсырма/мәтін:", item["task_text"])
            st.write("Дескрипторлар:", item["descriptors"])
            st.write("Түсіндірме/ЖИ талдауы:", item["explanation"])
            
            score = st.number_input("Мұғалім бекітетін ұпай", min_value=0.0, max_value=float(max_s), value=float(prop_score), step=0.5, key="score_" + item["id"])
            comment = st.text_area("Мұғалім ескертпесі", key="comment_" + item["id"])
            
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
            "Ескертпе": df.get("teacher_comment", "")
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
                st.write("Бекіткен мұғалім:", item["approved_by"])
                st.write("Бекітілген уақыты:", item["approved_at"])
                st.write("Ескертпе:", item["teacher_comment"] or "—")

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
        
        # Көрсеткіштер метрикасы
        col1, col2, col3 = st.columns(3)
        col1.metric("Бекітілген жұмыс саны", total_works)
        col2.metric("Орташа ұпай", f"{avg_score:.2f} / {max_possible}")
        
        # Сәттілік пайызы (50%-дан жоғары алғандар)
        success_count = len(df[df['teacher_score'] >= (df['max_score'] * 0.5)])
        success_rate = (success_count / total_works) * 100 if total_works > 0 else 0
        col3.metric("Табыстылық көрсеткіші", f"{success_rate:.1f}%")
        
        st.markdown("---")
        st.write("### Оқушылардың ұпайлар бөлінісі (График)")
        
        # Графикалық аналитика үшін Streamlit бағандық диаграммасы
        chart_data = df.set_index('student_code')[['teacher_score']]
        st.bar_chart(chart_data)
        
        st.write("Бұл график әрбір анонимді оқушы коды бойынша жиналған қорытынды ұпайларды визуалды түрде көрсетеді.")

elif menu == "Қауіпсіздік":
    st.subheader("Қауіпсіздік күйі")
    st.write("Дерекқор: компьютердегі data/smarttest.db")
    st.write("Сыртқы ЖИ режимі: Қосулы (GPT-4o Vision арқылы суретті оқу қосылған)")