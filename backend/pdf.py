"""The document, drawn on the server.

Until now the only thing that could draw an invoice was the browser: the
Send button rendered it with jsPDF and posted the bytes along with the
email. Anything the system sent on its own - a scheduled send, a recurring
invoice, the invoice raised when a quote is accepted, every reminder -
went out with no document at all, because there was no browser to draw one.

This is the same layout as generateInvoicePDF in app.js, point for point:
the same three-column header, the same table with the theme's columns, the
same totals, terms, signature and payment advice, the same footer. An
invoice the system sends looks like one the business sent from the screen.

reportlab because it is pure Python, draws with the same primitives jsPDF
does (text at a point, lines, rectangles, images), and uses the same three
built-in fonts, so the port is a translation and not a redesign. The one
thing to remember reading it: jsPDF measures y from the top of the page and
reportlab from the bottom, so every y below goes through T().
"""
import base64
import io
import re

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# What each kind of document calls things. The same table as PDF_DOC_TYPES
# in app.js, minus the element ids the browser reads its data from.
DOC_TYPES = {
    "invoice": {
        "heading": "TAX INVOICE", "date_label": "Invoice Date", "number_label": "Invoice Number",
        "total_label": "Amount Due", "date_out_label": "Due Date", "bank": True, "payment_advice": True,
    },
    "quote": {
        "heading": "QUOTE", "date_label": "Quote Date", "number_label": "Quote Number",
        "total_label": "Quote Total", "date_out_label": "Valid Until", "bank": False, "payment_advice": False,
    },
    "credit_note": {
        "heading": "CREDIT NOTE", "date_label": "Credit Note Date", "number_label": "Credit Note Number",
        "total_label": "Total Credited", "date_out_label": "Against Invoice", "bank": False, "payment_advice": False,
    },
}

# jsPDF has these three built in; so does every PDF reader.
FONTS = {
    "helvetica": ("Helvetica", "Helvetica-Bold"),
    "times": ("Times-Roman", "Times-Bold"),
    "courier": ("Courier", "Courier-Bold"),
}

# Symbols the built-in fonts cannot draw, written as the browser writes them.
PDF_SYMBOLS = {
    "₹": "Rs.", "₩": "W", "₪": "ILS", "₦": "N", "₫": "D", "₭": "K", "₮": "T",
    "₱": "P", "₲": "G", "₴": "grn", "₵": "GH", "₸": "T", "₺": "TL", "₼": "M", "₽": "R",
}

W, H = A4                     # 595.28 x 841.89, the same page jsPDF makes
ML, MR = 45, W - 45
PAGE_BOTTOM = H - 80


def pdf_symbol(sym):
    return PDF_SYMBOLS.get(sym, sym)


