import re
import json
import sys


# ---------------------------------------------------------
# SECTION HEADINGS
# ---------------------------------------------------------

KNOWN_HEADINGS = {
    "FACTS": "Facts",
    "FACTUAL BACKGROUND": "Facts",
    "BRIEF FACTS": "Facts",
    "PROCEEDINGS": "Proceedings and Discussion",
    "DISCUSSION": "Proceedings and Discussion",
    "SUBMISSIONS": "Proceedings and Discussion",
    "ORDER": "Order",
    "OPERATIVE ORDER": "Order",
}


# ---------------------------------------------------------
# OCR / DOCUMENT NOISE
# ---------------------------------------------------------

NOISE_PATTERNS = [
    # OCR watermark
    re.compile(r"Gaurav Arora\s+\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}"),

    # Common certificate metadata
    re.compile(r"Whether speaking/reasoned\s*[_:.-]*\s*Yes/No", re.I),
    re.compile(r"Whether reportable\s*[_:.-]*\s*Yes/No", re.I),

    # Document certificate
    re.compile(
        r"I attest to the accuracy and integrity of this document",
        re.I
    ),
]


# ---------------------------------------------------------
# BASIC CLEANING
# ---------------------------------------------------------

def normalize_line(line):
    line = line.replace("\x0c", " ")
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def is_page_marker(line):
    return bool(
        re.match(r"^=+\s*Page\s+\d+\s*=+$", line, re.I)
    )


def extract_page_number(line):
    match = re.search(r"Page\s+(\d+)", line, re.I)
    if match:
        return int(match.group(1))
    return None


# ---------------------------------------------------------
# PARAGRAPH DETECTION
# ---------------------------------------------------------

PARAGRAPH_RE = re.compile(r"^(\d+)[\.\)]\s+(.*)$")


def detect_paragraph_start(line):
    match = PARAGRAPH_RE.match(line)
    if match:
        return int(match.group(1)), match.group(2).strip()

    return None, None


def detect_heading(line):
    """Checks if a line is a known section heading (e.g. 'ORDER', 'FACTS')."""
    stripped = line.strip().upper()
    return KNOWN_HEADINGS.get(stripped)


# ---------------------------------------------------------
# SIGNATURE / CERTIFICATION DETECTION
# ---------------------------------------------------------

# The line that opens an order names the court the matter is heard in —
# "IN THE COURT OF THE CIVIL JUDGE, PUNE" — and so mentions a judge
# without being one. The JUDGE test alone fired on line 1, which
# started the signature block before a single paragraph had been read
# and filed the whole document under Signatures. Heading lines are
# therefore ruled out before that test runs.
COURT_HEADING_RE = re.compile(
    r"\b(IN THE COURT|COURT OF|BEFORE THE|PRESIDING|HON'BLE)\b",
    re.I,
)


def is_signature_line(line):
    upper = line.upper()

    if "JUDGE" in upper:
        if COURT_HEADING_RE.search(line):
            return False

        return True

    if re.match(r"^\(.*\)\s*\(.*\)$", line):
        return True

    return False


def is_certification_line(line):
    lower = line.lower()

    patterns = [
        "whether speaking/reasoned",
        "whether reportable",
        "i attest to the accuracy",
        "integrity of this document",
    ]

    return any(pattern in lower for pattern in patterns)


# ---------------------------------------------------------
# REMOVE OCR WATERMARKS
# ---------------------------------------------------------

def remove_inline_noise(text):
    for pattern in NOISE_PATTERNS:
        text = pattern.sub("", text)

    # Clean excessive spaces created after removal
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


# ---------------------------------------------------------
# CLEAN PARAGRAPH TEXT
# ---------------------------------------------------------

def clean_paragraph_text(text):
    """Remove OCR watermarks and other obvious OCR artifacts."""

    if not text:
        return ""

    # current_paragraph is a list of OCR lines
    if isinstance(text, list):
        text = " ".join(text)

    # Remove Gaurav Arora watermark
    text = re.sub(
        r"Gaurav\s+Arora",
        "",
        text,
        flags=re.I
    )

    # Remove watermark timestamp
    text = re.sub(
        r"\b\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\b",
        "",
        text
    )

    # Remove certification watermark
    text = re.sub(
        r"I\s+attest\s+to\s+the\s+accuracy\s+and\s+integrity\s+of\s+this\s+document",
        "",
        text,
        flags=re.I
    )

    # Remove PHHC document watermark
    text = re.sub(
        r"\b\d{4}:PHHC-\d{6}-DB\s*;\s*\d+\b",
        "",
        text,
        flags=re.I
    )

    # Remove artificial page markers
    text = re.sub(
        r"={3,}\s*Page\s+\d+\s*={3,}",
        "",
        text,
        flags=re.I
    )

    # Remove excessive whitespace
    text = re.sub(
        r"\s{2,}",
        " ",
        text
    ).strip()

    return text
