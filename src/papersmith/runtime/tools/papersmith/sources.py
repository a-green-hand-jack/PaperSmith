"""Deterministic source acquisition.

Candidate search uses the Bohrium CLI (`bohr paper search`, `bohr lkm search`).
Fixed identifiers are resolved via arXiv/CrossRef metadata APIs, PDFs are
downloaded with size/timeout limits and verified by magic bytes and hashing,
and license statements are captured with their source. All functions are
control-program calls returning typed records and evidence hashes, never
natural-language summaries. Full review, conversion, and acceptance remain
fail closed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ARXIV_API = "http://export.arxiv.org/api/query"
CROSSREF_API = "https://api.crossref.org/works"
PDF_MAX_BYTES = 64 * 1024 * 1024
SOURCE_MAX_BYTES = 256 * 1024 * 1024
USER_AGENT = "PaperSmith/0.1 (deterministic source tooling)"


class BlockedError(RuntimeError):
    def __init__(self, phase: str, reason: str) -> None:
        super().__init__(reason)
        self.phase = phase
        self.reason = reason


# ---------------------------------------------------------------------------
# Bohrium CLI search
# ---------------------------------------------------------------------------

def _bohr_bin() -> str | None:
    return shutil.which("bohr")


def _run_bohr(args: list[str], timeout: int = 120) -> dict:
    if not os.environ.get("BOHR_ACCESS_KEY"):
        raise BlockedError("proposal", "BOHR_ACCESS_KEY is not set; source search requires Bohrium credentials")
    if not _bohr_bin():
        raise BlockedError("proposal", "bohr CLI is not installed")
    proc = subprocess.run(
        ["bohr", *args, "--yes", "--output", "json"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    try:
        data = json.loads(proc.stdout or "")
    except json.JSONDecodeError:
        raise BlockedError("proposal", "bohr returned non-JSON output")
    if not data.get("ok"):
        message = (data.get("error") or {}).get("message", "unknown bohr error")
        raise BlockedError("proposal", f"bohr search failed: {message}")
    return data


def _candidate(item: dict, query: str) -> dict:
    raw = json.dumps(item, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {
        "candidate_id": str(item.get("paperId") or item.get("doi") or ""),
        "title": item.get("enName") or item.get("title") or "",
        "authors": item.get("authors") or [],
        "doi": item.get("doi"),
        "year": (item.get("coverDateStart") or "")[:4],
        "abstract": item.get("enAbstract") or "",
        "open_access": item.get("openAccess"),
        "paper_url": item.get("paperUrl"),
        "publication": item.get("publicationEnName"),
        "query": query,
        "evidence": {
            "source": "bohr-paper-search",
            "raw_hash": hashlib.sha256(raw).hexdigest(),
        },
    }


def search_papers(query: str, size: int = 5, year_from: int | None = None, year_to: int | None = None) -> list[dict]:
    args = ["paper", "search", query, "--size", str(size)]
    if year_from is not None:
        args += ["--year-from", str(year_from)]
    if year_to is not None:
        args += ["--year-to", str(year_to)]
    data = _run_bohr(args)
    items = (data.get("data") or {}).get("items") or []
    return [_candidate(item, query) for item in items]


def search_lkm(query: str, top_k: int = 5) -> dict:
    data = _run_bohr(["lkm", "search", query, "--top-k", str(top_k)])
    body = data.get("data") or {}
    return {
        "query": query,
        "papers": body.get("papers") or {},
        "variables": body.get("variables") or [],
        "evidence": {
            "source": "bohr-lkm-search",
            "raw_hash": hashlib.sha256(
                json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        },
    }


def _lkm_paper_candidate(paper: dict, query: str) -> dict:
    raw = json.dumps(paper, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {
        "candidate_id": str(paper.get("id") or paper.get("doi") or ""),
        "title": paper.get("en_title") or paper.get("zh_title") or "",
        "authors": [a.strip() for a in (paper.get("authors") or "").split("|") if a.strip()],
        "doi": paper.get("doi"),
        "year": (paper.get("cover_date_start") or "")[:4],
        "abstract": paper.get("en_abstract") or "",
        "open_access": None,
        "paper_url": None,
        "publication": paper.get("publication_name"),
        "query": query,
        "evidence": {
            "source": "bohr-lkm-search",
            "raw_hash": hashlib.sha256(raw).hexdigest(),
        },
    }


def search_lkm_papers(query: str, top_k: int = 5) -> list[dict]:
    result = search_lkm(query, top_k=top_k)
    return [_lkm_paper_candidate(paper, query) for paper in result["papers"].values()]


def search_candidates(query: str, size: int = 5) -> list[dict]:
    candidates: list[dict] = []
    seen: set[str] = set()
    for candidate in list(search_papers(query, size=size)) + search_lkm_papers(query, top_k=size):
        key = candidate.get("doi") or candidate.get("candidate_id") or candidate.get("title")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        candidates.append(candidate)
    return candidates


# ---------------------------------------------------------------------------
# Fixed identifier resolution (arXiv / CrossRef)
# ---------------------------------------------------------------------------

def _http_get(url: str, timeout: int = 30, max_bytes: int = 4 * 1024 * 1024) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(max_bytes + 1)
    except urllib.error.URLError as exc:
        raise BlockedError("proposal", f"metadata fetch failed: {exc.reason}")
    if len(data) > max_bytes:
        raise BlockedError("proposal", "metadata response exceeded size limit")
    return data


def _parse_arxiv_id(identifier: str) -> str:
    value = identifier.strip()
    value = re.sub(r"^(arxiv|arXiv):", "", value)
    value = re.sub(r"^https?://arxiv\.org/(abs|pdf)/", "", value)
    value = re.sub(r"v\d+$", "", value)
    if not re.fullmatch(r"[0-9]{4}\.[0-9]{4,5}([a-z]{1,2})?", value):
        raise BlockedError("proposal", f"invalid arXiv identifier: {identifier}")
    return value


def _parse_doi(identifier: str) -> str:
    value = identifier.strip()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:", "", value)
    if not re.search(r"^10\.\d{4,9}/", value):
        raise BlockedError("proposal", f"invalid DOI: {identifier}")
    return value


def _arxiv_license(entry: ET.Element, ns: dict) -> str | None:
    element = entry.find("arxiv:license", ns)
    return (element.text or "").strip() if element is not None and element.text else None


def _arxiv_abs_license(arxiv_id: str) -> str | None:
    try:
        html = _http_get(f"https://arxiv.org/abs/{arxiv_id}", timeout=30).decode("utf-8", "replace")
    except BlockedError:
        return None
    match = re.search(r'(https?://(?:creativecommons\.org/licenses/[^"\']+|arxiv\.org/licenses/[^"\']+))', html)
    return match.group(1) if match else None


def discover_candidates(categories: list[str], count: int, margin: int = 8) -> list[str]:
    """Query arXiv for recent papers across categories; return bare arXiv IDs."""
    if not categories:
        raise BlockedError("proposal", "no arXiv categories configured for discovery")
    query = "+OR+".join(f"cat:{c}" for c in categories)
    url = (
        f"{ARXIV_API}?search_query={query}"
        f"&start=0&max_results={max(count * margin, 10)}"
        f"&sortBy=submittedDate&sortOrder=descending"
    )
    xml = _http_get(url, timeout=60)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml)
    ids: list[str] = []
    for entry in root.findall("a:entry", ns):
        eid = entry.findtext("a:id", default="", namespaces=ns) or ""
        arxiv_id = eid.rsplit("/abs/", 1)[-1]
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)
        if re.match(r"^\d{4}\.\d{4,5}$", arxiv_id) and arxiv_id not in ids:
            ids.append(arxiv_id)
    return ids


def resolve_arxiv(identifier: str) -> dict:
    arxiv_id = _parse_arxiv_id(identifier)
    xml = _http_get(f"{ARXIV_API}?id_list={arxiv_id}&max_results=1")
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(xml)
    entry = root.find("a:entry", ns)
    if entry is None:
        raise BlockedError("proposal", f"arXiv identifier not found: {arxiv_id}")
    title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
    authors = [a.findtext("a:name", default="", namespaces=ns).strip() for a in entry.findall("a:author", ns)]
    abstract = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
    doi_el = entry.find("arxiv:doi", ns)
    doi = (doi_el.text or "").strip() if doi_el is not None and doi_el.text else None
    published = entry.findtext("a:published", default="", namespaces=ns) or ""
    year_match = re.search(r"([12][0-9]{3})", published)
    year = year_match.group(1) if year_match else ""
    license_value = _arxiv_license(entry, ns) or _arxiv_abs_license(arxiv_id)
    return {
        "candidate_id": f"arXiv:{arxiv_id}",
        "title": title,
        "authors": authors,
        "doi": doi or f"10.48550/arXiv.{arxiv_id}",
        "year": year,
        "abstract": abstract,
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        "license": license_value,
        "identifier": f"arXiv:{arxiv_id}",
        "evidence": {"source": "arxiv-api", "raw_hash": hashlib.sha256(xml).hexdigest()},
    }


def resolve_doi(identifier: str) -> dict:
    doi = _parse_doi(identifier)
    data = json.loads(_http_get(f"{CROSSREF_API}/{urllib.parse.quote(doi)}").decode("utf-8"))
    message = data.get("message") or {}
    authors = [
        f"{a.get('given', '')} {a.get('family', '')}".strip()
        for a in message.get("author", [])
        if a.get("family") or a.get("given")
    ]
    licenses = [entry.get("URL") for entry in message.get("license", []) if entry.get("URL")]
    title = (message.get("title") or [""])[0]
    year = None
    for key in ("published-print", "published-online", "issued", "created"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            year = str(parts[0][0])
            break
    return {
        "candidate_id": doi,
        "title": title,
        "authors": authors,
        "doi": doi,
        "year": year or "",
        "abstract": message.get("abstract") or "",
        "url": message.get("URL"),
        "license": licenses,
        "identifier": doi,
        "evidence": {"source": "crossref-api", "raw_hash": hashlib.sha256(json.dumps(message, sort_keys=True, ensure_ascii=False).encode()).hexdigest()},
    }


def resolve_identifier(identifier: str) -> dict:
    lowered = identifier.strip().lower()
    arxiv_doi = re.match(r"^10\.48550/arxiv\.(\d{4}\.\d{4,5}(?:[a-z]{1,2})?)", lowered)
    if arxiv_doi:
        return resolve_arxiv(arxiv_doi.group(1))
    if lowered.startswith("arxiv:") or re.match(r"^\d{4}\.\d{4,5}", lowered):
        return resolve_arxiv(identifier)
    if lowered.startswith("10.") or lowered.startswith("doi:") or "doi.org" in lowered:
        return resolve_doi(identifier)
    raise BlockedError("proposal", f"unsupported fixed identifier (expected arXiv or DOI): {identifier}")


# ---------------------------------------------------------------------------
# PDF acquisition and inspection
# ---------------------------------------------------------------------------

def download_pdf(url: str, dest: Path, max_bytes: int = PDF_MAX_BYTES, timeout: int = 180) -> dict:
    if not url:
        raise BlockedError("proposal", "no PDF URL available for this source")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read(max_bytes + 1)
    except urllib.error.URLError as exc:
        raise BlockedError("proposal", f"PDF download failed: {exc.reason}")
    if len(data) > max_bytes:
        raise BlockedError("proposal", "PDF exceeded size limit")
    if not data.startswith(b"%PDF"):
        raise BlockedError("proposal", "downloaded bytes are not a PDF (missing %PDF signature)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {
        "path": str(dest),
        "bytes": len(data),
        "content_type": content_type,
        "sha256": hashlib.sha256(data).hexdigest(),
        "source_url": url,
    }


def inspect_pdf(path: Path) -> dict:
    data = path.read_bytes()
    if not data.startswith(b"%PDF"):
        raise BlockedError("proposal", f"file is not a PDF: {path}")
    text = data[: (16 * 1024 * 1024)]
    page_markers = len(re.findall(rb"/Type\s*/Page\b", text))
    has_eof = data.rstrip().endswith(b"%%EOF")
    return {
        "magic": data[:8].decode("latin-1", errors="replace"),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "page_objects": page_markers,
        "has_eof_marker": has_eof,
    }


def acquire_sources(spec) -> list[dict]:
    raise BlockedError(
        "proposal",
        "full source acquisition (PDF/license for every candidate) is not implemented; fixed-identifier acquisition is available",
    )


def validate_source_roots(roots: list[Path]) -> list[Path]:
    resolved: list[Path] = []
    for root in roots:
        path = root.resolve()
        if not path.is_dir():
            raise BlockedError("proposal", f"authorized source root is not a directory: {root}")
        resolved.append(path)
    return resolved


def safe_extract_archive(data: bytes, dest: Path) -> None:
    """Extract a tar archive with path-traversal/symlink rejection (py3.11-safe)."""
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            target = (dest / member.name).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise BlockedError("proposal", f"archive entry escapes destination: {member.name}")
            archive.extract(member, dest)


def fetch_arxiv_source(identifier: str, dest: Path, timeout: int = 240) -> dict:
    """Download and safely extract the arXiv e-print source bundle."""
    arxiv_id = _parse_arxiv_id(identifier)
    data = _http_get(f"https://arxiv.org/e-print/{arxiv_id}", timeout=timeout, max_bytes=SOURCE_MAX_BYTES)
    if data.startswith(b"%PDF"):
        raise BlockedError("proposal", "arXiv e-print returned a PDF, not a source bundle; paper has no LaTeX source")
    dest.mkdir(parents=True, exist_ok=True)
    safe_extract_archive(data, dest)
    return {
        "arxiv_id": arxiv_id,
        "source_dir": str(dest),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
