# Valdi Scan-Type Validation

- **Timestamp:** 2026-03-26T17:03:00Z
- **Scan type:** Exposed cloud storage search via GrayHatWarfare public index
- **Scan type ID:** cloud_storage_index_query
- **Declared Layer:** 1 (Passive)
- **Declared Level:** 0 (No consent)
- **Verdict:** APPROVED
- **Approval token:** a1b2c3d4-4444-4aaa-bbbb-ghw0000000001
- **Function hash:** sha256:89d8d25b2fb360cecde97db47a5fa14385d81c5c9dbd1485bdbd9a24e4d9a422
- **Triggered by:** Claude Code (new tool integration)

## Tools Invoked

- Python `requests` library (HTTP GET to GrayHatWarfare API)
- No external CLI tools
- Requires `GRAYHATWARFARE_API_KEY` environment variable (gracefully skips if not set)

## URLs/Paths Requested

- `https://buckets.grayhatwarfare.com/api/v2/files?keywords={domain}` — queries the GrayHatWarfare exposed bucket index
- Requests go to GrayHatWarfare (a third-party public service), NOT to the target's infrastructure
- API key required for authentication with GrayHatWarfare service

## robots.txt Handling

**N/A.** No HTTP requests are sent to the target's web server or cloud storage infrastructure. GrayHatWarfare maintains a pre-existing index of publicly exposed cloud storage buckets. Querying this index is equivalent to searching a public database. The target's robots.txt does not govern access to third-party indexing services.

## Reasoning

GrayHatWarfare maintains a public index of exposed cloud storage buckets (AWS S3, Azure Blob, Google Cloud Storage) that have been discovered through public enumeration. Searching this index for a company's domain name reveals whether any of their cloud storage is publicly exposed — without making any requests to the target's infrastructure or cloud storage endpoints.

This is explicitly allowed under SCANNING_RULES.md Level 0: "Third-party public indexes — querying public databases or search engines for information about the target. No requests are sent to the target's infrastructure." GrayHatWarfare is listed in the Level 0 Allowed Tools table with the classification note: "Querying a third-party public index of exposed cloud storage buckets. No direct requests to the target's infrastructure."

The function:
1. Checks for GRAYHATWARFARE_API_KEY — skips entirely if not set (warns once)
2. Iterates through domains, querying GrayHatWarfare API for each
3. Parses JSON response — aggregates exposed buckets by bucket name with file counts
4. Returns dict of domain → [{bucket_name, file_count}]
5. Gracefully handles API errors (returns empty dict for failed domains)
6. Does NOT send any requests to the target's infrastructure
7. Does NOT access the exposed buckets themselves — only reads the index
8. Does NOT perform any Layer 2 or Layer 3 activity

**Important distinction:** This function queries an existing public index. It does NOT enumerate cloud storage directly (that would be CloudEnum, which is classified Layer 2). GrayHatWarfare has already done the enumeration; we are reading their results.

All activity is within Layer 1 (querying a third-party public index).

## Violations

None.
