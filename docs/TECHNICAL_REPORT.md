<!-- Generated from TECHNICAL_REPORT.src.md by scripts/build_docs.py. Edit the source. -->
# Mirsad: early detection of fraudulent links in search results, maps, and new certificates

Technical report, ScamShield AI hackathon (Abu Dhabi Police and 42 Abu Dhabi), November 2026.
Team: Muhammet Yalkapov (team lead), Sulaymon Sadullo, and Ahmed Mohamed Almheiri, Abu Dhabi University.
Academic supervisor: Dr. Moatsum Alawida, Abu Dhabi University.

Every number in this report is generated from the result files in `results/` by `scripts/build_docs.py`; none is typed by hand.

## Abstract

Fraudulent websites reach UAE residents through search results, paid search ads, and map listings, where they imitate fines, tolls, parcels, banks, and government services. Existing UAE protections act when a person meets a link; Mirsad acts earlier, where the scammer places it. Mirsad watches four channels (23 UAE service searches in English and Arabic, Google Maps listings around Abu Dhabi, newly issued certificates that imitate 31 UAE brands, and public phishing feeds), scores every link with a four-ensemble URL classifier, collects passive evidence for suspicious links, and gives an analyst a ranked queue, a case file, and an evidence package. The classifier follows the DaE2 ensemble design [1], which we re-implemented with a leakage-resistant representation and retrained on 2024 to 2025 data. Our audit of the common public benchmark showed that a one-line rule scores 83.8% on it, so we tested on sites never seen in training and on later months. On later months the deployed model reaches 92.0% accuracy at a 1.17% false-positive rate, while a model trained the usual way on the benchmark flags 88.6% of legitimate sites. Because fraud is rare in live traffic, a second stage of evidence rules and an officer's confirmation decide what reaches a takedown.

## 1. Introduction

Abu Dhabi Police warned three times in 2026 (17 April, 7 June, and 13 June) about fake websites that rank near the top of search results or buy search ads for public services. In the two years to October 2025, Abu Dhabi Police handled 15,642 online fraud cases and recovered AED 140 million for victims (The National, 22 October 2025). The UAE already protects individuals at the moment of contact: the RZAM browser extension (Dubai Electronic Security Center) blocks known malicious sites, TDRA's Digital FraudHunter checks a message a person has received, and the Aman service of Abu Dhabi Police takes reports from victims. The challenge asks for a different capability: detecting fraudulent links across the open internet, including search results and maps, early enough for proactive measures.

Mirsad's contributions, built over three days, are the following.

1. An end-to-end watch over four channels (search results and ads, map listings, new certificates, and threat feeds), running on one laptop with an isolated sandbox virtual machine.
2. A detection model that scores a URL in about 114.73 ms: four ensembles (AdaBoost, Bagging, Stacking, and Voting) after the DaE2 design [1], re-implemented with a canonical URL representation, chi-squared selection, truncated SVD, and 25 lexical features.
3. A dataset audit and a leakage-aware evaluation: a random split, a split by registered domain, and a temporal split on recent data, with every threshold fixed on validation data before testing.
4. A second stage of evidence rules (domain age, forms, logos, reputation, and channel context) with a two-signal policy for live channels, so that a URL score alone rarely reaches an analyst.
5. An analyst workflow with plain-language reasons, numbered exhibits, an evidence package, and summaries written by a UAE-built language model under a fact check.
6. A privacy and safety design: websites rather than people as the subject, keyed hashing of victim data, sandboxed page loads, and an append-only audit log.

## 2. System overview

Mirsad works in four stages.

| Stage | What happens | Main code |
|---|---|---|
| Discover | Collectors pull candidate links from the four channels | `mirsad/collectors/sources.py`, `certstream_local.py` |
| Enrich | Passive evidence for suspicious links: registration date, first certificate, reputation lists, sandbox capture, logo check | `mirsad/enrich/passive.py`, `mirsad/sandbox/client.py`, `sandbox_vm/` |
| Score | The four-ensemble model on every URL, then evidence rules that can only raise the risk, and an official-domain cap | `mirsad/models/dae2.py`, `mirsad/scoring/engine.py` |
| Act | Ranked queue, case file, hold-to-confirm decision, evidence package, audit log | `mirsad/api/`, `web/`, `mirsad/store/db.py` |

A FastAPI service on the laptop runs the collectors, the model, and a SQLite store, and serves the dashboard. The sandbox is an Ubuntu virtual machine reached through VirtualBox port forwards: port 8601 for page capture and Phishpedia, and port 8602 for a local Falcon model. The laptop never loads a suspicious page itself.

