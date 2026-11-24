<!-- Generated from README.src.md by scripts/build_docs.py. Edit the source. -->
# مرصاد Mirsad

Mirsad ("the watchtower") finds fraudulent links and websites where people in the UAE meet them: search results, paid search ads, map listings, and newly issued certificates. It scores every link with a four-ensemble URL classifier, gathers passive evidence for the suspicious ones, and gives an Abu Dhabi Police analyst a ranked queue, a case file with numbered exhibits, and an evidence package for a takedown or blocking request.

Built for ScamShield AI (Abu Dhabi Police and 42 Abu Dhabi, 24 and 25 November 2026). Challenge: "Detecting Fraudulent Links and Websites Used in Cybercrimes and Financial Fraud ... across the open internet, including those appearing in Search Engine results and Maps", with the objective of early identification and proactive measures.

## The problem

Abu Dhabi Police warned three times in 2026 (17 April, 7 June, and 13 June) about fake websites that rank near the top of search results or buy search ads for government services, consumer protection, fines, and deliveries. Abu Dhabi Police handled 15,642 online fraud cases and recovered AED 140 million for victims in the two years to October 2025 (The National, 22 October 2025). The UAE already protects individuals at the moment of contact: the RZAM browser extension (Dubai Electronic Security Center) blocks known malicious sites, and TDRA's Digital FraudHunter checks a suspicious message a person received. What is missing is the step before contact: finding the fraudulent site where the scammer placed it, early, and handing investigators the evidence.

## The solution

| Challenge clause | Mirsad |
|---|---|
| Search engine results | Runs 23 UAE service queries in English and Arabic ("salik recharge", "pay traffic fine abu dhabi", "تتبع شحنة بريد الإمارات") and screens every organic result and paid ad against the official domain of the brand the query names |
| Maps | Checks Google Maps listings around Abu Dhabi for websites unrelated to the business, brand names on non-official domains, and phone numbers shared across listings |
| Early identification | Watches Certificate Transparency for new certificates that contain or imitate a protected brand, often before the link circulates; domain age is a core signal |
| Detecting fraudulent links | DaE2 ensemble on every URL in milliseconds, then evidence rules (domain age, card or password forms, forms posting to another domain, logo on the wrong domain, reputation lists) |
| Proactive measures | Ranked queue, case file, hold-to-confirm decision, and an evidence package shaped for a registrar, aeDA, or a police blocking request under Articles 62 and 66 of Federal Decree-Law No. 34 of 2021 |

## Results (measured by our code)

The detection model combines four ensembles (AdaBoost, Bagging, Stacking, and Voting) after the DaE2 design, which we re-implemented, retrained on recent data, and tested in harder settings. The method, the experiments, and every table are in the [technical report](docs/TECHNICAL_REPORT.md) ([PDF](docs/Mirsad_Technical_Report.pdf)). Every number here is generated from `results/*.json`.

- Dataset audit: in the common public benchmark (malicious_phish), the single rule "malicious if the URL starts with a scheme" is already 83.8% accurate, and 80.9% of test rows under a random split share a domain with training rows.
- Public benchmark, random split, raw URLs (the conventional setting): accuracy 95.5% at a false-positive rate of 0.99%.
- Same split without scheme and "www." artifacts: 88.9%.
- Sites never seen in training (split by domain): 84.1% with our representation.
- Deployed model on later months (trained July 2024 to September 2025, tested September to December 2025): accuracy 92.0%, fraud recall 83.8%, false-positive rate 1.17%, ROC AUC 0.99.
- Speed: median 114.73 ms per URL, about 2,060 URLs a second in batches, on a laptop CPU.

## Reasoning behind the technical choices

