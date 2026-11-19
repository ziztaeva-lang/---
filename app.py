import streamlit as st
from PIL import Image
import base64
import pandas as pd
import io
import os
import re
from openai import OpenAI
from security_layer import (
    init_db, save_pending_result, get_pending_results, 
    approve_result, get_approved_results, external_ai_is_enabled,
    get_user_credits, deduct_credit, verify_user, add_payment_record,
    get_user_role, get_user_subject, clear_all_results
)

# PyMuPDF (fitz) — PDF-ті суретке айналдыру үшін (орнатылмаса да қосымша құламайды)
try:
    import fitz
except ImportError:
    fitz = None

# iPhone .HEIC / .HEIF форматтарын қолдау
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

st.set_page_config(page_title="SmartTest БЖБ–ТЖБ", layout="wide")
init_db()

# --- 3 ТІЛДІ СӨЗДІК (ҚАЗ / РУС / ENG) ---
TRANSLATIONS = {
    "ҚАЗ": {
        "lang_label": "🌐 Тіл / Язык / Language",
        "login_title": "🔐 SmartTest — Мұғалімнің жеке кабинетіне кіру",
        "login_desc": "Платформаға кіру үшін логиніңіз бен құпия сөзіңізді енгізіңіз.",
        "username": "Логин (Username)",
        "username_ph": "Мысалы: zoya",
        "password": "Құпия сөз (Password)",
        "password_ph": "Құпия сөз...",
        "login_btn": "Кіру",
        "welcome": "Қош келдіңіз",
        "login_err": "Логин немесе құпия сөз қате!",
        "user_lbl": "Қолданушы",
        "balance_lbl": "💳 Сіздің балансыңыз",
        "credit_unit": "кредит",
        "section_lbl": "Бөлім",
        "logout_btn": "🚪 Жүйеден шығу",
        "app_title": "📄 SmartTest — Автоматты түрде тексеру жүйесі",
        "menu_home": "Басты бет",
        "menu_check": "Жұмысты тексеру",
        "menu_approve": "Мұғалім бекітуі",
        "menu_results": "Нәтижелер",
        "menu_stats": "Статистика",
        "menu_billing": "Балансты толтыру",
        "menu_security": "Қауіпсіздік",
        "home_desc": "Оқушы жұмыстарын ҚР білім беру стандартына сай автоматты түрде тексеруге арналған платформа.",
        "pending_metric": "Мұғалім тексеруін күтуде",
        "approved_metric": "Бекітілген жұмыс",
        "check_sub": "Оқушы жұмыстарын жүктеу және автоматты тексеру",
        "mode_lbl": "📂 Жүктеу режимін таңдаңыз:",
        "mode_multi_students": "📑 Әр файл = 1 жеке оқушы (Көпбетті PDF немесе бүкіл сынып файлдары)",
        "mode_single_student": "📚 Барлық жүктелген суреттер = 1 оқушының жұмысы (Бөлек фотоларды біріктіру)",
        "mode_camera": "📸 Камерамен суретке түсіру (Бірнеше бетті қатарынан түсіру)",
        "max_score_lbl": "Ең жоғары балл (Шкала)",
        "upload_lbl": "Оқушылардың жұмыс файлдарын жүктеу (JPG, PNG, HEIC, көпбетті PDF — 1 файл = 1 кредит)",
        "upload_single_lbl": "Бір оқушының барлық беттерін (JPG, PNG, HEIC, PDF) бірге жүктеңіз (1 кредит)",
        "cam_widget_lbl": "📸 Дәптер бетін камерамен түсіріңіз",
        "cam_add_btn": "➕ Осы бетті тізімге қосу",
        "cam_clear_btn": "🗑️ Түсірілген беттерді тазалау (Келесі оқушы)",
        "cam_added_ok": "✅ {}-бет сәтті қосылды! Келесі бетті түсіре беруіңізге болады.",
        "cam_no_photo_warn": "⚠️ Алдымен камерамен суретке түсіріңіз!",
        "cam_pages_count": "📸 Қазір жиналған беттер саны: **{} бет** (Барлығы бірге 1 кредитпен тексеріледі)",
        "cam_empty_info": "ℹ️ Камераны іске қосып, дәптердің 1-ші бетін түсіріңіз де, **➕ Осы бетті тізімге қосу** батырмасын басыңыз.",
        "uploaded_ok": "Барлығы {} файл жүктелді (әр көпбетті PDF ішіндегі барлық беттер біртұтас жұмыс ретінде 1 кредитпен тексеріледі).",
        "uploaded_single_ok": "Бір оқушының {} файлы (барлығы {} бет) жүктелді. Барлық беттер біртұтас жұмыс ретінде 1 кредитпен тексеріледі.",
        "page_caption": "{}-бет: {}",
        "bulk_check_btn": "⚡ Барлық жұмысты бірден тексеру",
        "all_checked_info": "ℹ️ Барлық жүктелген жұмыстар тексеріліп қойған.",
        "no_credits_bulk": "❌ Барлық {} жұмысты тексеру үшін {} кредит қажет (Сізде: {} кредит).",
        "checking_progress": "⏳ Тексерілуде ({}/{}): **{}**...",
        "bulk_check_done": "✅ Барлық жұмыстар сәтті тексерілді!",
        "bulk_save_btn": "💾 Барлығын бірден сақтау",
        "missing_names_err": "❌ Келесі жұмыстарға оқушы аты-жөні енгізілмеген: {}",
        "bulk_save_done": "✅ Барлығы {} оқушының нәтижесі сәтті сақталды! Енді «Мұғалім бекітуі» бөлімінен бекіте аласыз.",
        "status_checked": "✅ Тексерілді",
        "status_pending": "⏳ Күтілуде",
        "work_lbl": "Жұмыс №",
        "pdf_loaded": "📄 PDF құжаты жүктелді ({} бет). Барлық бет бірге тексеріледі (1 кредит).",
        "pdf_missing_lib": "⚠️ PDF файлдарды өңдеу үшін `requirements.txt` файлына `pymupdf` қосып, қосымшаны қайта іске қосыңыз.",
        "img_err": "Суретті ашу мүмкін болмады.",
        "student_name_lbl": "👤 Оқушының аты-жөнін енгізіңіз *",
        "student_name_ph": "Мысалы: Асанов Алихан",
        "single_check_btn": "🟢 Автоматты тексеру (1 кредит)",
        "multi_page_check_btn": "🟢 Барлық бетті бірге тексеру (1 кредит)",
        "no_credits_err": "❌ Балансыңызда кредит жеткіліксіз!",
        "ai_spinner": "ЖИ ҚР білім стандартына сәйкес жұмыстың барлық беттерін толық талдап жатыр...",
        "single_check_ok": "✅ Жұмыс стандартқа сай сәтті тексерілді!",
        "analysis_res_hdr": "### 🎨 Талдау нәтижесі:",
        "check_hint": "ℹ️ Оқушының аты-жөнін жазып, **🟢 Автоматты тексеру** батырмасын басыңыз.",
        "score_input_lbl": "Жалпы жинаған ұпай саны",
        "feedback_lbl": "Толық кері байланыс мәтіні",
        "save_btn": "💾 Нәтижені сақтау",
        "save_ok": "✅ {} нәтижесі сәтті сақталды!",
        "save_name_err": "❌ Сақтау үшін жоғарыдағы өріске оқушының аты-жөнін міндетті түрде енгізіңіз!",
        "approve_sub": "Мұғалімнің қорытынды бағасын бекіту",
        "no_pending": "Бекітуді күтіп тұрған жұмыс жоқ.",
        "pending_count": "Бекітуді күтіп тұрған жұмыстар саны:",
        "bulk_approve_btn": "✅ Барлығын бірден бекіту",
        "bulk_approve_ok": "✅ Барлық жұмыстар сәтті бекітілді!",
        "approve_score_lbl": "Бекітілетін ұпай",
        "comment_lbl": "Ескертпе (міндетті емес)",
        "comment_ph": "Қажет болса, қосымша пікір қалдырыңыз...",
        "approve_btn": "Бекіту",
        "results_sub": "Мұғалім бекіткен нәтижелер",
        "no_results": "Әзірге нәтиже жоқ.",
        "stats_sub": "📊 Сыныптың статистикасы мен педагогикалық талдау",
        "no_stats": "Әзірге бекітілген нәтижелер жоқ. Статистика шығару үшін жұмыстарды тексеріп, бекітіңіз.",
        "col_student": "Оқушы аты-жөні",
        "col_score": "Бекітілген ұпай",
        "col_max": "Максималды балл",
        "col_fb": "Кері байланыс",
        "col_pct": "Пайыздық көрсеткіш (%)",
        "m_students": "Оқушы саны",
        "m_avg": "Орташа балл",
        "m_pass": "Үлгерім пайызы",
        "m_qual": "Сапа пайызы",
        "chart_hdr": "### 📈 Оқушылардың аты-жөні бойынша ұпайлары",
        "ai_ped_hdr": "### 🧠 Оқу мақсаттары бойынша автоматты педагогикалық талдау",
        "ai_ped_desc": "БЖБ / ТЖБ қорытынды анықтамасына арналған дайын талдау мәтінін құрастыру:",
        "subj_lbl": "📚 Пән атауы",
        "subj_ph": "Мысалы: Информатика / Математика / Қазақ тілі",
        "class_lbl": "🏫 Сынып",
        "class_ph": "Мысалы: 6 «А»",
        "assess_type_lbl": "📝 Бағалау түрі",
        "assess_options": ["БЖБ №1", "БЖБ №2", "БЖБ №3", "ТЖБ"],
        "ai_ped_btn": "🤖 Қол жеткізген және қиындық туғызған мақсаттарды талдау",
        "ai_ped_spin": "ЖИ барлық оқушылардың қателері мен жетістіктерін қорытындылап жатыр...",
        "copy_area_lbl": "Көшіріп алуға ыңғайлы мәтін (Word / Kundelik / BilimClass үшін):",
        "export_hdr": "### 📥 Есепті жүктеп алу",
        "excel_btn": "📊 Толық есепті Excel форматында жүктеу (.xlsx)",
        "billing_sub": "💳 Кредит сатып алу және балансты толтыру",
        "billing_desc": "1 кредит = 100 ₸. Қалаған кредит санын енгізіп, төлем жасаңыз.",
        "credits_buy_lbl": "Сатып алғыңыз келетін кредит саны:",
        "total_pay_lbl": "Төленетін жалпы сома:",
        "pay_steps": "📱 **Төлем жасау қадамдары:**\n1. Төмендегі QR кодтардың бірін сканерлеңіз;\n2. Соманы аударыңыз;\n3. Төлем чегіндегі транзакция / чек нөмірін енгізіңіз.",
        "txn_hdr": "### Төлемді растау үшін деректерді енгізіңіз:",
        "txn_lbl": "Транзакция / чек нөмірі",
        "txn_ph": "Операция нөмірін жазыңыз...",
        "txn_btn": "📤 Төлем туралы хабарлау",
        "txn_err": "❌ Дұрыс транзакция нөмірін енгізіңіз!",
        "txn_ok": "✅ Өтінім қабылданды! Тексерілгеннен кейін балансыңызға {} кредит қосылады.",
        "sec_sub": "Қауіпсіздік және жүйе күйі",
        "sec_denied": "⛔ Бұл бетке тек әкімші (admin) ғана кіре алады!",
        "db_mgmt_hdr": "⚙️ Дерекқорды басқару және тазалау",
        "db_mgmt_warn": "⚠️ Назар аударыңыз! Бұл әрекет базадағы барлық сақталған тексерілмеген және бекітілген оқушы нәтижелерін толығымен жояды.",
        "db_clear_btn": "🗑️ Базадағы барлық нәтижелерді толық тазалау",
        "db_clear_ok": "✅ Дерекқордағы барлық оқушы нәтижелері сәтті тазартылды!"
    },
    "РУС": {
        "lang_label": "🌐 Тіл / Язык / Language",
        "login_title": "🔐 SmartTest — Вход в личный кабинет учителя",
        "login_desc": "Введите ваш логин и пароль для входа на платформу.",
        "username": "Логин (Username)",
        "username_ph": "Например: zoya",
        "password": "Пароль (Password)",
        "password_ph": "Пароль...",
        "login_btn": "Войти",
        "welcome": "Добро пожаловать",
        "login_err": "Неверный логин или пароль!",
        "user_lbl": "Пользователь",
        "balance_lbl": "💳 Ваш баланс",
        "credit_unit": "кредитов",
        "section_lbl": "Раздел",
        "logout_btn": "🚪 Выйти из системы",
        "app_title": "📄 SmartTest — Система автоматической проверки",
        "menu_home": "Главная",
        "menu_check": "Проверка работ",
        "menu_approve": "Утверждение учителем",
        "menu_results": "Результаты",
        "menu_stats": "Статистика",
        "menu_billing": "Пополнить баланс",
        "menu_security": "Безопасность",
        "home_desc": "Платформа для автоматической проверки работ учащихся в соответствии со стандартами образования РК.",
        "pending_metric": "Ожидают проверки учителя",
        "approved_metric": "Утвержденные работы",
        "check_sub": "Загрузка и автоматическая проверка работ учащихся",
        "mode_lbl": "📂 Выберите режим загрузки:",
        "mode_multi_students": "📑 Каждый файл = 1 отдельный ученик (Многостраничный PDF или файлы всего класса)",
        "mode_single_student": "📚 Все загруженные фото = работа 1 ученика (Объединение отдельных фото)",
        "mode_camera": "📸 Сделать фото камерой (Съемка нескольких страниц подряд)",
        "max_score_lbl": "Максимальный балл (Шкала)",
        "upload_lbl": "Загрузить файлы работ учащихся (JPG, PNG, HEIC, многостраничный PDF — 1 файл = 1 кредит)",
        "upload_single_lbl": "Загрузите все страницы (JPG, PNG, HEIC, PDF) одного ученика вместе (1 кредит)",
        "cam_widget_lbl": "📸 Сфотографируйте страницу тетради",
        "cam_add_btn": "➕ Добавить эту страницу в список",
        "cam_clear_btn": "🗑️ Очистить снятые страницы (Следующий ученик)",
        "cam_added_ok": "✅ Страница №{} добавлена! Можете сфотографировать следующую страницу.",
        "cam_no_photo_warn": "⚠️ Сначала сделайте снимок камерой!",
        "cam_pages_count": "📸 Собрано страниц: **{} стр.** (Все вместе проверяются за 1 кредит)",
        "cam_empty_info": "ℹ️ Включите камеру, сфотографируйте 1-ю страницу тетради и нажмите **➕ Добавить эту страницу в список**.",
        "uploaded_ok": "Всего загружено файлов: {} (все страницы внутри каждого PDF проверяются как единая работа за 1 кредит).",
        "uploaded_single_ok": "Загружено файлов одного ученика: {} (всего страниц: {}). Все страницы будут проверены как единая работа за 1 кредит.",
        "page_caption": "Страница {}: {}",
        "bulk_check_btn": "⚡ Проверить все работы сразу",
        "all_checked_info": "ℹ️ Все загруженные работы уже проверены.",
        "no_credits_bulk": "❌ Для проверки всех {} работ необходимо {} кредитов (У вас: {} кредитов).",
        "checking_progress": "⏳ Проверяется ({}/{}): **{}**...",
        "bulk_check_done": "✅ Все работы успешно проверены!",
        "bulk_save_btn": "💾 Сохранить все сразу",
        "missing_names_err": "❌ Не указано ФИО ученика для следующих работ: {}",
        "bulk_save_done": "✅ Результаты {} учащихся успешно сохранены! Теперь вы можете утвердить их в разделе «Утверждение учителем».",
        "status_checked": "✅ Проверено",
        "status_pending": "⏳ Ожидает",
        "work_lbl": "Работа №",
        "pdf_loaded": "📄 Загружен PDF документ ({} стр.). Все страницы проверяются вместе (1 кредит).",
        "pdf_missing_lib": "⚠️ Для обработки PDF добавьте `pymupdf` в `requirements.txt` и перезапустите приложение.",
        "img_err": "Не удалось открыть изображение.",
        "student_name_lbl": "👤 Введите ФИО ученика *",
        "student_name_ph": "Например: Асанов Алихан",
        "single_check_btn": "🟢 Автоматическая проверка (1 кредит)",
        "multi_page_check_btn": "🟢 Проверить все страницы вместе (1 кредит)",
        "no_credits_err": "❌ Недостаточно кредитов на балансе!",
        "ai_spinner": "ИИ анализирует все страницы работы согласно стандартам образования РК...",
        "single_check_ok": "✅ Работа успешно проверена по стандарту!",
        "analysis_res_hdr": "### 🎨 Результат анализа:",
        "check_hint": "ℹ️ Введите ФИО ученика и нажмите **🟢 Автоматическая проверка**.",
        "score_input_lbl": "Общий набранный балл",
        "feedback_lbl": "Полный текст обратной связи",
        "save_btn": "💾 Сохранить результат",
        "save_ok": "✅ Результат ученика {} успешно сохранен!",
        "save_name_err": "❌ Для сохранения обязательно введите ФИО ученика в поле выше!",
        "approve_sub": "Утверждение итоговой оценки учителем",
        "no_pending": "Нет работ, ожидающих утверждения.",
        "pending_count": "Количество работ, ожидающих утверждения:",
        "bulk_approve_btn": "✅ Утвердить все сразу",
        "bulk_approve_ok": "✅ Все работы успешно утверждены!",
        "approve_score_lbl": "Утверждаемый балл",
        "comment_lbl": "Примечание (необязательно)",
        "comment_ph": "При необходимости оставьте комментарий...",
        "approve_btn": "Утвердить",
        "results_sub": "Результаты, утвержденные учителем",
        "no_results": "Пока нет результатов.",
        "stats_sub": "📊 Статистика класса и педагогический анализ",
        "no_stats": "Пока нет утвержденных результатов. Для вывода статистики проверьте и утвердите работы.",
        "col_student": "ФИО ученика",
        "col_score": "Утвержденный балл",
        "col_max": "Максимальный балл",
        "col_fb": "Обратная связь",
        "col_pct": "Процентный показатель (%)",
        "m_students": "Количество учеников",
        "m_avg": "Средний балл",
        "m_pass": "Процент успеваемости",
        "m_qual": "Качество знаний",
        "chart_hdr": "### 📈 Баллы по ФИО учащихся",
        "ai_ped_hdr": "### 🧠 Автоматический педагогический анализ по целям обучения",
        "ai_ped_desc": "Формирование готового текста анализа для итоговой справки СОР / СОЧ:",
        "subj_lbl": "📚 Название предмета",
        "subj_ph": "Например: Информатика / Математика / Русский язык",
        "class_lbl": "🏫 Класс",
        "class_ph": "Например: 6 «А»",
        "assess_type_lbl": "📝 Вид оценивания",
        "assess_options": ["СОР №1", "СОР №2", "СОР №3", "СОЧ"],
        "ai_ped_btn": "🤖 Анализ достигнутых и вызвавших затруднения целей",
        "ai_ped_spin": "ИИ обобщает ошибки и достижения всех учащихся...",
        "copy_area_lbl": "Удобный для копирования текст (для Word / Kundelik / BilimClass):",
        "export_hdr": "### 📥 Скачать отчет",
        "excel_btn": "📊 Скачать полный отчет в формате Excel (.xlsx)",
        "billing_sub": "💳 Покупка кредитов и пополнение баланса",
        "billing_desc": "1 кредит = 100 ₸. Укажите желаемое количество кредитов и произведите оплату.",
        "credits_buy_lbl": "Количество кредитов для покупки:",
        "total_pay_lbl": "Общая сумма к оплате:",
        "pay_steps": "📱 **Шаги оплаты:**\n1. Отсканируйте один из QR-кодов ниже;\n2. Переведите сумму;\n3. Введите номер транзакции / чека.",
        "txn_hdr": "### Введите данные для подтверждения оплаты:",
        "txn_lbl": "Номер транзакции / чека",
        "txn_ph": "Введите номер операции...",
        "txn_btn": "📤 Сообщить об оплате",
        "txn_err": "❌ Введите корректный номер транзакции!",
        "txn_ok": "✅ Заявка принята! После проверки на ваш баланс будет начислено {} кредитов.",
        "sec_sub": "Безопасность и состояние системы",
        "sec_denied": "⛔ Доступ к этой странице разрешен только администратору (admin)!",
        "db_mgmt_hdr": "⚙️ Управление и очистка базы данных",
        "db_mgmt_warn": "⚠️ Внимание! Это действие полностью удалит все сохраненные результаты и незавершенные работы учащихся из базы данных.",
        "db_clear_btn": "🗑️ Полностью очистить все результаты в базе",
        "db_clear_ok": "✅ Все результаты учащихся в базе данных успешно очищены!"
    },
    "ENG": {
        "lang_label": "🌐 Тіл / Язык / Language",
        "login_title": "🔐 SmartTest — Teacher's Personal Cabinet",
        "login_desc": "Enter your username and password to access the platform.",
        "username": "Username",
        "username_ph": "e.g., zoya",
        "password": "Password",
        "password_ph": "Password...",
        "login_btn": "Login",
        "welcome": "Welcome",
        "login_err": "Invalid username or password!",
        "user_lbl": "User",
        "balance_lbl": "💳 Your Balance",
        "credit_unit": "credits",
        "section_lbl": "Section",
        "logout_btn": "🚪 Logout",
        "app_title": "📄 SmartTest — Automated Grading System",
        "menu_home": "Home",
        "menu_check": "Grade Works",
        "menu_approve": "Teacher Approval",
        "menu_results": "Results",
        "menu_stats": "Statistics",
        "menu_billing": "Top Up Balance",
        "menu_security": "Security",
        "home_desc": "Automated grading platform aligned with the Educational Standards of the Republic of Kazakhstan.",
        "pending_metric": "Pending Teacher Review",
        "approved_metric": "Approved Works",
        "check_sub": "Upload and Automatically Grade Student Works",
        "mode_lbl": "📂 Select Upload Mode:",
        "mode_multi_students": "📑 Each file = 1 individual student (Multi-page PDF or batch class files)",
        "mode_single_student": "📚 All uploaded images = 1 student's work (Combine separate photos)",
        "mode_camera": "📸 Capture with Camera (Take multiple pages sequentially)",
        "max_score_lbl": "Maximum Score (Scale)",
        "upload_lbl": "Upload student work files (JPG, PNG, HEIC, multi-page PDF — 1 file = 1 credit)",
        "upload_single_lbl": "Upload all pages (JPG, PNG, HEIC, PDF) of a single student together (1 credit)",
        "cam_widget_lbl": "📸 Take a photo of the notebook page",
        "cam_add_btn": "➕ Add This Page to List",
        "cam_clear_btn": "🗑️ Clear Captured Pages (Next Student)",
        "cam_added_ok": "✅ Page #{} added! You may capture the next page.",
        "cam_no_photo_warn": "⚠️ Please take a photo with the camera first!",
        "cam_pages_count": "📸 Captured pages count: **{} page(s)** (Graded together for 1 credit)",
        "cam_empty_info": "ℹ️ Activate the camera, snap the 1st page of the notebook, and click **➕ Add This Page to List**.",
        "uploaded_ok": "Total {} files uploaded (all pages inside each multi-page PDF are graded together for 1 credit).",
        "uploaded_single_ok": "{} files ({} total pages) uploaded for 1 student. All pages will be graded together for 1 credit.",
        "page_caption": "Page {}: {}",
        "bulk_check_btn": "⚡ Grade All Works at Once",
        "all_checked_info": "ℹ️ All uploaded works have already been graded.",
        "no_credits_bulk": "❌ {} credits are required to grade all {} works (Your balance: {} credits).",
        "checking_progress": "⏳ Grading ({}/{}): **{}**...",
        "bulk_check_done": "✅ All works have been successfully graded!",
        "bulk_save_btn": "💾 Save All at Once",
        "missing_names_err": "❌ Student name is missing for: {}",
        "bulk_save_done": "✅ Results for {} students saved! You can now approve them in the 'Teacher Approval' tab.",
        "status_checked": "✅ Graded",
        "status_pending": "⏳ Pending",
        "work_lbl": "Work #",
        "pdf_loaded": "📄 PDF document uploaded ({} pages). All pages graded together (1 credit).",
        "pdf_missing_lib": "⚠️ To process PDF files, add `pymupdf` to `requirements.txt` and reboot the app.",
        "img_err": "Unable to open image.",
        "student_name_lbl": "👤 Enter Student Full Name *",
        "student_name_ph": "e.g., Alikhan Asanov",
        "single_check_btn": "🟢 Auto Grade (1 credit)",
        "multi_page_check_btn": "🟢 Grade All Pages Together (1 credit)",
        "no_credits_err": "❌ Insufficient credits in your balance!",
        "ai_spinner": "AI is analyzing all pages of the work according to RK educational standards...",
        "single_check_ok": "✅ Work successfully graded according to standards!",
        "analysis_res_hdr": "### 🎨 Analysis Result:",
        "check_hint": "ℹ️ Enter the student's name and click **🟢 Auto Grade**.",
        "score_input_lbl": "Total Score Earned",
        "feedback_lbl": "Full Feedback Text",
        "save_btn": "💾 Save Result",
        "save_ok": "✅ Result for {} saved successfully!",
        "save_name_err": "❌ Please enter the student's full name in the field above before saving!",
        "approve_sub": "Final Grade Approval by Teacher",
        "no_pending": "No works awaiting approval.",
        "pending_count": "Works awaiting approval:",
        "bulk_approve_btn": "✅ Approve All at Once",
        "bulk_approve_ok": "✅ All works have been successfully approved!",
        "approve_score_lbl": "Approved Score",
        "comment_lbl": "Note (optional)",
        "comment_ph": "Add an optional comment if needed...",
        "approve_btn": "Approve",
        "results_sub": "Teacher-Approved Results",
        "no_results": "No results yet.",
        "stats_sub": "📊 Class Statistics and Pedagogical Analysis",
        "no_stats": "No approved results yet. Grade and approve works to view statistics.",
        "col_student": "Student Full Name",
        "col_score": "Approved Score",
        "col_max": "Max Score",
        "col_fb": "Feedback",
        "col_pct": "Percentage (%)",
        "m_students": "Students Count",
        "m_avg": "Average Score",
        "m_pass": "Passing Rate",
        "m_qual": "Quality Rate",
        "chart_hdr": "### 📈 Scores by Student Name",
        "ai_ped_hdr": "### 🧠 Automated Pedagogical Analysis by Learning Objectives",
        "ai_ped_desc": "Generate a ready-to-use analytical report for BJB / TJB (summative assessments):",
        "subj_lbl": "📚 Subject Name",
        "subj_ph": "e.g., Computer Science / Mathematics / English",
        "class_lbl": "🏫 Grade / Class",
        "class_ph": "e.g., Grade 6A",
        "assess_type_lbl": "📝 Assessment Type",
        "assess_options": ["BJB (SAU) #1", "BJB (SAU) #2", "BJB (SAU) #3", "TJB (SAT)"],
        "ai_ped_btn": "🤖 Analyze Achieved & Challenging Objectives",
        "ai_ped_spin": "AI is summarizing errors and achievements across all students...",
        "copy_area_lbl": "Copy-ready text (for Word / Kundelik / BilimClass):",
        "export_hdr": "### 📥 Download Report",
        "excel_btn": "📊 Download Full Report in Excel (.xlsx)",
        "billing_sub": "💳 Buy Credits and Top Up Balance",
        "billing_desc": "1 credit = 100 ₸. Enter the desired number of credits and complete payment.",
        "credits_buy_lbl": "Number of credits to buy:",
        "total_pay_lbl": "Total amount payable:",
        "pay_steps": "📱 **Payment Steps:**\n1. Scan one of the QR codes below;\n2. Transfer the exact amount;\n3. Enter the transaction / receipt ID.",
        "txn_hdr": "### Enter details to verify payment:",
        "txn_lbl": "Transaction / Receipt ID",
        "txn_ph": "Enter operation number...",
        "txn_btn": "📤 Submit Payment Info",
        "txn_err": "❌ Please enter a valid transaction ID!",
        "txn_ok": "✅ Request received! {} credits will be added to your balance after verification.",
        "sec_sub": "Security & System Status",
        "sec_denied": "⛔ Access to this page is restricted to administrators only!",
        "db_mgmt_hdr": "⚙️ Database Management & Cleanup",
        "db_mgmt_warn": "⚠️ Warning! This action will completely delete all saved student results and unfinished works from the database.",
        "db_clear_btn": "🗑️ Clear All Results in Database",
        "db_clear_ok": "✅ All student results in the database have been successfully cleared!"
    }
}