## 3. Data collection

Search results and ads. Mirsad runs 23 UAE service searches in English and Arabic (for example "salik recharge", "pay traffic fine abu dhabi", and "تتبع شحنة بريد الإمارات") through SerpApi, with Serper as a fallback, and keeps every organic result and paid ad. When a search names a brand, each result is compared with that brand's official domains, so an ad for a Salik search that points elsewhere carries that fact into scoring.

Map listings. Mirsad runs 11 searches through Google Places around Abu Dhabi and checks three things: a website unrelated to the business, a brand name on a domain the brand does not own, and one phone number shared across listings with different websites. Under Google's terms Mirsad keeps only the place ID, category, website domain, coordinates for at most 30 days, and a hashed phone group.

New certificates. A scam site needs a certificate before the browser shows a padlock, and every certificate is published in Certificate Transparency logs within minutes. Mirsad starts certstream-server-go on the laptop, bound to 127.0.0.1, only for the minutes of a certificate run, and reads its feed of newly certified names; it also queries crt.sh for recent certificates that contain a protected brand. The stream carries thousands of names a second, so its brand check is stricter than elsewhere: a brand token of seven letters or more, or a near-miss spelling of one, counts on its own, while shorter or ordinary-word tokens count only beside UAE context (.ae, "dubai", "uae") or a scam word ("pay", "fines", "track").

Threat feeds. OpenPhish, URLhaus, and PhishStats supply links that others have already reported. Query strings are stripped on intake, because feed records can carry victims' details.

## 4. The detection model

### 4.1 Task

