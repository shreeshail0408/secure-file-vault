"""
Realistic demo content for `manage.py seed_files`.

Everything is generated in memory (bytes); nothing is written to disk here.
Each file gets its own random.Random(name), so the same name always produces
the same kind of content, and --count N always picks the same first N files.

    all_specs() -> list of Spec(name, build), where build(rng) returns the file's bytes.
"""

import io
from collections import namedtuple
from functools import lru_cache, partial

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image as PdfImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

Spec = namedtuple("Spec", ["name", "build"])

COMPANY = "Nimbus Works"  # fictional
PEOPLE = [
    "Asha Rao", "Vikram Shetty", "Meera Iyer", "Rahul Nair", "Priya Menon", "Arjun Kulkarni",
    "Sneha Patil", "Karthik Reddy", "Divya Hegde", "Rohan Joshi", "Ananya Bhat", "Nikhil Gowda",
]
CLIENTS = ["Acme Retail", "Bluepeak Logistics", "Greenleaf Foods", "Orbit Telecom", "Sunrise Clinics"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]

# Brand-neutral colour palette shared by charts, banners and posters.
PALETTE = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#ca8a04", "#db2777"]


# =============================================================================
# Text helpers
# =============================================================================

SUBJECTS = ["The team", "Our customers", "The new release", "Revenue", "The platform",
            "Support volume", "The vendor", "Infrastructure cost", "The pilot project",
            "User engagement", "The security audit", "Delivery speed"]
VERBS = ["increased steadily", "remained stable", "exceeded expectations",
         "needed extra attention", "improved after the update", "was reviewed in detail",
         "met the agreed targets", "showed early signs of recovery"]
TAILS = ["during the reporting period.", "compared with last quarter.", "across all regions.",
         "after the March rollout.", "thanks to the automation work.", "despite the hiring freeze.",
         "according to the latest survey.", "and will be monitored next month."]


def sentence(rng):
    return f"{rng.choice(SUBJECTS)} {rng.choice(VERBS)} {rng.choice(TAILS)}"


def paragraph_text(rng, sentences=(3, 6)):
    return " ".join(sentence(rng) for _ in range(rng.randint(*sentences)))


# =============================================================================
# PDF helpers (reportlab "platypus": build a list of flowables, then lay out)
# =============================================================================

STYLES = getSampleStyleSheet()
BODY = STYLES["BodyText"]
H1 = STYLES["Title"]
H2 = STYLES["Heading2"]
SMALL = ParagraphStyle("small", parent=BODY, fontSize=8, textColor=colors.grey)


def pdf_bytes(story, title, pagesize=A4):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=pagesize, title=title, author=COMPANY,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
    )
    doc.build(story)
    return buffer.getvalue()