# ---------------------------------------------------------
# SECTION OBJECT
# ---------------------------------------------------------

def create_section(section_id, title, page_start=None, page_end=None):
    return {
        "section_id": section_id,
        "title": title,
        "page_start": page_start,
        "page_end": page_end,
    }


def split_court_order(lines):

    sections = []

    case_details = create_section(
        "case_details",
        "Case Details"
    )

    proceedings = create_section(
        "proceedings",
        "Proceedings and Discussion"
    )

    order = create_section(
        "order",
        "Order"
    )

    signatures = create_section(
        "signatures",
        "Signatures"
    )

    certification = create_section(
        "certification",
        "Document Certification"
    )

    case_lines = []

    current_paragraph = None
    current_paragraph_number = None
    current_paragraph_page_start = None
    current_paragraph_page_end = None

    current_page = 1

    signatures_started = False
    certification_started = False
    order_heading_seen = False  # tracks whether an explicit ORDER heading was found

    def flush_paragraph():

        nonlocal current_paragraph
        nonlocal current_paragraph_number
        nonlocal current_paragraph_page_start
        nonlocal current_paragraph_page_end

        if current_paragraph_number is None:
            return

        text = clean_paragraph_text(current_paragraph)

        if not text:
            current_paragraph = None
            current_paragraph_number = None
            current_paragraph_page_start = None
            current_paragraph_page_end = None
            return

        paragraph = {
            "number": current_paragraph_number,
            "text": text,
            "page_start": current_paragraph_page_start,
            "page_end": current_paragraph_page_end,
        }

        # Route to Order only if an explicit ORDER heading was seen earlier;
        # otherwise default to Proceedings rather than guessing a boundary.
        if order_heading_seen:

            order.setdefault(
                "paragraphs", []
            ).append(paragraph)

        else:

            proceedings.setdefault(
                "paragraphs", []
            ).append(paragraph)

        current_paragraph = None
        current_paragraph_number = None
        current_paragraph_page_start = None
        current_paragraph_page_end = None

    def update_page(section, page):

        if section["page_start"] is None:
            section["page_start"] = page

        section["page_end"] = page

    # -----------------------------------------------------
    # PROCESS EVERY LINE
    # -----------------------------------------------------

    for raw_line in lines:

        line = normalize_line(raw_line)

        if not line:
            continue

        # -------------------------------------------------
        # PAGE MARKER
        # -------------------------------------------------

        if is_page_marker(line):

            page = extract_page_number(line)

            if page is not None:
                current_page = page

            continue

        # -------------------------------------------------
        # CERTIFICATION
        #
        # IMPORTANT:
        # Certification is checked ONLY after signatures
        # have started.
        # -------------------------------------------------

        if signatures_started and is_certification_line(line):

            flush_paragraph()

            certification_started = True

            update_page(
                certification,
                current_page
            )

            certification.setdefault(
                "text_lines", []
            ).append(line)

            continue

        # -------------------------------------------------
        # AFTER CERTIFICATION STARTS
        # -------------------------------------------------

        if certification_started:

            update_page(
                certification,
                current_page
            )

            certification.setdefault(
                "text_lines", []
            ).append(line)

            continue

        # -------------------------------------------------
        # SIGNATURE DETECTION
        #
        # Check signatures BEFORE certification.
        # -------------------------------------------------

        if is_signature_line(line):

            flush_paragraph()

            signatures_started = True

            update_page(
                signatures,
                current_page
            )

            signatures.setdefault(
                "text_lines", []
            ).append(line)

            continue

        # -------------------------------------------------
        # AFTER SIGNATURES
        # -------------------------------------------------

        if signatures_started:

            update_page(
                signatures,
                current_page
            )

            signatures.setdefault(
                "text_lines", []
            ).append(line)

            continue

        # -------------------------------------------------
        # HEADING DETECTION (marks the real start of the Order section)
        # -------------------------------------------------

        heading = detect_heading(line)
        if heading == "Order":
            # Close the paragraph that was still open *before* the flag
            # flips: everything written above an ORDER heading is
            # proceedings, and flushing after the flip filed the last
            # paragraph before the heading as part of the Order.
            flush_paragraph()

            order_heading_seen = True
            continue
        elif heading:
            # Other known headings (Facts, etc.) - currently just skip the
            # heading line itself; content still routes to Proceedings by default
            continue

        # -------------------------------------------------
        # PARAGRAPH START
        # -------------------------------------------------

        number, paragraph_text = detect_paragraph_start(line)

        if number is not None:

            # Finish previous paragraph
            flush_paragraph()

            current_paragraph_number = number

            current_paragraph = [
                paragraph_text
            ]

            current_paragraph_page_start = current_page
            current_paragraph_page_end = current_page

            # Determine section page range
            if order_heading_seen:

                update_page(
                    order,
                    current_page
                )

            else:

                update_page(
                    proceedings,
                    current_page
                )

            continue

        # -------------------------------------------------
        # CONTINUATION OF CURRENT PARAGRAPH
        # -------------------------------------------------

        if current_paragraph_number is not None:

            current_paragraph.append(line)

            current_paragraph_page_end = current_page

            if order_heading_seen:

                update_page(
                    order,
                    current_page
                )

            else:

                update_page(
                    proceedings,
                    current_page
                )

            continue

        # -------------------------------------------------
        # BEFORE PARAGRAPHS = CASE DETAILS
        # -------------------------------------------------

        case_lines.append(line)

        update_page(
            case_details,
            current_page
        )

    # -----------------------------------------------------
    # FLUSH LAST PARAGRAPH
    # -----------------------------------------------------

    flush_paragraph()

    # -----------------------------------------------------
    # CASE DETAILS
    # -----------------------------------------------------
    cleaned_case_lines = []

    for line in case_lines:

        cleaned = normalize_line(line)

        if not cleaned:
            continue

        # Remove OCR watermark
        cleaned = re.sub(
            r"Gaurav\s+Arora\s+\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}",
            "",
            cleaned,
            flags=re.I
        )

        # Remove certification watermark
        cleaned = re.sub(
            r"I\s+attest\s+to\s+the\s+accuracy\s+and\s+integrity\s+of\s+this\s+document",
            "",
            cleaned,
            flags=re.I
        )

        # Remove obvious OCR garbage
        if cleaned in ["ये KK", "KK"]:
            continue

        # Remove malformed signature fragment
        if re.match(
            r"^SUDEEPTI\s+SHARMA,\s*\d+\.$",
            cleaned,
            flags=re.I
        ):
            continue

        cleaned = re.sub(
            r"\s{2,}",
            " ",
            cleaned
        ).strip()

        if cleaned:
            cleaned_case_lines.append(cleaned)

    case_text = "\n".join(cleaned_case_lines)

    if case_text.strip():
        case_details["text"] = case_text.strip()
    # -----------------------------------------------------
    # SIGNATURE TEXT
    # -----------------------------------------------------

    if signatures.get("text_lines"):

        signatures["text"] = "\n".join(
            signatures["text_lines"]
        )

        del signatures["text_lines"]

    # -----------------------------------------------------
    # CERTIFICATION TEXT
    # -----------------------------------------------------

    if certification.get("text_lines"):

        certification["text"] = "\n".join(
            certification["text_lines"]
        )

        del certification["text_lines"]

    # -----------------------------------------------------
    # REMOVE EMPTY SECTIONS
    # -----------------------------------------------------

    if case_details.get("text"):

        sections.append(
            case_details
        )

    if proceedings.get("paragraphs"):

        sections.append(
            proceedings
        )

    if order.get("paragraphs"):

        sections.append(
            order
        )

    if signatures.get("text"):

        sections.append(
            signatures
        )

    if certification.get("text"):

        sections.append(
            certification
        )

    return {
        "sections": sections
    }