if "lang" not in st.session_state:
    st.session_state.lang = "ҚАЗ"

def t(key):
    return TRANSLATIONS[st.session_state.lang].get(key, key)

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

# --- PDF БЕТТЕР САНЫН АНЫҚТАУ ФУНКЦИЯСЫ ---
def count_pages_in_files(files_list):
    total = 0
    for f in files_list:
        if f.name.lower().endswith(".pdf"):
            if fitz is not None:
                try:
                    doc = fitz.open(stream=f.getvalue(), filetype="pdf")
                    total += len(doc)
                except Exception:
                    total += 1
            else:
                total += 1
        else:
            total += 1
    return total

# --- ФАЙЛДАРДЫ ЖИ-ГЕ ДАЙЫНДАУ ФУНКЦИЯСЫ (PDF + JPG/PNG + HEIC/HEIF) ---
def process_uploaded_files_list(files_list):
    images_b64 = []
    for uploaded_file in files_list:
        file_bytes = uploaded_file.getvalue()
        if uploaded_file.name.lower().endswith(".pdf"):
            if fitz is None:
                raise RuntimeError(t("pdf_missing_lib"))
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

# --- ЖИ АРҚЫЛЫ БІР ОҚУШЫНЫҢ (1 НЕМЕСЕ КӨП БЕТТІ) ЖҰМЫСЫН ТЕКСЕРУ ---
def evaluate_student_work(client, files_list, max_score, lang_code):
    images_b64 = process_uploaded_files_list(files_list)
    total_pages = len(images_b64)
    
    if lang_code == "РУС":
        prompt_text = f"""
Ты — опытный учитель-эксперт, досконально знающий государственные стандарты образования Республики Казахстан и систему критериального оценивания (приказы №399, №125 и №348).
Перед тобой работа ОДНОГО ученика, состоящая из {total_pages} стр. Внимательно изучи ВСЕ страницы как единую работу. Определи все задания и подпункты на всех страницах и проверь каждый отдельно.

ПРАВИЛА ОФОРМЛЕНИЯ:
1. Используй ту же нумерацию/буквы, что и в работе ученика.
2. Кратко укажи тему, учебную цель или предметное умение каждого задания и поставь отметку:
   - 🟢 [Верно] — если ответ полностью правильный.
   - 🔴 [Ошибка] — если ответ неверный или задание не выполнено.
   - 🟡 [Частично] — если ответ верен частично.
3. Кратко и содержательно объясни причину каждой оценки на русском языке, избегая механических повторов одинаковых фраз.
4. Перед итоговым баллом напиши сильный, всесторонний педагогический вывод в МОТИВАЦИОННОМ стиле (2–4 предложения), подходящий для любого учебного предмета:
   - опирайся на реальный учебный процесс ученика: понимание понятий, логику рассуждений, применение знаний и предметных умений, аккуратность и самостоятельность выполнения заданий;
   - отметь сильные стороны и точки роста с уважением, поддержкой и верой в успех ученика;
   - каждый раз подбирай свежие, живые и разные формулировки, не повторяя штампы от работы к работе.
5. В самом конце обязательно напиши общий суммарный балл за все страницы в точном формате:
   Итоговый балл: X/{int(max_score)}
"""
        sys_msg = "Вы эксперт-педагог, проверяющий работы учащихся по стандартам образования РК на русском языке в поддерживающем, содержательном и мотивационном ключе."
    elif lang_code == "ENG":
        prompt_text = f"""
You are an experienced expert teacher well-versed in the State Educational Standards of the Republic of Kazakhstan and the criteria-based assessment system (Orders No. 399, No. 348, and No. 125).
You are presented with the work of ONE student consisting of {total_pages} page(s). Carefully examine ALL pages as a single unified work. Identify all tasks and sub-items across all pages and grade each one individually.

GRADING & FORMATTING RULES:
1. Keep the same numbering/lettering as written in the student's work.
2. Briefly state the topic, learning objective, or subject skill of each task and assign a status tag:
   - 🟢 [Correct] — if the answer is completely correct.
   - 🔴 [Incorrect] — if the answer is wrong or missing.
   - 🟡 [Partial] — if the answer is partially correct.
3. Briefly and clearly explain the reason for each grade in English, avoiding repetitive phrasing across items.
4. Right before the final score, write a strong, comprehensive pedagogical concluding remark in a MOTIVATIONAL style (2–4 sentences), suitable for any school subject:
   - reflect the student's actual learning process: conceptual grasp, reasoning and argumentation, application of knowledge and subject skills, attentiveness, and effort;
   - frame strengths and areas for improvement constructively, warmly, and encouragingly;
   - vary your wording and imagery each time so every student receives a fresh, authentic message.
5. At the very end, strictly write the combined total score across all pages in this exact format:
   Total score: X/{int(max_score)}
"""
        sys_msg = "You are an expert educator grading student works according to RK educational standards in English with a comprehensive, encouraging, and varied pedagogical voice."
    else:
        prompt_text = f"""
Сен — Қазақстан Республикасының орта білім беру стандарты мен критериалды бағалау жүйесін жеттік білетін тәжірибелі сарапшы-ұстазсың. №399, №125 және №348 бұйрықтардың талаптары мен дескрипторларды қатаң басшылыққа ал.
Алдыңда БІР оқушының {total_pages} беттен тұратын жазбаша жұмысы берілген. Барлық беттерді біртұтас жұмыс ретінде мұқият оқып шық. Барлық беттердегі тапсырмалар мен тармақтарды анықтап, жеке-жеке тексер.

ТАРМАҚТАРДЫ БЕЛГІЛЕУ ЕРЕЖЕСІ:
1. Жұмыста қалай жазылған болса, сол форматты қолдан: қазақша әріптер (а, ә, б, в, г) немесе латын әріптері (a, b, c, d).
2. Әрбір тапсырманың тақырыбын, оқу мақсатын немесе пәндік дағдысын қысқаша көрсетіп, сәйкес белгі қой:
   - 🟢 [Дұрыс] — жауап толық дұрыс болса.
   - 🔴 [Қате] — жауап қате немесе орындалмаған болса.
   - 🟡 [Жартылай] — жартылай дұрыс болса.
3. Әр бағалаудың себебін түсіндіргенде сөз саптауды бірсарынды қайталамай, әр тапсырманың оқу мақсаты мен мазмұнына сай нақты әрі түсінікті жаз.
4. Қорытынды балдың алдында **педагогикалық тілмен, оқу процесін жан-жақты қамтитын, кез келген пәнге сай әрі МОТИВАЦИЯЛЫҚ стильдегі** салмақты қорытынды сөз (2–4 сөйлем) жаз:
   - оқу процесінің қырларын (ұғымдарды меңгеру тереңдігі, ой жүйелілігі мен дәлелдеу, білімді тәжірибеде қолдану, тапсырмаға ұқыптылық пен ізденіс) тұтас қамты;
   - оқушының жетістігін лайықты бағалап, ал қателік жіберген тұстарын сүріну емес, өсу нүктесі ретінде көрсетіп, оқуға деген сенімі мен ынтасын көтер;
   - әр жұмыс сайын сөздер мен тіркестерді түрлендіріп, жаттанды немесе қайталанбалы сөздерге жол берме.
5. Соңында барлық беттер бойынша ортақ қорытынды балды міндетті түрде мына форматта жаз:
   Жиынтық балл: X/{int(max_score)}
"""
        sys_msg = "Сіз ҚР білім беру стандартына сай оқушы жұмыстарын тексеретін, педагогикалық шеберлігі жоғары, әр оқушыға әртүрлі сөзбен, жан-жақты әрі мотивациялық қорытынды жасайтын ұстазсыз."

    messages_content = [{"type": "text", "text": prompt_text}]
    for img_b64 in images_b64:
        messages_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
        })

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": messages_content}
        ],
        max_tokens=2500,
        temperature=0.4
    )
    
    full_ai_resp = response.choices[0].message.content
    full_ai_resp = re.sub(r'\[ОҚУШЫ_АТЫ\].*?\[/ОҚУШЫ_АТЫ\]', '', full_ai_resp).strip()
    
    extracted_score = 0.0
    score_match = re.search(r'(?:Жиынтық балл|Итоговый балл|Total score):\s*([\d\.]+)', full_ai_resp, re.IGNORECASE)
    if score_match:
        try:
            val = float(score_match.group(1))
            if val <= float(max_score):
                extracted_score = val
        except:
            pass
            
    return full_ai_resp, extracted_score

