"""
PDF hisobot generatori — 50 savollik testlar uchun
Struktura: №, F.I.Sh, Fan (1-35)/70, Ped (36-50)/30, Jami/100, Toifa
"""
import io
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

pdfmetrics.registerFont(TTFont("DejaVu", FONT_PATH))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", FONT_BOLD_PATH))


def get_category(ball: int) -> str:
    if ball >= 86:
        return "Oliy +70%"
    elif ball >= 80:
        return "Oliy"
    elif ball >= 70:
        return "1-Toifa"
    elif ball >= 60:
        return "2-Toifa"
    return "O'tmagan"


def _parse_answers(s: str) -> list[str]:
    """Javoblar satrini ro'yxatga aylantiradi: 'abc' → ['a','b','c'], '1a2b3c' → ['a','b','c']"""
    if not s:
        return []
    s = s.lower().strip()
    if re.search(r'\d', s):
        return [m.group(1)[0] for m in re.finditer(r'\d+([a-zx]+)', s)]
    return list(re.sub(r'[^a-zx]', '', s))


def calc_fan_ped(correct_str: str, student_str: str):
    """
    50 savollik test uchun fan va ped balllarini hisoblaydi.
    Qaytaradi: (fan_ball, ped_ball) yoki (None, None) agar 50 savol bo'lmasa.
    """
    correct = _parse_answers(correct_str)
    if len(correct) != 50:
        return None, None

    student = _parse_answers(student_str)
    # Savol soni yetmasa bo'sh javob deb hisoblaymiz
    while len(student) < 50:
        student.append("")

    fan_correct = sum(1 for i in range(35) if correct[i] == student[i])
    ped_correct = sum(1 for i in range(35, 50) if correct[i] == student[i])

    return fan_correct * 2, ped_correct * 2


def generate_coin_rating_pdf(course, wallets: list, group_name: str = None) -> io.BytesIO:
    """
    course     — Course model instance
    wallets    — CoinWallet list (select_related('student') qilingan)
    group_name — agar berilsa guruh nomi sarlavhaga qo'shiladi
    """
    hdr_style = ParagraphStyle("hdr", fontName="DejaVu-Bold", fontSize=9, alignment=1, leading=11)
    cell_style = ParagraphStyle("cell", fontName="DejaVu", fontSize=9, leading=11)
    cell_center = ParagraphStyle("cell_c", fontName="DejaVu", fontSize=9, alignment=1, leading=11)
    title_style = ParagraphStyle("title", fontName="DejaVu-Bold", fontSize=12, alignment=1, spaceAfter=4)

    def h(text):
        return Paragraph(text, hdr_style)

    def c(text):
        return Paragraph(str(text), cell_style)

    def cc(text):
        return Paragraph(str(text), cell_center)

    header_row = [h("№"), h("F.I.Sh"), h("Umumiy\ntanga"), h("Joriy\nstreak"), h("Eng uzun\nstreak")]
    data = [header_row]
    for i, w in enumerate(wallets, 1):
        data.append([cc(i), c(w.student.full_name), cc(w.total_coins), cc(w.current_streak), cc(w.longest_streak)])

    col_widths = [12 * mm, 100 * mm, 35 * mm, 30 * mm, 35 * mm]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5596")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ROWHEIGHT", (0, 0), (0, 0), 36),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF2FA")]),
            ("ROWHEIGHT", (0, 1), (-1, -1), 16),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#1A3A6E")),
        ])
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    scope = f"Guruh: {group_name}" if group_name else "Umumiy reyting"
    title_text = f"{course.name}  |  {scope}  |  Jami: {len(wallets)} ta student"
    doc.build([Paragraph(title_text, title_style), Spacer(1, 3 * mm), table])
    buffer.seek(0)
    return buffer