def hex_rgb(value, fallback=(0, 0, 0)):
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", (value or "").strip())
    if not m:
        return fallback
    v = m.group(1)
    return tuple(int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def break_long(text, max_len):
    """A word longer than the cell is split, the way the browser splits it."""
    if not text:
        return ""
    out = []
    for word in str(text).split(" "):
        if len(word) > max_len:
            out.extend(word[i:i + max_len] for i in range(0, len(word), max_len))
        else:
            out.append(word)
    return " ".join(out)


def wrap(text, font, size, max_width):
    """jsPDF's splitTextToSize: words onto lines no wider than max_width."""
    lines = []
    for para in str(text or "").split("\n"):
        words = para.split(" ")
        line = ""
        for word in words:
            trial = word if not line else line + " " + word
            if stringWidth(trial, font, size) <= max_width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def image_reader(data_url):
    """An image reportlab can draw from a data: URL, or None. SVG is not a
    raster and cannot be drawn here - the browser cannot draw it either."""
    if not data_url or not str(data_url).startswith("data:image/") or "svg" in str(data_url)[:20]:
        return None
    try:
        raw = base64.b64decode(str(data_url).split(",", 1)[1])
        return ImageReader(io.BytesIO(raw))
    except Exception:
        return None


def fmt(n):
    return f"{float(n or 0):.2f}"


def qty_text(q):
    """A quantity as the screen shows it: 3, not 3.0; 0.5; 2.25."""
    try:
        v = float(q)
    except (TypeError, ValueError):
        return "" if q is None else str(q)
    return str(int(v)) if v == int(v) else f"{v:.4f}".rstrip("0").rstrip(".")


def tax_label_for(lines):
    """The tax named by the lines - 'VAT', 'GST' - when they all name the same
    one; 'Tax' otherwise. '20% VAT' -> 'VAT'."""
    names = []
    for li in lines:
        m = re.match(r"^\s*[\d.]+%\s*(.+)$", str(li.get("tax_rate") or ""))
        if m and m.group(1) not in names:
            names.append(m.group(1))
    return names[0] if len(names) == 1 else "Tax"


def tax_percent(label):
    m = re.match(r"^\s*([\d.]+)\s*%", str(label or ""))
    return float(m.group(1)) if m else 0.0


def line_amounts(li, tax_type):
    """Net and tax for a line, the same arithmetic as the app."""
    amount = float(li.get("qty") or 0) * float(li.get("price") or 0)
    d = float(li.get("disc") or 0)
    if d > 0:
        amount *= (1 - d / 100.0)
    rate = tax_percent(li.get("tax_rate")) / 100.0
    if tax_type == "exclusive":
        return amount, amount * rate
    if tax_type == "inclusive":
        net = amount / (1 + rate) if rate else amount
        return net, amount - net
    return amount, 0.0


def document_pdf(doc, kind="invoice"):
    """The PDF bytes for a document dict (see pdf_document_data in main.py)."""
    cfg = DOC_TYPES.get(kind, DOC_TYPES["invoice"])
    th = doc.get("theme") or {}
    layout = doc.get("layout") or []
    normal, bold = FONTS.get(th.get("font") or "helvetica", FONTS["helvetica"])
    brand = hex_rgb(th.get("brand_color") or "#000000")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{doc.get('number') or cfg['heading'].title()}")
    c.setAuthor((doc.get("company") or {}).get("name") or "")

    state = {"y": 0.0, "page": 1, "in_table": False, "table_top": 0.0}

    def T(y):
        return H - y

    def visible(block_id):
        for b in layout:
            if isinstance(b, dict) and b.get("id") == block_id:
                return b.get("visible") is not False
        return True

    def text(s, x, y, font=None, size=None, colour=None, align="left"):
        if font or size:
            c.setFont(font or c._fontname, size or c._fontsize)
        if colour is not None:
            c.setFillColorRGB(*colour)
        s = "" if s is None else str(s)
        if align == "right":
            c.drawRightString(x, T(y), s)
        elif align == "center":
            c.drawCentredString(x, T(y), s)
        else:
            c.drawString(x, T(y), s)

    def grey(v):
        return (v / 255.0,) * 3

    def line(x1, x2, y, width=0.5):
        c.setLineWidth(width)
        c.line(x1, T(y), x2, T(y))

    def vline(x, y1, y2):
        c.line(x, T(y1), x, T(y2))

    def footer():
        c.setFont(normal, 8)
        c.setFillColorRGB(*grey(150))
        if th.get("footer_note"):
            c.drawCentredString(W / 2, T(H - 36), str(th["footer_note"])[:120])
        if th.get("show_page_numbers", True) is not False:
            c.drawCentredString(W / 2, T(H - 25), f"Page {state['page']}")

    # --- data, as the browser reads it off the screen ------------------------
    company = doc.get("company") or {}
    bill_to = doc.get("bill_to") or {}
    contact = doc.get("to") or ""
    cust_email = doc.get("email") or ""
    cust_phone = doc.get("phone_number") or ""
    issue_date = doc.get("date") or ""
    date_out = doc.get("date_out") or ""
    number = doc.get("number") or ""
    ref = doc.get("ref") or ""
    bank = doc.get("bank_details") or ""
    currency = (doc.get("currency") or "GBP").upper()
    raw_sym = doc.get("symbol") or currency
    cs = pdf_symbol(raw_sym)
    lines = doc.get("line_items") or []
    tax_type = doc.get("tax_type") or "exclusive"
    subtotal, tax_total = 0.0, 0.0
    rows = []
    for li in lines:
        net, tax = line_amounts(li, tax_type)
        subtotal += net
        tax_total += tax
        rows.append({
            "name": li.get("name") or "", "desc": li.get("description") or "",
            "qty": qty_text(li.get("qty")),
            "price": fmt(li.get("price")), "disc": float(li.get("disc") or 0),
            "tax": tax_percent(li.get("tax_rate")), "amount": fmt(net),
        })
    total_text = f"{fmt(subtotal + tax_total)} {currency}"
    logo = th.get("logo_data") or doc.get("logo") or ""
    signature = doc.get("signature") or ""
    terms = doc.get("terms") or ""

    # --- the page ---------------------------------------------------------------
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    y = 45.0

    # Logo: on the right, or in a band of its own when moved off it.
    logo_w = logo_h = 65
    logo_y = y - 5
    off_right = th.get("logo_position") in ("left", "center")
    logo_x = MR - logo_w
    if th.get("logo_position") == "left":
        logo_x = ML
    elif th.get("logo_position") == "center":
        logo_x = (W - logo_w) / 2
    img = image_reader(logo)
    if img is not None:
        try:
            c.drawImage(img, logo_x, T(logo_y + logo_h), logo_w, logo_h, mask="auto")
        except Exception:
            img = None
    if img is None and not logo:
        c.setStrokeColorRGB(100 / 255, 150 / 255, 200 / 255)
        c.setLineWidth(1)
        c.rect(logo_x, T(logo_y + logo_h), logo_w, logo_h, stroke=1, fill=0)
        text("LOGO", logo_x + logo_w / 2, logo_y + logo_h / 2 + 3, "Helvetica", 7,
             (120 / 255, 150 / 255, 180 / 255), align="center")
    if off_right:
        y += logo_h + 12

    # Right column: the company, under the logo.
    comp_y = y if off_right else (logo_y + logo_h + 8)
    comp_lines = []
    if company.get("name"):
        comp_lines.append(company["name"])
    for l in str(company.get("address") or "").split("\n"):
        if l.strip():
            comp_lines.append(l.strip())
    if company.get("phone_number"):
        p = str(company["phone_number"])
        comp_lines.append(p if p.startswith("Tel") else "Tel: " + p)
    if company.get("email"):
        comp_lines.append(company["email"])
    if company.get("abn"):
        a = str(company["abn"])
        comp_lines.append(a if ":" in a else "Tax ID: " + a)
    c.setFont("Helvetica", 7.5)
    c.setFillColorRGB(*grey(30))
    for l in comp_lines:
        for wl in wrap(l, "Helvetica", 7.5, logo_w + 10):
            c.drawRightString(MR, T(comp_y), wl)
            comp_y += 10

    # Left column: the title, in the brand colour.
    heading = cfg["heading"]
    if kind == "quote":
        heading = th.get("quote_title") or heading
    elif kind == "invoice":
        heading = th.get("approved_invoice_title") or heading
    text(heading, ML, y + 18, bold, 26, brand)

    # Centre column: date, number, reference.
    centre_x = W / 2 - 40
    meta_y = y
    text(cfg["date_label"], centre_x, meta_y + 8, "Helvetica", 8, grey(80))
    text(issue_date or "-", centre_x, meta_y + 19, "Helvetica", 9, (0, 0, 0))
    meta_y += 28
    text(cfg["number_label"], centre_x, meta_y + 8, "Helvetica", 8, grey(80))
    text(number or "-", centre_x, meta_y + 19, "Helvetica", 9, (0, 0, 0))
    if ref:
        meta_y += 28
        text("Reference", centre_x, meta_y + 8, "Helvetica", 8, grey(80))
        text(ref, centre_x, meta_y + 19, "Helvetica", 9, (0, 0, 0))

    # The customer, under the title.
    cust_y = y + 32
    cust_lines = [l.strip() for l in str(contact).split("\n") if l.strip()]
    if bill_to.get("company"):
        cust_lines.append(str(bill_to["company"]).strip())
    for l in str(bill_to.get("address") or "").split("\n"):
        if l.strip():
            cust_lines.append(l.strip())
    if cust_email and cust_email != "No email":
        cust_lines.append(cust_email)
    if cust_phone and cust_phone != "No phone":
        cust_lines.append(cust_phone)
    if bill_to.get("tax_id"):
        cust_lines.append("Tax ID: " + str(bill_to["tax_id"]).strip())
    c.setFont("Helvetica", 8.5)
    c.setFillColorRGB(*grey(30))
    for l in cust_lines:
        for wl in wrap(break_long(l, 45), "Helvetica", 8.5, centre_x - ML - 10):
            c.drawString(ML, T(cust_y), wl)
            cust_y += 11

    y = max(cust_y, comp_y) + 18

    # --- the table ----------------------------------------------------------------
    num_cols = []
    if th.get("show_quantity", True) is not False:
        num_cols.append({"k": "qty", "label": th.get("label_quantity") or "Quantity"})
    if th.get("show_price", True) is not False:
        num_cols.append({"k": "price", "label": th.get("label_price") or "Unit Price"})
    if th.get("show_discount"):
        num_cols.append({"k": "disc", "label": th.get("label_discount") or "Discount"})
    if th.get("show_tax"):
        num_cols.append({"k": "tax", "label": th.get("label_tax") or "Tax"})
    num_cols.append({"k": "amount", "label": (th.get("label_amount") or "Amount") + " " + currency})
    num_w = min(78, max(46, (MR - ML - 150) / len(num_cols)))
    desc_w = (MR - ML) - num_w * len(num_cols)
    for i, col in enumerate(num_cols):
        col["x"] = ML + desc_w + i * num_w
        col["w"] = num_w
    desc_x = ML

    def row_borders(start_y, end_y):
        c.setStrokeColorRGB(*grey(200))
        c.setLineWidth(0.5)
        vline(ML, start_y, end_y)
        vline(MR, start_y, end_y)
        for col in num_cols:
            vline(col["x"], start_y, end_y)

    def table_header():
        nonlocal y
        c.setStrokeColorRGB(0, 0, 0)
        line(ML, MR, y, 0.8)
        top = y
        y += 8
        head = ((th.get("label_item") or "Item") + " / " + (th.get("label_description") or "Description")) \
            if th.get("show_item") else (th.get("label_description") or "Description")
        text(head, desc_x + 4, y + 10, bold, 8.5, brand)
        for col in num_cols:
            text(col["label"], col["x"] + col["w"] - 4, y + 10, align="right")
        y += 14
        c.setStrokeColorRGB(0, 0, 0)
        line(ML, MR, y, 0.8)
        row_borders(top, y)
        state["table_top"] = y

    def page_break(need):
        nonlocal y
        if y + need > PAGE_BOTTOM:
            if state["in_table"]:
                row_borders(state["table_top"], y)
                c.setStrokeColorRGB(0, 0, 0)
                line(ML, MR, y, 0.8)
            footer()
            c.showPage()
            c.setFillColorRGB(1, 1, 1)
            c.rect(0, 0, W, H, fill=1, stroke=0)
            state["page"] += 1
            y = 45.0
            if state["in_table"]:
                table_header()

    c.setFillColorRGB(0, 0, 0)
    c.setStrokeColorRGB(0, 0, 0)
    table_header()

    state["in_table"] = True
    for row in rows:
        name_lines = wrap(break_long(row["name"] or "-", 50), "Helvetica-Bold", 8.5, desc_w - 8) if th.get("show_item") else []
        desc_lines = wrap(break_long(row["desc"], 60), "Helvetica", 8.5, desc_w - 8) if row["desc"] else []
        all_lines = [(l, True) for l in name_lines] + [(l, False) for l in desc_lines] or [("-", True)]
        row_start = y
        padding = 6
        y += padding
        first = True
        i = 0
        while i < len(all_lines):
            page_break(12)
            if y == state["table_top"]:
                row_start = y
                y += padding
            s, is_name = all_lines[i]
            text(s, desc_x + 4, y + 8, "Helvetica-Bold" if is_name else "Helvetica", 8.5,
                 (0, 0, 0) if is_name else grey(80))
            if first:
                c.setFont(normal, 8.5)
                c.setFillColorRGB(0, 0, 0)
                for col in num_cols:
                    v = row[col["k"]]
                    if col["k"] == "disc":
                        v = f"{row['disc']:g}%" if row["disc"] else "-"
                    elif col["k"] == "tax":
                        v = f"{row['tax']:g}%" if row["tax"] else "-"
                    c.drawRightString(col["x"] + col["w"] - 4, T(y + 8), str(v))
                first = False
            y += 11
            i += 1
            if y + 12 > PAGE_BOTTOM and i < len(all_lines):
                y += padding
                row_borders(row_start, y)
                c.setStrokeColorRGB(0, 0, 0)
                line(ML, MR, y, 0.8)
        y += padding
        row_borders(row_start, y)
        c.setStrokeColorRGB(*grey(200))
        line(ML, MR, y, 0.5)
    state["in_table"] = False
    c.setStrokeColorRGB(0, 0, 0)
    line(ML, MR, y, 0.8)

    if not rows:
        text("No items.", desc_x + 4, y + 11, "Helvetica", 8.5, grey(120))
        y += 18

    if cfg["bank"] and bank and visible("bank_details"):
        y += 4
        bk = wrap("Account Details for payment: " + str(bank).replace("\n", ", "), "Helvetica", 8, MR - ML - 10)
        page_break(len(bk) * 11 + 8)
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(*grey(50))
        for i, l in enumerate(bk):
            c.drawString(desc_x, T(y + 10 + i * 11), l)
        y += len(bk) * 11 + 8

    c.setStrokeColorRGB(0, 0, 0)
    line(ML, MR, y, 0.5)
    y += 10

    # --- totals, hung off the last column ----------------------------------------------
    page_break(70)
    last = num_cols[-1]
    label_x = last["x"] - 6
    val_x = MR

    def total_row(label, val, is_bold=False):
        nonlocal y
        c.setFont(bold if is_bold else normal, 8.5)
        c.setFillColorRGB(0, 0, 0)
        c.drawRightString(label_x, T(y + 10), label)
        c.drawRightString(val_x, T(y + 10), val)
        y += 14

    total_row("Subtotal", fmt(subtotal))
    total_row(tax_label_for(lines), fmt(tax_total))
    c.setStrokeColorRGB(0, 0, 0)
    line(label_x - 60, val_x, y - 2, 0.5)
    y += 4
    total_row("TOTAL  " + currency, total_text, True)
    y += 10

    if date_out:
        page_break(30)
        text(cfg["date_out_label"] + ": " + str(date_out), ML, y + 12, "Helvetica-Bold", 9, (0, 0, 0))
        y += 18

    if terms and visible("terms_conditions"):
        tl = wrap(str(terms).strip(), "Helvetica", 8, MR - ML)
        page_break(len(tl) * 11 + 10)
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(*grey(60))
        for i, l in enumerate(tl):
            c.drawString(ML, T(y + 11 + i * 11), l)
        y += len(tl) * 11 + 10

    sig = image_reader(signature) if signature and visible("signature") else None
    if sig is not None:
        page_break(70)
        y += 10
        try:
            c.drawImage(sig, MR - 140, T(y + 45), 140, 45, mask="auto")
        except Exception:
            pass
        c.setStrokeColorRGB(0, 0, 0)
        line(MR - 140, MR, y + 48, 0.5)
        text("Authorised Signature", MR - 140, y + 58, "Helvetica", 8, grey(80))
        y += 68

    y += 20

    # --- payment advice, the part to cut off and send back ------------------------------
    if cfg["payment_advice"] and visible("payment_stub"):
        page_break(90)
        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.5)
        c.setDash([4, 3], 0)
        c.line(ML, T(y), MR, T(y))
        c.setDash([], 0)
        text("-X-", ML - 2, y - 3, "Helvetica", 12, (0, 0, 0))
        y += 16
        text("PAYMENT ADVICE", ML, y + 14, "Helvetica-Bold", 18, (0, 0, 0))
        y += 24
        pa_right = W / 2 + 10
        text("Customer", ML, y + 11, "Helvetica-Bold", 8, (0, 0, 0))
        text(cfg["number_label"], pa_right, y + 11)
        y += 13
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(*grey(30))
        pa_lines = wrap(contact or "-", "Helvetica", 8, pa_right - ML - 20)
        for i, l in enumerate(pa_lines):
            c.drawString(ML, T(y + 10 + i * 11), l)
        c.drawString(pa_right, T(y + 10), number or "-")
        y += len(pa_lines) * 11 + 8
        text(cfg["total_label"], ML, y + 11, "Helvetica-Bold", 8, (0, 0, 0))
        text(cfg["date_out_label"], pa_right, y + 11)
        y += 13
        text(cs + total_text, ML, y + 11, "Helvetica-Bold", 10, (0, 0, 0))
        text(date_out or "-", pa_right, y + 11, "Helvetica", 9)
        y += 20

    footer()
    c.showPage()
    c.save()
    return buf.getvalue()