The model receives a URL string and returns the probability that it is malicious. It sees only the string; everything a string cannot show (a domain's age, a card form, a logo) belongs to the second stage in Section 6.

### 4.2 Design: diverse ensembles

The model follows the DaE2 design [1]: train several different base learners and combine them through four ensemble schemes. The reasoning is that single models fail in different ways on URL data. A linear model over character patterns misses interactions between features; a deep decision tree overfits to frequent hosts; a nearest-neighbor model depends on how dense the training data is near a query. Ensembles reduce these errors in two ways: averaging many models trained on resampled data lowers variance, and combining models with different inductive biases lowers the chance that all of them fail on the same input.

The four schemes combine learners differently.

- AdaBoost trains weak learners one after another. After each round it raises the weight of the training examples the current ensemble gets wrong, so the next learner concentrates on them, and each learner's vote is weighted by how accurate it was. With weighted error e_m in round m, the learner's weight is a_m = r * ln((1 - e_m) / e_m), where r is the learning rate, and misclassified examples have their weights multiplied by exp(a_m).
- Bagging trains many learners in parallel, each on a random sample of the training data, and averages their predicted probabilities. It mainly reduces variance, which suits deep decision trees.
- Stacking trains several base learners and then a meta-learner that takes their predicted probabilities as input and learns how much to trust each one. The meta-learner is trained on out-of-fold predictions, so it never sees a base learner's prediction on that learner's own training rows.
- Voting averages the probabilities of a few strong but different learners (soft voting). It is the simplest combination and is robust when no single learner dominates.

Mirsad keeps all four and scores each link with the mean of their probabilities:

p(u) = (p_AdaBoost(u) + p_Bagging(u) + p_Stacking(u) + p_Voting(u)) / 4.

Keeping all four, instead of selecting one, has a practical benefit beyond accuracy: the four votes are shown to the analyst, and a case where all four agree reads differently from one where a single ensemble fires.

### 4.3 Representation

Our representation is designed so that the model cannot learn which source list a URL came from, a shortcut Section 7.2 measures.

1. Canonical form. Each URL is reduced to its host (lowercased, without the scheme, "www.", default port, or trailing slash), path, and query. The benchmark's malicious rows usually carry a scheme and its benign rows usually do not, so leaving the scheme in lets a model learn the list, not the fraud.
2. Character n-grams. The canonical string is split into overlapping character sequences of three to five characters, hashed into 2^19 columns, and weighted by TF-IDF with sublinear term frequency: w(t, u) = (1 + ln tf(t, u)) * idf(t), with idf(t) = ln((1 + N) / (1 + df(t))) + 1, followed by L2 normalization. Character n-grams capture lookalike spellings, digit substitutions, and suspicious word pieces that whole-word tokens miss.
3. Selection and reduction. A chi-squared test keeps the 20,000 hashed columns most associated with the label, and a truncated singular value decomposition reduces them to 100 components. Truncated SVD is principal component analysis for sparse matrices (without centering); selecting first keeps the stored projection small and the scoring fast.
4. Lexical features. 25 handcrafted features describe the URL's structure: the lengths of the URL, host, path, and query; dots, hyphens, and digits in the host; subdomain count; slashes, parameters, "@" and "%" signs; digit ratio and host entropy; whether the host is an IP address, uses punycode or non-ASCII characters, has a port, is a known shortener, or uses a cheap top-level domain; lure words; brand mentions, brand-off-domain, and lookalike distance to the nearest protected brand; and a phone number in the query.
5. Two blocks. The sparse TF-IDF block feeds the linear and naive Bayes learners; the dense block (100 SVD components plus the lexical features, standardized) feeds trees and nearest neighbors. One featurizer serves all four ensembles, so a link is vectorized once and scored four times.

A second representation, word-level TF-IDF of the raw URL string, is kept only for the benchmark comparison in Section 7 (E1a and E2p).

### 4.4 The four ensembles as implemented

| Ensemble | Base learners | Input block | Main settings |
|---|---|---|---|
| AdaBoost | Decision trees of depth 3 | Dense | 150 rounds, learning rate 0.5 |
| Bagging | Decision trees of depth 22, at least 2 rows per leaf | Dense | 30 trees, each on a sample of half the rows drawn with replacement |
| Stacking | Logistic regression, complement naive Bayes, calibrated linear SVM (sparse); random forest of 60 trees and a decision tree of depth 18 (dense) | Both | Logistic-regression meta-learner on 3-fold out-of-fold probabilities |
| Voting | K-nearest neighbors (k = 15, distance-weighted, fitted on a 50,000-row sample), logistic regression, calibrated linear SVM | Both | Soft voting (mean probability) |

Two implementation decisions changed during the build. Boosting logistic regression on the hashed TF-IDF block collapsed to a constant output, so AdaBoost boosts shallow trees on the dense block. Exact nearest neighbors over half a million rows was too slow for live scoring, so the KNN member is fitted on a stratified sample. The linear SVM is wrapped in sigmoid calibration, because stacking and voting need probabilities, not margins.

### 4.5 Threshold

Thresholds are never tuned on the test set. Each experiment holds out 10% of its training rows as a validation slice; after fitting, the threshold is set to the lowest score at which the validation false-positive rate is at most 1%, and it is frozen before the test rows are scored. The deployed threshold is 0.66. A police queue full of false alarms would be ignored, so the false-positive rate is the constraint and recall is what the model achieves under it.

### 4.6 Engineering for live scoring

Training uses all processor cores; live scoring switches every estimator to one thread, because starting a worker pool costs more than one prediction. The deployed model file is 91.2 MB after xz compression and loads in 5.5 s. On the development laptop it scores one URL in a median of 114.73 ms (95th percentile 127.45 ms) and about 2,060 URLs a second in batches (AMD Ryzen 5 4600H, 6 cores, 15.4 GB RAM, Windows 11, one process).

## 5. Methods and approaches

Dr. Moatsum Alawida, our academic supervisor and the corresponding author of the DaE2 paper [1], gave the team permission to use the paper's methodology. This section describes that methodology in our own words, shows where each of its parts appears in Mirsad and where we departed from it, and then covers the other learning methods in the system: the deep learning models of the second stage and the analytics that turn scores into decisions. The paper's text, tables, and figures are not reproduced here, because the publisher holds their copyright; [1] remains the source for them.

### 5.1 The DaE2 methodology

DaE2 treats malicious URL detection as supervised classification: a URL is mapped to a feature vector x, and a learned function f assigns the label sign(f(x)), malicious or benign. The paper organizes the evidence a detector can use into six feature families: blacklist membership, lexical features of the URL string, host features such as registration and network data, content features of the page (HTML, JavaScript, and visual appearance), context features, and popularity features. Its pre-processing pipeline removes noise, encodes the URL text numerically with TF-IDF, rebalances the classes by resampling, ranks features by importance, and reduces dimensionality with principal component analysis.

On these features the paper trains a pool of diverse base learners (support vector machines, random forests, logistic regression, decision trees, naive Bayes, Bayesian networks, k-nearest neighbors, and artificial neural networks) and combines them through four ensemble schemes: AdaBoost, Bagging, Stacking, and Voting. Hyperparameters are tuned by grid search, models are validated with k-fold cross-validation, and the ensembles are compared on accuracy, precision, recall, F-score, and detection time, so that the chosen model balances accuracy against speed. The paper also sketches a deployment architecture beyond its offline experiments: a live URL feed and crawler, feature extraction from lexical, WHOIS, HTML, and blacklist sources, a predictor, and online updating from analyst feedback.

### 5.2 From the methodology to Mirsad

Mirsad adopts the DaE2 design where it fits a live, processor-only police tool, and departs from it where the live setting or our evaluation required. The table maps each element to its place in Mirsad.

| DaE2 element | In Mirsad | Where |
|---|---|---|
| Binary formulation | The model returns a probability of fraud; a threshold fixed on validation data turns it into a flag | Sections 4.1 and 4.5 |
| Lexical features | Character n-gram TF-IDF of the canonical URL, plus 25 handcrafted lexical features | Section 4.3 |
| Host features | Registration date, registrar, and name servers from RDAP; hosting address and network from DNS; first certificate from Certificate Transparency | Section 6.1 |
| Content features | One sandboxed page load: forms, redirect chain, screenshot, and logo identity | Section 6.2 |
| Blacklist features | URLhaus, OpenPhish, PhishStats, and VirusTotal | Sections 3 and 6.3 |
| Context and popularity features | The search that surfaced a link, its rank, whether it was an ad, and the map-listing checks | Sections 3 and 6.3 |
| Noise removal | Canonical form, and one record per canonical URL and channel | Section 4.3 |
| Numeric encoding | Hashed TF-IDF with sublinear term frequency | Section 4.3 |
| Feature importance | Chi-squared selection of the columns most associated with the label | Section 4.3 |
| Principal component analysis | Truncated SVD, its counterpart for sparse matrices | Section 4.3 |
| Class rebalancing | No resampling; stratified sampling keeps class ratios, and imbalance is handled at decision time by the false-positive-rate threshold and the two-signal policy | Sections 4.5 and 6.4 |
| Base learners | Logistic regression, complement naive Bayes, linear SVM, random forest, decision trees, and k-nearest neighbors; no Bayesian network or neural network | Section 4.4 |
| Four ensemble schemes | All four kept and averaged, with each vote shown to the analyst | Section 4.2 |
| Grid search | Not run; settings were chosen during the build and frozen before testing | Section 4.4 |
| k-fold cross-validation | A validation slice for the threshold, then three test protocols: random, by domain, and by time | Sections 4.5 and 7.3 |
| Deployment architecture | Collectors, enrichment, scoring, and the analyst queue are implemented; analyst decisions are recorded but do not yet retrain the model | Sections 2 and 11 |

Three departures need a reason. First, Mirsad averages the four ensembles instead of selecting the best one, because the four votes help an analyst judge a case. Second, k-fold cross-validation over individual URLs lets the same site fall into both training and test folds, which overstates performance on new sites (Section 7.2); splits by domain and by time measure the situation a police deployment meets. Third, Mirsad divides the feature families between two stages. The model reads only the URL string, in milliseconds, while host, content, blacklist, and context evidence arrives through rules for the few links that warrant it, since collecting that evidence costs network requests and, for content, a sandboxed page load.

### 5.3 Deep learning in the second stage

Two parts of Mirsad use deep neural networks, both in the second stage, where a few slower calls per case are affordable.

The logo check runs Phishpedia [2] in the sandbox virtual machine. A Faster R-CNN object detector, built on Detectron2, finds logo regions in the page screenshot. A Siamese network with a ResNetV2 backbone then embeds each logo and compares it with reference logos of known brands by cosine similarity; above a similarity threshold, the logo is attributed to that brand, and the page's registered domain is checked against the brand's domains. Both networks come pre-trained from the Phishpedia authors and run on the virtual machine's processor, and Mirsad accepts a match only on the brand's exact domains (Section 6.2).

Case summaries come from transformer language models: Jais 3, a bilingual Arabic and English model from MBZUAI's Institute of Foundation Models, reached through its API, or a local Falcon model served by llama.cpp inside the sandbox. The model writes at temperature zero from facts Mirsad has already established, a fact check rejects any unsupported statement, and the model never changes a score or a decision (Section 8).

Deep learning was also considered for the URL model itself and left out. Character-level convolutional networks such as URLNet [8] and transformers trained on URLs such as URLTran [9] and URLBERT [10] are strong published approaches. We did not use them for three reasons: training or fine-tuning them on our data did not fit the event on a laptop processor, they would add to the scoring time of every link, and their decisions are harder to explain in a case file than four votes and a list of rules. A compact transformer added as a fifth vote, and tested under the same domain and time splits, is the next experiment.

### 5.4 Analytics

Analytics in Mirsad work at three levels.

Model analytics decide whether the classifier can be trusted: per-class precision, recall, and F1, the false-positive rate at the frozen threshold, ROC AUC, and the precision to expect at a realistic share of fraud (Section 6.4). The dataset audit (Section 7.2) applies the same discipline to the data, testing whether a trivial rule or shared domains explain a score.

Case analytics explain one link: the four ensemble votes against the threshold, the rules that fired with one sentence each, numbered exhibits with their source and time, a timeline, and a graph of how the evidence connects. Infrastructure analytics then place the link among others. The hosting address and its network owner come from DNS over HTTPS and Team Cymru's IP-to-ASN service, and a case links to other cases that share its address or its private name servers; content-delivery networks and common name-server providers are excluded, so a shared link means shared infrastructure.

Operational analytics show the watch as a whole on the dashboard: links screened and flagged per channel, flags per hour over the last day, cases awaiting review and confirmed, the median scoring time, the map-check results (listings whose website matches the business, mismatches, and phone numbers shared across listings), and the audit log of views, decisions, and exports. The summary report gathers the same picture into one PDF in English or Arabic.

## 6. The second stage: evidence and decision

### 6.1 Passive enrichment

For links near or above the threshold, Mirsad collects evidence by looking only: the registration date from RDAP, the first certificate from crt.sh (which stands in for .ae domains, whose registry hides dates), URLhaus and VirusTotal verdicts, and, when the sandbox is running, one page load. It never logs in, submits a form, or probes a server. Sites on shared hosting platforms (framer.app, github.io, and others in the Public Suffix List's private section) are marked as such, because the platform's registration date says nothing about the site.

### 6.2 Sandbox capture and logo check

The sandbox service loads the page once in a fresh Playwright Chromium context and returns a screenshot, the redirect chain, and every form with its fields and target domain. A route handler and an internal SOCKS proxy resolve each request's host and refuse private, loopback, link-local, and other non-global addresses, which closes the DNS-rebinding gap between two lookups. Navigations other than GET and HEAD are aborted, so a page cannot submit a form by itself. Phishpedia then looks for a known brand's logo in the screenshot and checks whether the page's registered domain belongs to that brand; Mirsad counts a match only on the brand's exact domains, stricter than Phishpedia's default.

### 6.3 Evidence rules

Each rule sets a minimum risk when it fires and adds one sentence to the case. Rules can only raise the risk; the one exception is the official-domain cap, which keeps a brand's own domains (and any .gov.ae host) out of the queue.

| Rule | Fires when |
|---|---|
| Brand off domain | The name imitates a protected brand on a domain the brand does not own |
| Card form, password form | The captured page asks for a card number or a password |
| Form to another domain | A form on the page posts to a different registered domain |
| Logo mismatch | Phishpedia finds a brand's logo on a domain that brand does not use |
| Ad for a brand query | The link was bought as an ad for a search that names a brand |
| Ranks for a brand query | The link ranks in organic results for a brand search without being official |
| Listing checks | A map listing's website is unrelated to the business, a brand appears on a non-official domain (flagging only when that domain is young or on a cheap top-level domain), or one phone number appears on three or more listings |
| Reputation | URLhaus or OpenPhish lists the link, or at least two VirusTotal engines flag it |
| Injected phone number | An official brand page is linked with a phone number in its query string, a trick that shows a fake support number on a real site |
| Young domain | The domain was first seen within 90 days (a reason, and a stronger brand rule when within 30) |

### 6.4 Two signals on live channels

The validation results imply that a URL score alone cannot carry a live queue. If 1% of screened links were fraudulent, precision would be P = (TPR * b) / (TPR * b + FPR * (1 - b)) with b = 0.01; for the deployed model this gives about 41.9%. Our first live run confirmed it: ordinary business websites from map listings crossed the threshold on their address alone. On the search, maps, and certificate channels a link therefore enters the queue only with a model score of at least 0.97, or with at least one solid rule that agrees. Weak rules (a young domain on its own, an unrelated listing website, an organic result for a brand query) do not count as that second signal. Links that miss the bar stay just under the threshold, on watch.

## 7. Evaluation

### 7.1 Data

Two public datasets were used. malicious_phish (Kaggle) is the common benchmark for URL classification: 651,191 URLs labeled benign, defacement, phishing, or malware, pooled from several older sources. PhreshPhish (Hugging Face, CC BY 4.0) holds phishing and benign pages from July 2024 to December 2025 with a strictly later test split; Mirsad reads only its URL, label, and date columns. Each experiment trains on a stratified sample of up to 200,000 rows, a limit set by the build time; the exact counts are in the result files.

### 7.2 Dataset audit (E0)

Before any training, `scripts/audit_dataset.py` measured what the benchmark rewards.

- The rule "malicious if the URL starts with a scheme" is 83.8% accurate, because 68.4% of malicious rows carry a scheme against 8.3% of benign rows.
- Under a random 80/20 split, 80.9% of test rows share their registered domain with training rows, so a model can pass by remembering sites.
- The defacement class has 96,457 rows from only 2,122 registered domains.
- There are 10,072 exact duplicate URLs and 4,017 canonical URLs with two different labels.

These findings motivated the canonical representation and the two harder test settings below.

### 7.3 Protocol and metrics

All experiments are binary (benign against malicious). Thresholds come from the validation slice as described in Section 4.5. Reported metrics are accuracy; precision, recall, and F1 for the fraud class; the false-positive rate; ROC AUC; and precision at a 1% prevalence. The tables show the four ensembles and their mean at each one's own validation threshold.

### 7.4 E1: public benchmark, random split

Random, stratified 80/20 split of the benchmark sample (144,000 training rows, 16,000 validation rows, 40,000 test rows).

E1a, raw URL with word TF-IDF (the conventional setting):

| Model | Accuracy | Precision (fraud) | Recall (fraud) | F1 (fraud) | False-positive rate | ROC AUC | Precision if 1% of links are fraud |
|---|---|---|---|---|---|---|---|
| AdaBoost | 91.5% | 97.6% | 77.1% | 0.86 | 0.99% | 0.98 | 44.1% |
| Bagging | 94.5% | 97.8% | 85.7% | 0.91 | 0.99% | 0.98 | 46.7% |
| Stacking | 95.5% | 98.1% | 88.7% | 0.93 | 0.91% | 0.99 | 49.5% |
| Voting | 94.6% | 97.9% | 86.1% | 0.92 | 0.97% | 0.99 | 47.4% |
| Mean of the four | 95.5% | 97.9% | 88.7% | 0.93 | 0.99% | 0.99 | 47.5% |

E1b, our canonical representation on the same split:

| Model | Accuracy | Precision (fraud) | Recall (fraud) | F1 (fraud) | False-positive rate | ROC AUC | Precision if 1% of links are fraud |
|---|---|---|---|---|---|---|---|
| AdaBoost | 79.0% | 95.0% | 40.8% | 0.57 | 1.11% | 0.89 | 27.1% |
| Bagging | 85.0% | 96.4% | 58.4% | 0.73 | 1.14% | 0.95 | 34.2% |
| Stacking | 90.4% | 97.3% | 74.1% | 0.84 | 1.08% | 0.98 | 40.8% |
| Voting | 89.8% | 97.1% | 72.5% | 0.83 | 1.11% | 0.98 | 39.7% |
| Mean of the four | 88.9% | 97.1% | 69.7% | 0.81 | 1.09% | 0.97 | 39.1% |

Removing the scheme and "www." costs the ensemble mean about 6.58 accuracy points: the share of the conventional score that came from recognizing source lists rather than fraud.

### 7.5 E2: sites never seen in training

Duplicates and conflicting labels removed; the split is grouped by registered domain, so no domain appears on both sides (0 shared domains).

With the raw representation:

| Model | Accuracy | Precision (fraud) | Recall (fraud) | F1 (fraud) | False-positive rate | ROC AUC | Precision if 1% of links are fraud |
|---|---|---|---|---|---|---|---|
| AdaBoost | 89.7% | 95.5% | 73.3% | 0.83 | 1.78% | 0.95 | 29.3% |
| Bagging | 91.6% | 94.9% | 79.7% | 0.87 | 2.24% | 0.96 | 26.4% |
| Stacking | 91.8% | 93.0% | 82.3% | 0.87 | 3.22% | 0.97 | 20.5% |
| Voting | 90.8% | 91.3% | 80.7% | 0.86 | 3.97% | 0.96 | 17.0% |
| Mean of the four | 92.0% | 93.5% | 82.3% | 0.88 | 2.97% | 0.97 | 21.9% |

With ours:

| Model | Accuracy | Precision (fraud) | Recall (fraud) | F1 (fraud) | False-positive rate | ROC AUC | Precision if 1% of links are fraud |
|---|---|---|---|---|---|---|---|
| AdaBoost | 76.5% | 95.0% | 33.0% | 0.49 | 0.91% | 0.86 | 26.9% |
| Bagging | 80.3% | 95.4% | 44.5% | 0.61 | 1.12% | 0.88 | 28.6% |
| Stacking | 84.6% | 94.3% | 58.5% | 0.72 | 1.82% | 0.94 | 24.5% |
| Voting | 84.7% | 93.2% | 59.6% | 0.73 | 2.25% | 0.93 | 21.1% |
| Mean of the four | 84.1% | 95.2% | 56.2% | 0.71 | 1.47% | 0.93 | 27.9% |

### 7.6 E3: recent threats, later months

Trained on PhreshPhish URLs from 2024-07-02 to 2025-09-08 (180,000 training rows) and tested on 168,060 URLs from 2025-09-08 to 2025-12-16, a strictly later period. This is the deployed model.

| Model | Accuracy | Precision (fraud) | Recall (fraud) | F1 (fraud) | False-positive rate | ROC AUC | Precision if 1% of links are fraud |
|---|---|---|---|---|---|---|---|
| AdaBoost | 86.4% | 98.0% | 71.7% | 0.83 | 1.23% | 0.97 | 37.0% |
| Bagging | 85.3% | 97.9% | 69.4% | 0.81 | 1.25% | 0.97 | 35.9% |
| Stacking | 92.9% | 98.3% | 85.9% | 0.92 | 1.24% | 0.99 | 41.1% |
| Voting | 92.5% | 98.2% | 85.3% | 0.91 | 1.32% | 0.99 | 39.5% |
| Mean of the four | 92.0% | 98.4% | 83.8% | 0.90 | 1.17% | 0.99 | 41.9% |

E3b scores the same later test set with the E1a model, trained the conventional way on the benchmark:

| Model | Accuracy | Precision (fraud) | Recall (fraud) | F1 (fraud) | False-positive rate | ROC AUC | Precision if 1% of links are fraud |
|---|---|---|---|---|---|---|---|
| AdaBoost | 53.3% | 49.4% | 93.1% | 0.65 | 80.29% | 0.63 | 1.2% |
| Bagging | 50.9% | 48.0% | 88.9% | 0.62 | 81.09% | 0.54 | 1.1% |
| Stacking | 52.5% | 49.0% | 96.7% | 0.65 | 84.58% | 0.70 | 1.1% |
| Voting | 56.8% | 51.5% | 95.9% | 0.67 | 76.15% | 0.66 | 1.3% |
| Mean of the four | 50.9% | 48.1% | 97.8% | 0.65 | 88.59% | 0.63 | 1.1% |

### 7.7 Discussion

The benchmark score in the conventional setting is mostly a measure of the dataset, not of fraud detection: one rule about the scheme reaches 83.8%, and accuracy falls to 84.1% once sites cannot be shared between training and test. The temporal test is the one that matters for a police deployment, and it separates the two training choices sharply. The benchmark-trained model flags 88.6% of legitimate later URLs, while the model retrained on recent data holds a 1.17% false-positive rate with 83.8% recall. Even so, at realistic prevalence about 41.9% of model-only flags would be right, which is why Section 6 exists.

## 8. Analyst workflow

The Watch screen shows the ranked queue, a stylized map of Abu Dhabi with map-check results, flags per hour, and the selected case. The case page shows the four ensemble votes, the final risk against the threshold, a timeline, a graph of how the evidence connects, numbered exhibits with their sources, and the reasons in plain words. An analyst confirms a case by holding a button, which prevents accidental decisions; the evidence package then exports the redacted link, exhibits, timeline, and a request shaped for the registrar, aeDA, or a police blocking request.

Case summaries in English and Arabic are written by Jais 3 (MBZUAI Institute of Foundation Models) or, in a zero-egress mode, by a local Falcon in the sandbox. The model receives only facts Mirsad has established, never page text, because a page can carry instructions aimed at a language model (prompt injection). A fact check rejects any summary with a number, a protected brand, or an imitation claim that the facts do not support, and summaries may not say a site is live; a template is written instead. Summaries are rewritten whenever cases are rescored.

## 9. Privacy, security, and legal design

The subject of Mirsad is websites, not people. It collects no visitor data, cookies, or form inputs. Query values in stored links, which can carry a victim's email or token, appear in every list view only as keyed HMAC-SHA-256 hashes, and feed URLs lose their query strings on intake. Suspicious pages load only in the sandbox, with private addresses blocked and no form submission. The lab server binds to localhost. The public demo on Hugging Face Spaces runs in a separate public mode that never opens a suspect page, replaces every query value with a placeholder, caps live runs per hour and per day, and accepts changes only from its own origin (`docs/SECURITY.md`). On both, every case view, decision, export, and on-demand check is written to an append-only audit table. No case is blocked automatically; an officer decides.

The legal frame is Federal Decree-Law No. 34 of 2021 on countering rumors and cybercrimes. Articles 11, 15, 40, and 48 describe the offenses Mirsad detects (fake websites, card-data capture, internet fraud, and misleading online advertisements); Articles 1 to 4 and 12 bound how it collects (public pages only, one load per page, rate limits, no logins or form submission, no vulnerability scanning); Articles 62 and 66 provide the blocking powers its evidence package serves. Mirsad also applies the principles of the Personal Data Protection Law (Federal Decree-Law No. 45 of 2021): purpose limitation, minimization, accuracy, and security. Details are in `docs/PRIVACY.md`.

## 10. Live results

In live runs on 23 November 2026, Mirsad screened 337 links across the four channels and flagged 5: 4 from the threat feeds and 1 from the certificate stream (emirates-airlines.battery.cam, which places the Emirates airline name on an unrelated domain). The search and map channels produced candidates but no flags under the two-signal policy. Testing exposed and fixed five problems:

- address-only flags on ordinary business sites, fixed by the two-signal policy and host-only brand matching;
- stale summaries that named brands a case no longer had, fixed by the fact check and rewriting on rescore;
- the certificate stream saturating VirtualBox's network when it ran in the sandbox, fixed by running it on the host during a run only;
- short brand tokens matching ordinary words in thousands of certificates, fixed by the stricter certificate check;
- long retry loops while crt.sh was down, fixed by stopping after two failed queries.

## 11. Limitations and future work

Training used samples of up to 200,000 rows per experiment. The evidence rules are hand-set floors; with a few hundred analyst decisions they should be learned and calibrated. Of the 31 protected brands, only 2 have official domains verified from a source, and a deployment needs each brand to confirm its domains and phone numbers. Search ads vary by time and location, so a deployment should query from UAE locations on a schedule and add the Google Ads Transparency Center. Free service tiers (OpenPhish community, VirusTotal public) are non-commercial. With more time, the next steps are learning the second stage from officer decisions, Arabic-script and punycode lookalikes at scale, registrar abuse APIs, and a 90-day pilot with the Cybercrime unit that measures the time from a new certificate to a takedown.

## 12. Use of AI tools

The team chose the challenge, the approach, the scope, the data sources, the design direction, and every product decision. Anthropic's Claude Code helped with research about datasets and UAE fraud context; implemented the prototype and experiments. The team reviewed the results and is responsible for the submission.

## References

[1] Omolara, A.E. and Alawida, M. (2025). DaE2: Unmasking malicious URLs by leveraging diverse and efficient ensemble machine learning for online security. Computers & Security 148, 104170. https://doi.org/10.1016/j.cose.2024.104170

[2] Lin, Y., Liu, R., Divakaran, D.M., Ng, J.Y., Chan, Q.Z., Lu, Y., Si, Y., Zhang, F., and Dong, J.S. (2021). Phishpedia: A hybrid deep learning based approach to visually identify phishing webpages. USENIX Security Symposium. Code: https://github.com/lindsey98/Phishpedia

[3] PhreshPhish dataset. Hugging Face, phreshphish/phreshphish, CC BY 4.0.

[4] malicious_phish dataset. Kaggle, sid321axn, "Malicious URLs dataset", CC0.

[5] certstream-server-go, version 1.10.1. https://github.com/d-Rickyy-b/certstream-server-go (MIT).

[6] Federal Decree-Law No. 34 of 2021 on Countering Rumours and Cybercrimes, United Arab Emirates (English translation hosted by ADGM; the Arabic text is authoritative).

[7] Federal Decree-Law No. 45 of 2021 on the Protection of Personal Data, United Arab Emirates.

[8] Le, H., Pham, Q., Sahoo, D., and Hoi, S.C.H. (2018). URLNet: Learning a URL representation with deep learning for malicious URL detection. arXiv:1802.03162. Code: https://github.com/Antimalweb/URLNet

[9] Maneriker, P., Stokes, J.W., Garcia Lazo, E., Carutasu, D., Tajaddodianfar, F., and Gururajan, A. (2021). URLTran: Improving phishing URL detection using transformers. IEEE Military Communications Conference (MILCOM).

[10] URLBERT, a BERT model pre-trained on URLs for URL classification. Code: https://github.com/Davidup1/URLBERT (Apache-2.0).
