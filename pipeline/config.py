"""Pipeline configuration: constants, paths, and classification rules."""

import os
from pathlib import Path

# Ensure Go binaries are discoverable
_go_bin = Path.home() / "go" / "bin"
if _go_bin.is_dir() and str(_go_bin) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_go_bin}:{os.environ.get('PATH', '')}"

# --- Paths ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "prospects"
BRIEFS_DIR = DATA_DIR / "briefs"
DEFAULT_INPUT = PROJECT_ROOT / "docs" / "reference" / "CVR-extraction-sample.xlsx"

# --- Excel column indices (0-based) ---
COL_CVR = 0
COL_START_DATE = 1
COL_END_DATE = 2
COL_NAME = 3
COL_ADDRESS = 4
COL_POSTCODE = 5
COL_CITY = 6
COL_COMPANY_FORM = 7
COL_INDUSTRY = 8
COL_PHONE = 9
COL_EMAIL = 10
COL_AD_PROTECTED = 11

# --- Free webmail providers (discard if email domain matches) ---
FREE_WEBMAIL = frozenset({
    "gmail.com", "googlemail.com",
    "hotmail.com", "hotmail.dk",
    "outlook.com", "outlook.dk",
    "live.com", "live.dk",
    "yahoo.com", "yahoo.dk",
    "icloud.com", "me.com", "mac.com",
    "mail.dk", "jubii.dk",
    "msn.com", "aol.com",
    "protonmail.com", "proton.me",
    "stofanet.dk", "tdcadsl.dk",
    "webspeed.dk", "post.dk",
    "email.dk", "mail.com",
    "zoho.com",
    "yandex.com", "gmx.com", "gmx.dk",
    "fastmail.com",
    "tutanota.com", "tuta.io",
})

# --- Bucket definitions ---
# CMS values (lowercase) that map to each bucket
BUCKET_A_CMS = {"wordpress"}
BUCKET_B_CMS = {"joomla", "drupal", "prestashop", "typo3", "magento", "craft cms", "concrete5"}
BUCKET_C_PLATFORMS = {"shopify", "squarespace", "wix", "weebly", "webflow", "mono.net", "one.com website builder", "simply.com"}

# --- GDPR-sensitive industry codes (branchekode prefixes) ---
# These are the leading digits of the Danish DB07 industry codes
GDPR_SENSITIVE_CODES = {
    "86": "Sundhedsvæsen (Healthcare)",
    "69": "Advokat- og revisionsvirksomhed (Legal & Accounting)",
    "6910": "Advokatvirksomhed (Legal)",
    "6920": "Revisionsvirksomhed (Accounting)",
    "68": "Ejendomsmægler (Real estate)",
    "6831": "Ejendomsmæglere (Real estate agents)",
    "8623": "Tandlæge (Dental)",
    "64": "Finansiel virksomhed (Financial services)",
    "65": "Forsikring (Insurance)",
    "66": "Finansiel service (Financial service activities)",
}

# --- HTTP settings ---
REQUEST_TIMEOUT = 15  # seconds
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# --- CVR scraping ---
CVR_BASE_URL = "https://datacvr.virk.dk/enhed/virksomhed"
CVR_ACCORDION_XPATH = '//*[@id="accordion-udvidede-virksomhedsoplysninger-button"]'
CVR_SCRAPE_DELAY = (1, 3)  # random delay range in seconds between requests