# --- АУТЕНТИФИКАЦИЯ ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "username" not in st.session_state:
    st.session_state.username = ""

if not st.session_state.authenticated:
    lang_col1, lang_col2 = st.columns([3, 1])
    with lang_col2:
        selected_login_lang = st.radio(
            t("lang_label"),
            ["ҚАЗ", "РУС", "ENG"],
            index=["ҚАЗ", "РУС", "ENG"].index(st.session_state.lang),
            horizontal=True,
            key="login_lang_selector"
        )
        if selected_login_lang != st.session_state.lang:
            st.session_state.lang = selected_login_lang
            st.rerun()

    st.title(t("login_title"))
    st.write(t("login_desc"))
    
    with st.form("login_form"):
        username_input = st.text_input(t("username"), placeholder=t("username_ph"))
        password_input = st.text_input(t("password"), type="password", placeholder=t("password_ph"))
        if st.form_submit_button(t("login_btn")):
            user = verify_user(username_input, password_input)
            if not user:
                secrets_passwords = st.secrets.get("passwords", {})
                clean_username = username_input.strip().lower()
                if clean_username in secrets_passwords and secrets_passwords[clean_username] == password_input:
                    user = {"username": clean_username, "full_name": clean_username.capitalize()}
            if user:
                st.session_state.authenticated = True
                st.session_state.username = user["username"]
                st.success(f"{t('welcome')}, {user.get('full_name', user['username'])}!")
                st.rerun()
            else:
                st.error(t("login_err"))
    st.stop()