- A four-ensemble model as the first stage. It is explainable (four votes per link), steadier than any one of its models, and fast enough to screen every link the collectors find. We first measured it in the conventional benchmark setting, so the comparison is fair, then changed only what the audit showed was wrong.
- Canonical URLs and a domain split. The audit showed that the benchmark dataset rewards recognizing which source list a URL came from. Removing the scheme and "www." and splitting by domain gives lower but honest numbers for sites the model has never seen, which is the early-identification case.
- Retraining on recent data. Phishing changes monthly. The deployed model trains on 2024 to 2025 URLs and is tested on later months.
- A rules stage on top of the model. Domain age, forms, logos, and channel context cannot be learned from a URL string. They enter as floors that only raise the risk, each with a plain reason, so an officer can see why a case is in the queue.
- Two signals before the queue. At a 1% base rate the model alone would be right on only about 41.9% of its flags, and our first live run flagged ordinary business sites on the URL alone. On live channels a link therefore needs either a very high model score (0.97) or one piece of evidence that agrees.
- Thresholds at a 1% false-positive rate. A police queue full of false alarms gets ignored; the threshold is fixed on validation data before testing.
- Isolation. Suspicious pages load only inside an Ubuntu VM (fresh browser, private addresses blocked, no form submission); Phishpedia's logo matching needs Linux anyway.
- UAE-built language models for summaries. Jais writes English and Arabic summaries from Mirsad's own facts; a local Falcon gives a zero-egress mode. The model writes and never decides, and it never reads the attacker's page text, which could carry prompt injection.

## Trade-offs, what we left out, and what we would do differently

- Trained on samples of up to 200,000 URLs per experiment instead of the full datasets, to fit the 24-hour build.
- The second-stage rules are hand-set floors, not learned weights; with a few hundred analyst decisions they should be learned and calibrated.
- The brand list covers 31 UAE brands; only 2 have their official domains verified from a source, and an operational version needs each brand to confirm its domains and phone numbers.
- Map checks use Google Places; Google's terms forbid storing business names, so the case file shows category and place ID. A police deployment would agree data terms with the map provider.
- Search ads vary by time and location; a deployment would query from UAE locations on a schedule and use the Google Ads Transparency Center as a second source.
- Free tiers (OpenPhish community, VirusTotal public) are non-commercial; an operational deployment needs commercial tiers.
- With more time: learn the second stage from analyst decisions, add Arabic-script and Punycode lookalikes to the certificate watch at scale, push confirmed cases to registrars automatically through their abuse APIs, and run a pilot with a bank's fraud team.

## Quick start (Windows, macOS, or Linux)

You need Git and Python 3.11, 3.12, or 3.13. No API key, sandbox, or training is needed, because the trained model ships in `models/`.

```
git clone https://github.com/muhammet-tm/mirsad.git
cd mirsad
python run.py
```

The first run creates a virtual environment in `.venv`, installs the requirements (a few minutes), loads demo cases, starts the service on http://127.0.0.1:8600, and opens the dashboard; later runs start in seconds. If `python` is another version, `run.py` looks for Python 3.12, 3.13, or 3.11 on its own (`py -3.12` on Windows, `python3.12` elsewhere).

The demo cases are five invented lookalikes of UAE brands (Salik, TAMM, UAE PASS, Emirates Post, ADCB) on the reserved `.example` domain, which can never belong to a real site, and three official sites that the official-domain cap keeps out of the queue. When the machine is online, the public phishing feeds (OpenPhish and PhishStats) are screened as well. Type any address into "Check a link" to score it.

To score a test set, pass a text file with one URL per line, or a CSV file with a `url` column and an optional `label` column:

```
python run.py --score test_urls.csv --out scored.csv
```

`python run.py --score demo/demo_links.csv` tries it on the demo links. Each row of `scored.csv` holds the risk, the verdict at the frozen threshold of 0.6574, the four ensemble votes, the brand imitated, and the reasons. When labels are present, the command also prints accuracy, precision, recall, F1, false-positive rate, and ROC AUC. With `--expand-short-links`, short links (bit.ly and the like) are scored at their destination, which Mirsad learns from the shortener without contacting the destination. The same scoring is available to other systems as `POST /api/check/batch` ([docs/API.md](docs/API.md)).

`python run.py --test` runs the test suite, and `python run.py --help` lists the other options (`--port`, `--no-browser`, `--no-demo`, `--no-feeds`).

## Full build and live channels (Windows, PowerShell)

The steps below rebuild the data and the model from scratch and switch on the channels that need keys. They need about 2 GB of disk, and VirtualBox for the optional sandbox VM. Run `python run.py --test` once first if you skipped the quick start, so that `.venv` exists. Keys go in `.env`, and every integration is optional:

```powershell
copy .env.example .env
```

Data and models (about 15 minutes of downloads and 1 to 2 hours of training on a laptop CPU):