# ---------------------------------------------------------
# FILE PROCESSING
# ---------------------------------------------------------

def process_file(input_file, output_file="court_order_sections.json"):

    with open(
        input_file,
        "r",
        encoding="utf-8",
        errors="replace"
    ) as f:

        lines = f.readlines()

    result = split_court_order(lines)

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=4,
            ensure_ascii=False
        )

    print(
        f"Successfully created "
        f"{len(result['sections'])} section(s)."
    )

    print()

    for section in result["sections"]:

        print(
            f"--- {section['title']} "
            f"({section['section_id']}) ---"
        )

        print(
            f"Pages: "
            f"{section.get('page_start')} - "
            f"{section.get('page_end')}"
        )

        if "paragraphs" in section:

            print(
                f"Paragraphs: "
                f"{len(section['paragraphs'])}"
            )

            for p in section["paragraphs"]:

                preview = p["text"]

                if len(preview) > 180:
                    preview = preview[:180] + "..."

                print(
                    f"  {p['number']}. {preview}"
                )

        elif "text" in section:

            print(section["text"][:1000])

        print()

    print(
        f"Output saved to: {output_file}"
    )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

if __name__ == "__main__":

    if len(sys.argv) < 2:

        print(
            "Usage: "
            "python3 court_order_section_splitter.py "
            "real_pdf_ocr_output.txt"
        )

        sys.exit(1)

    input_file = sys.argv[1]

    process_file(input_file)