# --- НЕГІЗГІ ҚОСЫМША ---
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

current_user = st.session_state.get("username", "teacher")
user_balance = get_user_credits(current_user)
price_per_credit = 100  
total_tenge = user_balance * price_per_credit

user_role = get_user_role(current_user)
user_default_subject = get_user_subject(current_user) or ""
is_admin = (user_role == "admin" or current_user.lower() in ["zoya", "admin"])

st.sidebar.title("SmartTest")
selected_sidebar_lang = st.sidebar.radio(
    t("lang_label"),
    ["ҚАЗ", "РУС", "ENG"],
    index=["ҚАЗ", "РУС", "ENG"].index(st.session_state.lang),
    horizontal=True,
    key="sidebar_lang_selector"
)
if selected_sidebar_lang != st.session_state.lang:
    st.session_state.lang = selected_sidebar_lang
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(f"👤 **{t('user_lbl')}:** {current_user}")
st.sidebar.metric(label=t("balance_lbl"), value=f"{user_balance} {t('credit_unit')}", delta=f"{total_tenge:,.0f} ₸")
st.sidebar.markdown("---")

menu_keys = ["menu_home", "menu_check", "menu_approve", "menu_results", "menu_stats", "menu_billing"]
if is_admin:
    menu_keys.append("menu_security")

