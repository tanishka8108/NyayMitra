"""
Malicious-content scanner for uploaded court-order PDFs.
Tuesday, Week 4 task: "scan uploaded PDFs for malformed/malicious content
before processing"

This goes beyond basic type/size validation (already handled in
upload_validation.py / pdf_extraction_pipeline.py). A PDF can be a
perfectly valid, readable PDF file and still be dangerous - PDFs support
embedded scripts and auto-actions that can execute when the file is opened.

HISTORY / WHY THIS IS NOT A PLAIN BYTE GREP
-------------------------------------------
The first version of this scanner ran six bare regexes over the whole
file. That rejected ordinary court documents, proven on real files:

  * a genuine e-filed court order carried /OpenAction[1 0 R /XYZ ...]
    (a "open at page 1" view setting - harmless navigation);
  * a report PDF had the bytes "/JS" occur at random INSIDE an
    ASCII85-compressed content stream;
  * scan-to-PDF devices embed JSON job tickets as /EmbeddedFile.

The scanner therefore does what PDF syntax allows and a byte-grep
cannot: it walks the file ONCE, masks everything that is not structural
text (stream BODIES, literal strings, hex strings), and only then looks
for indicator NAME OBJECTS in the remaining structure. Comments are
deliberately NOT masked - an indicator written in a comment is still
treated as hostile (fail closed).

WHAT IS BLOCKED (unchanged in substance, sharper in precision)
    /JavaScript, /JS        real JavaScript action name objects
    /OpenAction, /AA        automatic actions UNLESS positively
                            identified as page navigation:
                              - a destination array  [page /XYZ ...]
                              - an action dict with /S /GoTo, a /D
                                destination and no file reference
                              - an action dict with /S /Named and
                                /Name one of NextPage/PrevPage/
                                FirstPage/LastPage
                            Indirect references (N 0 R) are resolved
                            and checked; anything ambiguous, exotic or
                            unresolvable is REJECTED (fail closed).
                            Objects hidden inside compressed object
                            streams therefore cannot hide - the
                            reference stays visible in plaintext and
                            fails to resolve, which is itself a
                            rejection.
    /Launch                 launch actions - always blocked
    /GoToE, /GoToR          embedded/remote file navigation - always
                            blocked (active-content vector)
    /EF, /EmbeddedFile     file attachments are judged by their ACTUAL
                            bytes: the payload is decoded with the
                            declared filter chain (Flate/ASCII85/
                            ASCIIHex), then checked against executable
                            signatures (PE, ELF, Mach-O, shebang
                            scripts, PostScript, OLE, zip containers)
                            and against active-content subtypes
                            (javascript, executables, ...). A harmless
                            filename or MIME subtype alone is NEVER
                            trusted. Payloads that cannot be decoded
                            (unknown filters, predictors, bombs) are
                            rejected - fail closed. Inert attachments
                            (JSON/XML job tickets, images) are allowed
                            but logged for audit.

NOT DETECTED BY THIS SCANNER (documented limitations, unchanged from
before): payloads hidden inside COMPRESSED stream bodies are invisible
to any raw-byte scan, because readers decompress them at runtime; this
scanner blocks such documents by their *declarations* (/S /JavaScript
etc.), which must exist in plaintext for any reader to act on them.
Full structural decoding would need a PDF parser library.
"""

import base64
import logging
import re
import sys
import zlib

logger = logging.getLogger("nyaymitra.pdf_security")

# The indicator vocabulary, kept as documentation of what a finding
# means. The scan below uses its own compiled patterns.
SUSPICIOUS_PATTERNS = {
    rb"/JavaScript": "Embedded JavaScript (can execute code automatically)",
    rb"/JS\b": "Embedded JavaScript action",
    rb"/OpenAction": "Auto-trigger action on file open",
    rb"/AA\b": "Additional actions (can trigger on close/print/etc.)",
    rb"/Launch": "Launch action (can run external programs/files)",
    rb"/EmbeddedFile": "Embedded file hidden inside the PDF",
}


class PDFSecurityError(Exception):
    """Raised when a PDF contains suspicious/malicious content indicators."""
    pass


