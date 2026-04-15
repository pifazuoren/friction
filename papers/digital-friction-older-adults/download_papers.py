#!/usr/bin/env python3
from __future__ import annotations

import csv
import mimetypes
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parent
MANIFEST = BASE_DIR / "download_manifest.tsv"
REPORT = BASE_DIR / "download_report.tsv"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)


def fetch(url: str, timeout: int = 45) -> tuple[bytes, str]:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get_content_type()
        return resp.read(), content_type


def discover_pdf_url(page_url: str) -> str | None:
    try:
        html_bytes, _ = fetch(page_url)
    except Exception:
        return None

    html = html_bytes.decode("utf-8", errors="ignore")
    patterns = [
        r'name="citation_pdf_url"\s+content="([^"]+)"',
        r'name="citation_abstract_pdf_url"\s+content="([^"]+)"',
        r'name="bepress_citation_pdf_url"\s+content="([^"]+)"',
        r'name="eprints\.document_url"\s+content="([^"]+)"',
        r'href="([^"]+\.pdf(?:\?[^"]*)?)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return urljoin(page_url, match.group(1).replace("&amp;", "&"))
    return None


def looks_like_pdf(content_type: str, body: bytes, url: str) -> bool:
    if body.startswith(b"%PDF"):
        return True
    if content_type == "application/pdf":
        return True
    guess, _ = mimetypes.guess_type(url)
    return guess == "application/pdf" and body[:4] == b"%PDF"


def safe_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def is_valid_pdf(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 4 and path.read_bytes().startswith(b"%PDF")
    except Exception:
        return False


def metadata_text(row: dict[str, str], final_pdf_url: str | None, error: str | None) -> str:
    lines = [
        f"English Title: {row['title_en']}",
        f"Chinese Title: {row['title_zh']}",
        f"Category: {row['category']}",
        f"Page URL: {row['page_url']}",
        f"PDF URL: {final_pdf_url or row['pdf_url'] or ''}",
        f"Notes: {row['notes']}",
    ]
    if error:
        lines.append(f"Download Status: metadata_only ({error})")
    else:
        lines.append("Download Status: metadata_only")
    return "\n".join(lines) + "\n"


def main() -> int:
    rows: list[dict[str, str]] = []
    with MANIFEST.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows.extend(reader)

    report_rows: list[dict[str, str]] = []

    for row in rows:
        category_dir = BASE_DIR / row["category"]
        pdf_path = category_dir / f"{row['slug']}.pdf"
        meta_path = category_dir / f"{row['slug']}.txt"

        if is_valid_pdf(pdf_path):
            report_rows.append(
                {
                    "category": row["category"],
                    "slug": row["slug"],
                    "status": "downloaded_pdf",
                    "pdf_path": str(pdf_path),
                    "metadata_path": str(meta_path if meta_path.exists() else ""),
                    "pdf_url": row["pdf_url"],
                    "page_url": row["page_url"],
                }
            )
            print(f"{row['slug']}: downloaded_pdf (existing)")
            continue

        if pdf_path.exists() and not is_valid_pdf(pdf_path):
            pdf_path.unlink()

        if meta_path.exists():
            report_rows.append(
                {
                    "category": row["category"],
                    "slug": row["slug"],
                    "status": "metadata_only",
                    "pdf_path": "",
                    "metadata_path": str(meta_path),
                    "pdf_url": row["pdf_url"],
                    "page_url": row["page_url"],
                }
            )
            print(f"{row['slug']}: metadata_only (existing)")
            continue

        candidate_pdf_url = row["pdf_url"] or discover_pdf_url(row["page_url"])
        status = "metadata_only"
        error_message = ""

        if candidate_pdf_url:
            try:
                body, content_type = fetch(candidate_pdf_url, timeout=60)
                if looks_like_pdf(content_type, body, candidate_pdf_url):
                    safe_write(pdf_path, body)
                    status = "downloaded_pdf"
                else:
                    error_message = f"non_pdf_response:{content_type}"
            except (HTTPError, URLError, TimeoutError, ValueError) as exc:
                error_message = exc.__class__.__name__
            except Exception as exc:
                error_message = exc.__class__.__name__
        else:
            error_message = "pdf_url_not_found"

        if status != "downloaded_pdf":
            safe_write(
                meta_path,
                metadata_text(row, candidate_pdf_url, error_message).encode("utf-8"),
            )
        else:
            safe_write(
                meta_path,
                metadata_text(row, candidate_pdf_url, None).encode("utf-8"),
            )

        report_rows.append(
            {
                "category": row["category"],
                "slug": row["slug"],
                "status": status,
                "pdf_path": str(pdf_path if status == "downloaded_pdf" else ""),
                "metadata_path": str(meta_path),
                "pdf_url": candidate_pdf_url or "",
                "page_url": row["page_url"],
            }
        )

        print(f"{row['slug']}: {status}")

    with REPORT.open("w", encoding="utf-8", newline="") as fh:
        fieldnames = [
            "category",
            "slug",
            "status",
            "pdf_path",
            "metadata_path",
            "pdf_url",
            "page_url",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(report_rows)

    return 0


if __name__ == "__main__":
    sys.exit(main())