selected_menu_key = st.sidebar.selectbox(
    t("section_lbl"),
    menu_keys,
    format_func=lambda k: t(k)
)

if st.sidebar.button(t("logout_btn")):
    st.session_state.authenticated = False
    st.session_state.username = ""
    st.rerun()

st.title(t("app_title"))

if selected_menu_key == "menu_home":
    st.write(t("home_desc"))
    c1, c2 = st.columns(2)
    c1.metric(t("pending_metric"), len(get_pending_results()))
    c2.metric(t("approved_metric"), len(get_approved_results()))

elif selected_menu_key == "menu_check":
    st.subheader(t("check_sub"))
    if fitz is None:
        st.warning(t("pdf_missing_lib"))
    
    # --- 3 ЖҮКТЕУ РЕЖИМІН ТАҢДАУ ---
    upload_mode = st.radio(
        t("mode_lbl"),
        ["multi_students", "single_student", "camera_mode"],
        format_func=lambda m: (
            t("mode_multi_students") if m == "multi_students" 
            else (t("mode_single_student") if m == "single_student" else t("mode_camera"))
        )
    )

    max_score = st.number_input(
        t("max_score_lbl"), 
        min_value=1.0, 
        max_value=50.0, 
        value=10.0, 
        step=1.0
    )

    # =========================================================================
    # РЕЖИМ 3: КАМЕРАМЕН БІРНЕШЕ БЕТТІ ҚАТАРЫНАН СУРЕТКЕ ТҮСІРУ (1 КРЕДИТ)
    # =========================================================================
    if upload_mode == "camera_mode":
        if "camera_pages" not in st.session_state:
            st.session_state.camera_pages = []
        if "cam_widget_counter" not in st.session_state:
            st.session_state.cam_widget_counter = 0

        cam_photo = st.camera_input(
            t("cam_widget_lbl"), 
            key=f"cam_input_{st.session_state.cam_widget_counter}"
        )

        cam_btn_col1, cam_btn_col2 = st.columns(2)
        with cam_btn_col1:
            if st.button(t("cam_add_btn"), use_container_width=True):
                if cam_photo is not None:
                    st.session_state.camera_pages.append(cam_photo)
                    st.session_state.cam_widget_counter += 1
                    st.success(t("cam_added_ok").format(len(st.session_state.camera_pages)))
                    st.rerun()
                else:
                    st.warning(t("cam_no_photo_warn"))

        with cam_btn_col2:
            if st.button(t("cam_clear_btn"), use_container_width=True):
                st.session_state.camera_pages = []
                st.session_state.cam_ai_result = ""
                st.session_state.cam_exp_text = ""
                st.session_state.cam_score = 0.0
                st.session_state.cam_widget_counter += 1
                st.rerun()

        if st.session_state.camera_pages:
            st.success(t("cam_pages_count").format(len(st.session_state.camera_pages)))
            col_img, col_form = st.columns([1, 1])
            with col_img:
                for p_idx, f in enumerate(st.session_state.camera_pages):
                    st.markdown(f"**{t('page_caption').format(p_idx+1, f.name)}**")
                    try:
                        image = Image.open(f)
                        st.image(image, use_container_width=True)
                    except Exception:
                        st.error(t("img_err"))

            with col_form:
                st_code = st.text_input(
                    t("student_name_lbl"),
                    placeholder=t("student_name_ph"),
                    key="cam_st_name"
                )

                if "cam_ai_result" not in st.session_state:
                    st.session_state.cam_ai_result = ""

                if st.button(t("multi_page_check_btn"), key="btn_check_cam"):
                    current_balance = get_user_credits(current_user)
                    if not is_admin and current_balance < 1.0:
                        st.error(t("no_credits_err"))
                    else:
                        with st.spinner(t("ai_spinner")):
                            try:
                                full_ai_resp, extracted_score = evaluate_student_work(
                                    client, st.session_state.camera_pages, max_score, st.session_state.lang
                                )
                                st.session_state.cam_ai_result = full_ai_resp
                                st.session_state.cam_exp_text = full_ai_resp
                                st.session_state.cam_score = extracted_score
                                if not is_admin:
                                    deduct_credit(current_user, amount=1.0)
                                st.success(t("single_check_ok"))
                                st.rerun()
                            except Exception as e:
                                st.error(f"Қате: {e}")

                current_ai_text = st.session_state.get("cam_ai_result", "")
                if current_ai_text:
                    st.markdown(t("analysis_res_hdr"))
                    lines = current_ai_text.split('\n')
                    for line in lines:
                        if any(k in line for k in ['🟢', '[Дұрыс]', '[Верно]', '[Correct]', 'дұрыс', 'верно', 'correct']):
                            st.markdown(f"<div class='correct-card'>{line}</div>", unsafe_allow_html=True)
                        elif any(k in line for k in ['🔴', '[Қате]', '[Ошибка]', '[Incorrect]', 'қате', 'ошибка', 'incorrect']):
                            st.markdown(f"<div class='incorrect-card'>{line}</div>", unsafe_allow_html=True)
                        elif any(k in line for k in ['🟡', '[Жартылай]', '[Частично]', '[Partial]', 'жартылай', 'частично', 'partial']):
                            st.markdown(f"<div class='warning-card'>{line}</div>", unsafe_allow_html=True)
                        elif line.strip():
                            st.write(line)
                else:
                    st.info(t("check_hint"))

                prop_score = st.number_input(
                    t("score_input_lbl"),
                    min_value=0.0,
                    max_value=float(max_score),
                    value=st.session_state.get("cam_score", 0.0),
                    step=0.5,
                    key="cam_score"
                )

                if "cam_exp_text" not in st.session_state:
                    st.session_state.cam_exp_text = current_ai_text

                explanation = st.text_area(
                    t("feedback_lbl"),
                    value=st.session_state.cam_exp_text,
                    height=250,
                    key="cam_exp_text"
                )

                if st.button(t("save_btn"), key="save_cam_btn"):
                    current_st_name = st_code.strip()
                    if current_st_name:
                        pages_num = len(st.session_state.camera_pages)
                        full_feedback = f"Кері байланыс (Камера, {pages_num} бет):\n{explanation.strip()}"
                        save_pending_result(
                            current_st_name,
                            f"[Камера] Оқушы жұмысы ({pages_num} бет)",
                            "ҚР стандарттары бойынша критериалды бағалау",
                            float(prop_score),
                            float(max_score),
                            full_feedback
                        )
                        st.success(t("save_ok").format(current_st_name))
                    else:
                        st.error(t("save_name_err"))
        else:
            st.info(t("cam_empty_info"))

    # =========================================================================
    # РЕЖИМ 1 ЖӘНЕ РЕЖИМ 2: ФАЙЛ ЖҮКТЕУ (JPG, PNG, HEIC, PDF)
    # =========================================================================
    else:
        uploader_prompt = t("upload_lbl") if upload_mode == "multi_students" else t("upload_single_lbl")
        uploaded_files = st.file_uploader(
            uploader_prompt, 
            type=["jpg", "jpeg", "png", "pdf", "heic", "heif"], 
            accept_multiple_files=True
        )
        
        if uploaded_files:
            # --- РЕЖИМ 2: БАРЛЫҚ ЖҮКТЕЛГЕН СУРЕТТЕР / БЕТТЕР = 1 ОҚУШЫ (1 КРЕДИТ) ---
            if upload_mode == "single_student":
                total_p = count_pages_in_files(uploaded_files)
                st.success(t("uploaded_single_ok").format(len(uploaded_files), total_p))
                files_sig = "_".join([f.name for f in uploaded_files])
                
                col_img, col_form = st.columns([1, 1])
                with col_img:
                    for p_idx, f in enumerate(uploaded_files):
                        st.markdown(f"**{t('page_caption').format(p_idx+1, f.name)}**")
                        if f.name.lower().endswith('.pdf'):
                            p_cnt = count_pages_in_files([f])
                            st.info(t("pdf_loaded").format(p_cnt))
                        else:
                            try:
                                image = Image.open(f)
                                st.image(image, use_container_width=True)
                            except Exception:
                                st.error(t("img_err"))
                                
                with col_form:
                    single_name_key = f"single_st_name_{files_sig}"
                    single_ai_key = f"single_st_ai_{files_sig}"
                    single_score_key = f"single_st_score_{files_sig}"
                    single_exp_key = f"single_st_exp_{files_sig}"
                    
                    st_code = st.text_input(
                        t("student_name_lbl"),
                        placeholder=t("student_name_ph"),
                        key=single_name_key
                    )
                    
                    if single_ai_key not in st.session_state:
                        st.session_state[single_ai_key] = ""
                        
                    if st.button(t("multi_page_check_btn"), key=f"btn_multi_page_{files_sig}"):
                        current_balance = get_user_credits(current_user)
                        if not is_admin and current_balance < 1.0:
                            st.error(t("no_credits_err"))
                        else:
                            with st.spinner(t("ai_spinner")):
                                try:
                                    full_ai_resp, extracted_score = evaluate_student_work(client, uploaded_files, max_score, st.session_state.lang)
                                    st.session_state[single_ai_key] = full_ai_resp
                                    st.session_state[single_exp_key] = full_ai_resp
                                    st.session_state[single_score_key] = extracted_score
                                    if not is_admin:
                                        deduct_credit(current_user, amount=1.0)
                                    st.success(t("single_check_ok"))
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Қате: {e}")
                                    
                    current_ai_text = st.session_state.get(single_ai_key, "")
                    if current_ai_text:
                        st.markdown(t("analysis_res_hdr"))
                        lines = current_ai_text.split('\n')
                        for line in lines:
                            if any(k in line for k in ['🟢', '[Дұрыс]', '[Верно]', '[Correct]', 'дұрыс', 'верно', 'correct']):
                                st.markdown(f"<div class='correct-card'>{line}</div>", unsafe_allow_html=True)
                            elif any(k in line for k in ['🔴', '[Қате]', '[Ошибка]', '[Incorrect]', 'қате', 'ошибка', 'incorrect']):
                                st.markdown(f"<div class='incorrect-card'>{line}</div>", unsafe_allow_html=True)
                            elif any(k in line for k in ['🟡', '[Жартылай]', '[Частично]', '[Partial]', 'жартылай', 'частично', 'partial']):
                                st.markdown(f"<div class='warning-card'>{line}</div>", unsafe_allow_html=True)
                            elif line.strip():
                                st.write(line)
                    else:
                        st.info(t("check_hint"))
                        
                    prop_score = st.number_input(
                        t("score_input_lbl"),
                        min_value=0.0,
                        max_value=float(max_score),
                        value=st.session_state.get(single_score_key, 0.0),
                        step=0.5,
                        key=single_score_key
                    )
                    
                    if single_exp_key not in st.session_state:
                        st.session_state[single_exp_key] = current_ai_text
                        
                    explanation = st.text_area(
                        t("feedback_lbl"),
                        value=st.session_state[single_exp_key],
                        height=250,
                        key=single_exp_key
                    )
                    
                    if st.button(t("save_btn"), key=f"save_single_{files_sig}"):
                        current_st_name = st_code.strip()
                        if current_st_name:
                            full_feedback = f"Кері байланыс ({total_p} бет):\n{explanation.strip()}"
                            save_pending_result(
                                current_st_name,
                                f"[Автоматты тексеру] Оқушы жұмысы ({total_p} бет)",
                                "ҚР стандарттары бойынша критериалды бағалау",
                                float(prop_score),
                                float(max_score),
                                full_feedback
                            )
                            st.success(t("save_ok").format(current_st_name))
                        else:
                            st.error(t("save_name_err"))

            # --- РЕЖИМ 1: ӘР ФАЙЛ (КӨПБЕТТІ PDF НЕМЕСЕ СУРЕТ) = 1 ЖЕКЕ ОҚУШЫ ---
            else:
                st.success(t("uploaded_ok").format(len(uploaded_files)))
                
                bulk_col1, bulk_col2 = st.columns(2)
                with bulk_col1:
                    if st.button(t("bulk_check_btn"), use_container_width=True):
                        unchecked_indices = [
                            i for i, f in enumerate(uploaded_files) 
                            if not st.session_state.get(f"ai_result_{i}_{f.name}", "")
                        ]
                        if not unchecked_indices:
                            st.info(t("all_checked_info"))
                        else:
                            current_balance = get_user_credits(current_user)
                            needed_credits = float(len(unchecked_indices))
                            if not is_admin and current_balance < needed_credits:
                                st.error(t("no_credits_bulk").format(len(unchecked_indices), int(needed_credits), int(current_balance)))
                            else:
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                for step_num, idx in enumerate(unchecked_indices):
                                    f = uploaded_files[idx]
                                    st_name_preview = st.session_state.get(f"name_input_{idx}_{f.name}", f"{t('work_lbl')}{idx+1}").strip() or f"{t('work_lbl')}{idx+1}"
                                    status_text.info(t("checking_progress").format(step_num+1, len(unchecked_indices), st_name_preview))
                                    try:
                                        ai_resp, sc = evaluate_student_work(client, [f], max_score, st.session_state.lang)
                                        st.session_state[f"ai_result_{idx}_{f.name}"] = ai_resp
                                        st.session_state[f"exp_text_{idx}_{f.name}"] = ai_resp
                                        st.session_state[f"score_{idx}_{f.name}"] = sc
                                        if not is_admin:
                                            deduct_credit(current_user, amount=1.0)
                                    except Exception as e:
                                        st.error(f"Қате ({f.name}): {e}")
                                    progress_bar.progress((step_num + 1) / len(unchecked_indices))
                                status_text.success(t("bulk_check_done"))
                                st.rerun()

                with bulk_col2:
                    if st.button(t("bulk_save_btn"), use_container_width=True):
                        missing_names = []
                        saved_count = 0
                        for idx, f in enumerate(uploaded_files):
                            st_name = st.session_state.get(f"name_input_{idx}_{f.name}", "").strip()
                            if not st_name:
                                missing_names.append(f"{t('work_lbl')}{idx+1} ({f.name})")
                        
                        if missing_names:
                            st.error(t("missing_names_err").format(', '.join(missing_names)))
                        else:
                            for idx, f in enumerate(uploaded_files):
                                st_name = st.session_state.get(f"name_input_{idx}_{f.name}", "").strip()
                                sc = float(st.session_state.get(f"score_{idx}_{f.name}", 0.0))
                                exp_txt = st.session_state.get(f"exp_text_{idx}_{f.name}", "").strip()
                                full_feedback = f"Кері байланыс:\n{exp_txt}"
                                save_pending_result(
                                    st_name,
                                    "[Автоматты тексеру] Оқушы жұмысы",
                                    "ҚР стандарттары бойынша критериалды бағалау",
                                    sc,
                                    float(max_score),
                                    full_feedback
                                )
                                saved_count += 1
                            st.success(t("bulk_save_done").format(saved_count))

                st.markdown("---")

                for idx, uploaded_file in enumerate(uploaded_files):
                    input_key = f"name_input_{idx}_{uploaded_file.name}"
                    current_display_name = st.session_state.get(input_key, "").strip()
                    ai_res_key = f"ai_result_{idx}_{uploaded_file.name}"
                    is_checked = bool(st.session_state.get(ai_res_key, ""))
                    status_badge = t("status_checked") if is_checked else t("status_pending")
                    p_cnt = count_pages_in_files([uploaded_file])
                    page_tag = f" ({p_cnt} бет)" if p_cnt > 1 else ""
                    
                    expander_title = f"📁 {t('work_lbl')}{idx+1}: {current_display_name if current_display_name else uploaded_file.name}{page_tag} — [{status_badge}]"
                    
                    with st.expander(expander_title, expanded=True):
                        col_img, col_form = st.columns([1, 1])
                        with col_img:
                            if uploaded_file.name.lower().endswith('.pdf'):
                                st.info(t("pdf_loaded").format(p_cnt))
                            else:
                                try:
                                    image = Image.open(uploaded_file)
                                    st.image(image, caption=uploaded_file.name, use_container_width=True)
                                except Exception:
                                    st.error(t("img_err"))
                        with col_form:
                            st_code = st.text_input(
                                t("student_name_lbl"), 
                                placeholder=t("student_name_ph"), 
                                key=input_key
                            )
                            
                            if ai_res_key not in st.session_state:
                                st.session_state[ai_res_key] = ""

                            if st.button(t("single_check_btn"), key=f"ai_btn_{idx}_{uploaded_file.name}"):
                                current_balance = get_user_credits(current_user)
                                
                                if not is_admin and current_balance < 1.0:
                                    st.error(t("no_credits_err"))
                                else:
                                    with st.spinner(t("ai_spinner")):
                                        try:
                                            full_ai_resp, extracted_score = evaluate_student_work(client, [uploaded_file], max_score, st.session_state.lang)
                                            st.session_state[ai_res_key] = full_ai_resp
                                            st.session_state[f"exp_text_{idx}_{uploaded_file.name}"] = full_ai_resp
                                            st.session_state[f"score_{idx}_{uploaded_file.name}"] = extracted_score
                                            
                                            if not is_admin:
                                                deduct_credit(current_user, amount=1.0)
                                            st.success(t("single_check_ok"))
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Қате: {e}")

                            current_ai_text = st.session_state.get(ai_res_key, "")
                            
                            if current_ai_text:
                                st.markdown(t("analysis_res_hdr"))
                                lines = current_ai_text.split('\n')
                                for line in lines:
                                    if any(k in line for k in ['🟢', '[Дұрыс]', '[Верно]', '[Correct]', 'дұрыс', 'верно', 'correct']):
                                        st.markdown(f"<div class='correct-card'>{line}</div>", unsafe_allow_html=True)
                                    elif any(k in line for k in ['🔴', '[Қате]', '[Ошибка]', '[Incorrect]', 'қате', 'ошибка', 'incorrect']):
                                        st.markdown(f"<div class='incorrect-card'>{line}</div>", unsafe_allow_html=True)
                                    elif any(k in line for k in ['🟡', '[Жартылай]', '[Частично]', '[Partial]', 'жартылай', 'частично', 'partial']):
                                        st.markdown(f"<div class='warning-card'>{line}</div>", unsafe_allow_html=True)
                                    elif line.strip():
                                        st.write(line)
                            else:
                                st.info(t("check_hint"))

                            score_key = f"score_{idx}_{uploaded_file.name}"
                            prop_score = st.number_input(
                                t("score_input_lbl"), 
                                min_value=0.0, 
                                max_value=float(max_score), 
                                value=st.session_state.get(score_key, 0.0), 
                                step=0.5, 
                                key=score_key
                            )
                            
                            exp_key = f"exp_text_{idx}_{uploaded_file.name}"
                            if exp_key not in st.session_state:
                                st.session_state[exp_key] = current_ai_text

                            explanation = st.text_area(
                                t("feedback_lbl"), 
                                value=st.session_state[exp_key], 
                                height=250, 
                                key=exp_key
                            )
                            
                            if st.button(t("save_btn"), key=f"save_btn_{idx}_{uploaded_file.name}"):
                                current_st_name = st_code.strip()
                                if current_st_name:
                                    full_feedback = f"Кері байланыс:\n{explanation.strip()}"
                                    save_pending_result(
                                        current_st_name, 
                                        "[Автоматты тексеру] Оқушы жұмысы", 
                                        "ҚР стандарттары бойынша критериалды бағалау", 
                                        float(prop_score), 
                                        float(max_score), 
                                        full_feedback
                                    )
                                    st.success(t("save_ok").format(current_st_name))
                                else:
                                    st.error(t("save_name_err"))