class _Uninspectable(Exception):
    """Internal signal: the document structure cannot be scanned safely.

    Raised instead of guessing, so every caller fails closed.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# INDICATOR PATTERNS
#
# A PDF name is introduced by "/" and is self-delimiting, so an indicator
# that appears as "/JS" or "/OpenAction" anywhere in STRUCTURAL bytes is a
# name token (strings and stream bodies are masked before we get here).
# The (?![A-Za-z0-9]) guard stops longer names such as /JSX or
# /EmbeddedFiles from being mistaken for the indicator itself.
# ---------------------------------------------------------------------------

def _indicator(name: bytes) -> re.Pattern:
    return re.compile(re.escape(name) + rb"(?![A-Za-z0-9])")


_IND_JS_NAME = _indicator(rb"/JavaScript")
_IND_JS_SHORT = _indicator(rb"/JS")
_IND_OPENACTION = _indicator(rb"/OpenAction")
_IND_AA = _indicator(rb"/AA")
_IND_LAUNCH = _indicator(rb"/Launch")
_IND_GOTOE = _indicator(rb"/GoToE")
_IND_GOTOR = _indicator(rb"/GoToR")
_IND_EMBEDDED_FILE = _indicator(rb"/EmbeddedFile")
_IND_EF = _indicator(rb"/EF")

# Action type inside an action dictionary: /S /GoTo, /S /JavaScript, ...
_IND_ACTION_S = re.compile(
    rb"/S[ \t]*/(GoTo|Named|JavaScript|Launch|GoToE|GoToR|SubmitForm|"
    rb"ImportData|Movie|Sound|Rendition|Trans|URI|JS)(?![A-Za-z0-9])"
)

# Named navigation actions are the only /S /Named worth allowing.
_SAFE_NAMED_ACTIONS = re.compile(
    rb"/Name[ \t]*/(NextPage|PrevPage|FirstPage|LastPage)(?![A-Za-z0-9])"
)

# A GoTo must carry a destination: an array /D[...] or a name/ref /D N 0 R.
_GOTO_DESTINATION = re.compile(rb"/D[ \t]*(\[|\d+[ \t]+\d+[ \t]+R)")

# A file specification inside a "navigation" action makes it remote
# (opens/reads a file) - never what a court order needs.
_FILE_SPEC_IN_ACTION = re.compile(rb"/F(?:S)?(?![A-Za-z0-9])[ \t]*[</(\d]")

# A destination array: a page (ref or number) then a fit type.
_DESTINATION_ARRAY = re.compile(
    rb"(?:\d+[ \t]+\d+[ \t]+R|\d+)[ \t]*/"
    rb"(?:XYZ|FitH|FitV|FitB|FitBH|FitBV)(?![A-Za-z0-9])"
)

# /AA event keys - the only things an Additional-Actions dict holds.
_AA_EVENT = re.compile(rb"/(O|C|PO|PC|PV|PI)(?![A-Za-z0-9])[ \t]*")

# Stream keyword followed by its mandatory end-of-line.
_STREAM_KW = re.compile(rb"stream(\r\n|\n|\r)")
_ENDSTREAM_KW = re.compile(rb"endstream(?![A-Za-z0-9])")
_ENDOBJ_KW = re.compile(rb"endobj(?![A-Za-z0-9])")

# /Length as a direct integer, or as an indirect reference.
_LENGTH_DIRECT = re.compile(rb"/Length(?![A-Za-z0-9])[ \t]*(\d+)(?![\d \t]+\d[ \t]*R)")
_LENGTH_REF = re.compile(rb"/Length(?![A-Za-z0-9])[ \t]*(\d+)[ \t]+\d+[ \t]+R")

# What follows a legitimately-ended stream or object, used to validate
# that a keyword hit is real structure and not binary noise.
_AFTER_STRUCTURE = re.compile(
    rb"[\t\r\n ]*(endobj|endstream|trailer|%%EOF|\d+[ \t]+\d+[ \t]+obj)"
)

# Embedded-file subtypes that are active content regardless of anything
# else in the file. Substrings, checked case-insensitively against the
# decoded subtype (e.g. application#2Fjavascript -> application/javascript).
_ACTIVE_SUBTYPE = re.compile(
    rb"(?i)(javascript|ecmascript|vbscript|shockwave|executable|dosexec|"
    rb"msdownload|msdos|portable-executable|x-sh\b|x-bat|batch|powershell|"
    rb"shellscript|x-csh|x-perl|python|postscript|x-elf|x-mach|sharedlib|"
    rb"\bexe\b)"
)

# Byte signatures of active/binary payloads, checked against the ACTUAL
# attachment bytes (after decoding the declared filter chain) - a
# harmless-looking filename or MIME subtype alone is never trusted.
_ACTIVE_MAGIC = (
    (b"MZ", "PE/MS-DOS executable"),
    (b"\x7fELF", "ELF executable"),
    (b"\xca\xfe\xba\xbe", "Mach-O/Java class data"),
    (b"\xce\xfa\xed\xfe", "Mach-O executable"),
    (b"#!", "script with a shebang interpreter line"),
    (b"%!PS", "PostScript (can execute commands)"),
    (b"PK\x03\x04", "ZIP container (archives can carry executables)"),
    (b"PK\x05\x06", "empty ZIP container"),
    (b"\xd0\xcf\x11\xe0", "legacy OLE compound document"),
)

# PNG-style predictors change the byte layout, so signatures would be
# unreliable - and an attacker could exploit exactly that. Fail closed.
_PREDICTOR = re.compile(rb"/Predictor(?![A-Za-z0-9])[ \t]+(?:[2-9]|\d{2,})")

# Attachment sniffing never inflates beyond this many bytes; a Flate
# stream expanding past it is treated as hostile (compression bomb).
_MAX_SNIFF_BYTES = 8 * 1024 * 1024

# How far back before a stream body to look for the stream's own
# dictionary keys when deciding whether it is an embedded file.
_EMBEDDED_DICT_WINDOW = 8192


# ---------------------------------------------------------------------------
# SMALL PDF PARSER - one pass, masking everything that is not structure
# ---------------------------------------------------------------------------

def _fill(buf: bytearray, start: int, end: int) -> None:
    """Overwrite buf[start:end] with NULs, preserving all offsets."""
    if end > start:
        buf[start:end] = b"\x00" * (end - start)


def _mask_string(buf: bytearray, start: int) -> int:
    """Mask a literal string ( ... ) with escapes and nesting handled.

    Returns the position just past the closing paren. Raises
    _Uninspectable for an unbalanced string - fail closed.
    """
    depth = 1
    i = start + 1
    size = len(buf)

    while i < size:
        byte = buf[i]

        if byte == 0x5C:  # backslash: the next byte is escaped content
            i += 2
            continue
        if byte == 0x28:  # (
            depth += 1
        elif byte == 0x29:  # )
            depth -= 1
            if depth == 0:
                _fill(buf, start + 1, i)
                return i + 1
        i += 1

    raise _Uninspectable("unbalanced literal string in PDF structure")


def _find_endstream(data: bytes, start: int):
    """Position of a VALID endstream at/after start, or None.

    Validated against the bytes that may follow it, so a stray
    "endstream" occurring inside binary data cannot cut a region short
    and leave the true payload outside the masked area.
    """
    pos = start

    while True:
        match = _ENDSTREAM_KW.search(data, pos)
        if not match:
            return None
        if _AFTER_STRUCTURE.match(data, match.end()):
            return match.start()
        pos = match.end()


def _body_end_at(data: bytes, candidate: int):
    """Position of the endstream keyword at/near `candidate`.

    Writers differ on whether the trailing EOL before "endstream" counts
    toward /Length, so allow a 0-2 byte slop. Returns None when no
    keyword sits there - the caller then falls back to a validated
    search or fails closed.
    """
    for slop in (0, 1, 2):
        if _ENDSTREAM_KW.match(data, candidate + slop):
            return candidate + slop
    return None


def _find_object(data: bytes, number: int):
    """(start, end) of object `number`'s body.

    Called on the masked copy, so object keywords inside strings or
    stream bodies cannot interfere.
    """
    pattern = re.compile(
        rb"(?:^|[\s>])" + str(number).encode() + rb"[ \t]+\d+[ \t]+obj(?![A-Za-z0-9])"
    )
    match = pattern.search(data)
    if not match:
        return None

    start = match.end()
    end_match = _ENDOBJ_KW.search(data, start)
    if not end_match:
        return None
    return start, end_match.start()


def _mask_and_index_streams(data: bytes):
    """Single left-to-right walk.

    Strings and comments are recognised BEFORE the stream keyword can be,
    so a string that merely contains "stream" cannot fake a stream and
    hide payload from the scan. Stream bodies are masked via /Length
    (direct or resolved indirect) with a validated endstream fallback;
    anything that cannot be delimited raises _Uninspectable.

    Returns (masked, regions) where regions holds
    (dict_start, body_start, body_end) triples for /EmbeddedFile checks.
    """
    masked = bytearray(data)
    regions = []
    i = 0
    size = len(data)

    while i < size:
        byte = data[i]

        if byte == 0x25:  # % comment: skipped over, content KEPT for scan
            newline = data.find(b"\n", i)
            i = size if newline == -1 else newline + 1
            continue

        if byte == 0x28:  # literal string
            i = _mask_string(masked, i)
            continue

        if byte == 0x3C:
            if i + 1 < size and data[i + 1] == 0x3C:  # << starts a dict
                i += 2
                continue
            # Single "<" opens a hex string: mask until its closing ">".
            close = data.find(b">", i + 1)
            if close == -1:
                raise _Uninspectable("unbalanced hex string in PDF structure")
            _fill(masked, i + 1, close)
            i = close + 1
            continue

        if byte == 0x73:  # 's' - possible "stream" keyword
            header = _STREAM_KW.match(data, i)
            # Must be the keyword itself: preceded by whitespace or the
            # dict's ">>" - not part of "endstream" (preceded by 'd')
            # and not a name such as "/stream".
            if header and (i == 0 or data[i - 1] in b" \t\r\n>"):
                body_start = header.end()
                dict_start = data.rfind(b"<<", 0, i)

                window_start = max(0, i - 4096)
                if dict_start > window_start:
                    window_start = dict_start

                body_end = None

                # /Length as a direct integer: the exact body length.
                direct = _LENGTH_DIRECT.search(data, window_start, i)
                if direct:
                    body_end = _body_end_at(
                        data, body_start + int(direct.group(1))
                    )

                # /Length as an indirect reference: resolve the object.
                if body_end is None:
                    ref = _LENGTH_REF.search(data, window_start, i)
                    if ref:
                        found = _find_object(data, int(ref.group(1)))
                        if found:
                            digits = re.fullmatch(
                                rb"\s*(\d+)\s*", data[found[0]:found[1]]
                            )
                            if digits:
                                body_end = _body_end_at(
                                    data, body_start + int(digits.group(1))
                                )

                # No usable /Length (or a wrong one): take the first
                # endstream whose surrounding structure validates. If
                # none exists the document cannot be inspected safely.
                if body_end is None:
                    validated = _find_endstream(data, body_start)
                    if validated is None:
                        raise _Uninspectable(
                            "stream/endstream boundaries could not be delimited"
                        )
                    body_end = validated

                _fill(masked, body_start, body_end)
                regions.append((dict_start, body_start, body_end))
                i = body_end + len(b"endstream")
                continue

        i += 1

    return masked, regions


def _decode_name_escapes(data: bytes) -> bytes:
    """Decode PDF '#XX' name escapes so /Java#53cript cannot dodge the
    /JavaScript check and application#2Fjson reads as application/json."""
    return re.sub(
        rb"#([0-9A-Fa-f]{2})",
        lambda match: bytes([int(match.group(1), 16)]),
        data,
    )


