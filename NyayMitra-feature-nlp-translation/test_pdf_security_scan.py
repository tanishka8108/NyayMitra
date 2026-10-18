"""Unit tests for pdf_security_scan - the PDF malicious-content scanner.

No service required: every case builds a small PDF in memory (or takes
truncated bytes) and calls the scanner / upload validation directly.

Covers the five real-world scenarios from the investigation report:
  1. a normal generated court-order PDF          -> accepted
  2. a scanned / image-only PDF                  -> accepted
  3. a PDF with links, annotations and a harmless
     /OpenAction that opens a page               -> accepted
  4. a malformed PDF                             -> appropriate error
  5. a PDF with an automatic JavaScript action   -> rejected, generic
     message to the caller, details in the server log only

plus the security-regression cases: genuine JavaScript/launch actions
still blocked, JS-looking bytes inside compressed/text data not flagged,
indirect object references cannot bypass, ambiguous actions fail closed,
and embedded files judged by their actual bytes rather than their label.
"""

from __future__ import annotations

import logging
import zlib

import pytest

from pdf_security_scan import (
    PDFSecurityError,
    scan_pdf_for_malicious_content,
    secure_validate_pdf,
)
from upload_validation import UploadValidationError, validate_pdf_upload

# A JPEG header good enough for pdfplumber to see an image XObject.
_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xd9"
)


# ---------------------------------------------------------------------------
# PDF BUILDERS - minimal but structurally valid (correct xref + trailer),
# so pdfplumber can open them as well as the scanner reading their bytes.
# ---------------------------------------------------------------------------

def _flate_stream(dict_extra: bytes, payload: bytes) -> bytes:
    comp = zlib.compress(payload)
    return (
        b"<<" + dict_extra
        + b" /Length " + str(len(comp)).encode()
        + b" /Filter /FlateDecode >>\nstream\n"
        + comp + b"\nendstream"
    )


def _base_objects() -> dict[int, bytes]:
    return {
        1: b"<</Type/Catalog/Pages 2 0 R>>",
        2: b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        3: _page_object(),
        4: _flate_stream(
            b"", b"BT /F1 12 Tf 40 780 Td (IN THE COURT OF ADL JUDGE) Tj ET"
        ),
        5: b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    }


def _page_object(extras: bytes = b"", resources: bytes | None = None) -> bytes:
    """Page dict; `extras` is spliced in before the closing bracket and
    `resources` replaces the default font resource dictionary."""
    if resources is None:
        resources = b"<</Font<</F1 5 0 R>>>>"
    return (
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]"
        b"/Contents 4 0 R/Resources" + resources + extras + b">>"
    )


def _catalog_object(extras: bytes = b"") -> bytes:
    """Catalog dict; `extras` is spliced in before the closing bracket."""
    return b"<</Type/Catalog/Pages 2 0 R" + extras + b">>"