def generate_topic_pdf(topic, tasks: list) -> io.BytesIO:
    """
    topic  — Topic model instance (correct_answers, title, course)
    tasks  — Task queryset/list (task.student.full_name, task.test_answers)
    """
    # To'g'ri javoblar satrini olamiz
    test_code = next(iter(topic.correct_answers), None) if topic.correct_answers else None
    correct_str = topic.correct_answers.get(test_code, "") if test_code else ""

    # Har bir student uchun ball hisoblash
    rows = []
    for task in tasks:
        if not task.test_answers:
            continue
        fan_ball, ped_ball = calc_fan_ped(correct_str, task.test_answers)
        if fan_ball is None:
            continue
        jami = fan_ball + ped_ball
        rows.append((task.student.full_name, fan_ball, ped_ball, jami, get_category(jami)))

    # Jami ball bo'yicha kamayish tartibida saralanadi
    rows.sort(key=lambda r: r[3], reverse=True)

    # ── Styles ──────────────────────────────────────────────────
    hdr_style = ParagraphStyle("hdr", fontName="DejaVu-Bold", fontSize=9, alignment=1, leading=11)
    cell_style = ParagraphStyle("cell", fontName="DejaVu", fontSize=9, leading=11)
    cell_center = ParagraphStyle("cell_c", fontName="DejaVu", fontSize=9, alignment=1, leading=11)
    title_style = ParagraphStyle("title", fontName="DejaVu-Bold", fontSize=11, alignment=1, spaceAfter=4)

    def h(text):
        return Paragraph(text, hdr_style)

    def c(text):
        return Paragraph(str(text), cell_style)

    def cc(text):
        return Paragraph(str(text), cell_center)

    # ── Jadval ma'lumotlari ──────────────────────────────────────
    header_row = [h("№"), h("F.I.Sh"), h("Fan\n(1-35)\n/70"), h("Ped\n(36-50)\n/30"), h("Jami\n/100"), h("Toifa")]
    data = [header_row]
    for i, (name, fan, ped, jami, toifa) in enumerate(rows, 1):
        data.append([cc(i), c(name), cc(fan), cc(ped), cc(jami), cc(toifa)])

    # ── Ustun kengliklari (landscape A4 ≈ 277 mm ish maydoni) ───
    col_widths = [12 * mm, 90 * mm, 30 * mm, 30 * mm, 25 * mm, 38 * mm]

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            # Sarlavha
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5596")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ROWHEIGHT", (0, 0), (0, 0), 36),
            # Ma'lumot qatorlari
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF2FA")]),
            ("ROWHEIGHT", (0, 1), (-1, -1), 16),
            # Chegara
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#1A3A6E")),
        ])
    )

    # ── Sahifa ──────────────────────────────────────────────────
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )

    course_name = topic.course.name if topic.course else ""
    title_text = f"{topic.title}  |  Kod: {test_code or '—'}  |  {course_name}  |  Jami: {len(rows)} ta"

    doc.build([Paragraph(title_text, title_style), Spacer(1, 3 * mm), table])
    buffer.seek(0)
    return buffer


def generate_coin_monthly_pdf(course, rows: list, group_name: str = None, month_label: str = "") -> io.BytesIO:
    """
    Oylik tanga hisoboti (streak yo'q).
    rows: [{'wallet__student__full_name': ..., 'oylik': ...}, ...]
    """
    hdr_style = ParagraphStyle("mhdr2", fontName="DejaVu-Bold", fontSize=9, alignment=1, leading=11)
    cell_style = ParagraphStyle("mcell2", fontName="DejaVu", fontSize=9, leading=11)
    cell_c = ParagraphStyle("mcell_c2", fontName="DejaVu", fontSize=9, alignment=1, leading=11)
    title_style = ParagraphStyle("mtitle2", fontName="DejaVu-Bold", fontSize=12, alignment=1, spaceAfter=4)

    def h(t): return Paragraph(t, hdr_style)
    def c(t): return Paragraph(str(t), cell_style)
    def cc(t): return Paragraph(str(t), cell_c)

    data = [[h("№"), h("F.I.Sh"), h("Oylik\ntanga")]]
    for i, row in enumerate(rows, 1):
        data.append([cc(i), c(row['wallet__student__full_name']), cc(row['oylik'])])

    col_widths = [12 * mm, 110 * mm, 40 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5596")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ROWHEIGHT", (0, 0), (0, 0), 30),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF2FA")]),
        ("ROWHEIGHT", (0, 1), (-1, -1), 16),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#1A3A6E")),
    ]))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=15 * mm, leftMargin=15 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    scope = f"Guruh: {group_name}" if group_name else "Umumiy"
    title_text = f"{course.name}  |  {scope}  |  📅 {month_label}  |  {len(rows)} ta student"
    doc.build([Paragraph(title_text, title_style), Spacer(1, 3 * mm), table])
    buffer.seek(0)
    return buffer