def table(rows, widths=None, header="#1f4e79"):
    t = Table(rows, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6fa")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def p(text, style=BODY):
    return Paragraph(text, style)


def money(value):
    return f"Rs {value:,.2f}"


def embedded_image(image_bytes, width_cm, height_cm):
    return PdfImage(io.BytesIO(image_bytes), width=width_cm * cm, height=height_cm * cm)


# =============================================================================
# PDFs
# =============================================================================

def invoice_pdf(rng, year, month):
    client = rng.choice(CLIENTS)
    number = f"INV-{year}-{month:02d}-{rng.randint(100, 999)}"
    items = [
        ("Cloud hosting (monthly)", 1, rng.randint(8000, 15000)),
        ("Support hours", rng.randint(5, 40), 1500),
        ("Storage add-on (TB)", rng.randint(1, 8), 2200),
        ("API calls (per million)", rng.randint(2, 30), 450),
        ("Security monitoring", 1, rng.randint(4000, 9000)),
        ("Data backup service", 1, rng.randint(2000, 5000)),
        ("Consulting (days)", rng.randint(1, 6), 12000),
        ("SSL certificates", rng.randint(1, 4), 3000),
    ]
    items = rng.sample(items, rng.randint(5, len(items)))
    rows = [["Description", "Qty", "Unit price", "Amount"]]
    subtotal = 0
    for name, qty, price in items:
        rows.append([name, str(qty), money(price), money(qty * price)])
        subtotal += qty * price
    tax = subtotal * 0.18
    rows += [["", "", "Subtotal", money(subtotal)], ["", "", "GST 18%", money(tax)],
             ["", "", "Total due", money(subtotal + tax)]]

    story = [
        p(f"INVOICE {number}", H1),
        p(f"<b>From:</b> {COMPANY}, 4th Floor, Tech Park, Bengaluru 560001"),
        p(f"<b>Bill to:</b> {client}, Accounts Payable"),
        p(f"<b>Invoice date:</b> 05 {MONTH_NAMES[month - 1]} {year} &nbsp; "
          f"<b>Due:</b> 30 days from invoice date"),
        Spacer(1, 12),
        table(rows, widths=[8 * cm, 2 * cm, 3.5 * cm, 3.5 * cm]),
        Spacer(1, 12),
        p(paragraph_text(rng, (2, 3))),
        PageBreak(),
        p("Payment details", H2),
        table([["Field", "Value"], ["Bank", "Example Bank Ltd"], ["Account name", COMPANY],
               ["Account no.", f"XXXX XXXX {rng.randint(1000, 9999)}"], ["IFSC", "EXMP0001234"],
               ["Reference", number]], widths=[5 * cm, 9 * cm]),
        Spacer(1, 12),
        p("Terms and conditions", H2),
        p("Payment is due within 30 days. Late payments may incur a 1.5% monthly charge. "
          "Please quote the invoice number with your payment."),
        p(paragraph_text(rng)),
        p("This is a computer-generated demo invoice for the Secure File Vault project.", SMALL),
    ]
    return pdf_bytes(story, f"Invoice {number}")


def report_pdf(rng, department, period):
    metrics = ["Revenue", "New customers", "Churn rate", "Avg. response time",
               "Tickets closed", "NPS score", "Active users", "Cost per lead"]
    kpis = [["Metric", "Target", "Actual", "Status"]]
    for metric in rng.sample(metrics, 6):
        target = rng.randint(50, 500)
        actual = int(target * rng.uniform(0.7, 1.3))
        kpis.append([metric, str(target), str(actual), "On track" if actual >= target else "Behind"])

    regions = [["Region", "Q-o-Q change", "Share", "Owner"]]
    for region in ["North", "South", "East", "West", "Central"]:
        regions.append([region, f"{rng.uniform(-8, 15):+.1f}%", f"{rng.randint(10, 30)}%",
                        rng.choice(PEOPLE)])

    chart = image_bytes(bar_chart(rng, f"{department} - {period}", MONTHS[:6], (1000, 560)), "png")

    story = [
        p(f"{department} Report - {period}", H1),
        p(f"Prepared by {rng.choice(PEOPLE)} for the {COMPANY} leadership team.", SMALL),
        p("Executive summary", H2), p(paragraph_text(rng)), p(paragraph_text(rng)),
        p("Key performance indicators", H2), table(kpis, widths=[6 * cm, 3 * cm, 3 * cm, 4 * cm]),
        PageBreak(),
        p("Monthly trend", H2), embedded_image(chart, 16, 9), p(paragraph_text(rng)),
        PageBreak(),
        p("Regional performance", H2), table(regions, widths=[4 * cm, 4 * cm, 3 * cm, 5 * cm]),
        p(paragraph_text(rng)),
    ]
    if rng.random() < 0.6:  # some reports have an extra recommendations page
        story += [PageBreak(), p("Recommendations", H2)] + [p(paragraph_text(rng)) for _ in range(3)]
    return pdf_bytes(story, f"{department} Report {period}")


def certificate_pdf(rng, course):
    person = rng.choice(PEOPLE)
    cert_id = f"NW-CERT-{rng.randint(10000, 99999)}"
    big = ParagraphStyle("big", parent=H1, fontSize=34, leading=42, textColor=colors.HexColor("#1f4e79"))
    center = ParagraphStyle("center", parent=BODY, alignment=1, fontSize=14, leading=20)
    modules = [["Module", "Hours", "Score", "Result"]]
    for i in range(1, rng.randint(6, 10)):
        score = rng.randint(62, 99)
        modules.append([f"{course} - Module {i}", str(rng.randint(4, 12)), f"{score}%",
                        "Distinction" if score >= 85 else "Pass"])

    story = [
        Spacer(1, 40),
        p("Certificate of Completion", big),
        Spacer(1, 20),
        p("This is to certify that", center),
        p(f"<b>{person}</b>", ParagraphStyle("name", parent=center, fontSize=26, leading=34)),
        p(f"has successfully completed the course <b>{course}</b>", center),
        p(f"with an overall score of {rng.randint(75, 98)}% on "
          f"{rng.randint(1, 28)} {rng.choice(MONTH_NAMES)} 2026.", center),
        Spacer(1, 30),
        p(f"Certificate ID: {cert_id} &nbsp;&nbsp; Issued by {COMPANY} Academy", center),
        PageBreak(),
        p("Course transcript", H2),
        table(modules, widths=[12 * cm, 3 * cm, 3 * cm, 4 * cm]),
        Spacer(1, 12),
        p(paragraph_text(rng)),
        p(f"Verify this certificate with ID {cert_id}. Demo document.", SMALL),
    ]
    return pdf_bytes(story, f"Certificate {course}", pagesize=landscape(A4))


def minutes_pdf(rng, meeting, date_text):
    attendees = rng.sample(PEOPLE, rng.randint(4, 8))
    actions = [["#", "Action item", "Owner", "Due"]]
    tasks = ["Share updated budget", "Fix login timeout bug", "Draft hiring plan",
             "Review vendor contract", "Prepare demo for client", "Update security policy",
             "Book offsite venue", "Migrate reports to new dashboard"]
    for i, task in enumerate(rng.sample(tasks, rng.randint(3, 6)), start=1):
        actions.append([str(i), task, rng.choice(attendees), f"{rng.randint(1, 28)} {rng.choice(MONTHS)}"])

    story = [
        p(f"Minutes - {meeting}", H1),
        p(f"<b>Date:</b> {date_text} &nbsp; <b>Chair:</b> {attendees[0]} &nbsp; "
          f"<b>Minutes by:</b> {attendees[-1]}"),
        p("Attendees", H2),
        table([["Name", "Role"]] + [[a, rng.choice(["Engineering", "Product", "Finance", "HR",
                                                     "Design", "Sales"])] for a in attendees],
              widths=[7 * cm, 7 * cm]),
        p("Agenda", H2),
    ]
    for i in range(1, rng.randint(3, 5)):
        story.append(p(f"{i}. {sentence(rng)}"))
    story += [PageBreak(), p("Discussion", H2)]
    story += [p(paragraph_text(rng)) for _ in range(rng.randint(2, 4))]
    story += [p("Action items", H2), table(actions, widths=[1 * cm, 8 * cm, 4 * cm, 3 * cm]),
              p(f"Next meeting: to be scheduled by {attendees[0]}.", SMALL)]
    return pdf_bytes(story, f"Minutes {meeting}")


def spec_pdf(rng, project, photos):
    reqs = [["ID", "Requirement", "Priority"]]
    features = ["User login with JWT", "Role-based access", "Audit logging", "Export to CSV",
                "Search and filters", "Mobile-friendly layout", "Email notifications",
                "Encrypted storage", "Two-factor authentication", "Usage analytics dashboard"]
    for i, feature in enumerate(rng.sample(features, rng.randint(6, 9)), start=1):
        reqs.append([f"REQ-{i:03d}", feature, rng.choice(["Must", "Should", "Could"])])
    milestones = [["Milestone", "Owner", "Target date"]]
    for name in ["Design sign-off", "API complete", "Beta release", "Security review", "Go-live"]:
        milestones.append([name, rng.choice(PEOPLE), f"{rng.randint(1, 28)} {rng.choice(MONTH_NAMES)} 2026"])

    story = [
        p(f"Project Specification: {project}", H1),
        p(f"Version {rng.randint(1, 3)}.{rng.randint(0, 9)} - owner {rng.choice(PEOPLE)}", SMALL),
        p("1. Overview", H2), p(paragraph_text(rng)), p(paragraph_text(rng)),
        p("2. Requirements", H2), table(reqs, widths=[2.5 * cm, 10 * cm, 3 * cm]),
        PageBreak(),
        p("3. Architecture", H2), p(paragraph_text(rng)), p(paragraph_text(rng)),
        p("4. Milestones", H2), table(milestones, widths=[6 * cm, 5 * cm, 5 * cm]),
    ]
    # "Site photos / mockups": large embedded JPEGs make these the biggest PDFs.
    for i in range(photos):
        photo = image_bytes(photo_image(rng, (1800, 1200), rng.randrange(len(SCENES))), "jpg", quality=92)
        story += [PageBreak(), p(f"Appendix {chr(65 + i)}: reference image", H2),
                  embedded_image(photo, 16, 10.7), p(paragraph_text(rng, (2, 3)))]
    return pdf_bytes(story, f"Spec {project}")


# =============================================================================
# Image helpers
# =============================================================================

@lru_cache(maxsize=None)
def font(size):
    return ImageFont.load_default(size=max(int(size), 8))


def hex_rgb(color):
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def gradient(size, stops, horizontal=False):
    """Linear gradient through the given colours (fast: tiny strip, then resize)."""
    w, h = size
    strip = Image.new("RGB", (len(stops), 1) if horizontal else (1, len(stops)))
    strip.putdata([hex_rgb(c) if isinstance(c, str) else c for c in stops])
    return strip.resize(size, Image.BILINEAR)


def darker(rgb, amount):
    return tuple(int(c * (1 - amount)) for c in rgb)


def image_bytes(img, ext, quality=88):
    buffer = io.BytesIO()
    if ext == "png":
        img.save(buffer, format="PNG")
    else:
        img.convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def translucent_shapes(img, rng, count):
    """Draw soft see-through circles on top of an image (for banners/posters)."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = img.size
    for _ in range(count):
        r = rng.randint(min(w, h) // 10, min(w, h) // 2)
        x, y = rng.randint(0, w), rng.randint(0, h)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rng.randint(18, 55)))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# =============================================================================
# Images
# =============================================================================

def bar_chart(rng, title, labels, size):
    w, h = size
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    values = [rng.randint(15, 100) for _ in labels]
    left, right, top, bottom = int(w * 0.1), int(w * 0.95), int(h * 0.16), int(h * 0.84)
    d.text((w // 2, int(h * 0.07)), title, font=font(h / 17), fill="#1f2937", anchor="mm")
    for i in range(6):  # gridlines + y-axis labels
        y = bottom - (bottom - top) * i / 5
        d.line([(left, y), (right, y)], fill="#e5e7eb")
        d.text((left - 8, y), str(i * 20), font=font(h / 38), fill="#6b7280", anchor="rm")
    slot = (right - left) / len(values)
    color = rng.choice(PALETTE)
    for i, (label, value) in enumerate(zip(labels, values)):
        x0, x1 = left + slot * (i + 0.15), left + slot * (i + 0.85)
        y0 = bottom - (bottom - top) * value / 100
        d.rectangle([x0, y0, x1, bottom], fill=color)
        d.text(((x0 + x1) / 2, y0 - 4), str(value), font=font(h / 40), fill="#374151", anchor="md")
        d.text(((x0 + x1) / 2, bottom + 8), label, font=font(h / 38), fill="#374151", anchor="mt")
    d.line([(left, top), (left, bottom), (right, bottom)], fill="#374151", width=2)
    return img


def pie_chart(rng, title, labels, size):
    w, h = size
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    values = [rng.randint(5, 40) for _ in labels]
    total = sum(values)
    d.text((w // 2, int(h * 0.07)), title, font=font(h / 17), fill="#1f2937", anchor="mm")
    radius = int(min(w * 0.3, h * 0.38))
    cx, cy = int(w * 0.36), int(h * 0.55)
    angle = -90
    for i, value in enumerate(values):
        sweep = 360 * value / total
        color = PALETTE[i % len(PALETTE)]
        d.pieslice([cx - radius, cy - radius, cx + radius, cy + radius], angle, angle + sweep,
                   fill=color, outline="white", width=3)
        angle += sweep
        # legend
        ly = int(h * 0.25) + i * int(h * 0.075)
        lx = int(w * 0.7)
        d.rectangle([lx, ly, lx + h // 30, ly + h // 30], fill=color)
        d.text((lx + h // 22, ly + h // 60), f"{labels[i]} ({100 * value / total:.0f}%)",
               font=font(h / 36), fill="#374151", anchor="lm")
    return img


def banner(rng, title, subtitle, size):
    w, h = size
    c1, c2 = rng.sample(PALETTE, 2)
    img = gradient(size, [c1, c2], horizontal=True)
    img = translucent_shapes(img, rng, 12)
    d = ImageDraw.Draw(img)
    d.text((int(w * 0.06), int(h * 0.42)), title.upper(), font=font(h / 4.5), fill="white", anchor="lm")
    d.text((int(w * 0.06), int(h * 0.72)), subtitle, font=font(h / 11), fill="white", anchor="lm")
    d.text((w - 20, h - 16), COMPANY, font=font(h / 16), fill="white", anchor="rs")
    return img


def badge(rng, person, role, size):
    w, h = size
    accent = rng.choice(PALETTE)
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, int(h * 0.2)], fill=accent)
    d.text((w // 2, int(h * 0.1)), COMPANY.upper(), font=font(h / 16), fill="white", anchor="mm")
    # "photo": a circle with the person's initials
    r = int(w * 0.24)
    cx, cy = w // 2, int(h * 0.38)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#e5e7eb", outline=accent, width=6)
    initials = "".join(part[0] for part in person.split())
    d.text((cx, cy), initials, font=font(r * 0.8), fill="#6b7280", anchor="mm")
    d.text((w // 2, int(h * 0.6)), person, font=font(h / 18), fill="#111827", anchor="mm")
    d.text((w // 2, int(h * 0.66)), role, font=font(h / 28), fill=accent, anchor="mm")
    d.text((w // 2, int(h * 0.72)), f"ID: NW-{rng.randint(1000, 9999)}", font=font(h / 32),
           fill="#374151", anchor="mm")
    # fake barcode
    x, top, bottom = int(w * 0.15), int(h * 0.8), int(h * 0.9)
    while x < w * 0.85:
        bar = rng.randint(2, 7)
        d.rectangle([x, top, x + bar, bottom], fill="black")
        x += bar + rng.randint(2, 6)
    d.text((w // 2, int(h * 0.95)), "Valid until 31 Dec 2027", font=font(h / 40),
           fill="#6b7280", anchor="mm")
    return img


def poster(rng, title, details, size):
    w, h = size
    stops = rng.sample(PALETTE, 3)
    img = translucent_shapes(gradient(size, stops), rng, 18)
    d = ImageDraw.Draw(img)
    words = title.upper().split()
    lines = [" ".join(words[i:i + 2]) for i in range(0, len(words), 2)]  # 2 words per line
    y = int(h * 0.3)
    for line in lines:
        d.text((w // 2, y), line, font=font(w / 9), fill="white", anchor="mm")
        y += int(w / 7.5)
    for i, detail in enumerate(details):
        d.text((w // 2, int(h * 0.72) + i * int(h * 0.05)), detail, font=font(w / 24),
               fill="white", anchor="mm")
    d.text((w // 2, int(h * 0.94)), COMPANY, font=font(w / 30), fill="white", anchor="mm")
    return img


# Sky / sun / land colours for photo-like scenes.
SCENES = [
    (["#7dd3fc", "#e0f2fe"], "#fde68a", "#166534"),  # mountain lake
    (["#0f172a", "#312e81"], "#f8fafc", "#1e293b"),  # night
    (["#fdba74", "#fef3c7"], "#fff7ed", "#c2410c"),  # desert
    (["#94a3b8", "#e2e8f0"], "#f1f5f9", "#14532d"),  # misty forest
    (["#f97316", "#fde047"], "#fef9c3", "#1e3a8a"),  # sunset over ocean
    (["#bae6fd", "#f0f9ff"], "#ffffff", "#e2e8f0"),  # snow
    (["#fed7aa", "#fff7ed"], "#fde68a", "#9a3412"),  # autumn
]


def photo_image(rng, size, scene, grain=0.06):
    """A photo-like landscape: sky gradient, sun, hills, a little blur and film grain."""
    w, h = size
    sky, sun, land = SCENES[scene]
    img = gradient(size, sky)
    d = ImageDraw.Draw(img)
    r = rng.randint(h // 14, h // 8)
    cx, cy = rng.randint(w // 5, 4 * w // 5), rng.randint(h // 8, h // 3)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=sun)
    for layer in range(3):  # far hills are lighter, near hills darker
        base_y = int(h * (0.5 + 0.14 * layer))
        points, x = [(0, h)], 0
        while x <= w + w // 8:
            points.append((x, base_y - rng.randint(0, h // (4 + 2 * layer))))
            x += rng.randint(w // 20, w // 8)
        points += [(w, h)]
        d.polygon(points, fill=darker(hex_rgb(land), 0.25 * layer))
    img = img.filter(ImageFilter.GaussianBlur(1.5))
    # Film grain from rng (deterministic). Real photos are noisy, which is also
    # what makes them large: this gives realistic file sizes.
    noise = Image.frombytes("RGB", size, rng.randbytes(w * h * 3))
    return Image.blend(img, noise, grain)


def encoded(make_image, ext, rng, quality=88, **kwargs):
    """Build an image with `make_image(rng, **kwargs)` and return PNG/JPG bytes."""
    return image_bytes(make_image(rng, **kwargs), ext, quality)


# =============================================================================
# The catalogue: 50 PDFs + 50 images
# =============================================================================

def pdf_specs():
    specs = []
    for month in range(1, 13):
        specs.append(Spec(f"invoice_2026_{month:02d}.pdf", partial(invoice_pdf, year=2026, month=month)))
    for q in range(1, 5):
        specs.append(Spec(f"report_sales_q{q}.pdf", partial(report_pdf, department="Sales", period=f"Q{q} 2026")))
    for name, dept, period in [
        ("report_marketing_2026_01", "Marketing", "January 2026"),
        ("report_marketing_2026_04", "Marketing", "April 2026"),
        ("report_hr_monthly_2026_05", "HR", "May 2026"),
        ("report_finance_q2", "Finance", "Q2 2026"),
        ("report_operations_2026_06", "Operations", "June 2026"),
        ("report_it_security_2026_07", "IT Security", "July 2026"),
        ("report_customer_support_2026_08", "Customer Support", "August 2026"),
        ("report_engineering_q3", "Engineering", "Q3 2026"),
    ]:
        specs.append(Spec(f"{name}.pdf", partial(report_pdf, department=dept, period=period)))
    for slug, course in [
        ("ai_ml", "AI and Machine Learning"), ("cloud_aws", "Cloud Computing on AWS"),
        ("cybersecurity", "Cybersecurity Fundamentals"), ("data_science", "Data Science with Python"),
        ("python_advanced", "Advanced Python"), ("react_frontend", "React Frontend Development"),
        ("project_management", "Agile Project Management"), ("devops_kubernetes", "DevOps and Kubernetes"),
        ("ux_design", "UX Design Principles"),
    ]:
        specs.append(Spec(f"certificate_{slug}.pdf", partial(certificate_pdf, course=course)))
    for name, meeting, date_text in [
        ("minutes_board_2026_01_15", "Board Meeting", "15 January 2026"),
        ("minutes_board_2026_04_15", "Board Meeting", "15 April 2026"),
        ("minutes_sprint_review_14", "Sprint 14 Review", "06 March 2026"),
        ("minutes_sprint_review_15", "Sprint 15 Review", "20 March 2026"),
        ("minutes_all_hands_2026_03", "All Hands", "28 March 2026"),
        ("minutes_product_sync_2026_05_06", "Product Sync", "06 May 2026"),
        ("minutes_security_review_2026_06", "Security Review", "12 June 2026"),
        ("minutes_budget_planning_2026_08", "Budget Planning", "18 August 2026"),
        ("minutes_client_kickoff_acme", "Client Kickoff - Acme Retail", "02 September 2026"),
    ]:
        specs.append(Spec(f"{name}.pdf", partial(minutes_pdf, meeting=meeting, date_text=date_text)))
    for slug, project, photos in [
        ("mobile_app_v2", "Mobile App v2", 1), ("payment_gateway", "Payment Gateway", 0),
        ("file_vault_api", "File Vault API", 0), ("crm_migration", "CRM Migration", 1),
        ("data_warehouse", "Data Warehouse", 2), ("chatbot_support", "Support Chatbot", 0),
        ("inventory_system", "Inventory System", 1), ("website_redesign", "Website Redesign", 2),
    ]:
        specs.append(Spec(f"spec_{slug}.pdf", partial(spec_pdf, project=project, photos=photos)))
    return specs


def image_specs():
    specs = []
    for name, title, labels, size, ext in [
        ("revenue_2026", "Revenue 2026 (Rs lakh)", MONTHS, (1280, 720), "png"),
        ("signups_monthly", "Monthly sign-ups", MONTHS[:8], (1024, 768), "png"),
        ("expenses_by_dept", "Expenses by department",
         ["Eng", "Sales", "HR", "Ops", "Mktg", "Legal"], (800, 600), "png"),
        ("tickets_resolved", "Support tickets resolved", MONTHS[:6], (1600, 900), "png"),
        ("website_traffic", "Website traffic (k visits)", MONTHS, (1920, 1080), "jpg"),
        ("sales_by_region", "Sales by region", ["North", "South", "East", "West", "Central"], (900, 600), "png"),
        ("headcount", "Headcount by team",
         ["Backend", "Frontend", "QA", "Design", "Data", "DevOps", "Support"], (1200, 800), "png"),
        ("cloud_costs", "Cloud costs per month", MONTHS[:9], (1366, 768), "jpg"),
        ("app_downloads", "App downloads (k)", MONTHS[:10], (1080, 1080), "png"),
        ("quarterly_profit", "Quarterly profit", ["Q1", "Q2", "Q3", "Q4"], (640, 480), "png"),
    ]:
        specs.append(Spec(f"chart_bar_{name}.{ext}",
                          partial(encoded, bar_chart, ext, title=title, labels=labels, size=size)))
    for name, title, labels, size in [
        ("market_share", "Market share", ["Us", "Rival A", "Rival B", "Others"], (1000, 700)),
        ("budget_split", "Budget split", ["Salaries", "Cloud", "Marketing", "Office", "Training"], (900, 600)),
        ("traffic_sources", "Traffic sources", ["Search", "Direct", "Social", "Email", "Ads"], (1200, 800)),
        ("device_usage", "Device usage", ["Mobile", "Desktop", "Tablet"], (800, 800)),
        ("customer_segments", "Customer segments", ["Enterprise", "SMB", "Startup", "Govt"], (1024, 768)),
        ("time_allocation", "Engineering time", ["Features", "Bugs", "Meetings", "Ops", "Learning"], (1000, 700)),
        ("survey_results", "Survey: satisfaction", ["Very happy", "Happy", "Neutral", "Unhappy"], (900, 650)),
        ("storage_usage", "Storage usage", ["PDFs", "Images", "Backups", "Logs", "Other"], (1100, 750)),
    ]:
        specs.append(Spec(f"chart_pie_{name}.png",
                          partial(encoded, pie_chart, "png", title=title, labels=labels, size=size)))
    for name, title, subtitle, size, ext in [
        ("summer_sale", "Summer Sale", "Up to 40% off all annual plans", (1600, 400), "jpg"),
        ("product_launch", "Vault 2.0", "Encrypted sharing is here", (1920, 500), "jpg"),
        ("welcome_new_hires", "Welcome aboard", "Say hi to our September joiners", (1200, 300), "png"),
        ("webinar_ai", "AI Webinar", "Thursday 6 PM - register now", (1500, 450), "jpg"),
        ("black_friday", "Black Friday", "Biggest discounts of the year", (1920, 600), "jpg"),
        ("hackathon_2026", "Hackathon 2026", "48 hours - build anything", (1400, 350), "png"),
        ("newsletter_header", "Monthly Digest", "News from the Nimbus team", (1200, 400), "jpg"),
        ("holiday_greetings", "Happy Holidays", "From all of us at Nimbus Works", (1600, 500), "jpg"),
    ]:
        specs.append(Spec(f"banner_{name}.{ext}",
                          partial(encoded, banner, ext, quality=90, title=title, subtitle=subtitle, size=size)))
    for person, role, size in [
        ("Asha Rao", "Software Engineer", (600, 900)), ("Vikram Shetty", "Product Manager", (640, 1010)),
        ("Meera Iyer", "UX Designer", (600, 900)), ("Rahul Nair", "DevOps Engineer", (540, 860)),
        ("Priya Menon", "Data Scientist", (600, 900)), ("Arjun Kulkarni", "Security Analyst", (640, 1010)),
        ("Sneha Patil", "HR Partner", (600, 900)), ("Karthik Reddy", "Visitor", (540, 860)),
    ]:
        slug = person.lower().replace(" ", "_")
        specs.append(Spec(f"badge_employee_{slug}.png",
                          partial(encoded, badge, "png", person=person, role=role, size=size)))
    for name, title, details, size, ext in [
        ("tech_conference", "Tech Conference 2026", ["12-13 March", "Bengaluru"], (1200, 1800), "jpg"),
        ("team_offsite", "Team Offsite Coorg", ["2-4 October", "Bus leaves 7 AM"], (1080, 1620), "png"),
        ("security_awareness", "Think Before You Click", ["Security Awareness Month"], (900, 1350), "jpg"),
        ("yoga_day", "International Yoga Day", ["21 June, 7 AM", "Terrace garden"], (1080, 1620), "jpg"),
        ("coding_bootcamp", "Coding Bootcamp", ["6 weeks", "Python + React"], (1200, 1800), "jpg"),
        ("music_night", "Friday Music Night", ["Cafeteria, 6 PM"], (900, 1350), "jpg"),
        ("blood_donation_camp", "Blood Donation Camp", ["15 August", "Ground floor"], (1080, 1620), "jpg"),
        ("annual_day", "Annual Day 2026", ["20 December", "Dress code: festive"], (1000, 1500), "png"),
    ]:
        specs.append(Spec(f"poster_{name}.{ext}",
                          partial(encoded, poster, ext, quality=90, title=title, details=details, size=size)))
    # More grain = more "photographic" and bigger files (up to ~2 MB).
    for name, scene, size, ext, grain in [
        ("mountain_lake", 0, (2400, 1600), "jpg", 0.18), ("city_night", 1, (2000, 1333), "jpg", 0.12),
        ("desert_dunes", 2, (2400, 1600), "jpg", 0.18), ("forest_mist", 3, (1600, 1067), "jpg", 0.10),
        ("ocean_sunset", 4, (2400, 1350), "jpg", 0.20), ("office_space", 3, (1024, 683), "png", 0.06),
        ("snow_peaks", 5, (1800, 1200), "jpg", 0.08), ("autumn_park", 6, (1200, 800), "png", 0.06),
    ]:
        specs.append(Spec(f"photo_{name}.{ext}", partial(
            encoded, photo_image, ext, quality=94, size=size, scene=scene, grain=grain)))
    return specs


def all_specs():
    """All 100 files, alternating PDF / image so --count N gives a mix of both."""
    pdfs, images = pdf_specs(), image_specs()
    return [spec for pair in zip(pdfs, images) for spec in pair]