def _build_pdf(objects: dict[int, bytes], trailer_extra: bytes = b"") -> bytes:
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"

    xref_pos = len(out)
    size = max(objects) + 1
    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for num in range(1, size):
        if num in offsets:
            out += f"{offsets[num]:010d} 00000 n \n".encode()
        else:
            out += b"0000000000 65535 f \n"
    out += (
        f"trailer\n<</Size {size}/Root 1 0 R".encode()
        + trailer_extra
        + b">>\n"
        + f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


def _assert_rejected(data: bytes) -> None:
    """The scan must flag it AND secure_validate_pdf must raise the
    generic user-facing error (no indicator names leak out)."""
    findings = scan_pdf_for_malicious_content(data)
    assert findings, "scanner reported no findings for a hostile PDF"
    with pytest.raises(PDFSecurityError) as excinfo:
        secure_validate_pdf(data)
    message = str(excinfo.value)
    assert "security reasons" in message
    assert "JavaScript" not in message
    assert "OpenAction" not in message
    assert "Traceback" not in message


# ---------------------------------------------------------------------------
# THE FIVE REPORT SCENARIOS
# ---------------------------------------------------------------------------

def test_scenario_1_normal_generated_pdf_is_accepted():
    data = _build_pdf(_base_objects())
    assert scan_pdf_for_malicious_content(data) == []
    secure_validate_pdf(data)          # no raise
    validate_pdf_upload(data)          # pdfplumber agrees


def test_scenario_2_scanned_image_only_pdf_is_accepted():
    objs = _base_objects()
    objs[6] = (
        b"<</Type/XObject/Subtype/Image/Width 2/Height 2"
        b"/ColorSpace/DeviceGray/BitsPerComponent 8/Filter/DCTDecode"
        b"/Length " + str(len(_JPEG)).encode() + b" >>\nstream\n"
        + _JPEG + b"\nendstream"
    )
    # The page renders the image instead of text - a photocopied order.
    objs[3] = _page_object(resources=b"<</XObject<</Im0 6 0 R>>>>")
    objs[4] = _flate_stream(b"", b"q 200 0 0 100 50 700 cm /Im0 Do Q")

    data = _build_pdf(objs)
    assert scan_pdf_for_malicious_content(data) == []
    secure_validate_pdf(data)
    validate_pdf_upload(data)


def test_scenario_3_links_annotations_and_page_open_action_accepted():
    objs = _base_objects()
    # Opens at page 1 with a view setting - the exact construct the old
    # byte-grep rejected on a real e-filed court order.
    objs[1] = _catalog_object(b"/OpenAction[3 0 R/XYZ null null 0]")
    objs[3] = _page_object(b"/Annots[6 0 R]")
    objs[6] = (
        b"<</Type/Annot/Subtype/Link/Rect[0 0 300 20]/Border[0 0 0]"
        b"/A<</S/URI/URI(https://ecourts.gov.in/orders)>>>>"
    )

    data = _build_pdf(objs)
    assert scan_pdf_for_malicious_content(data) == []
    secure_validate_pdf(data)
    validate_pdf_upload(data)


def test_scenario_4_malformed_pdf_gets_appropriate_error():
    # The same shape as the live suite's corrupt fixture: recognised as
    # a PDF by magic, unreadable by any parser.
    data = b"%PDF-1.4\nthis is not really a pdf body\n"
    with pytest.raises(UploadValidationError) as excinfo:
        validate_pdf_upload(data)
    message = str(excinfo.value).lower()
    assert any(word in message for word in ("could not be read", "corrupt", "valid"))
    assert "Traceback" not in message


def test_scenario_4_stream_without_endstream_fails_closed():
    # A stream whose endstream never appears: the scanner cannot delimit
    # it safely, so the document is a rejection rather than a guess.
    objs = _base_objects()
    objs[6] = b"<< /Length 50 >>\nstream\nBT (unfinished"
    data = _build_pdf(objs)

    findings = scan_pdf_for_malicious_content(data)
    assert findings and "safely inspected" in findings[0]
    with pytest.raises(PDFSecurityError):
        secure_validate_pdf(data)


def test_scenario_4_unbalanced_string_fails_closed():
    objs = _base_objects()
    objs[6] = b"<</Note(broken with no closing paren"
    data = _build_pdf(objs)

    findings = scan_pdf_for_malicious_content(data)
    assert findings and "safely inspected" in findings[0]
    with pytest.raises(PDFSecurityError):
        secure_validate_pdf(data)


def test_scenario_5_automatic_javascript_rejected_with_generic_message():
    objs = _base_objects()
    objs[1] = _catalog_object(b"/OpenAction<</S/JavaScript/JS(app.alert(1))>>>")
    _assert_rejected(_build_pdf(objs))


def test_rejection_details_go_to_server_log_not_the_caller(caplog):
    objs = _base_objects()
    objs[1] = _catalog_object(b"/OpenAction<</S/JavaScript/JS(app.alert(1))>>>")
    data = _build_pdf(objs)

    with caplog.at_level(logging.WARNING, logger="nyaymitra.pdf_security"):
        with pytest.raises(PDFSecurityError) as excinfo:
            secure_validate_pdf(data)

    assert "JavaScript" in caplog.text        # full finding in the log
    assert "JavaScript" not in str(excinfo.value)  # never to the caller


# ---------------------------------------------------------------------------
# SECURITY REGRESSIONS - what must STAY blocked
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("catalog_extras,payload_object", [
    # Auto-running JavaScript action.
    (b"/OpenAction<</S/JavaScript/JS(app.alert(1))>>>", None),
    # JavaScript payload hidden behind an indirect reference.
    (b"/OpenAction<</S/JavaScript/JS 6 0 R>>>", b"(app.alert(1))"),
    # Name-object escape: /Java#53cript must still read as /JavaScript.
    (b"/OpenAction<</S/Java#53cript/JS(1)>>", None),
    # Launch actions can run external programs - never acceptable.
    (b"/Launch<</F(pwn.exe)>>", None),
    # Embedded/remote file navigation - active-content vectors.
    (b"/OpenAction<</S/GoToE/D[3 0 R/XYZ null null 0]>>", None),
    (b"/OpenAction<</S/GoToR/D[3 0 R/XYZ null null 0]>>", None),
])
def test_genuine_javascript_and_launch_actions_remain_blocked(
    catalog_extras, payload_object,
):
    objs = _base_objects()
    objs[1] = _catalog_object(catalog_extras)
    if payload_object is not None:
        objs[6] = payload_object
    _assert_rejected(_build_pdf(objs))


def test_additional_action_with_javascript_event_is_blocked():
    objs = _base_objects()
    objs[1] = _catalog_object(
        b"/AA<</O<</S/JavaScript/JS(app.alert(1))>>>>"
    )
    _assert_rejected(_build_pdf(objs))


def test_additional_action_referencing_javascript_object_is_blocked():
    objs = _base_objects()
    objs[1] = _catalog_object(b"/AA<</O 6 0 R>>")
    objs[6] = b"<</S/JavaScript/JS(app.alert(1))>>"
    _assert_rejected(_build_pdf(objs))


# ---------------------------------------------------------------------------
# FALSE-POSITIVE GUARDS - what must be ALLOWED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("openaction_value", [
    b"/OpenAction[3 0 R/XYZ null null 0]",        # page-open view (real case)
    b"/OpenAction<</S/GoTo/D[3 0 R/XYZ null null 0]>>",
    b"/OpenAction<</S/Named/Name/NextPage>>",
    b"/OpenAction<</S/GoTo/D 7 0 R>>",            # destination by reference
])
def test_harmless_page_navigation_open_action_accepted(openaction_value):
    objs = _base_objects()
    objs[1] = _catalog_object(openaction_value)
    objs[7] = b"[3 0 R/XYZ null null 0]"           # named destination object
    data = _build_pdf(objs)
    assert scan_pdf_for_malicious_content(data) == []
    secure_validate_pdf(data)