# ---------------------------------------------------------------------------
# ACTION SAFETY - "safe" must be PROVEN, everything else is rejected
# ---------------------------------------------------------------------------

def _skip_ws(data: bytes, pos: int) -> int:
    while pos < len(data) and data[pos] in b" \t\r\n":
        pos += 1
    return pos


def _dict_bounds(data: bytes, pos: int):
    """End index of the <<...>> dict opened at pos, or None if it never
    balances (which is itself an uninspectable structure)."""
    depth = 0
    i = pos

    while i < len(data) - 1:
        pair = data[i:i + 2]
        if pair == b"<<":
            depth += 1
            i += 2
            continue
        if pair == b">>":
            depth -= 1
            i += 2
            if depth == 0:
                return i
            continue
        i += 1

    return None


def _action_is_safe(data: bytes, pos: int, depth: int = 0) -> bool:
    """True ONLY when the value at pos is positively identified as
    page navigation. Ambiguous or unresolvable values return False,
    which makes the caller reject the document (fail closed)."""
    if depth > 3:
        return False

    pos = _skip_ws(data, pos)
    if pos >= len(data):
        return False

    # A destination array: [page-ref /XYZ ...]
    if data[pos] == 0x5B:
        close = data.find(b"]", pos)
        if close == -1 or close - pos > 256:
            return False
        return bool(_DESTINATION_ARRAY.search(data[pos:close + 1]))

    # An action dictionary: <</S /GoTo /D ...>> or <</S /Named /Name ...>>
    if data[pos:pos + 2] == b"<<":
        end = _dict_bounds(data, pos)
        if end is None or end - pos > 8192:
            return False
        window = data[pos:end]

        kind = _IND_ACTION_S.search(window)
        if not kind:
            return False
        # A "navigation" action that carries a file spec is actually
        # reading/launching something - reject.
        if _FILE_SPEC_IN_ACTION.search(window):
            return False
        if kind.group(1) == b"GoTo":
            return bool(_GOTO_DESTINATION.search(window))
        if kind.group(1) == b"Named":
            return bool(_SAFE_NAMED_ACTIONS.search(window))
        return False  # JavaScript, Launch, GoToE, SubmitForm, ...

    # An indirect reference: resolve the object and judge its content.
    ref = re.match(rb"(\d+)[ \t]+\d+[ \t]+R(?![A-Za-z0-9])", data[pos:])
    if ref:
        found = _find_object(data, int(ref.group(1)))
        if found is None:
            return False  # cannot resolve -> fail closed
        return _action_is_safe(data[found[0]:found[1]], 0, depth + 1)

    return False


