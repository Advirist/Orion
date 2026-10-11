from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from ._common import resolve_in_playground, to_relative, parse_int, truncate

MAX_PDF_PAGES_PER_CALL = 10

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "image_info",
            "description": "Reports basic details about an image file in the sandboxed playground: format, width and height in pixels, color mode, frame count (for animations), and file size. It cannot see or describe what the image depicts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the image file, relative to the playground root."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_text_extract",
            "description": "Extracts the text from pages of a PDF in the sandboxed playground, a few pages at a time. If more pages remain, the result says which start_page to use next. Scanned PDFs that are only images will return little or no text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the .pdf file, relative to the playground root."
                    },
                    "start_page": {
                        "type": "integer",
                        "description": "First page to extract, starting at 1. Defaults to 1."
                    },
                    "max_pages": {
                        "type": "integer",
                        "description": "How many pages to extract in this call, from 1 to 10. Defaults to 5."
                    }
                },
                "required": ["path"]
            }
        }
    },
]


#Tool to read image metadata
def image_info(path):
    resolved, err = resolve_in_playground(path)
    if err:
        return err
    if not resolved.is_file():
        return {
            "success": False,
            "error": "not_a_file",
            "message": f"'{path}' is not a file."
        }

    rel = to_relative(resolved)

    #Image.open only reads the file header here; it doesn't decode every pixel
    try:
        with Image.open(resolved) as img:
            width, height = img.size
            image_format = img.format
            mode = img.mode
            frames = getattr(img, 'n_frames', 1)
    except UnidentifiedImageError:
        return {
            "success": False,
            "error": "not_an_image",
            "message": f"'{rel}' is not a recognized image format."
        }
    except Image.DecompressionBombError:
        return {
            "success": False,
            "error": "image_too_large",
            "message": f"'{rel}' has an unusually large pixel count and was not opened, as a safety precaution."
        }
    except PermissionError:
        return {
            "success": False,
            "error": "permission_denied",
            "message": f"Permission denied when trying to open '{rel}'."
        }

    return {
        "success": True,
        "path": rel,
        "format": image_format,
        "width": width,
        "height": height,
        "color_mode": mode,
        "frame_count": frames,
        "size_bytes": resolved.stat().st_size,
        "message": f"'{rel}' is a {width}x{height} {image_format} image."
    }


#Tool to extract text from a PDF, paginated like read_file
def pdf_text_extract(path, start_page=1, max_pages=5):
    resolved, err = resolve_in_playground(path)
    if err:
        return err
    if not resolved.is_file():
        return {
            "success": False,
            "error": "not_a_file",
            "message": f"'{path}' is not a file."
        }
    if resolved.suffix.lower() != '.pdf':
        return {
            "success": False,
            "error": "unsupported_file_type",
            "message": f"'{path}' is not a .pdf file."
        }

    start_page, err = parse_int(start_page, 'start_page')
    if err:
        return err
    max_pages, err = parse_int(max_pages, 'max_pages')
    if err:
        return err
    max_pages = max(1, min(max_pages, MAX_PDF_PAGES_PER_CALL))

    rel = to_relative(resolved)

    try:
        reader = PdfReader(resolved)
        if reader.is_encrypted:
            #many "encrypted" PDFs have an empty user password and open fine
            try:
                if not reader.decrypt(''):
                    raise ValueError("password required")
            except Exception:
                return {
                    "success": False,
                    "error": "encrypted_pdf",
                    "message": f"'{rel}' is password-protected and can't be read."
                }
        total_pages = len(reader.pages)
    except PdfReadError as e:
        return {
            "success": False,
            "error": "unreadable_pdf",
            "message": f"'{rel}' could not be read as a PDF: {e}"
        }

    if total_pages == 0:
        return {"success": True, "total_pages": 0, "text": "", "message": f"'{rel}' has no pages."}

    if start_page < 1 or start_page > total_pages:
        return {
            "success": False,
            "error": "invalid_page",
            "message": f"start_page must be between 1 and {total_pages} for '{rel}'."
        }

    end_page = min(start_page + max_pages - 1, total_pages)
    chunks = []
    try:
        for page_number in range(start_page, end_page + 1):
            page_text = reader.pages[page_number - 1].extract_text() or ''
            chunks.append(f"--- Page {page_number} ---\n{page_text.strip()}")
    except Exception as e:
        return {
            "success": False,
            "error": "extraction_failed",
            "message": f"Text extraction failed on page {page_number} of '{rel}': {e}"
        }

    combined, truncated = truncate("\n\n".join(chunks))
    has_text = any(len(c.split('\n', 1)[-1].strip()) > 0 for c in chunks)

    message = f"Extracted pages {start_page}-{end_page} of {total_pages} from '{rel}'."
    if not has_text:
        message += " These pages contain no extractable text; the PDF may be scanned images."
    if truncated:
        message += " The text was long and has been cut off; try a smaller max_pages."
    if end_page < total_pages:
        message += f" To continue, call this tool again with start_page={end_page + 1}."

    return {
        "success": True,
        "path": rel,
        "total_pages": total_pages,
        "start_page": start_page,
        "end_page": end_page,
        "text": combined,
        "truncated": truncated,
        "message": message
    }


TOOL_REGISTRY = {
    "image_info": {'function': image_info, 'mutating': False},
    "pdf_text_extract": {'function': pdf_text_extract, 'mutating': False},
}