def test_openaction_via_indirect_reference_is_resolved_both_ways():
    # Safe reference: resolved and allowed.
    objs = _base_objects()
    objs[1] = _catalog_object(b"/OpenAction 6 0 R")
    objs[6] = b"<</S/GoTo/D[3 0 R/XYZ null null 0]>>"
    data = _build_pdf(objs)
    assert scan_pdf_for_malicious_content(data) == []
    secure_validate_pdf(data)

    # Hostile reference: resolved and blocked.
    objs[6] = b"<</S/JavaScript/JS(app.alert(1))>>"
    _assert_rejected(_build_pdf(objs))


def test_js_markers_in_compressed_and_text_data_are_not_flagged():
    # Inside a compressed content stream (what a real document's prose
    # looks like after Flate encoding) ...
    objs = _base_objects()
    objs[4] = _flate_stream(
        b"",
        b"BT /F1 12 Tf (Discussion of /JavaScript, /JS and /OpenAction) Tj ET",
    )
    # ... and inside an ordinary literal string in the catalog.
    objs[1] = _catalog_object(
        b"/Title(memo on /JS handling and /OpenAction policy)"
    )
    data = _build_pdf(objs)
    assert scan_pdf_for_malicious_content(data) == []
    secure_validate_pdf(data)
    validate_pdf_upload(data)


@pytest.mark.parametrize("catalog_extras", [
    b"/OpenAction<</S/GoTo>>",                    # GoTo with no destination
    b"/OpenAction<</S/SubmitForm>>",              # not page navigation
    b"/OpenAction 99 0 R",                        # unresolvable reference
    b"/OpenAction 5",                             # bare number, not an action
    b"/OpenAction<</S/GoTo/D[3 0 R/Fit]/F(evil.bin)>>",  # file smuggled in
    b"/AA<<>>",                                   # no recognisable event
    b"/AA<</O<</S/Trans>>>>",                     # event that is not navigation
])
def test_ambiguous_actions_fail_closed(catalog_extras):
    data = _build_pdf(_with_extras(catalog_extras))
    _assert_rejected(data)