elif selected_menu_key == "menu_approve":
    st.subheader(t("approve_sub"))
    pending = get_pending_results()
    if not pending:
        st.info(t("no_pending"))
    else:
        st.write(f"{t('pending_count')} **{len(pending)}**")
        if st.button(t("bulk_approve_btn")):
            for item in pending:
                sc_val = float(st.session_state.get("app_" + str(item["id"]), item["proposed_score"]))
                com_val = st.session_state.get("com_" + str(item["id"]), "")
                approve_result(item["id"], sc_val, current_user, com_val)
            st.success(t("bulk_approve_ok"))
            st.rerun()
            
        st.markdown("---")
        for item in pending:
            with st.expander(f"{item['student_code']} — {item['proposed_score']} балл", expanded=True):
                score = st.number_input(t("approve_score_lbl"), value=float(item['proposed_score']), key="app_" + str(item["id"]))
                comment = st.text_area(t("comment_lbl"), placeholder=t("comment_ph"), key="com_" + str(item["id"]))
                if st.button(t("approve_btn"), key="btn_" + str(item["id"])):
                    approve_result(item["id"], score, current_user, comment)
                    st.rerun()

elif selected_menu_key == "menu_results":
    st.subheader(t("results_sub"))
    rows = get_approved_results()
    if not rows:
        st.info(t("no_results"))
    else:
        df_res = pd.DataFrame(rows)
        st.dataframe(df_res)

