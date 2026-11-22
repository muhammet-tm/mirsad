"""Phishpedia worker for the Mirsad sandbox.

Runs with Phishpedia's own Python (the pixi environment in /srv/scamshield/Phishpedia/.pixi/envs/default),
started and supervised by sandbox_service.py. It loads the models once and then answers one JSON line per
request on stdin with one JSON line on stdout:

    in : {"id": 1, "url": "https://salik-topup-uae.top/recharge", "shot_path": "/tmp/pp-x.png"}
    out: {"id": 1, "ok": true, "brand": "Salik", "confidence": 0.93, "logo_box": [x1, y1, x2, y2],
          "domain_matches_brand": false, "phishpedia_consistent": false, "verdict": "brand_mismatch", ...}

The pipeline is Phishpedia's own (logo_recog.pred_rcnn, then logo_matching.pred_brand with the settings that
PhishpediaWrapper.test_orig_phishpedia uses), with two changes:
1. The brand is reported even when the domain matches it, so the caller can see "this is the real site".
2. domain_matches_brand is strict: the page's registered domain must be one of the brand's domains.
   Upstream also accepts any domain with the same second-level label on a country-code TLD
   (for example salik.com.ae for salik.ae); that relaxed verdict is returned as phishpedia_consistent.

Other modes:
    python phishpedia_worker.py --build-cache            rebuild LOGO_FEATS.npy after adding brands
    python phishpedia_worker.py --selftest SHOT.png URL  run one screenshot and print the result
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import time
import traceback


def _protocol_stream():
    """Keep the real stdout for protocol lines and send everything else (library prints) to stderr."""
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return proto


def main(argv):
    proto = _protocol_stream()

    def send(obj):
        proto.write(json.dumps(obj, ensure_ascii=False) + "\n")
        proto.flush()

    pp_dir = os.environ.get("PHISHPEDIA_DIR", "/srv/scamshield/Phishpedia")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    sys.path.insert(0, pp_dir)
    os.chdir(pp_dir)

    rebuild = "--build-cache" in argv
    try:
        import numpy as np
        import torch

        torch.set_num_threads(max(1, int(os.environ.get("PHISHPEDIA_THREADS", "2"))))
        import tldextract
        from configs import load_config
        from logo_matching import COUNTRY_TLDs, pred_brand
        from logo_recog import pred_rcnn
        from utils import brand_converter

        (ele_model, siamese_thre, siamese_model, logo_feats, logo_files,
         domain_map_path) = load_config(reload_targetlist=rebuild)
        # load_config returns Python lists when it has just built the cache, and pred_brand needs arrays.
        logo_feats = np.asarray(logo_feats)
        logo_files = np.asarray(logo_files)
        with open(domain_map_path, "rb") as handle:
            domain_map = pickle.load(handle)
    except Exception as exc:
        traceback.print_exc()
        send({"ready": False, "error": f"{type(exc).__name__}: {exc}"[:500]})
        return 1

    if rebuild:
        send({"ready": True, "rebuilt": True, "reference_logos": int(len(logo_feats)), "brands": len(domain_map)})
        return 0

    topk = max(1, int(os.environ.get("PHISHPEDIA_TOPK", "1")))  # upstream test_orig_phishpedia uses 1
    _extract = tldextract.TLDExtract(suffix_list_urls=())  # bundled list, no network at run time

    def registered(host_or_url):
        r = _extract(host_or_url)
        return f"{r.domain}.{r.suffix}" if r.domain and r.suffix else (r.domain or "")

    def strict_match(url, domains):
        page = registered(url)
        return bool(page) and page in {registered(d) for d in domains}

    def upstream_consistent(url, domains):
        """logo_matching.check_domain_brand_inconsistency, inverted: True means Phishpedia calls it benign."""
        ext = _extract(url)
        suffix_part = "." + ext.suffix
        domain_part = ext.domain
        if domain_part + suffix_part in domains:
            return True
        parts = [_extract(x).domain for x in domains]
        return domain_part in parts and ("." + suffix_part.split(".")[-1]) in COUNTRY_TLDs

    def infer(url, shot_path):
        t0 = time.monotonic()
        boxes = pred_rcnn(im=shot_path, predictor=ele_model)
        if boxes is not None:
            boxes = boxes.detach().cpu().numpy()
        n = 0 if boxes is None else int(len(boxes))
        out = {"brand": None, "confidence": 0.0, "logo_box": None, "domain_matches_brand": False,
               "phishpedia_consistent": None, "brand_domains": [], "logos_detected": n,
               "threshold": float(siamese_thre), "verdict": "no_logo" if n == 0 else "no_brand"}
        found = consistent_hit = None
        best_sim = 0.0
        for i in range(min(n, topk)):
            bbox = [float(v) for v in boxes[i]]
            if out["logo_box"] is None:
                out["logo_box"] = [round(v, 1) for v in bbox]
            target, domains, conf = pred_brand(siamese_model, domain_map, logo_feats, logo_files,
                                               shot_path, bbox, similarity_threshold=siamese_thre,
                                               grayscale=False, do_resolution_alignment=False,
                                               do_aspect_ratio_check=False)
            conf = float(conf) if conf is not None else 0.0
            best_sim = max(best_sim, conf)
            if target and domains:
                domains = [str(d) for d in domains]
                hit = {"brand": brand_converter(target), "confidence": conf,
                       "logo_box": [round(v, 1) for v in bbox],
                       "domain_matches_brand": strict_match(url, domains),
                       "phishpedia_consistent": upstream_consistent(url, domains),
                       "brand_domains": domains[:20]}
                if not hit["phishpedia_consistent"]:
                    found = hit  # upstream stops at the first inconsistent brand
                    break
                if consistent_hit is None:
                    consistent_hit = hit
        hit = found or consistent_hit
        if hit:
            out.update(hit)
            out["verdict"] = "brand_match" if hit["domain_matches_brand"] else "brand_mismatch"
        else:
            out["confidence"] = best_sim
        out["confidence"] = round(float(out["confidence"]), 4)
        out["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        return out

    if "--selftest" in argv:
        i = argv.index("--selftest")
        shot, url = argv[i + 1], argv[i + 2]  # a relative SHOT is read from the Phishpedia folder
        send(dict(ok=True, **infer(url, os.path.abspath(shot))))
        return 0

    send({"ready": True, "reference_logos": int(len(logo_feats)), "brands": len(domain_map),
          "threshold": float(siamese_thre), "device": "cuda" if torch.cuda.is_available() else "cpu"})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            result = infer(str(req["url"]), str(req["shot_path"]))
            send(dict(id=rid, ok=True, **result))
        except Exception as exc:
            traceback.print_exc()
            send({"id": rid, "ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
