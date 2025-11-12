#!/usr/bin/env python3
"""
Simple PDF generation test without Django dependency
"""
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
import random

def generate_simple_pdf():
    """700 ta student uchun oddiy PDF yaratish"""
    print("PDF report yaratilmoqda...")
    
    # Mavzular
    topics = [f"M{i+1}" for i in range(10)]
    
    # Jadval sarlavhalari
    data = [["№", "Talaba"] + topics + ["O'rt"]]
    
    # 700 ta student uchun datalar
    for i in range(1, 701):
        row = [str(i), f"Student {i}"]
        grades = []
        for _ in topics:
            # Tasodifiy baho yoki bo'sh
            if random.random() < 0.7:
                grade = random.choice([3, 4, 5])
                grades.append(grade)
                row.append(str(grade))
            else:
                row.append("—")
        
        # O'rtacha baho
        if grades:
            avg = sum(grades) / len(grades)
            row.append(f"{avg:.1f}")
        else:
            row.append("—")
        
        data.append(row)
    
    # PDF yaratish
    filename = "/home/rasulbek/Projects/vazifa_bot/test_report_700_students.pdf"
    doc = SimpleDocTemplate(filename, pagesize=landscape(A4))
    
    # Ustun kengliklarini sozlash
    col_widths = [25, 80] + [30] * len(topics) + [35]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    
    # Jadval stilini sozlash
    style = TableStyle([
        # Sarlavha
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        
        # Har ikkinchi qator rangi
        *[("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F2F2F2")) 
          for i in range(2, len(data), 2)],
        
        # O'rtacha ustun
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
        ("FONTNAME", (-1, 0), (-1, -1), "Helvetica-Bold"),
    ])
    table.setStyle(style)
    
    # PDF ga qo'shish
    doc.build([table])
    
    print(f"✅ PDF yaratildi: {filename}")
    print(f"📊 Jami qatorlar: {len(data)} (1 sarlavha + 700 student)")
    print(f"📊 Jami ustunlar: {len(data[0])} (№ + Ism + {len(topics)} mavzu + O'rtacha)")
    print(f"\n📄 Faylni ochish uchun: xdg-open {filename}")
    return filename


if __name__ == "__main__":
    print("=" * 70)
    print("700 ta student uchun PDF report test")
    print("=" * 70)
    generate_simple_pdf()
    print("=" * 70)