def generate_group_matrix_pdf(group_name, topics: list, tasks_map: dict, students: list, month_label: str = None) -> io.BytesIO:
    """
    Har sahifada max 10 ta mavzu ustun (matrix).
    group_name : str yoki None (None → "Barcha guruhlar")
    topics     : Topic objects (tartibli)
    tasks_map  : {topic_id: {student_id: task_obj}}
    students   : Student objects (satr sifatida)

    Ustunlar: №, F.I.Sh, [mavzu1], ..., [mavzu10], O'rt%
    - 50q: jami ball  |  boshqa: "to'g'ri/jami"  |  topshirmagan: "—"
    """
    COLS_PER_PAGE = 10

    hdr_style = ParagraphStyle("ghdr", fontName="DejaVu-Bold", fontSize=7, alignment=1, leading=9)
    cell_style = ParagraphStyle("gcell", fontName="DejaVu", fontSize=8, leading=10)
    cell_c = ParagraphStyle("gcell_c", fontName="DejaVu", fontSize=8, alignment=1, leading=10)
    title_style = ParagraphStyle("gtitle", fontName="DejaVu-Bold", fontSize=10, alignment=1, spaceAfter=3)

    def h(t): return Paragraph(str(t), hdr_style)
    def c(t): return Paragraph(str(t), cell_style)
    def cc(t): return Paragraph(str(t), cell_c)

    scope = f"Guruh: {group_name}" if group_name else "Barcha guruhlar"
    course_name = topics[0].course.name if topics and topics[0].course else ""
    total_pages = (len(topics) + COLS_PER_PAGE - 1) // COLS_PER_PAGE

    story = []

    for page_idx in range(total_pages):
        if page_idx > 0:
            story.append(PageBreak())

        page_topics = topics[page_idx * COLS_PER_PAGE:(page_idx + 1) * COLS_PER_PAGE]
        n = len(page_topics)

        # Har mavzu uchun meta ma'lumot
        metas = []
        for t in page_topics:
            tc = next(iter(t.correct_answers), None) if t.correct_answers else None
            cs = t.correct_answers.get(tc, "") if tc else ""
            cl = _parse_answers(cs)
            metas.append((tc, cs, cl, len(cl)))

        def _score(topic, meta, student):
            tc, cs, cl, total_q = meta
            task = tasks_map.get(topic.id, {}).get(student.id)
            if not task or not task.test_answers:
                return "—", None
            if total_q == 50:
                fan, ped = calc_fan_ped(cs, task.test_answers)
                if fan is None:
                    return "—", None
                jami = fan + ped
                return str(jami), jami / 100
            if total_q == 0:
                return "—", None
            sl = _parse_answers(task.test_answers)
            while len(sl) < total_q:
                sl.append("")
            cnt = sum(1 for j in range(total_q) if cl[j] == sl[j])
            return f"{cnt}/{total_q}", cnt / total_q

        # Studentlar satrlarini qurish
        rows = []
        for student in students:
            scores, pcts = [], []
            for topic, meta in zip(page_topics, metas):
                disp, pct = _score(topic, meta, student)
                scores.append(disp)
                if pct is not None:
                    pcts.append(pct)
            avg = sum(pcts) / len(pcts) if pcts else -1
            avg_str = f"{round(avg * 100)}%" if avg >= 0 else "—"
            rows.append((student.full_name, scores, avg_str, avg))

        # O'rtacha bo'yicha saralash (topshirganlar yuqorida)
        rows.sort(key=lambda r: r[3], reverse=True)

        # Ustun kengliklari: landscape A4 ≈ 277mm
        # №:10 + F.I.Sh:65 + O'rt:16 = 91mm  →  qolgan 186mm / n ta mavzu
        topic_w = min(22, 186 / n) if n else 22

        # Sarlavha qatori: mavzu kodlari
        header = [h("№"), h("F.I.Sh")]
        for topic, (tc, *_) in zip(page_topics, metas):
            code = tc or topic.title[:8]
            header.append(h(code))
        header.append(h("O'rt\n%"))

        data = [header]
        for idx, (name, scores, avg_str, _) in enumerate(rows, 1):
            data.append([cc(idx), c(name)] + [cc(s) for s in scores] + [cc(avg_str)])

        col_widths = [10 * mm, 65 * mm] + [topic_w * mm] * n + [16 * mm]

        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E5596")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ROWHEIGHT", (0, 0), (0, 0), 30),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF2FA")]),
            ("ROWHEIGHT", (0, 1), (-1, -1), 14),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#AAAAAA")),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#1A3A6E")),
        ]))

        codes = ", ".join(
            (m[0] or t.title[:8]) for t, m in zip(page_topics, metas)
        )
        month_part = f"  |  📅 {month_label}" if month_label else ""
        title_text = (
            f"{course_name}  |  {scope}{month_part}  |  "
            f"Sahifa {page_idx + 1}/{total_pages}: [{codes}]  |  {len(rows)} ta student"
        )
        story.append(Paragraph(title_text, title_style))
        story.append(Spacer(1, 2 * mm))
        story.append(table)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm, leftMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
    )
    doc.build(story)
    buffer.seek(0)
    return buffer