# ---------------------------------------------------------------------------
# EMBEDDED FILE CHECKS - the actual bytes decide, not the label
# ---------------------------------------------------------------------------

def _extract_filters(decoded_dict: bytes) -> list:
    """All declared filter names, from the direct or array form of
    /Filter."""
    names = []
    for bracket in re.findall(rb"/Filter(?![A-Za-z0-9])[ \t]*\[([^\]]*)\]", decoded_dict):
        names += re.findall(rb"/([A-Za-z0-9]+)", bracket)
    names += re.findall(rb"/Filter(?![A-Za-z0-9])[ \t]*/([A-Za-z0-9]+)", decoded_dict)
    return names


def _decode_filter_chain(payload: bytes, filters: list):
    """Decode `payload` with the declared filters (applied in encoding
    order, so decoded in reverse). Returns None when a filter is
    unknown or decoding fails - the caller then fails closed."""
    try:
        for name in reversed(filters):
            if name == b"FlateDecode":
                obj = zlib.decompressobj()
                payload = obj.decompress(payload, _MAX_SNIFF_BYTES)
                if len(payload) >= _MAX_SNIFF_BYTES:
                    return None
            elif name == b"ASCII85Decode":
                stripped = re.sub(rb"\s+", b"", payload)
                if stripped.endswith(b"~>"):
                    stripped = stripped[:-2]
                payload = base64.a85decode(stripped)
            elif name == b"ASCIIHexDecode":
                text = re.sub(rb"\s+", b"", payload)
                if text.endswith(b">"):
                    text = text[:-1]
                if len(text) % 2:
                    text += b"0"
                payload = bytes.fromhex(text.decode("ascii"))
            else:
                return None
        return payload
    except Exception:
        return None


