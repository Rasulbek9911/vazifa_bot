"""
700 ta dummy student va 10 ta mavzu uchun PDF report test qilish
"""
import os
import django
import sys

# Django sozlamalarini yuklash
sys.path.append('/home/rasulbek/Projects/vazifa_bot')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from base_app.models import Student, Group, Topic, Task
from django.utils.timezone import now, timedelta
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import random

def create_dummy_data():
    """700 ta student va 10 ta mavzu yaratish"""
    print("Dummy datalar yaratilmoqda...")
    
    # Guruh yaratish yoki olish
    group, created = Group.objects.get_or_create(
        name="Test Guruh 700",
        defaults={"telegram_group_id": "-1001234567890"}
    )
    if created:
        print(f"✅ Guruh yaratildi: {group.name}")
    else:
        print(f"✅ Guruh mavjud: {group.name}")
    
    # 10 ta mavzu yaratish
    topics = []
    for i in range(1, 11):
        topic, created = Topic.objects.get_or_create(
            title=f"Mavzu {i}",
            defaults={"is_active": True}
        )
        topics.append(topic)
    print(f"✅ {len(topics)} ta mavzu tayyor")
    
    # 700 ta student yaratish
    students = []
    for i in range(1, 701):
        student, created = Student.objects.get_or_create(
            telegram_id=f"test_user_{i}",
            defaults={
                "full_name": f"Student {i}",
                "group": group
            }
        )
        students.append(student)
        
        # Har bir student uchun tasodifiy vazifalar yaratish
        for topic in topics:
            # 70% ehtimol bilan vazifa topshiradi
            if random.random() < 0.7:
                Task.objects.get_or_create(
                    student=student,
                    topic=topic,
                    defaults={
                        "file_link": "test_file_id",
                        "grade": random.choice([3, 4, 5, None])
                    }
                )
    
    print(f"✅ {len(students)} ta student yaratildi")
    return group, students, topics


def generate_pdf_report(group, students, topics):
    """PDF report yaratish"""
    print("PDF report yaratilmoqda...")
    
    # Jadval sarlavhalari
    data = [["№", "Talaba"] + [f"M{i+1}" for i in range(len(topics))]]
    
    # Studentlar uchun qatordan-qatordan to'ldirish
    for idx, student in enumerate(students, 1):
        row = [str(idx), student.full_name[:20]]  # Ism qisqartiriladi
        for topic in topics:
            task = Task.objects.filter(student=student, topic=topic).first()
            if task and task.grade:
                row.append(str(task.grade))
            elif task:
                row.append("—")
            else:
                row.append("✗")
        data.append(row)
    
    # PDF yaratish
    filename = f"/home/rasulbek/Projects/vazifa_bot/test_report_700_students.pdf"
    doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
    
    # Jadval yaratish
    # Ustun kengliklarini sozlash
    col_widths = [30, 120] + [40] * len(topics)  # № va Ism uchun kengrok
    table = Table(data, colWidths=col_widths, repeatRows=1)
    
    # Jadval stilini sozlash
    style = TableStyle([
        # Sarlavha
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        
        # Qator ranglari (har ikkinchi qator)
        *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F2F2F2")) 
          for i in range(2, len(data), 2)],
    ])
    table.setStyle(style)
    
    # PDF ga qo'shish
    elements = [table]
    doc.build(elements)
    
    print(f"✅ PDF yaratildi: {filename}")
    print(f"📊 Jami qatorlar: {len(data)} (1 sarlavha + {len(students)} student)")
    print(f"📊 Jami ustunlar: {len(data[0])} (№ + Ism + {len(topics)} mavzu)")
    return filename


def main():
    print("=" * 60)
    print("700 ta student uchun PDF report test")
    print("=" * 60)
    
    # 1. Dummy datalar yaratish
    group, students, topics = create_dummy_data()
    
    # 2. PDF report yaratish
    pdf_file = generate_pdf_report(group, students, topics)
    
    print("\n" + "=" * 60)
    print("✅ Test muvaffaqiyatli yakunlandi!")
    print(f"📄 PDF fayl: {pdf_file}")
    print("=" * 60)
    
    # 3. Faylni ochish (ixtiyoriy)
    print("\nPDF faylni ochish uchun quyidagi buyruqni kiriting:")
    print(f"  xdg-open {pdf_file}")


if __name__ == "__main__":
    main()