```powershell
.\.venv\Scripts\python.exe scripts\download_data.py kaggle
.\.venv\Scripts\python.exe scripts\download_data.py tranco
.\.venv\Scripts\python.exe scripts\phreshphish_columns.py --split train --out data\raw\phreshphish_train_urls.parquet
.\.venv\Scripts\python.exe scripts\phreshphish_columns.py --split test --out data\raw\phreshphish_test_urls.parquet
.\.venv\Scripts\python.exe scripts\audit_dataset.py
.\.venv\Scripts\python.exe scripts\train_eval.py --exp e1,e2,e3,e4 --sample 200000
```

Run the service and open the dashboard at http://127.0.0.1:8600:

```powershell
.\.venv\Scripts\python.exe -m uvicorn mirsad.api.app:app --host 127.0.0.1 --port 8600
```

Started this way, the service loads no demo cases (run `.\.venv\Scripts\python.exe scripts\load_demo.py` for them). Two other ways to see it working:

- Interface preview, no network and no database: open http://127.0.0.1:8600/?mock=1. The screen marks the data as demo data.
- Real data without any API key: the feeds channel (OpenPhish and PhishStats) and the certificate channel need no key. The certificate channel downloads the certstream-server-go release once, checks its SHA-256, and runs it on 127.0.0.1 only while the run listens; it downloads every new certificate from the public logs, tens of megabits a second, so keep runs short on shared networks.

```powershell
.\.venv\Scripts\python.exe scripts\run_watch.py feeds
```

```powershell
.\.venv\Scripts\python.exe scripts\run_watch.py certificates --stream-seconds 60
```

With keys in `.env` (see `.env.example`), collect from every channel; search needs SerpApi or Serper, maps needs Google Places, and summaries use Jais (a template is written without a key):

```powershell
.\.venv\Scripts\python.exe scripts\run_watch.py all
```

Optional sandbox VM for page capture, Phishpedia, and local Falcon: see [sandbox_vm/README.md](sandbox_vm/README.md). Without it, Mirsad still scores and enriches links; cases simply have no capture.

Tests and documents:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\build_docs.py
```

## Documents

[technical report](docs/TECHNICAL_REPORT.md) ([PDF](docs/Mirsad_Technical_Report.pdf)), [architecture](docs/ARCHITECTURE.md), [privacy design](docs/PRIVACY.md), [data and services](docs/DATA.md), [API](docs/API.md), [use of AI tools](docs/AI_USE.md).

The presentation is in `deck/`: `Mirsad_Deck.html` is the animated deck for presenting (open it in a browser; arrow keys move, F gives full screen), `Mirsad_Deck.pdf` is the same deck as a PDF, and `Mirsad_Deck.pptx` is an editable PowerPoint copy. All three come from one source, `deck/Mirsad_Deck.src.html`, whose numbers are filled from `results/*.json` like the documents. The PowerPoint copy uses Inter and Consolas in place of the deck's web fonts, so the PDF is the exact version. To rebuild the deck after new results (needs Node.js and Playwright with Chromium):

```powershell
.\.venv\Scripts\python.exe scripts\build_docs.py
npm install --prefix deck\tools
node deck\tools\render_slides.cjs
node deck\tools\build_pptx.cjs
```

## Team

Muhammet Yalkapov (team lead, security and product), Sulaymon Sadullo (data and AI), and Ahmed Mohamed Almheiri (deployment and partnerships), Abu Dhabi University. Academic supervisor: Dr. Moatsum Alawida, Abu Dhabi University.

## Use of AI tools

The team chose the challenge, the approach, the scope, the data sources, the design direction, and every product decision. Anthropic's Claude Code helped with research about datasets and UAE fraud context; implemented the prototype and experiments. The team reviewed the results and is responsible for the submission. Inside the product, Jais (or a local Falcon) writes case summaries from Mirsad's own facts and never decides; see [docs/AI_USE.md](docs/AI_USE.md).

## Credits

The detection model follows the DaE2 ensemble design: Omolara, A.E. and Alawida, M. (2025), Computers & Security 148, 104170, https://doi.org/10.1016/j.cose.2024.104170. Third-party components and data keep their own licenses (see [LICENSE.md](LICENSE.md) and [docs/DATA.md](docs/DATA.md)).