def _check_embedded_stream(data: bytes, dict_slice: bytes,
                           body_start: int, body_end: int) -> list:
    """Judge one attachment stream by decoding its payload and checking
    the actual bytes. Returns findings (empty = inert, allowed+logged)."""
    decoded_dict = _decode_name_escapes(dict_slice)

    if _PREDICTOR.search(decoded_dict):
        return [
            "Embedded file using a predictor encoding the scanner cannot inspect"
        ]

    subtype_match = re.search(
        rb"/Subtype(?![A-Za-z0-9])[ \t]*/([^\s<>\[\]()]+)", decoded_dict
    )
    subtype = subtype_match.group(1) if subtype_match else b"(none)"

    filters = _extract_filters(decoded_dict)
    payload = data[body_start:body_end]

    if filters:
        if set(filters) == {b"DCTDecode"}:
            pass  # JPEG: sniff the raw bytes below
        elif all(
            name in (b"FlateDecode", b"ASCII85Decode", b"ASCIIHexDecode")
            for name in filters
        ):
            decoded = _decode_filter_chain(payload, filters)
            if decoded is None:
                return [
                    "Embedded file whose contents could not be decoded for inspection"
                ]
            payload = decoded
        else:
            return [
                "Embedded file encoded with a filter the scanner cannot decode"
            ]

        if len(payload) >= _MAX_SNIFF_BYTES:
            return ["Embedded file expanding beyond the inspection limit"]

    if _ACTIVE_SUBTYPE.search(subtype):
        return [
            "Embedded file with an active-content subtype "
            f"({subtype.decode('latin-1', 'replace')})"
        ]

    for magic, label in _ACTIVE_MAGIC:
        if payload.startswith(magic):
            return [f"Embedded file containing {label}"]

    # Inert attachment: allowed, but recorded server-side so the
    # decision is auditable.
    logger.info(
        "allowed inert attachment: subtype=%s bytes=%d",
        subtype.decode("latin-1", "replace"),
        body_end - body_start,
    )
    return []


