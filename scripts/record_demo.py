"""Record a captioned walkthrough of the running app (http://localhost:8000) and save slide screenshots.

    python scripts/record_demo.py            # needs: pip install playwright imageio-ffmpeg; playwright install chromium
Output: deliverables/demo_video.mp4, deliverables/screenshots/*.png
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables"
SHOTS = OUT / "screenshots"
RAW = OUT / "_raw_video"
URL = "http://localhost:8000"
W, H = 1440, 900

CAPTION_JS = """
(t) => {
  let el = document.getElementById('__cap');
  if (!el) {
    el = document.createElement('div'); el.id='__cap';
    el.style.cssText = 'position:fixed;left:50%;bottom:22px;transform:translateX(-50%);max-width:1150px;z-index:99999;' +
      'background:rgba(15,23,42,.92);color:#fff;font:600 21px/1.4 Segoe UI,Arial,sans-serif;padding:14px 26px;' +
      'border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.35);text-align:center;transition:opacity .25s';
    document.body.appendChild(el);
  }
  if (!t) { el.style.opacity = 0; return; }
  el.style.opacity = 1; el.innerHTML = t;
}"""


def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    if RAW.exists():
        shutil.rmtree(RAW)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(RAW),
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()

        def cap(text, secs=0.0):
            page.evaluate(CAPTION_JS, text)
            if secs:
                page.wait_for_timeout(int(secs * 1000))

        def shot(name):
            page.evaluate(CAPTION_JS, "")
            page.wait_for_timeout(300)
            page.screenshot(path=str(SHOTS / f"{name}.png"))

        def scroll_main(y):
            page.evaluate(f"document.querySelector('main').scrollTo({{top:{y},behavior:'smooth'}})")
            page.wait_for_timeout(700)

        def wait_done(timeout=120):
            t0 = time.time()
            while time.time() - t0 < timeout:
                if page.locator(".prio").count():
                    return
                page.wait_for_timeout(500)
            raise RuntimeError("case did not finish")

        def click_finding(substr):
            page.locator(".fcard", has_text=substr).first.click()
            page.wait_for_timeout(900)

        # --- intro
        page.goto(URL)
        page.wait_for_timeout(800)
        cap("<b>DocForensics</b> - AI-powered document forensics &amp; contextual intelligence.<br>"
            "OCR tells you what a document says. We check whether to believe it.", 5)
        shot("01_home")
        cap("Scenario: a loan application with 4 supporting documents - application form (PDF), ID card (scan), "
            "salary slip (scan) and bank statement (PDF).", 4.5)

        # --- upload
        files = sorted(str(f) for f in (ROOT / "samples" / "case_02_visual_tamper").iterdir())
        page.fill("#caseName", "Loan application PL-2026-931076")
        page.set_input_files("#files", files)
        cap("Step 1 - Document submission: all four files are uploaded together as one investigation.", 3.5)
        page.click("#startBtn")
        page.wait_for_timeout(1200)
        cap("Every original is hashed (SHA-256) on arrival and never modified. Ten pipeline stages run live: "
            "classification, OCR, structure, visual forensics, contextual and cross-document checks...", 6)
        shot("02_progress")
        cap("Digital PDFs are read from their text layer (with font names); scans go through OCR with per-line confidence.", 1)
        wait_done()
        page.wait_for_timeout(800)
        cap("Investigation complete: review priority HIGH - 4 potential manipulations, 6 inconsistencies, "
            "4 observations. Nothing is ever labelled 'fraud'.", 6)
        shot("03_results")

        # --- corroborated anomaly
        click_finding("Corroborated anomaly: net pay")
        cap("<b>Corroborated anomaly</b>: independent methods agree on the salary slip's Net Pay - visual forensics "
            "AND arithmetic AND the bank statement all say it does not fit.", 6)
        scroll_main(560)
        cap("Every finding links to evidence: document, field, value and the exact pixel box on the original page.", 5)
        shot("04_corroborated")
        page.locator("tr.ev").nth(1).click()
        page.wait_for_timeout(1200)
        cap("Click any evidence row - the viewer jumps to that document and highlights the region.", 5)
        shot("05_traceability")

        # --- overwritten pdf value
        scroll_main(0)
        click_finding("Overwritten value")
        cap("PDF forensics: the declared income '95,000' was typed over a white box - the original '58,000' is still "
            "in the PDF text layer underneath. A deterministic, reproducible fact.", 7)
        scroll_main(520)
        page.wait_for_timeout(1500)
        shot("06_overwritten")

        # --- signature copy
        scroll_main(0)
        click_finding("Signature appears")
        cap("Signature analysis: the applicant's signature on the form is a near-identical copy of the ID card's "
            "signature (correlation 0.97). Real signatures always vary.", 6)

        # --- noise patch & review
        click_finding("Noise-free patch")
        cap("Scan forensics: scanner noise is everywhere except a smooth patch behind Net Pay - typical of a value "
            "pasted digitally after scanning.", 6)
        scroll_main(400)
        page.wait_for_timeout(800)
        page.fill("#rvNote", "Request original payslip from employer")
        page.click("button[data-d='confirmed']")
        page.wait_for_timeout(900)
        cap("Human in the loop: the reviewer confirms or dismisses each finding. Decisions are audit-logged and "
            "appear in the dossier.", 5)
        shot("07_review")

        # --- documents tab
        scroll_main(0)
        page.click(".tabs button[data-t='documents']")
        page.wait_for_timeout(800)
        page.click(".doctabs button:has-text('salary_slip')")
        page.wait_for_timeout(1000)
        cap("Documents &amp; extraction: classification with confidence, structured fields with OCR confidence and "
            "source location, and overlays on the page.", 6)
        shot("08_documents")
        page.locator("tr[data-f='net_pay']").click()
        page.wait_for_timeout(1500)
        cap("Clicking a field highlights where it came from on the original document.", 3)
        page.check("input[data-l='ela']")
        page.wait_for_timeout(1500)
        cap("Error Level Analysis heat-map: inserted content recompresses differently from the rest of the scan.", 5)
        shot("09_ela")
        page.uncheck("input[data-l='ela']")

        # --- contextual case
        scroll_main(0)
        cap("Second case: four documents that look perfectly clean - but the information inside them disagrees.", 3.5)
        page.locator("#samples button", has_text="case 03 contextual").click()
        page.wait_for_timeout(1500)
        cap("Contextual intelligence: arithmetic, ID check digits, age vs date of birth, running balances, and "
            "every document compared against every other.", 1)
        wait_done()
        page.wait_for_timeout(700)
        cap("10 inconsistencies found, 0 visual alarms: checksum failure, DOB conflict, wrong age, payslip arithmetic, "
            "broken running balance, salary credit mismatch, missing signature...", 7)
        shot("10_contextual")
        click_finding("Running balance")
        cap("The system reasons like an analyst: one wrong printed balance breaks two equations - it pinpoints the "
            "single figure that does not fit.", 6)
        scroll_main(0)
        page.click(".tabs button[data-t='cross']")
        page.wait_for_timeout(1000)
        scroll_main(260)
        cap("Cross-document entity graph: each document links to the values it asserts. Red = conflicting values for "
            "the same person (name, DOB, ID number, address).", 7)
        shot("11_graph")
        scroll_main(820)
        cap("Comparison matrix: fuzzy matching tolerates harmless variations (e.g. 'Pvt Ltd') but flags real conflicts.", 5)

        # --- safe failure
        scroll_main(0)
        page.locator("#samples button", has_text="misc failure handling").click()
        page.wait_for_timeout(1000)
        wait_done()
        page.click(".tabs button[data-t='documents']")
        page.wait_for_timeout(1000)
        cap("Safe failure: a corrupted PDF is rejected with a clear reason and an unrelated note is marked "
            "'unsupported' - the investigation still completes.", 6)
        shot("12_failure")
        page.click(".tabs button[data-t='caps']")
        page.wait_for_timeout(900)
        cap("Capabilities and limitations are reported honestly: implemented, partial, unsupported.", 4.5)

        # --- audit
        page.click(".tabs button[data-t='audit']")
        page.wait_for_timeout(1000)
        cap("Tamper-evident audit trail: every action is hash-chained (SHA-256), so any later edit to the log is "
            "detectable.", 5)
        shot("13_audit")

        # --- dossier
        cid = page.evaluate("S.caseId")
        cases = page.evaluate("fetch('/api/cases').then(r=>r.json())")
        tamper = next(c["id"] for c in cases if c["name"].startswith("Loan application"))
        page.goto(f"{URL}/api/cases/{tamper}/dossier")
        page.wait_for_timeout(1200)
        cap("The investigation dossier: overview, extracted information, contextual analysis, visual findings, "
            "evidence &amp; traceability, summary, limitations and audit trail.", 6)
        shot("14_dossier")
        for y in (1400, 3200, 5200, 7600):
            page.evaluate(f"window.scrollTo({{top:{y},behavior:'smooth'}})")
            page.wait_for_timeout(1700)
        cap("Annotated pages show every finding at its recorded coordinates. Export as HTML, PDF (print) or JSON.", 5)
        page.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        page.wait_for_timeout(800)
        cap("<b>DocForensics</b> - evidence-backed, explainable, human-in-the-loop document investigation.<br>"
            "Detected 17/17 planted anomalies with 0 false positives on the demonstration dataset.", 6)
        _ = cid
        video = page.video.path()
        ctx.close()
        browser.close()

    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    mp4 = OUT / "demo_video.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(video), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-crf", "23", "-preset", "medium", "-movflags", "+faststart", str(mp4)], check=True)
    shutil.rmtree(RAW, ignore_errors=True)
    print("video:", mp4, round(mp4.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    sys.exit(main())
