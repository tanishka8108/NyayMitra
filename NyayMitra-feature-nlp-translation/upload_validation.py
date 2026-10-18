import magic

PDF_MAX_SIZE_BYTES = 10 * 1024 * 1024
AUDIO_MAX_SIZE_BYTES = 5 * 1024 * 1024

ALLOWED_PDF_MIME_TYPES = {"application/pdf"}
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/wav", "audio/x-wav",
    "audio/mpeg",
    "audio/mp4", "audio/x-m4a",
}


class UploadValidationError(Exception):
    pass


def validate_pdf_upload(file_bytes: bytes) -> None:
    if len(file_bytes) > PDF_MAX_SIZE_BYTES:
        raise UploadValidationError(
            f"File too large. Maximum allowed size is {PDF_MAX_SIZE_BYTES // (1024*1024)} MB."
        )
    if len(file_bytes) == 0:
        raise UploadValidationError("Uploaded file is empty.")

    detected_type = magic.from_buffer(file_bytes, mime=True)
    if detected_type not in ALLOWED_PDF_MIME_TYPES:
        raise UploadValidationError(
            "File does not appear to be a valid PDF. Please upload a PDF document."
        )

    try:
        import pdfplumber
        import io
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) == 0:
                raise UploadValidationError("PDF appears to have no readable pages.")
    except UploadValidationError:
        raise
    except Exception:
        raise UploadValidationError(
            "This PDF could not be read. It may be corrupted or password-protected."
        )


def validate_audio_upload(file_bytes: bytes) -> None:
    if len(file_bytes) > AUDIO_MAX_SIZE_BYTES:
        raise UploadValidationError(
            f"Audio file too large. Maximum allowed size is {AUDIO_MAX_SIZE_BYTES // (1024*1024)} MB."
        )
    if len(file_bytes) == 0:
        raise UploadValidationError("Uploaded audio file is empty.")

    detected_type = magic.from_buffer(file_bytes, mime=True)
    if detected_type not in ALLOWED_AUDIO_MIME_TYPES:
        raise UploadValidationError(
            "File does not appear to be a valid audio recording (wav/mp3/m4a)."
        )

    try:
        import torchaudio
        import io
        wav, sr = torchaudio.load(io.BytesIO(file_bytes))
        if wav.numel() == 0:
            raise UploadValidationError("Audio file appears to contain no sound data.")
    except UploadValidationError:
        raise
    except Exception:
        raise UploadValidationError(
            "This audio file could not be read. It may be corrupted or in an unsupported format."
        )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python upload_validation.py <pdf|audio> <file_path>")
        sys.exit(1)

    kind, path = sys.argv[1], sys.argv[2]
    with open(path, "rb") as f:
        data = f.read()

    try:
        if kind == "pdf":
            validate_pdf_upload(data)
        elif kind == "audio":
            validate_audio_upload(data)
        else:
            print("First argument must be 'pdf' or 'audio'")
            sys.exit(1)
        print(f"'{path}' passed all validation checks.")
    except UploadValidationError as e:
        print(f"Validation failed: {e}")