def _check_embedded_object(data: bytes, number: int) -> list:
    """Resolve an /EF reference and judge the stream it points at."""
    pattern = re.compile(
        rb"(?:^|[\s>])" + str(number).encode()
        + rb"[ \t]+\d+[ \t]+obj(?![A-Za-z0-9])"
    )
    match = pattern.search(data)
    if not match:
        return ["File attachment reference that could not be resolved"]

    start = match.end()
    endobj = _ENDOBJ_KW.search(data, start)
    header = _STREAM_KW.search(data, start, start + 65536)

    if header is None or (endobj and endobj.start() < header.start()):
        return ["File attachment pointing at a non-stream object"]

    body_start = header.end()
    body_end = _find_endstream(data, body_start)
    if body_end is None:
        return ["File attachment whose data stream could not be delimited"]

    return _check_embedded_stream(
        data, data[start:header.start()], body_start, body_end
    )


def _attachment_findings(data: bytes, masked: bytearray, regions,
                         structure: bytes) -> list:
    """All attachment checks: streams declaring /EmbeddedFile, plus every
    /EF (embedded-file) reference - the latter catches attachments that
    are only linked through a name tree or file specification."""
    findings = []
    previous_body_end = 0

    # (A) A stream whose own dictionary declares it an embedded file.
    # Only that dictionary is used for subtype/filter keys - a wider
    # window would pick up neighbouring objects' keys. The wider search
    # below exists solely for dicts with nested sub-dictionaries, and is
    # bounded by the previous stream so one attachment can never taint
    # the next stream's checks. Slices come from the masked copy, so a
    # literal string merely mentioning /EmbeddedFile cannot qualify a
    # stream either.
    for dict_start, body_start, body_end in regions:
        dict_slice = None

        own_start = masked.rfind(b"<<", 0, body_start)
        if own_start >= 0:
            own = bytes(masked[own_start:body_start])
            if _IND_EMBEDDED_FILE.search(_decode_name_escapes(own)):
                dict_slice = own

        if dict_slice is None:
            window_start = max(
                previous_body_end, body_start - _EMBEDDED_DICT_WINDOW
            )
            window = bytes(masked[window_start:body_start])
            matches = list(
                _IND_EMBEDDED_FILE.finditer(_decode_name_escapes(window))
            )
            if matches:
                # Anchor on the declaration: its outer dict opens at the
                # nearest "<<" before it.
                decl = window_start + matches[-1].start()
                outer = masked.rfind(b"<<", 0, decl)
                if outer >= 0:
                    candidate = bytes(masked[outer:body_start])
                    if _IND_EMBEDDED_FILE.search(_decode_name_escapes(candidate)):
                        dict_slice = candidate

        if dict_slice is not None:
            findings.extend(
                _check_embedded_stream(data, dict_slice, body_start, body_end)
            )

        previous_body_end = body_end

    # (B) Every /EF << /F N 0 R >> file specification in the structure.
    for match in _IND_EF.finditer(structure):
        pos = _skip_ws(structure, match.end())
        if structure[pos:pos + 2] != b"<<":
            findings.append(
                "File-attachment dictionary that could not be inspected"
            )
            continue
        end = _dict_bounds(structure, pos)
        if end is None:
            findings.append(
                "File-attachment dictionary that could not be inspected"
            )
            continue
        for num in re.findall(
            rb"(\d+)[ \t]+\d+[ \t]+R(?![A-Za-z0-9])", structure[pos:end]
        ):
            findings.extend(_check_embedded_object(data, int(num)))

    return findings


