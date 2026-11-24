# UAE brand logos for Phishpedia

Phishpedia recognizes a brand by comparing each logo it finds in a screenshot with a reference list of logos. The list it ships with covers 277 global brands. Most of the UAE brands that scammers imitate, such as Salik, Abu Dhabi Police, TAMM, and Emirates Post, are probably not in it. The install script in this folder, `install_brands.py`, adds them to Phishpedia inside the sandbox VM.

## Rules for the logo files

The team fetches each logo at setup time from the brand's own official website, which means a domain in the table below. No other source qualifies, including search engine images, logo collections, and copies from phishing pages. A phishing copy may be altered, and in any case its rights belong to the brand.

Logo files never go into git. They are the brands' intellectual property, and Mirsad only needs them as local reference data in the VM. The `.gitignore` in `sandbox_vm` excludes `brands/logos/`. Keep the files in the VM at `/srv/scamshield/brands/logos/`. If you prepare them on Windows first, put them in `sandbox_vm\brands\logos\`, and setup copies them into the VM.

Write a `SOURCE.txt` file next to each brand's logos with the page URL and the date you fetched it, for example `https://www.salik.ae/ fetched 2026-11-23 from the site header`. The install script warns when this file is missing. Delete the logos after the event, together with the captures.

## How Phishpedia stores brands

Phishpedia reads two things, both under `/srv/scamshield/Phishpedia/models/`:

```
expand_targetlist/            one folder per brand; the folder name is the brand name
  Salik/
    mirsad_logo_en.png        any number of PNG or JPEG logo crops
    mirsad_logo_ar.png
  Abu Dhabi Police/
    mirsad_logo.png
  ...
domain_map.pkl                a pickled dict: brand name -> list of official domains
                              {"Salik": ["salik.ae"], "Abu Dhabi Police": ["adpolice.gov.ae"], ...}
```

Every brand folder must have an entry with exactly the same name in `domain_map.pkl`. Phishpedia looks up the matched folder in this map and raises an error for every page whose logo resembles a folder that has no entry. Phishpedia also caches the reference embeddings in `LOGO_FEATS.npy` and `LOGO_FILES.npy` in its own folder. Rebuild them after any change; otherwise Phishpedia ignores the new logos.

`install_brands.py` handles all three parts. It copies the logos, merges the domains into `domain_map.pkl` (after backing it up as `domain_map.pkl.orig` and a timestamped copy), and rebuilds the cache.

## Steps

1. Collect the logos. For each brand, open its official site and save the logo from the page header. Prefer the site's own PNG or SVG file. Convert an SVG to PNG, for example by taking a screenshot of the logo element, and crop it tightly to the logo with a few pixels of margin. Add the Arabic logo and any light-on-dark variant as separate files. A width of 150 to 400 pixels is enough. The script puts transparent pixels on a white background, because Phishpedia converts logos to RGB and transparency would otherwise turn black.

2. Put each brand's files in a folder whose name is exactly the brand name in the table below, for example `/srv/scamshield/brands/logos/Salik/logo_en.png`. The script skips file names that start with `homepage` or `loginpage`, as Phishpedia does.

3. Check the plan without changing anything, then install. Replace `<vm-user>` with your VM account:

   ```bash
   PP=/srv/scamshield/Phishpedia/.pixi/envs/default/bin/python
   sudo -u <vm-user> env HOME=/srv/scamshield/home $PP /srv/scamshield/app/brands/install_brands.py --dry-run
   sudo -u <vm-user> env HOME=/srv/scamshield/home $PP /srv/scamshield/app/brands/install_brands.py
   sudo systemctl restart mirsad-sandbox
   ```

   The script refuses a folder name that is not in `uae_brands.json` and lists the valid names. It also warns when Phishpedia already has a similar folder, such as an existing entry for an airline, so that one brand does not end up under two names.