elif selected_menu_key == "menu_stats":
    st.subheader(t("stats_sub"))
    rows = get_approved_results()
    if not rows:
        st.info(t("no_stats"))
    else:
        df_stat = pd.DataFrame(rows)
        
        if all(isinstance(c, int) for c in df_stat.columns):
            num_cols = []
            str_cols = []
            for c in df_stat.columns:
                converted = pd.to_numeric(df_stat[c], errors='coerce')
                if converted.notna().sum() == len(df_stat) and c != 0:
                    num_cols.append(c)
                else:
                    str_cols.append(c)
            
            student_col = 1 if 1 in df_stat.columns else (str_cols[0] if str_cols else 0)
            
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
                
            fb_col = max(str_cols, key=lambda c: df_stat[c].astype(str).str.len().mean()) if str_cols else None
            
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
            score_col = next((c for c in ['teacher_score', 'final_score', 'approved_score', 'score', 'proposed_score'] if c in df_stat.columns), None)
            student_col = next((c for c in ['student_code', 'student_name', 'student'] if c in df_stat.columns), None)
            max_col_name = 'max_score' if 'max_score' in df_stat.columns else None
            fb_col_name = next((c for c in ['feedback', 'explanation', 'rubric', 'teacher_comment'] if c in df_stat.columns), None)

            rename_dict_map = {}
            if student_col:
                rename_dict_map[student_col] = "Оқушы аты-жөні"
                student_col = "Оқушы аты-жөні"
            if score_col:
                rename_dict_map[score_col] = "Бекітілген ұпай"
                score_col = "Бекітілген ұпай"
            if max_col_name:
                rename_dict_map[max_col_name] = "Максималды балл"
                max_col_name = "Максималды балл"
            if fb_col_name:
                rename_dict_map[fb_col_name] = "Кері байланыс"
                fb_col_name = "Кері байланыс"
            df_stat = df_stat.rename(columns=rename_dict_map)

        if not score_col or score_col not in df_stat.columns:
            st.error("Кестеден ұпай бағаны табылмады.")
            st.stop()

        df_stat[score_col] = pd.to_numeric(df_stat[score_col], errors='coerce').fillna(0.0)
        
        total_students = len(df_stat)
        avg_score = df_stat[score_col].mean()
        pct_col_name = "Пайыздық көрсеткіш (%)"
        
        if max_col_name and max_col_name in df_stat.columns:
            df_stat[max_col_name] = pd.to_numeric(df_stat[max_col_name], errors='coerce').fillna(10.0)
            max_possible = df_stat[max_col_name].mean()
            df_stat[pct_col_name] = (df_stat[score_col] / df_stat[max_col_name].replace(0, 10.0)) * 100
        else:
            max_possible = 10.0
            df_stat[pct_col_name] = (df_stat[score_col] / max_possible) * 100

        passing_count = len(df_stat[df_stat[pct_col_name] >= 40])
        quality_count = len(df_stat[df_stat[pct_col_name] >= 65])
            
        passing_rate = (passing_count / total_students) * 100
        quality_rate = (quality_count / total_students) * 100

        col1, col2, col3, col4 = st.columns(4)
        col1.metric(t("m_students"), f"{total_students}")
        col2.metric(t("m_avg"), f"{avg_score:.1f} / {max_possible:.0f}")
        col3.metric(t("m_pass"), f"{passing_rate:.1f}%")
        col4.metric(t("m_qual"), f"{quality_rate:.1f}%")

        st.markdown("---")
        st.markdown(t("chart_hdr"))
        if student_col and student_col in df_stat.columns:
            df_stat[student_col] = df_stat[student_col].astype(str)
            if df_stat[student_col].duplicated().any():
                df_stat[student_col] = df_stat[student_col] + " (" + (df_stat.groupby(student_col).cumcount() + 1).astype(str) + ")"
            st.bar_chart(df_stat.set_index(student_col)[score_col])
            
            display_cols = [student_col, score_col]
            if max_col_name:
                display_cols.append(max_col_name)
            display_cols.append(pct_col_name)
            st.dataframe(df_stat[display_cols], use_container_width=True)
        else:
            st.bar_chart(df_stat[score_col])

        st.markdown("---")
        st.markdown(t("ai_ped_hdr"))
        st.write(t("ai_ped_desc"))

        # --- ПӘН, СЫНЫП ЖӘНЕ БАҒАЛАУ ТҮРІН ТАҢДАУ ӨРІСТЕРІ ---
        meta_c1, meta_c2, meta_c3 = st.columns(3)
        with meta_c1:
            subject_name = st.text_input(
                t("subj_lbl"),
                value=user_default_subject,
                placeholder=t("subj_ph"),
                key="stats_subject_name"
            )
        with meta_c2:
            class_name = st.text_input(
                t("class_lbl"),
                placeholder=t("class_ph"),
                key="stats_class_name"
            )
        with meta_c3:
            assess_type = st.selectbox(
                t("assess_type_lbl"),
                t("assess_options"),
                key="stats_assess_type"
            )

        if "class_ai_analysis" not in st.session_state:
            st.session_state.class_ai_analysis = ""

        if st.button(t("ai_ped_btn")):
            with st.spinner(t("ai_ped_spin")):
                try:
                    feedback_records = []
                    for idx_r, r in df_stat.iterrows():
                        st_name = r.get(student_col, f'Оқушы-{idx_r+1}') if student_col else f'Оқушы-{idx_r+1}'
                        sc = r.get(score_col, 0)
                        mx = r.get(max_col_name, max_possible) if max_col_name else max_possible
                        fb = r.get(fb_col_name, '') if fb_col_name else ''
                        feedback_records.append(f"Оқушы: {st_name} | Балл: {sc}/{mx}\nТалдауы:\n{fb}\n---")
                    
                    combined_data = "\n".join(feedback_records)

                    clean_subj = subject_name.strip()
                    clean_class = class_name.strip()

                    if st.session_state.lang == "РУС":
                        subj_disp = clean_subj if clean_subj else "Не указан"
                        class_disp = clean_class if clean_class else "Не указан"
                        analysis_prompt = f"""
Ты — опытный методист-учитель школ Республики Казахстан, составляющий аналитическую справку по итогам СОР и СОЧ.
На основе статистики и проверенных работ учащихся напиши глубокий, всесторонний педагогический анализ на РУССКОМ языке в ПОДДЕРЖИВАЮЩЕМ и МОТИВАЦИОННОМ стиле, избегая шаблонных клише и повторяющихся формулировок.

ОБЩИЕ СВЕДЕНИЯ:
- Предмет: {subj_disp}
- Класс: {class_disp}
- Вид оценивания: {assess_type}

СТАТИСТИКА КЛАССА:
- Всего учащихся: {total_students}
- Средний балл: {avg_score:.1f} / {max_possible:.0f}
- Успеваемость: {passing_rate:.1f}%
- Качество знаний: {quality_rate:.1f}%

РЕЗУЛЬТАТЫ И ОШИБКИ УЧАЩИХСЯ:
{combined_data[:12000]}

ТРЕБУЕМАЯ СТРУКТУРА (В начале документа обязательно укажи заголовок с предметом, классом и видом оценивания — {assess_type}):
**Аналитическая справка по итогам {assess_type} по предмету «{subj_disp}» ({class_disp} класс)**

1. **Достигнутые цели обучения:** Темы, понятия, навыки и цели обучения, успешно освоенные учащимися (🟢), с опорой на понимание материала, логику и самостоятельность.
2. **Цели обучения, вызвавшие затруднения:** Учебные цели и умения, где учащиеся встретили трудности (🔴 и 🟡), с анализом причин ошибок и восприятием их как точек роста.
3. **Рекомендации по коррекционной работе и мотивационный вывод:** Конкретные методические шаги для развития предметных умений и ободряющий, вдохновляющий педагогический итог о потенциале {class_disp} класса и движении вперед.
"""
                        ped_sys = "Вы эксперт-методист образования РК, составляющий всесторонний, живой и мотивационный педагогический анализ результатов обучения на русском языке без шаблонных повторов."
                    elif st.session_state.lang == "ENG":
                        subj_disp = clean_subj if clean_subj else "Not specified"
                        class_disp = clean_class if clean_class else "Not specified"
                        analysis_prompt = f"""
You are an experienced educational methodologist in the Republic of Kazakhstan preparing a comprehensive analytical summary of BJB and TJB (summative assessment) results.
Based on the class statistics and graded student works below, write a thorough pedagogical analysis in ENGLISH using a constructive, encouraging, and MOTIVATIONAL tone, varying your phrasing so it never sounds repetitive or formulaic.

GENERAL INFORMATION:
- Subject: {subj_disp}
- Class / Grade: {class_disp}
- Assessment Type: {assess_type}

CLASS STATISTICS:
- Total students: {total_students}
- Average score: {avg_score:.1f} / {max_possible:.0f}
- Passing rate: {passing_rate:.1f}%
- Quality rate: {quality_rate:.1f}%

STUDENT RESULTS & ERRORS:
{combined_data[:12000]}

REQUIRED STRUCTURE (Start the report with a clear header showing the subject, class, and assessment type — {assess_type}):
**Analytical Report on {assess_type} Results in {subj_disp} ({class_disp})**

1. **Achieved Learning Objectives:** Concepts, topics, reasoning skills, and learning objectives successfully mastered by students (🟢).
2. **Challenging Learning Objectives:** Learning objectives and skills where students faced difficulties (🔴 and 🟡), explaining why gaps occurred and framing them as growth opportunities.
3. **Corrective Recommendations & Motivational Conclusion:** Practical teaching steps to strengthen learning and an uplifting, motivating pedagogical closing highlighting the potential of {class_disp} and forward momentum.
"""
                        ped_sys = "You are an RK educational methodologist writing comprehensive, encouraging, and varied motivational pedagogical analyses in English."
                    else:
                        subj_disp = clean_subj if clean_subj else "Көрсетілмеген"
                        class_disp = clean_class if clean_class else "Көрсетілмеген"
                        analysis_prompt = f"""
Сен — Қазақстан Республикасы мектептеріндегі БЖБ және ТЖБ қорытындылары бойынша жан-жақты педагогикалық талдау дайындайтын тәжірибелі әдіскер-ұстазсың.
Төмендегі сынып оқушыларының тексерілген жұмыстарының нәтижелері мен статистикасына сүйене отырып, **педагогикалық тілмен**, **оқу процесін тұтас қамтитын**, **жігерлендіретін МОТИВАЦИЯЛЫҚ стильде** және **әр жолы әртүрлі, жаттанды емес, бай сөздермен** талдау жаз.

ЖАЛПЫ МӘЛІМЕТТЕР:
- Пән атауы: {subj_disp}
- Сынып: {class_disp}
- Бағалау түрі: {assess_type}

СЫНЫП СТАТИСТИКАСЫ:
- Барлық оқушы саны: {total_students}
- Орташа балл: {avg_score:.1f} / {max_possible:.0f}
- Үлгерім пайызы: {passing_rate:.1f}%
- Білім сапасы: {quality_rate:.1f}%

ОҚУШЫЛАРДЫҢ ЖҰМЫС НӘТИЖЕЛЕРІ МЕН ҚАТЕЛЕРІ:
{combined_data[:12000]}

ТАЛАП ЕТІЛЕТІН ҚҰРЫЛЫМ (Талдаудың ең басында пән атауын, сыныпты және бағалау түрін — {assess_type} міндетті түрде ресми тақырып ретінде көрсет):
**«{subj_disp}» пәні бойынша {class_disp} сыныптың {assess_type} қорытындысына педагогикалық талдау**

1. **Қол жеткізген оқу мақсаттары:** Оқу процесінде {class_disp} сынып оқушыларының (🟢 белгіленген) сәтті меңгерген ұғымдары, тақырыптары, ойлау жүйелілігі мен пәндік дағдылары.
2. **Қиындық туғызған оқу мақсаттары:** Оқушыларға әзірге күрделілік туғызған (🔴 және 🟡 белгіленген) мақсаттар мен дағдылар — қателіктердің себебін талдап, оларды сыныптың алға жылжуына бағытталған өсу нүктесі ретінде көрсет.
3. **Түзету (коррекциялық) жұмыстары және мотивациялық қорытынды:** Оқу нәтижесін нығайтуға арналған нақты әдістемелік қадамдар және {class_disp} сынып оқушыларының ізденісі мен мүмкіндігіне сенім білдіретін, оқуға ынталандыратын, әсерлі педагогикалық қорытынды сөз. Әр талдауда сөз саптауды түрлендіріп, бірсарынды клишелерді қайталама.
"""
                        ped_sys = "Сіз ҚР білім беру стандарты бойынша оқу процесін жан-жақты қамтитын, мотивациялық стильдегі, әр жолы әртүрлі әрі мазмұнды педагогикалық талдау жасайтын әдіскерсіз."

                    resp = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": ped_sys},
                            {"role": "user", "content": analysis_prompt}
                        ],
                        max_tokens=1800,
                        temperature=0.4
                    )
                    st.session_state.class_ai_analysis = resp.choices[0].message.content
                except Exception as e:
                    st.error(f"Қате: {e}")

        if st.session_state.class_ai_analysis:
            st.markdown(f"<div class='analysis-box'>{st.session_state.class_ai_analysis}</div>", unsafe_allow_html=True)
            st.text_area(
                t("copy_area_lbl"),
                value=st.session_state.class_ai_analysis,
                height=260
            )

        st.markdown("---")
        st.markdown(t("export_hdr"))
        
        export_cols = []
        if student_col and student_col in df_stat.columns:
            export_cols.append(student_col)
        if score_col and score_col in df_stat.columns:
            export_cols.append(score_col)
        if max_col_name and max_col_name in df_stat.columns:
            export_cols.append(max_col_name)
        if pct_col_name in df_stat.columns:
            export_cols.append(pct_col_name)
        if fb_col_name and fb_col_name in df_stat.columns:
            export_cols.append(fb_col_name)

        df_export_students = df_stat[export_cols].copy() if export_cols else df_stat.copy()
        df_export_students[pct_col_name] = df_export_students[pct_col_name].round(1)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_export_students.to_excel(writer, index=False, sheet_name='Оқушылар_нәтижесі')
            
            summary_df = pd.DataFrame({
                "Көрсеткіш": [
                    "Пән атауы",
                    "Сынып",
                    "Бағалау түрі",
                    "Оқушы саны", 
                    "Орташа балл", 
                    "Үлгерім пайызы (%)", 
                    "Білім сапасы (%)", 
                    "Педагогикалық талдау"
                ],
                "Мәні": [
                    subject_name.strip() if subject_name.strip() else "Көрсетілмеген",
                    class_name.strip() if class_name.strip() else "Көрсетілмеген",
                    assess_type,
                    total_students, 
                    round(avg_score, 1), 
                    round(passing_rate, 1), 
                    round(quality_rate, 1),
                    st.session_state.class_ai_analysis if st.session_state.class_ai_analysis else "Талдау жасалмаған"
                ]
            })
            summary_df.to_excel(writer, index=False, sheet_name='Қорытынды_анализ')
            
        excel_data = output.getvalue()

        safe_subj = re.sub(r'[^\w\-]', '_', subject_name.strip()) if subject_name.strip() else ""
        safe_class = re.sub(r'[^\w\-]', '_', class_name.strip()) if class_name.strip() else ""
        safe_type = re.sub(r'[^\w\-]', '_', assess_type.strip())
        file_parts = [p for p in ["SmartTest", safe_subj, safe_class, safe_type, "талдауы"] if p]
        excel_filename = "_".join(file_parts) + ".xlsx"

        st.download_button(
            label=t("excel_btn"),
            data=excel_data,
            file_name=excel_filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

elif selected_menu_key == "menu_billing":
    st.subheader(t("billing_sub"))
    st.write(t("billing_desc"))
    
    credits_to_buy = st.number_input(t("credits_buy_lbl"), min_value=1, max_value=1000, value=10, step=1)
    amount = credits_to_buy * 100
    
    st.markdown(f"**{t('total_pay_lbl')}** <span style='color: #10b981; font-size: 20px; font-weight: bold;'>{amount:,.0f} ₸</span>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.info(t("pay_steps"))
    
    qr_col1, qr_col2 = st.columns(2)
    with qr_col1:
        st.write("### 🟡 Kaspi QR")
        if os.path.exists("kaspi_qr_ИЗС.png"):
            st.image("kaspi_qr_ИЗС.png", caption="SmartTest — Kaspi Pay QR", width=260)
        else:
            st.warning("⚠️ `kaspi_qr_ИЗС.png` файлы табылмады.")
            
    with qr_col2:
        st.write("### 🟢 Halyk QR")
        if os.path.exists("halyk_qr_ЫРЫС.png"):
            st.image("halyk_qr_ЫРЫС.png", caption="SmartTest — Halyk QR", width=260)
        else:
            st.warning("⚠️ `halyk_qr_ЫРЫС.png` файлы табылмады.")
    
    with st.form("payment_verification_form"):
        st.markdown(t("txn_hdr"))
        txn_id = st.text_input(t("txn_lbl"), placeholder=t("txn_ph"))
        
        submit_payment = st.form_submit_button(t("txn_btn"))
        
        if submit_payment:
            if not txn_id.strip():
                st.error(t("txn_err"))
            else:
                try:
                    add_payment_record(current_user, amount, float(credits_to_buy), txn_id.strip())
                    st.success(t("txn_ok").format(credits_to_buy))
                except Exception as e:
                    st.error(f"Қате: {e}")

elif selected_menu_key == "menu_security":
    if not is_admin:
        st.error(t("sec_denied"))
        st.stop()

    st.subheader(t("sec_sub"))
    st.write(t("user_lbl") + f": **{current_user}** | " + t("balance_lbl") + f": **{user_balance} {t('credit_unit')}** ({total_tenge:,.0f} ₸)")
    
    st.markdown("---")
    st.subheader(t("db_mgmt_hdr"))
    st.warning(t("db_mgmt_warn"))
    
    if st.button(t("db_clear_btn"), type="primary"):
        try:
            clear_all_results()
            st.success(t("db_clear_ok"))
            st.rerun()
        except Exception as e:
            st.error(f"Қате орын алды: {e}")