# ---------------------------------------------------------------------------
# THE SCAN
# ---------------------------------------------------------------------------

def scan_pdf_for_malicious_content(file_bytes: bytes) -> list:
    """
    Scans a PDF for known malicious-content indicators, with the stream
    and string payloads masked out first so random compressed bytes can
    never impersonate structure. Returns a list of finding descriptions;
    an empty list means nothing suspicious was detected.

    A document whose structure cannot be delimited, balanced or resolved
    is itself a finding (fail closed) - the caller rejects it.
    """
    try:
        masked, regions = _mask_and_index_streams(file_bytes)
    except _Uninspectable as exc:
        return [f"structure could not be safely inspected ({exc.reason})"]

    # '#XX' escapes are decoded only for the structural copy used by the
    # indicator scan; the raw/offset-preserving copy is kept for region
    # and payload checks.
    structure = _decode_name_escapes(bytes(masked))

    findings = []

    # JavaScript, in either spelling, as a real name object.
    if _IND_JS_NAME.search(structure):
        findings.append(SUSPICIOUS_PATTERNS[rb"/JavaScript"])
    if _IND_JS_SHORT.search(structure):
        findings.append(SUSPICIOUS_PATTERNS[rb"/JS\b"])

    # Automatic actions on open - allowed only when positively identified
    # as page navigation (destination array, /GoTo with /D, or a named
    # page jump). Everything else, including an unresolvable reference,
    # is rejected.
    for match in _IND_OPENACTION.finditer(structure):
        if not _action_is_safe(structure, match.end()):
            findings.append(
                "Automatic action on file open that is not simple page navigation"
            )

    # Additional actions (close/print/etc.) - each event must be proven
    # page navigation, or the document is rejected.
    for match in _IND_AA.finditer(structure):
        pos = _skip_ws(structure, match.end())
        if structure[pos:pos + 2] != b"<<":
            if not _action_is_safe(structure, match.end()):
                findings.append(
                    "Additional-action entry that is not simple page navigation"
                )
            continue

        end = _dict_bounds(structure, pos)
        if end is None:
            findings.append("Additional-actions dictionary could not be inspected")
            continue

        events = list(_AA_EVENT.finditer(structure, pos, end))
        if not events:
            findings.append(
                "Additional-actions dictionary with no recognisable event"
            )
            continue

        for event in events:
            if not _action_is_safe(structure, event.end()):
                findings.append(
                    "Additional-action event that is not simple page navigation"
                )
                break

    # Launch and embedded/remote file navigation are never needed by a
    # court order, so their presence alone blocks the document.
    if _IND_LAUNCH.search(structure):
        findings.append(SUSPICIOUS_PATTERNS[rb"/Launch"])
    if _IND_GOTOE.search(structure):
        findings.append("Embedded-file navigation action (GoToE)")
    if _IND_GOTOR.search(structure):
        findings.append("Remote-file navigation action (GoToR)")

    # Embedded attachments: judged by actual content, not by label.
    findings.extend(_attachment_findings(file_bytes, masked, regions, structure))

    return findings


def secure_validate_pdf(file_bytes: bytes) -> None:
    """
    Full security check: raises PDFSecurityError if anything suspicious
    is found. Call this IN ADDITION TO validate_pdf() from
    pdf_extraction_pipeline.py - this checks content safety, not
    type/size/readability (which the other function already handles).
    """
    findings = scan_pdf_for_malicious_content(file_bytes)
    if findings:
        # Detailed findings stay in the server log for audit/debugging.
        logger.warning(
            "PDF rejected: bytes=%d findings: %s",
            len(file_bytes),
            "; ".join(findings),
        )
        # But raise a generic, safe message - never expose the specific
        # attack indicators to the end user (that would help an attacker
        # learn what our scanner checks for)
        raise PDFSecurityError(
            "This PDF could not be accepted for security reasons. "
            "Please upload a standard, unmodified court document."
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_security_scan.py <pdf_path>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "rb") as handle:
        data = handle.read()

    findings = scan_pdf_for_malicious_content(data)

    if findings:
        print(f"SUSPICIOUS: '{path}' contains {len(findings)} red flag(s):")
        for description in findings:
            print(f"  - {description}")
    else:
        print(f"CLEAN: '{path}' shows no known malicious-content indicators.")