4. Test with a real page of the brand. Capture the official site, then send the screenshot to `/phishpedia` with the official URL. The expected verdict is `brand_match`. The same screenshot with a made-up domain should give `brand_mismatch`.

To undo every change, copy `domain_map.pkl.orig` back over `domain_map.pkl`, delete the `mirsad_*` files from `expand_targetlist`, delete `LOGO_FEATS.npy` and `LOGO_FILES.npy`, and restart the service. Phishpedia rebuilds the cache on the next start, which takes several minutes.

## Brand name to official domains

`uae_brands.json` holds this list. The team generated it on 23 November 2026 from `mirsad/features/brands.py`, which remains the source of truth. When `brands.py` changes, regenerate the file instead of editing it by hand. From the repository root, on the host:

```powershell
.venv\Scripts\python.exe -c "import json; from mirsad.features.brands import BRANDS; json.dump({'source': 'mirsad/features/brands.py', 'brands': [{'name': b.name, 'sector': b.sector, 'domains': list(b.domains), 'verified': b.verified} for b in BRANDS]}, open('sandbox_vm/brands/uae_brands.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)"
```

In `brands.py`, "verified" means that a source read on 22 November 2026 showed the domain as the brand's own. The domains in every other row exist in DNS, but their ownership still needs checking before an operational deployment. Check the domain of each unverified brand when you visit its site for the logo, and update `brands.py` if it is wrong.

| Brand (folder name) | Sector | Official domains | Verified |
|---|---|---|---|
| Abu Dhabi Police | Police | adpolice.gov.ae | yes |
| UAE government portal | Federal government | u.ae | yes |
| Dubai Police | Police | dubaipolice.gov.ae, ecrime.ae | no |
| Ministry of Interior | Federal government | moi.gov.ae | no |
| ICP | Federal government | icp.gov.ae | no |
| UAE Pass | Digital identity | uaepass.ae | no |
| TAMM | Abu Dhabi government | tamm.abudhabi | no |
| Darb (ITC) | Abu Dhabi tolls | itc.gov.ae | no |
| Salik | Dubai tolls | salik.ae | no |
| RTA | Dubai transport and fines | rta.ae | no |
| ADDED consumer protection | Abu Dhabi economy | added.gov.ae | no |
| Ministry of Economy | Consumer protection | moec.gov.ae | no |
| Federal Tax Authority | Federal government | tax.gov.ae | no |
| MOHRE | Work permits | mohre.gov.ae | no |
| Central Bank of the UAE | Regulator | centralbank.ae | no |
| First Abu Dhabi Bank | Bank | bankfab.com | no |
| ADCB | Bank | adcb.com | no |
| ADIB | Bank | adib.ae | no |
| Emirates NBD | Bank | emiratesnbd.com | no |
| Dubai Islamic Bank | Bank | dib.ae | no |
| Mashreq | Bank | mashreq.com | no |
| RAKBANK | Bank | rakbank.ae | no |
| e& (Etisalat) | Telecom | etisalat.ae, eand.com | no |
| du | Telecom | du.ae | no |
| Emirates Post | Courier | emiratespost.ae | no |
| Aramex | Courier | aramex.com | no |
| ADDC | Utility | addc.ae | no |
| DEWA | Utility | dewa.gov.ae | no |
| SEWA | Utility | sewa.gov.ae | no |
| Etihad Airways | Airline | etihad.com | no |
| Emirates | Airline | emirates.com | no |

## How the domain check treats these brands

The service's `domain_matches_brand` is true only when the page's registered domain is in the brand's list, so `www.salik.ae` matches Salik and `salik.co.ae` does not. Upstream Phishpedia would also accept `salik.co.ae`, because the second-level label matches on a country-code domain. The service reports that relaxed verdict separately as `phishpedia_consistent`. If a brand legitimately uses another domain, for example a separate payment site, add it to `brands.py`, regenerate `uae_brands.json`, and run the install script again. The script only adds domains and never removes them.
