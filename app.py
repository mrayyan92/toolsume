from flask import Flask, render_template, request, send_file, jsonify, url_for, Response
from PIL import Image, ImageDraw, ImageFont
from rembg import remove
from pyzbar.pyzbar import decode
import qrcode
from reportlab.lib.units import mm
import fitz  # PyMuPDF
import img2pdf
import pytesseract
from PyPDF2 import PdfMerger
import uuid
from pdf2docx import Converter
from PyPDF2 import PdfReader, PdfWriter
from pdf2image import convert_from_path
import zipfile
from reportlab.pdfgen import canvas
from reportlab.lib.colors import Color
from reportlab.lib.units import inch
import io
import subprocess
import tempfile
import logging
import platform
import re
import shutil
import threading
import time
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException
import os

# --- Platform-specific imports -------------------------------------------
# pythoncom (pywin32) and docx2pdf are Windows-only and docx2pdf additionally
# requires Microsoft Word. Importing them unconditionally makes the app
# impossible to boot on a Linux host.
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:
        import pythoncom
        from docx2pdf import convert as _docx2pdf_convert
        WORD_CONVERTER = "docx2pdf"
    except ImportError:
        pythoncom = None
        _docx2pdf_convert = None
        WORD_CONVERTER = None
else:
    pythoncom = None
    _docx2pdf_convert = None
    # On Linux we shell out to LibreOffice instead.
    WORD_CONVERTER = "libreoffice" if shutil.which("soffice") else None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB max upload

# Behind nginx / Cloudflare this makes request.url_root report the real
# https:// host, so canonical URLs and sitemap.xml are correct.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Return generic error messages to clients in production (no path leakage).
DEBUG_ERRORS = os.environ.get("TOOLHUB_DEBUG_ERRORS", "").lower() in ("1", "true", "yes")

# Guard against decompression-bomb images (default Pillow limit is ~89M px).
Image.MAX_IMAGE_PIXELS = 80_000_000

# How long a generated file stays downloadable before the janitor removes it.
OUTPUT_RETENTION_SECONDS = int(os.environ.get("TOOLHUB_RETENTION_SECONDS", 1800))

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


@app.template_filter("meta_content")
def meta_content(rendered_block):
    """Extract the content="..." value from a rendered <meta> block.

    The seo_description block contains only a void <meta> element, so
    |striptags returns an empty string - which is why every tool page was
    emitting "description": "" in its JSON-LD. This pulls the real text out
    and escapes it for safe embedding inside a JSON string literal.
    """
    match = re.search(r'content=["\'](.*?)["\']', str(rendered_block), re.S)
    text = match.group(1).strip() if match else ""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def safe_filename(filename):
    """Sanitize filename and prepend a UUID to prevent collisions and path traversal."""
    name = secure_filename(filename)
    if not name:
        name = "file"
    unique_name = f"{uuid.uuid4().hex}_{name}"
    return unique_name


def safe_delete(filepath):
    """Safely delete a file if it exists."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except OSError:
        pass


def error_response(exc, fallback="Something went wrong while processing your file."):
    """Never leak server paths / stack details to the client in production."""
    message = str(exc) if DEBUG_ERRORS else fallback
    return jsonify({"success": False, "message": message}), 500


def _sweep(folder, max_age):
    now = time.time()
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        path = os.path.join(folder, name)
        try:
            if now - os.path.getmtime(path) <= max_age:
                continue
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except OSError:
            pass


def _janitor():
    """Background cleanup.

    Generated files must survive long enough for the browser to follow the
    download_url we hand back, so they cannot be deleted in the request's
    `finally` block. This thread reclaims them once they are old enough.
    """
    while True:
        _sweep(OUTPUT_FOLDER, OUTPUT_RETENTION_SECONDS)
        _sweep(UPLOAD_FOLDER, OUTPUT_RETENTION_SECONDS)
        time.sleep(300)


# ================= ERROR HANDLERS =================

@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/download/") or request.accept_mimetypes.best == "application/json":
        return jsonify({"success": False, "message": "Not found."}), 404
    return render_template("errors/404.html"), 404


@app.errorhandler(413)
def handle_413(e):
    return jsonify({
        "success": False,
        "message": "File is too large. Maximum upload size is 100 MB."
    }), 413


@app.errorhandler(500)
def handle_500(e):
    return render_template("errors/500.html"), 500


@app.errorhandler(Exception)
def handle_unexpected(e):
    if isinstance(e, HTTPException):
        return e
    logger.exception("Unhandled error on %s", request.path)
    if request.method == "POST":
        return jsonify({
            "success": False,
            "message": "Something went wrong while processing your file."
        }), 500
    return render_template("errors/500.html"), 500


# ================= ROBOTS.TXT =================

@app.route("/robots.txt")
def robots_txt():
    robots_content = """User-agent: *
Allow: /
Disallow: /compress-image
Disallow: /remove-background
Disallow: /convert-pdf
Disallow: /convert-word
Disallow: /watermark-pdf-file
Disallow: /scan-qr-file
Disallow: /generate-qr
Disallow: /image-watermark-file
Disallow: /crop-image-file
Disallow: /rotate-image-file
Disallow: /flip-image-file
Disallow: /resize-image-file
Disallow: /convert-png-jpg
Disallow: /convert-jpg-png
Disallow: /image-to-webp-file
Disallow: /webp-to-jpg-file
Disallow: /webp-to-png-file
Disallow: /convert-jpg
Disallow: /rotate-pdf-file
Disallow: /protect-pdf-file
Disallow: /unlock-pdf-file
Disallow: /convert-pdf-jpg
Disallow: /compress-pdf-file
Disallow: /split-pdf-file
Disallow: /extract-pdf-file
Disallow: /delete-pdf-pages-file
Disallow: /add-page-numbers-file
Disallow: /merge-pdf-file
Disallow: /uploads/
Disallow: /outputs/