def _with_extras(catalog_extras: bytes) -> dict[int, bytes]:
    objs = _base_objects()
    objs[1] = _catalog_object(catalog_extras)
    return objs


# ---------------------------------------------------------------------------
# EMBEDDED FILES - judged by their actual bytes, not their label
# ---------------------------------------------------------------------------

def _embedded_object(subtype: bytes, payload: bytes) -> bytes:
    comp = zlib.compress(payload)
    head = b"<< /Type /EmbeddedFile"
    if subtype:
        head += b" /Subtype /" + subtype
    return (
        head + b" /Length " + str(len(comp)).encode()
        + b" /Filter /FlateDecode >>\nstream\n" + comp + b"\nendstream"
    )


def test_inert_json_attachment_is_allowed_and_logged(caplog):
    # Scan-to-PDF devices embed JSON job tickets - inert, must pass.
    objs = _base_objects()
    objs[6] = _embedded_object(
        b"application#2Fjson", b'{"type":"Form","device":"scan-01"}'
    )
    data = _build_pdf(objs)

    with caplog.at_level(logging.INFO, logger="nyaymitra.pdf_security"):
        assert scan_pdf_for_malicious_content(data) == []
    assert "allowed inert attachment" in caplog.text
    secure_validate_pdf(data)


def test_embedded_file_with_executable_bytes_is_blocked_despite_harmless_label():
    # A harmless MIME subtype must NOT save an executable payload.
    fake_pe = b"MZ\x90\x00" + b"\x00" * 64
    objs = _base_objects()
    objs[6] = _embedded_object(b"application#2Fjson", fake_pe)
    _assert_rejected(_build_pdf(objs))


def test_embedded_file_with_active_subtype_is_blocked():
    objs = _base_objects()
    objs[6] = _embedded_object(
        b"application#2Fjavascript", b"app.alert(1)"
    )
    _assert_rejected(_build_pdf(objs))


def test_attachment_linked_only_through_file_spec_is_checked_by_bytes():
    # No /Type /EmbeddedFile on the stream at all - only the name tree
    # and /EF point at it. The payload still decides (ELF here, no
    # subtype to lean on).
    objs = _base_objects()
    objs[1] = _catalog_object(
        b"/Names<</EmbeddedFiles<</Names[(payload.bin)6 0 R]>>>>"
    )
    objs[6] = b"<</Type/Filespec/F(payload.bin)/EF<</F 7 0 R>>>>"
    objs[7] = _embedded_object(b"", b"\x7fELF" + b"\x00" * 32)
    _assert_rejected(_build_pdf(objs))


@pytest.mark.parametrize("extra_keys", [
    b" /Filter /RunLengthDecode",                # decoder we do not have
    b" /Filter /FlateDecode /DecodeParms<</Predictor 12>>",  # layout obfuscation
])
def test_attachment_the_scanner_cannot_decode_fails_closed(extra_keys):
    objs = _base_objects()
    comp = zlib.compress(b'{"harmless":true}')
    objs[6] = (
        b"<< /Type /EmbeddedFile /Length " + str(len(comp)).encode()
        + extra_keys + b" >>\nstream\n" + comp + b"\nendstream"
    )
    _assert_rejected(_build_pdf(objs))


# ---------------------------------------------------------------------------
# ENCRYPTED DOCUMENTS
# ---------------------------------------------------------------------------

def test_encrypted_pdf_gets_appropriate_error():
    objs = _base_objects()
    objs[6] = (
        b"<</Filter/Standard/V 1/R 2"
        b"/O(0123456789abcdef)/U(0123456789abcdef)/P -4>>"
    )
    data = _build_pdf(objs, trailer_extra=b"/Encrypt 6 0 R")

    with pytest.raises(UploadValidationError) as excinfo:
        validate_pdf_upload(data)
    message = str(excinfo.value).lower()
    assert any(
        word in message
        for word in ("password", "corrupt", "could not be read", "valid")
    )
    assert "Traceback" not in message
