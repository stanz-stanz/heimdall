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
DEFAULT_INPUT = DATA_DIR / "CVR-extract.xlsx"
DEFAULT_FILTERS = DATA_DIR / "filters.json"
INDUSTRY_CODES_PATH = DATA_DIR / "industry_codes.json"

# --- Excel column indices (0-based) ---
COL_CVR = 0
COL_NAME = 1
COL_ADDRESS = 2
COL_POSTCODE = 3
COL_CITY = 4
COL_COMPANY_FORM = 5
COL_INDUSTRY = 6
COL_PHONE = 7
COL_EMAIL = 8
COL_AD_PROTECTED = 9

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