Sitemap: {}/sitemap.xml""".format(request.url_root.rstrip('/'))
    return Response(robots_content, mimetype='text/plain')


# ================= SITEMAP =================

@app.route("/sitemap.xml")
def sitemap():
    base = request.url_root.rstrip('/')
    pages = [
        ("", "1.0", "daily"),
        ("pdf-tools", "0.8", "weekly"),
        ("image-tools", "0.8", "weekly"),
        ("utility-tools", "0.8", "weekly"),
        ("about", "0.6", "monthly"),
        ("contact", "0.6", "monthly"),
        ("privacy", "0.4", "monthly"),
        ("terms", "0.4", "monthly"),
        ("disclaimer", "0.4", "monthly"),
        ("pdf-to-word", "0.9", "weekly"),
        ("word-to-pdf", "0.9", "weekly"),
        ("merge-pdf", "0.9", "weekly"),
        ("split-pdf", "0.9", "weekly"),
        ("compress-pdf", "0.9", "weekly"),
        ("rotate-pdf", "0.7", "weekly"),
        ("watermark-pdf", "0.7", "monthly"),
        ("protect-pdf", "0.7", "monthly"),
        ("unlock-pdf", "0.7", "monthly"),
        ("pdf-to-jpg", "0.8", "weekly"),
        ("extract-pdf", "0.7", "monthly"),
        ("delete-pdf-pages", "0.7", "monthly"),
        ("add-page-numbers", "0.7", "monthly"),
        ("compressor", "0.9", "weekly"),
        ("remover", "0.9", "weekly"),
        ("crop-image", "0.8", "weekly"),
        ("rotate-image", "0.7", "monthly"),
        ("flip-image", "0.7", "monthly"),
        ("resize-image", "0.8", "weekly"),
        ("image-watermark", "0.7", "monthly"),
        ("image-to-text", "0.8", "weekly"),
        ("image-to-webp", "0.7", "monthly"),
        ("webp-to-jpg", "0.7", "monthly"),
        ("webp-to-png", "0.7", "monthly"),
        ("jpg-to-pdf", "0.8", "weekly"),
        ("jpg-to-png", "0.8", "weekly"),
        ("png-to-jpg", "0.8", "weekly"),
        ("uuid-generator", "0.7", "monthly"),
        ("password-generator", "0.8", "weekly"),
        ("password-strength-checker", "0.7", "monthly"),
        ("qr-generator", "0.8", "weekly"),
        ("qr-scanner", "0.7", "monthly"),
        ("word-counter", "0.7", "monthly"),
        ("lorem-ipsum-generator", "0.7", "monthly"),
    ]
    lastmod = time.strftime("%Y-%m-%d", time.gmtime(os.path.getmtime(__file__)))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for path, priority, changefreq in pages:
        xml += '  <url>\n'
        xml += '    <loc>{}/{}</loc>\n'.format(base, path)
        xml += '    <lastmod>{}</lastmod>\n'.format(lastmod)
        xml += '    <changefreq>{}</changefreq>\n'.format(changefreq)
        xml += '    <priority>{}</priority>\n'.format(priority)
        xml += '  </url>\n'
    xml += '</urlset>'
    return Response(xml, mimetype='application/xml')


# ================= HOME =================

@app.route("/")
def index():
    return render_template("pages/index.html")



# ================= IMAGE COMPRESSOR =================


@app.route("/compressor")
def compressor():
    return render_template("tools/compressor.html")


@app.route("/compress-image", methods=["POST"])
def compress_image():

    if "image" not in request.files:
        return jsonify({"success": False, "message": "No image uploaded."}), 400

    file = request.files["image"]

    if file.filename == "":
        return jsonify({"success": False, "message": "No file selected."}), 400

    try:
        quality = int(request.form.get("quality", 70))
        quality = max(1, min(quality, 100))
    except (ValueError, TypeError):
        return jsonify({"success": False, "message": "Invalid quality value."}), 400

    filename = safe_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(input_path)

    try:
        img = Image.open(input_path)

        if img.mode == "RGBA" and not filename.lower().endswith((".webp",)):
            img = img.convert("RGB")

        # Build the result in memory so there is no temp file to race against.
        buffer = io.BytesIO()
        img.save(buffer, format=img.format or "JPEG", optimize=True, quality=quality)
        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name=os.path.basename(file.filename) or "compressed",
            mimetype=Image.MIME.get(img.format, "application/octet-stream")
        )
    except Exception as e:
        logger.error("Compress image error: %s", e)
        return jsonify({"success": False, "message": "Failed to compress image."}), 500
    finally:
        safe_delete(input_path)


# ================= BACKGROUND REMOVER =================

@app.route("/remover")
def remover():
    return render_template("tools/remover.html")


@app.route("/remove-background", methods=["POST"])
def remove_background():

    if "image" not in request.files:
        return jsonify({"success": False, "message": "No image uploaded."}), 400

    file = request.files["image"]

    if file.filename == "":
        return jsonify({"success": False, "message": "No file selected."}), 400

    filename = safe_filename(file.filename)
    input_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(input_path)

    try:
        with open(input_path, "rb") as f:
            input_data = f.read()

        output_data = remove(input_data)

        download_name = os.path.splitext(os.path.basename(file.filename))[0] + ".png"

        return send_file(
            io.BytesIO(output_data),
            as_attachment=True,
            download_name=download_name,
            mimetype="image/png"
        )
    except Exception as e:
        logger.error("Remove background error: %s", e)
        return jsonify({"success": False, "message": "Failed to remove background."}), 500
    finally:
        safe_delete(input_path)


# ================= PDF TO WORD =================

@app.route("/pdf-to-word")
def pdf_to_word():
    return render_template("tools/pdf_to_word.html")

@app.route("/word-to-pdf")
def word_to_pdf():
    return render_template("tools/word_to_pdf.html")

@app.route("/convert-word", methods=["POST"])
def convert_word():

    if WORD_CONVERTER is None:
        return jsonify({
            "success": False,
            "message": "Word to PDF conversion is not available on this server."
        }), 503

    if pythoncom is not None:
        pythoncom.CoInitialize()

    word_path = None

    try:

        if "word" not in request.files:
            return jsonify({
                "success": False,
                "message": "No Word file uploaded."
            })

        file = request.files["word"]

        if file.filename == "":
            return jsonify({
                "success": False,
                "message": "No file selected."
            })

        filename = safe_filename(file.filename)

        word_path = os.path.join(UPLOAD_FOLDER, filename)

        pdf_filename = os.path.splitext(filename)[0] + ".pdf"

        pdf_path = os.path.join(OUTPUT_FOLDER, pdf_filename)

        file.save(word_path)

        if WORD_CONVERTER == "docx2pdf":
            _docx2pdf_convert(word_path, pdf_path)
        else:
            # LibreOffice writes <name>.pdf into --outdir; it cannot be told
            # the exact output filename.
            subprocess.run([
                "soffice", "--headless", "--convert-to", "pdf",
                "--outdir", OUTPUT_FOLDER, word_path
            ], check=True, timeout=180)
            produced = os.path.join(
                OUTPUT_FOLDER,
                os.path.splitext(os.path.basename(word_path))[0] + ".pdf"
            )
            if produced != pdf_path and os.path.exists(produced):
                os.replace(produced, pdf_path)

        if not os.path.exists(pdf_path):
            raise RuntimeError("Conversion produced no output file.")

        return jsonify({

            "success": True,

            "filename": pdf_filename,

            "download_url": url_for(
                "download_file",
                filename=pdf_filename
            )

        })

    except Exception as e:

        return error_response(e)

    finally:
        if word_path:
            safe_delete(word_path)

        if pythoncom is not None:
            pythoncom.CoUninitialize()


@app.route("/convert-pdf", methods=["POST"])
def convert_pdf():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    pdf_path = os.path.join(UPLOAD_FOLDER, filename)

    docx_filename = os.path.splitext(filename)[0] + ".docx"

    docx_path = os.path.join(OUTPUT_FOLDER, docx_filename)

    file.save(pdf_path)

    try:
        cv = Converter(pdf_path)
        cv.convert(docx_path)
        cv.close()

        return jsonify({
            "success": True,
            "filename": docx_filename,
            "download_url": url_for(
                "download_file",
                filename=docx_filename
            )
        })

    except Exception as e:
        logger.error("Convert PDF error: %s", e)
        return error_response(e)

    finally:
        safe_delete(pdf_path)


@app.route("/download/<filename>")
def download_file(filename):

    safe_name = secure_filename(filename)
    if not safe_name or safe_name != filename:
        return "Invalid filename.", 400

    file_path = os.path.join(OUTPUT_FOLDER, safe_name)

    real_output = os.path.realpath(OUTPUT_FOLDER)
    real_file = os.path.realpath(file_path)

    if not real_file.startswith(real_output):
        return "Access denied.", 403

    if not os.path.exists(file_path):
        return "File not found.", 404

    return send_file(file_path, as_attachment=True)


# ================= WATERMARK PDF =================

@app.route("/watermark-pdf")
def watermark_pdf():
    return render_template("tools/watermark_pdf.html")


@app.route("/watermark-pdf-file", methods=["POST"])
def watermark_pdf_file():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    watermark_text = request.form.get("watermark")

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    if not watermark_text:
        return jsonify({
            "success": False,
            "message": "Please enter watermark text."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    output_path = None

    file.save(input_path)

    try:
        reader = PdfReader(input_path)

        writer = PdfWriter()

        packet = io.BytesIO()

        first_page = reader.pages[0]

        page_width = float(first_page.mediabox.width)

        page_height = float(first_page.mediabox.height)

        c = canvas.Canvas(
            packet,
            pagesize=(page_width, page_height)
        )

        c.saveState()

        c.setFont("Helvetica-Bold", 40)

        c.setFillColor(Color(
            0.6,
            0.6,
            0.6,
            alpha=0.30
        ))

        c.translate(
            page_width / 2,
            page_height / 2
        )

        c.rotate(45)

        c.drawCentredString(
            0,
            0,
            watermark_text
        )

        c.restoreState()

        c.save()

        packet.seek(0)

        watermark_pdf = PdfReader(packet)

        watermark_page = watermark_pdf.pages[0]

        for page in reader.pages:

            page.merge_page(watermark_page)

            writer.add_page(page)

        output_name = "watermarked_" + filename

        output_path = os.path.join(
            OUTPUT_FOLDER,
            output_name
        )

        with open(output_path, "wb") as output_file:

            writer.write(output_file)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Watermark PDF error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

    # ================= UUID GENERATOR =================

@app.route("/uuid-generator")
def uuid_generator():

    return render_template("tools/uuid_generator.html")

# ================= LOREM IPSUM GENERATOR =================

@app.route("/lorem-ipsum-generator")
def lorem_ipsum_generator():

    return render_template("tools/lorem_ipsum_generator.html")

# ================= WORD COUNTER =================

@app.route("/word-counter")
def word_counter():

    return render_template("tools/word_counter.html")
    

    # ================= MERGE PDF =================

@app.route("/merge-pdf")
def merge_pdf():
    return render_template("tools/merge_pdf.html")


@app.route("/merge-pdf-file", methods=["POST"])
def merge_pdf_file():

    if "pdfs" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF files uploaded."
        })

    files = request.files.getlist("pdfs")

    if len(files) < 2:
        return jsonify({
            "success": False,
            "message": "Please select at least two PDF files."
        })

    output_path = None

    saved_files = []

    try:
        merger = PdfMerger()

        valid_count = 0

        for file in files:

            if file.filename == "":
                continue

            filename = safe_filename(file.filename)

            input_path = os.path.join(
                UPLOAD_FOLDER,
                filename
            )

            file.save(input_path)

            saved_files.append(input_path)

            merger.append(input_path)

            valid_count += 1

        if valid_count < 2:
            return jsonify({
                "success": False,
                "message": "Please select at least two valid PDF files."
            })

        output_name = "merged_" + uuid.uuid4().hex[:8] + ".pdf"

        output_path = os.path.join(
            OUTPUT_FOLDER,
            output_name
        )

        merger.write(output_path)

        merger.close()

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Merge PDF error: %s", e)
        return error_response(e)

    finally:
        for f in saved_files:
            safe_delete(f)
    
    # ================= IMAGE WATERMARK =================

@app.route("/image-watermark")
def image_watermark():

    return render_template("tools/image_watermark.html")


@app.route("/image-watermark-file", methods=["POST"])
def image_watermark_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        image = Image.open(input_path).convert("RGBA")

        watermark_text = request.form.get("watermark", "ToolHub")

        position = request.form.get("position", "bottom-right")

        draw = ImageDraw.Draw(image)

        font = ImageFont.load_default()

        left, top, right, bottom = draw.textbbox(
            (0, 0),
            watermark_text,
            font=font
        )

        text_width = right - left

        text_height = bottom - top

        margin = 20

        positions = {
            "top-left": (margin, margin),
            "top-right": (image.width - text_width - margin, margin),
            "center": ((image.width - text_width) // 2, (image.height - text_height) // 2),
            "bottom-left": (margin, image.height - text_height - margin),
            "bottom-right": (image.width - text_width - margin, image.height - text_height - margin)
        }

        x, y = positions.get(position, positions["bottom-right"])

        draw.text(
            (x, y),
            watermark_text,
            fill=(255, 255, 255, 180),
            font=font
        )

        output_name = "watermarked_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        extension = os.path.splitext(filename)[1].lower()

        if extension in [".jpg", ".jpeg"]:
            image = image.convert("RGB")
            image.save(output_path, quality=95, optimize=True)
        elif extension == ".png":
            image.save(output_path, optimize=True)
        elif extension == ".webp":
            image.save(output_path, "WEBP", quality=95)
        else:
            image.save(output_path)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Image watermark error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    
   
    
    # ================= QR CODE SCANNER =================

@app.route("/qr-scanner")
def qr_scanner():

    return render_template("tools/qr_scanner.html")


@app.route("/scan-qr-file", methods=["POST"])
def scan_qr_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No QR image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        image = Image.open(input_path)

        qr_codes = decode(image)

        if not qr_codes:
            return jsonify({
                "success": False,
                "message": "No QR Code found in the uploaded image."
            })

        qr_text = qr_codes[0].data.decode("utf-8")

        return jsonify({
            "success": True,
            "message": qr_text
        })

    except Exception as e:
        logger.error("QR scanner error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)

        # ================= PASSWORD GENERATOR =================

@app.route("/password-generator")
def password_generator():

    return render_template("tools/password_generator.html")

# ================= PASSWORD STRENGTH CHECKER =================

@app.route("/password-strength-checker")
def password_strength_checker():

    return render_template("tools/password_strength_checker.html")
    # ================= CROP IMAGE =================

@app.route("/crop-image")
def crop_image():

    return render_template("tools/crop_image.html")


@app.route("/crop-image-file", methods=["POST"])
def crop_image_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        x = int(request.form["x"])
        y = int(request.form["y"])
        width = int(request.form["width"])
        height = int(request.form["height"])

        image = Image.open(input_path)

        image_width, image_height = image.size

        if x < 0 or y < 0:
            return jsonify({
                "success": False,
                "message": "X and Y must be zero or greater."
            })

        if width <= 0 or height <= 0:
            return jsonify({
                "success": False,
                "message": "Width and Height must be greater than zero."
            })

        if x + width > image_width or y + height > image_height:
            return jsonify({
                "success": False,
                "message": f"Crop area exceeds image size ({image_width} x {image_height})."
            })

        cropped = image.crop((x, y, x + width, y + height))

        output_name = "cropped_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        save_kwargs = {}

        if output_name.lower().endswith((".jpg", ".jpeg")):
            if cropped.mode == "RGBA":
                cropped = cropped.convert("RGB")
            save_kwargs["quality"] = 95
            save_kwargs["optimize"] = True

        cropped.save(output_path, **save_kwargs)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except (ValueError, KeyError):
        return jsonify({
            "success": False,
            "message": "Please enter valid numeric crop values."
        })

    except Exception as e:
        logger.error("Crop image error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

    # ================= ROTATE IMAGE =================

@app.route("/rotate-image")
def rotate_image():

    return render_template("tools/rotate_image.html")


@app.route("/rotate-image-file", methods=["POST"])
def rotate_image_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        image = Image.open(input_path)

        rotation = request.form.get("rotation", "90")

        if rotation == "custom":
            angle = float(request.form.get("custom_angle", 0))
        else:
            angle = float(rotation)

        rotated = image.rotate(
            -angle,
            expand=True,
            resample=Image.BICUBIC
        )

        output_name = "rotated_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        save_kwargs = {}

        if output_name.lower().endswith((".jpg", ".jpeg")):
            if rotated.mode == "RGBA":
                rotated = rotated.convert("RGB")
            save_kwargs["quality"] = 95
            save_kwargs["optimize"] = True

        rotated.save(output_path, **save_kwargs)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except ValueError:
        return jsonify({
            "success": False,
            "message": "Please enter a valid rotation angle."
        })

    except Exception as e:
        logger.error("Rotate image error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)


        # ================= IMAGE TO TEXT OCR =================

# ===========================
# IMAGE TO TEXT (OCR)
# ===========================

@app.route("/image-to-text", methods=["GET", "POST"])
def image_to_text():

    if request.method == "GET":
        return render_template("tools/image_to_text.html")

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "Please select an image."
        })

    filename = safe_filename(file.filename)

    upload_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(upload_path)

    try:
        image = Image.open(upload_path)

        image = image.convert("L")

        image = image.point(lambda x: 0 if x < 150 else 255)

        extracted_text = pytesseract.image_to_string(image, lang="eng")

        return jsonify({
            "success": True,
            "text": extracted_text
        })

    except Exception as e:
        logger.error("OCR error: %s", e)
        return jsonify({
            "success": False,
            "message": "An error occurred while processing the image."
        }), 500

    finally:
        safe_delete(upload_path)

        # ================= FLIP IMAGE =================

@app.route("/flip-image")
def flip_image():

    return render_template("tools/flip_image.html")


@app.route("/flip-image-file", methods=["POST"])
def flip_image_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        image = Image.open(input_path)

        direction = request.form.get("direction", "horizontal")

        if direction == "horizontal":
            flipped = image.transpose(Image.FLIP_LEFT_RIGHT)
        elif direction == "vertical":
            flipped = image.transpose(Image.FLIP_TOP_BOTTOM)
        else:
            return jsonify({
                "success": False,
                "message": "Invalid flip direction."
            })

        output_name = "flipped_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        save_kwargs = {}

        if output_name.lower().endswith((".jpg", ".jpeg")):
            if flipped.mode == "RGBA":
                flipped = flipped.convert("RGB")
            save_kwargs["quality"] = 95
            save_kwargs["optimize"] = True

        flipped.save(output_path, **save_kwargs)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Flip image error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    
    # ================= QR CODE GENERATOR =================

@app.route("/qr-generator")
def qr_generator():

    return render_template("tools/qr_generator.html")


@app.route("/generate-qr", methods=["POST"])
def generate_qr():

    output_path = None

    try:

        data = request.form.get("data", "").strip()

        if data == "":
            return jsonify({
                "success": False,
                "message": "Please enter some text."
            })

        box_size = int(request.form.get("size", 8))

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=box_size,
            border=4
        )

        qr.add_data(data)
        qr.make(fit=True)

        image = qr.make_image(
            fill_color="black",
            back_color="white"
        )

        output_name = "qr_code_" + uuid.uuid4().hex[:8] + ".png"

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        image.save(output_path)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("QR generator error: %s", e)
        return error_response(e)

        # ================= IMAGE TO WEBP =================

@app.route("/image-to-webp")
def image_to_webp():

    return render_template("tools/image_to_webp.html")


@app.route("/image-to-webp-file", methods=["POST"])
def image_to_webp_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    try:
        quality = int(request.form.get("quality", 90))
        quality = max(1, min(quality, 100))
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid quality value."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        image = Image.open(input_path)

        output_name = os.path.splitext(filename)[0] + ".webp"

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGB")

        image.save(output_path, "WEBP", quality=quality, method=6)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Image to WebP error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

    # ================= WEBP TO JPG =================

@app.route("/webp-to-jpg")
def webp_to_jpg():

    return render_template("tools/webp_to_jpg.html")


@app.route("/webp-to-jpg-file", methods=["POST"])
def webp_to_jpg_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No WebP image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    try:
        quality = int(request.form.get("quality", 95))
        quality = max(1, min(quality, 100))
    except (ValueError, TypeError):
        return jsonify({
            "success": False,
            "message": "Invalid quality value."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        image = Image.open(input_path)

        if image.mode in ("RGBA", "LA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        output_name = os.path.splitext(filename)[0] + ".jpg"

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        image.save(output_path, "JPEG", quality=quality, optimize=True)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("WebP to JPG error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

    # ================= WEBP TO PNG =================

@app.route("/webp-to-png")
def webp_to_png():

    return render_template("tools/webp_to_png.html")


@app.route("/webp-to-png-file", methods=["POST"])
def webp_to_png_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No WebP image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        image = Image.open(input_path)

        if image.mode not in ("RGBA", "RGB"):
            image = image.convert("RGBA")

        output_name = os.path.splitext(filename)[0] + ".png"

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        image.save(output_path, "PNG", optimize=True)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("WebP to PNG error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
        # ================= JPG TO PDF =================

@app.route("/jpg-to-pdf")
def jpg_to_pdf():
    return render_template("tools/jpg_to_pdf.html")



@app.route("/convert-jpg", methods=["POST"])
def convert_jpg():

    if "images" not in request.files:
        return jsonify({
            "success": False,
            "message": "No images uploaded."
        })

    files = request.files.getlist("images")

    image_paths = []

    try:

        for file in files:

            if file.filename == "":
                continue

            filename = safe_filename(file.filename)

            image_path = os.path.join(UPLOAD_FOLDER, filename)

            file.save(image_path)

            image_paths.append(image_path)

        if len(image_paths) == 0:

            return jsonify({
                "success": False,
                "message": "No valid images selected."
            })

        output_name = "converted_images_" + uuid.uuid4().hex[:8] + ".pdf"

        output_pdf = os.path.join(OUTPUT_FOLDER, output_name)

        with open(output_pdf, "wb") as f:

            f.write(img2pdf.convert(image_paths))

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("JPG to PDF error: %s", e)
        return error_response(e)

    finally:
        for p in image_paths:
            safe_delete(p)
    

    # ================= ROTATE PDF =================

@app.route("/rotate-pdf")
def rotate_pdf():
    return render_template("tools/rotate_pdf.html")


@app.route("/rotate-pdf-file", methods=["POST"])
def rotate_pdf_file():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    output_path = None

    file.save(input_path)

    try:
        angle = int(request.form.get("angle", 90))

        if angle not in (90, 180, 270):
            return jsonify({
                "success": False,
                "message": "Angle must be 90, 180, or 270."
            })

        reader = PdfReader(input_path)

        writer = PdfWriter()

        for page in reader.pages:
            page.rotate(angle)
            writer.add_page(page)

        output_name = "rotated_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Rotate PDF error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

    # ================= PROTECT PDF =================

@app.route("/protect-pdf")
def protect_pdf():
    return render_template("tools/protect_pdf.html")


@app.route("/protect-pdf-file", methods=["POST"])
def protect_pdf_file():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    password = request.form.get("password")

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    if not password:
        return jsonify({
            "success": False,
            "message": "Please enter a password."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    output_path = None

    file.save(input_path)

    try:
        reader = PdfReader(input_path)

        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(password)

        output_name = "protected_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Protect PDF error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

    # ================= UNLOCK PDF =================

@app.route("/unlock-pdf")
def unlock_pdf():
    return render_template("tools/unlock_pdf.html")


@app.route("/unlock-pdf-file", methods=["POST"])
def unlock_pdf_file():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    password = request.form.get("password")

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    if not password:
        return jsonify({
            "success": False,
            "message": "Please enter the PDF password."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    output_path = None

    file.save(input_path)

    try:
        reader = PdfReader(input_path)

        if reader.is_encrypted:
            success = reader.decrypt(password)
            if success == 0:
                return jsonify({
                    "success": False,
                    "message": "Incorrect password."
                })

        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        output_name = "unlocked_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Unlock PDF error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

# ================= PDF TO JPG =================

from pdf2image import convert_from_path
import zipfile

@app.route("/pdf-to-jpg")
def pdf_to_jpg():
    return render_template("tools/pdf_to_jpg.html")


@app.route("/convert-pdf-jpg", methods=["POST"])
def convert_pdf_jpg():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    pdf_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(pdf_path)

    output_folder = None

    zip_path = None

    try:
        poppler_path = os.environ.get("POPPLER_PATH", None)
        convert_kwargs = {}
        if poppler_path:
            convert_kwargs["poppler_path"] = poppler_path

        images = convert_from_path(pdf_path, **convert_kwargs)

        output_folder = os.path.join(
            OUTPUT_FOLDER,
            os.path.splitext(filename)[0]
        )

        os.makedirs(output_folder, exist_ok=True)

        for i, image in enumerate(images):
            image.save(
                os.path.join(output_folder, f"page_{i+1}.jpg"),
                "JPEG"
            )

        zip_name = os.path.splitext(filename)[0] + ".zip"

        zip_path = os.path.join(OUTPUT_FOLDER, zip_name)

        with zipfile.ZipFile(zip_path, "w") as zipf:
            for image_file in os.listdir(output_folder):
                zipf.write(
                    os.path.join(output_folder, image_file),
                    image_file
                )

        return jsonify({
            "success": True,
            "filename": zip_name,
            "download_url": url_for(
                "download_file",
                filename=zip_name
            )
        })

    except Exception as e:
        logger.error("PDF to JPG error: %s", e)
        return error_response(e)

    finally:
        safe_delete(pdf_path)
        if output_folder and os.path.exists(output_folder):
            import shutil
            shutil.rmtree(output_folder, ignore_errors=True)


    # ================= COMPRESS PDF =================

@app.route("/compress-pdf")
def compress_pdf():
    return render_template("tools/compress_pdf.html")


@app.route("/compress-pdf-file", methods=["POST"])
def compress_pdf_file():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    output_path = None

    file.save(input_path)

    try:
        output_name = "compressed_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        default_gs = (
            r"C:\Program Files\gs\gs10.07.1\bin\gswin64c.exe"
            if IS_WINDOWS else "gs"
        )
        gs_path = os.environ.get("GHOSTSCRIPT_PATH", default_gs)

        subprocess.run([
            gs_path,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={output_path}",
            input_path
        ], check=True, timeout=180)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Compress PDF error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)


# ================= PNG TO JPG =================

@app.route("/png-to-jpg")
def png_to_jpg():
    return render_template("tools/png_to_jpg.html")


@app.route("/convert-png-jpg", methods=["POST"])
def convert_png_jpg():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PNG uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        output_name = os.path.splitext(filename)[0] + ".jpg"

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        image = Image.open(input_path)

        if image.mode in ("RGBA", "LA", "P"):
            rgb = Image.new("RGB", image.size, (255, 255, 255))
            rgb.paste(
                image,
                mask=image.split()[-1] if image.mode == "RGBA" else None
            )
            image = rgb
        else:
            image = image.convert("RGB")

        image.save(output_path, "JPEG", quality=95)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("PNG to JPG error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    
    # ================= JPG TO PNG =================

@app.route("/jpg-to-png")
def jpg_to_png():
    return render_template("tools/jpg_to_png.html")


@app.route("/convert-jpg-png", methods=["POST"])
def convert_jpg_png():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No JPG uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        output_name = os.path.splitext(filename)[0] + ".png"

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        image = Image.open(input_path)

        image.save(output_path, "PNG")

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("JPG to PNG error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

# ================= MERGE PDF =================


# ================= SPLIT PDF =================

@app.route("/split-pdf")
def split_pdf():

    return render_template("tools/split_pdf.html")


@app.route("/split-pdf-file", methods=["POST"])
def split_pdf_file():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    page_range = request.form.get("page_range")

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    if not page_range:
        return jsonify({
            "success": False,
            "message": "Please enter a page range."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    output_path = None

    file.save(input_path)

    try:
        reader = PdfReader(input_path)

        total_pages = len(reader.pages)

        if "-" not in page_range:
            return jsonify({
                "success": False,
                "message": "Use page range like 1-5."
            })

        start, end = page_range.split("-")

        start = int(start)
        end = int(end)

        if start < 1 or end > total_pages or start > end:
            return jsonify({
                "success": False,
                "message": f"Enter pages between 1 and {total_pages}."
            })

        writer = PdfWriter()

        for i in range(start - 1, end):
            writer.add_page(reader.pages[i])

        output_name = "split_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except ValueError:
        return jsonify({
            "success": False,
            "message": "Invalid page range. Example: 1-5"
        })

    except Exception as e:
        logger.error("Split PDF error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

    # ================= EXTRACT PDF PAGES =================

@app.route("/extract-pdf")
def extract_pdf():

    return render_template("tools/extract_pdf.html")


@app.route("/extract-pdf-file", methods=["POST"])
def extract_pdf_file():

    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    pages_input = request.form.get("pages")

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    if not pages_input:
        return jsonify({
            "success": False,
            "message": "Please enter page numbers."
        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    output_path = None

    file.save(input_path)

    try:
        reader = PdfReader(input_path)

        total_pages = len(reader.pages)

        writer = PdfWriter()

        selected_pages = []

        parts = pages_input.split(",")

        for part in parts:
            part = part.strip()

            if "-" in part:
                start, end = part.split("-")
                start = int(start)
                end = int(end)

                if start < 1 or end > total_pages or start > end:
                    return jsonify({
                        "success": False,
                        "message": f"Pages must be between 1 and {total_pages}."
                    })

                for page in range(start, end + 1):
                    if page not in selected_pages:
                        selected_pages.append(page)
            else:
                page = int(part)
                if page < 1 or page > total_pages:
                    return jsonify({
                        "success": False,
                        "message": f"Pages must be between 1 and {total_pages}."
                    })
                if page not in selected_pages:
                    selected_pages.append(page)

        for page in selected_pages:
            writer.add_page(reader.pages[page - 1])

        output_name = "extracted_pages_" + uuid.uuid4().hex[:8] + ".pdf"

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        with open(output_path, "wb") as output_file:
            writer.write(output_file)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except ValueError:
        return jsonify({
            "success": False,
            "message": "Invalid input. Examples: 1,3,5 or 2-4"
        })

    except Exception as e:
        logger.error("Extract PDF error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    

    # ================= DELETE PDF PAGES =================

@app.route("/delete-pdf-pages")
def delete_pdf_pages():

    return render_template("tools/delete_pdf_pages.html")


@app.route("/delete-pdf-pages-file", methods=["POST"])
def delete_pdf_pages_file():

    if "pdf" not in request.files:

        return jsonify({

            "success": False,

            "message": "No PDF uploaded."

        })

    file = request.files["pdf"]

    pages_input = request.form.get("pages")

    if file.filename == "":

        return jsonify({

            "success": False,

            "message": "No file selected."

        })

    if not pages_input:

        return jsonify({

            "success": False,

            "message": "Please enter page numbers."

        })

    filename = safe_filename(file.filename)

    input_path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    output_path = None

    file.save(input_path)

    try:

        reader = PdfReader(input_path)

        total_pages = len(reader.pages)

        pages_to_delete = set()

        parts = pages_input.split(",")

        for part in parts:

            part = part.strip()

            if "-" in part:

                start, end = part.split("-")

                start = int(start)

                end = int(end)

                if start < 1 or end > total_pages or start > end:

                    return jsonify({

                        "success": False,

                        "message": f"Pages must be between 1 and {total_pages}."

                    })

                for page in range(start, end + 1):

                    pages_to_delete.add(page)

            else:

                page = int(part)

                if page < 1 or page > total_pages:

                    return jsonify({

                        "success": False,

                        "message": f"Pages must be between 1 and {total_pages}."

                    })

                pages_to_delete.add(page)

        if len(pages_to_delete) == total_pages:

            return jsonify({

                "success": False,

                "message": "You cannot delete all pages from the PDF."

            })

        writer = PdfWriter()

        for page_number in range(1, total_pages + 1):

            if page_number not in pages_to_delete:

                writer.add_page(reader.pages[page_number - 1])

        output_name = "pages_deleted_" + uuid.uuid4().hex[:8] + ".pdf"

        output_path = os.path.join(
            OUTPUT_FOLDER,
            output_name
        )

        with open(output_path, "wb") as output_file:

            writer.write(output_file)

        return jsonify({

            "success": True,

            "filename": output_name,

            "download_url": url_for(

                "download_file",

                filename=output_name

            )

        })

    except ValueError:

        return jsonify({

            "success": False,

            "message": "Invalid input. Examples: 2,5 or 3-6"

        })

    except Exception as e:

        logger.error("Delete PDF pages error: %s", e)

        return error_response(e)

    finally:
        safe_delete(input_path)
    


    # ================= ADD PAGE NUMBERS =================
@app.route("/add-page-numbers")
def add_page_numbers():

    return render_template("tools/add_page_numbers.html")


@app.route("/add-page-numbers-file", methods=["POST"])
def add_page_numbers_file():
    
    if "pdf" not in request.files:
        return jsonify({
            "success": False,
            "message": "No PDF uploaded."
        })

    file = request.files["pdf"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    position = request.form.get("position", "bottom-center")

    try:
        start_page = int(request.form.get("start_page", 1))
    except (ValueError, TypeError):
        start_page = 1

    if start_page < 1:
        start_page = 1

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    output_path = None

    file.save(input_path)

    try:
        doc = fitz.open(input_path)

        for page_number in range(len(doc)):

            page = doc[page_number]

            rect = page.rect

            number = str(page_number + start_page)

            fontsize = 16

            if position == "bottom-center":
                point = fitz.Point(rect.width / 2 - 8, rect.height - 25)
            elif position == "bottom-right":
                point = fitz.Point(rect.width - 60, rect.height - 25)
            elif position == "top-right":
                point = fitz.Point(rect.width - 60, 25)
            else:
                point = fitz.Point(rect.width / 2 - 8, rect.height - 25)

            page.insert_text(
                point,
                number,
                fontsize=fontsize,
                fontname="helv",
                color=(0, 0, 0)
            )

        output_name = "numbered_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        doc.save(output_path)

        doc.close()

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Add page numbers error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)
    
    # ================= RESIZE IMAGE =================

@app.route("/resize-image")
def resize_image():

    return render_template("tools/resize_image.html")


@app.route("/resize-image-file", methods=["POST"])
def resize_image_file():

    if "image" not in request.files:
        return jsonify({
            "success": False,
            "message": "No image uploaded."
        })

    file = request.files["image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected."
        })

    try:
        width = int(request.form["width"])
        height = int(request.form["height"])

        if width <= 0 or height <= 0:
            return jsonify({
                "success": False,
                "message": "Width and height must be greater than zero."
            })

        if width > 10000 or height > 10000:
            return jsonify({
                "success": False,
                "message": "Width and height must be 10000 or less."
            })

    except (ValueError, KeyError):
        return jsonify({
            "success": False,
            "message": "Please enter valid width and height values."
        })

    keep_ratio = "keep_ratio" in request.form

    filename = safe_filename(file.filename)

    input_path = os.path.join(UPLOAD_FOLDER, filename)

    file.save(input_path)

    try:
        image = Image.open(input_path)

        if image.mode == "RGBA" and filename.lower().endswith((".jpg", ".jpeg")):
            image = image.convert("RGB")

        if keep_ratio:
            original_width, original_height = image.size
            ratio = min(width / original_width, height / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
        else:
            new_width = width
            new_height = height

        resized = image.resize((new_width, new_height), Image.LANCZOS)

        output_name = "resized_" + filename

        output_path = os.path.join(OUTPUT_FOLDER, output_name)

        save_kwargs = {}

        if output_name.lower().endswith((".jpg", ".jpeg")):
            save_kwargs["quality"] = 95
            save_kwargs["optimize"] = True

        resized.save(output_path, **save_kwargs)

        return jsonify({
            "success": True,
            "filename": output_name,
            "download_url": url_for(
                "download_file",
                filename=output_name
            )
        })

    except Exception as e:
        logger.error("Resize image error: %s", e)
        return error_response(e)

    finally:
        safe_delete(input_path)


# ================= ABOUT =================

@app.route("/about")
def about():
    return render_template("about.html")




# ================= CONTACT =================

@app.route("/contact", methods=["GET", "POST"])
def contact():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            return jsonify({
                "success": False,
                "message": "Please fill in your name, email and message."
            }), 400

        if "@" not in email or "." not in email.split("@")[-1]:
            return jsonify({
                "success": False,
                "message": "Please enter a valid email address."
            }), 400

        if len(message) > 5000:
            return jsonify({
                "success": False,
                "message": "Message is too long (5000 characters max)."
            }), 400

        # Persist the enquiry. Swap this for SMTP / Resend / a database when
        # you have credentials - the endpoint contract stays the same.
        try:
            with open(os.path.join(BASE_DIR, "contact_messages.log"), "a", encoding="utf-8") as f:
                f.write("%s\t%s\t%s\t%s\n" % (
                    name.replace("\t", " "),
                    email.replace("\t", " "),
                    subject.replace("\t", " "),
                    message.replace("\n", " ").replace("\t", " ")
                ))
        except OSError as e:
            logger.error("Contact save error: %s", e)
            return jsonify({
                "success": False,
                "message": "Could not send your message. Please try again."
            }), 500

        logger.info("Contact form submission from %s <%s>", name, email)

        return jsonify({
            "success": True,
            "message": "Thanks! Your message has been received."
        })

    return render_template("contact.html")




# ================= START APP =================

# ===========================
# CATEGORY PAGES
# ===========================

# ===========================
# TOOL CATEGORY PAGES
# ===========================

@app.route("/pdf-tools")
def pdf_tools():

    return render_template(
        "category.html",
        title="PDF Tools",
        icon="fa-file-pdf",
        category="pdf"
    )


@app.route("/image-tools")
def image_tools():

    return render_template(
        "category.html",
        title="Image Tools",
        icon="fa-image",
        category="image"
    )


@app.route("/utility-tools")
def utility_tools():

    return render_template(
        "category.html",
        title="Utility Tools",
        icon="fa-screwdriver-wrench",
        category="utility"
    )
@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/disclaimer")
def disclaimer():
    return render_template("disclaimer.html")


# Start the background janitor once the app module is imported (works under
# gunicorn/waitress as well as `python app.py`).
threading.Thread(target=_janitor, daemon=True).start()


if __name__ == "__main__":
    # debug=True exposes the Werkzeug console (remote code execution).
    # Set TOOLHUB_DEBUG=1 locally if you really want the reloader.
    debug = os.environ.get("TOOLHUB_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(debug=debug)