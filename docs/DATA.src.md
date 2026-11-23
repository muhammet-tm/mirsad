# Data and services

Every dataset and service Mirsad uses, with its license or terms and what the code keeps. Checked on 22 and 23 November 2026.

## Training and evaluation data

| Dataset | What it is | License | How Mirsad uses it |
|---|---|---|---|
| malicious_phish (Kaggle, sid321axn) | 651,191 URLs labeled benign, defacement, phishing, or malware, pooled from ISCX-URL2016, PhishTank, PhishStorm, a malware domain list, and a benign list | CC0 (public domain), per the Kaggle API | Reproduction of the DaE2 paper (E1) and the domain-split test (E2). Downloaded with `scripts/download_data.py kaggle`; not committed. |
| PhreshPhish (Hugging Face, phreshphish/phreshphish) | Phishing and benign web pages collected from July 2024 to December 2025, with a strictly later test split | CC BY 4.0 | Only the `url`, `label`, `target`, `date`, and `lang` columns are read (about 27 MB of the 36.6 GB dataset) with `scripts/phreshphish_columns.py`. Training data of the deployed model (E3). |
| Tranco top 1 million (list 46YLX, 21 November 2026) | Research ranking of popular sites, aggregated from several providers | Cite the Tranco paper; input lists carry their own licenses (tranco-list.eu) | Benign reference for live evaluation. |
| UAE brand list (`mirsad/features/brands.py`) | {{app.brands}} brands and their official domains | Team-compiled from public sources | Brand-mismatch and lookalike checks. Only {{app.brands_verified}} brands have domains verified from a source; the rest exist in DNS and need ownership checks before a deployment. |

## Live services

| Service | Use | Terms that shape the code | Key |
|---|---|---|---|
| SerpApi | Search results and ads for {{app.search_queries}} UAE service queries in English and Arabic | Free plan 250 searches a month; results not resold | `SERPAPI_API_KEY` |
| Serper | Fallback search results | 2,500 free queries; ads not returned in our test | `SERPER_API_KEY` |
| Google Places API (New), Text Search | Map listings around Abu Dhabi with website, phone, and location | Store place IDs indefinitely and coordinates for at most 30 days; do not store business names, addresses, or reviews. Mirsad keeps place ID, category, website domain, coordinates, and a hashed phone group only. | `PLACES_API_KEY` |
| crt.sh and the Certificate Transparency stream (certstream-server-go 1.10.1, MIT, run on the host only during a certificate run) | Newly issued certificates that contain or imitate a protected brand | Public logs; about 5 requests a minute to crt.sh; the stream downloads every new certificate from every log while it runs, tens of megabits a second, so runs are kept to a few minutes | none |
| RDAP (IANA bootstrap) | Domain registration date for generic top-level domains | Public; .ae has no RDAP and hides dates, so the first certificate date stands in | none |
| OpenPhish community feed | Fresh phishing URLs | Non-commercial use only | none |
| abuse.ch URLhaus | Malware-distribution URLs and per-URL lookups | Free under fair use | `ABUSECH_AUTH_KEY` |
| PhishStats | Recent phishing URLs | 50 requests a day without a key; records can carry victim data, so query strings are stripped on intake | none |
| VirusTotal public API | Multi-engine verdicts on flagged links | 4 requests a minute, 500 a day, non-commercial only | `VIRUSTOTAL_API_KEY` |
| Jais 3 (MBZUAI Institute of Foundation Models) | Case summaries in English and Arabic | Built in the UAE; hosting location not verified | `JAIS_API_KEY` |
| Falcon (TII), local | Zero-egress summaries inside the sandbox VM | TII Falcon License | none |
| Phishpedia | Logo-versus-domain check on captured pages, inside the sandbox VM | CC0-1.0 | none |

A hackathon prototype is non-commercial. An operational deployment for the police would move to commercial tiers (Google Web Risk instead of Safe Browsing, paid OpenPhish and VirusTotal access) and would need the brand list verified with each brand.

## What is never stored

Visitor data, cookies, anything behind a login, form inputs (Mirsad never submits a form), map business names and addresses, raw query-string values outside the evidence package, the DaE2 paper itself (Elsevier copyright), and raw datasets (rebuilt by scripts).
