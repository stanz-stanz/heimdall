"""CVR data ingestion: read Excel and derive website domains."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from pipeline.config import (
    COL_ADDRESS,
    COL_AD_PROTECTED,
    COL_CITY,
    COL_COMPANY_FORM,
    COL_CVR,
    COL_EMAIL,
    COL_INDUSTRY,
    COL_NAME,
    COL_PHONE,
    COL_POSTCODE,
    FREE_WEBMAIL,
)

log = logging.getLogger(__name__)


@dataclass
class Company:
    cvr: str
    name: str
    address: str = ""
    postcode: str = ""
    city: str = ""
    company_form: str = ""
    industry_code: str = ""
    industry_name: str = ""
    phone: str = ""
    email: str = ""
    ad_protected: bool = False
    website_domain: str = ""
    discard_reason: str = ""

    @property
    def discarded(self) -> bool:
        return bool(self.discard_reason)


def _parse_industry(raw: str) -> tuple[str, str]:
    """Split '468600 Engroshandel med ...' into code and name."""
    if not raw:
        return "", ""
    parts = raw.strip().split(" ", 1)
    code = parts[0] if parts else ""
    name = parts[1] if len(parts) > 1 else ""
    return code, name


def _extract_domain(email: str) -> str:
    """Get domain from email address, lowercased."""
    if not email or "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip().lower()


def read_excel(path: Path) -> list[Company]:
    """Read the CVR Excel export and return a list of Company objects."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    companies = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row[COL_CVR]:
            continue

        industry_code, industry_name = _parse_industry(str(row[COL_INDUSTRY] or ""))

        company = Company(
            cvr=str(row[COL_CVR]).strip(),
            name=str(row[COL_NAME] or "").strip(),
            address=str(row[COL_ADDRESS] or "").strip(),
            postcode=str(row[COL_POSTCODE] or "").strip(),
            city=str(row[COL_CITY] or "").strip(),
            company_form=str(row[COL_COMPANY_FORM] or "").strip(),
            industry_code=industry_code,
            industry_name=industry_name,
            phone=str(row[COL_PHONE] or "").strip(),
            email=str(row[COL_EMAIL] or "").strip().lower() if row[COL_EMAIL] else "",
            ad_protected=str(row[COL_AD_PROTECTED] or "").strip().lower() == "ja",
        )
        companies.append(company)

    wb.close()
    log.info("Read %d companies from %s", len(companies), path.name)
    return companies


def derive_domains(companies: list[Company]) -> list[Company]:
    """Extract website domain from email. Discard free webmail and missing emails."""
    for company in companies:
        if company.discarded:
            continue

        if not company.email:
            company.discard_reason = "no_email"
            continue

        domain = _extract_domain(company.email)
        if not domain:
            company.discard_reason = "invalid_email"
            continue

        if domain in FREE_WEBMAIL:
            company.discard_reason = f"free_webmail:{domain}"
            continue

        company.website_domain = domain

    kept = sum(1 for c in companies if not c.discarded)
    discarded = sum(1 for c in companies if c.discarded)
    log.info("Domain derivation: %d kept, %d discarded", kept, discarded)
    return companies
