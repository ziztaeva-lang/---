import streamlit as st
from openai import OpenAI
from PIL import Image
import io
import base64

# OpenAI клиентін іске қосу (client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"]))
# API кілтін тікелей жазбаймыз, Streamlit-тің жасырын қоймасынан аламыз
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="БЖБ – ТЖБ SMART CHECK", layout="wide")

# Мәзір (Sidebar)
st.sidebar.title("Мәзір")
menu = st.sidebar.selectbox("Бөлім", ["Басты бет", "Жұмысты тексеру", "Нәтижелер"])

if menu == "Басты бет":
    st.title("📄 БЖБ – ТЖБ SMART CHECK")
    st.write("Оқушы жұмыстарын тексеру және бағалау платформасы")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Тексерілген жұмыс", "1")
    col2.metric("БЖБ", "1")
    col3.metric("ТЖБ", "0")
    
    st.subheader("Платформа мүмкіндіктері")
    st.markdown("""
    - 🖼️ Сурет немесе PDF файлдарын жүктеу
    - 🤖 AI көмегімен қолжазбаны оқу және бағалау
    - ✅ Дұрыс жауаптарды жасыл белгімен, ❌ қателерді қызыл белгімен көрсету
    - 👨‍🏫 Мұғалімнің балды растауы және кері байланыс беруі
    """)

elif menu == "Жұмысты тексеру":
    st.title("🔍 Жұмысты тексеру панелі")
    
    descriptors = st.text_area(
        "Бағалау критерийлері (Дескрипторлар):", 
        "1. Тапсырманың шартын дұрыс жазады (2 балл)\n2. Есептеулерді қатесіз орындайды (3 балл)"
    )
    
    uploaded_file = st.file_uploader("Оқушының жұмысын жүктеңіз (Сурет)", type=["jpg", "png", "jpeg"])
    
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption="Жүктелген оқушы жұмысы", use_container_width=True)
        
        if st.button("🤖 ЖИ арқылы тексеруді бастау"):
            with st.spinner("Жасанды интеллект жұмысты тексеруде... Күте тұрыңыз."):
                try:
                    buffered = io.BytesIO()
                    image.save(buffered, format="JPEG")
                    img_str = base64.b64encode(buffered.getvalue()).decode()
                    
                    # AI-ға дұрыс/қате белгілерін қою туралы қатаң нұсқау берілді
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "Сіз мектеп мұғалімісіз. Берілген дескрипторлар мен оқушының жұмысының суретіне қарап бағалаңыз. "
                                    "Міндетті түрде әр дескриптор немесе тармақ үшін дұрыс орындалса '✅ [Дұрыс / Балл]', "
                                    "ал қате немесе орындалмаса '❌ [Қате / 0 балл]' белгілерін қолданып, қазақша кері байланыс беріңіз."
                                )
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": f"Мына дескрипторлар бойынша жұмысты бағалаңыз: \n{descriptors}"},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{img_str}"
                                        }
                                    }
                                ]
                            }
                        ]
                    )
                    
                    ai_result = response.choices[0].message.content
                    
                    st.success("Тексеру аяқталды!")
                    st.subheader("📊 AI ұсынған нәтиже (✅ / ❌ белгілерімен):")
                    st.markdown(ai_result)
                    
                    if st.button("✅ Бағаны растау және сақтау"):
                        st.balloons()
                        st.success("Нәтиже базаға сәтті сақталды!")
                        
                except Exception as e:
                    st.error(f"Қате орын алды: {e}")

elif menu == "Нәтижелер":
    st.title("📊 Нәтижелер тізімі")
    st.write("Мұнда тексерілген жұмыстардың жалпы тізімі шығады.")