"""
Record the 3-minute demo video by driving the running app in Chrome (Playwright).

Prerequisites: `docker compose up --build` is running (app on http://localhost:3000, key in .env for live chat).
Usage (from the project root):  .venv\\Scripts\\python demo\\record_demo.py
Output: demo/udyam_digital_demo.mp4 (narrated).

Captions are drawn on the page and read aloud.
It follows docs/demo_script.md: advisor -> quote -> checkout -> Smart KYC -> tracker -> partner view.
Every caption is also read aloud (Windows built-in speech, offline) and mixed into the mp4.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BASE = "http://localhost:3000"
OUT = Path(__file__).resolve().parent
VIEW = {"width": 430, "height": 860}          # phone-sized, the journey is mobile-first

CAPTION_JS = """
(text) => {
  let el = document.getElementById('demo-caption');
  if (!el) {
    el = document.createElement('div');
    el.id = 'demo-caption';
    Object.assign(el.style, {position: 'fixed', left: '10px', right: '10px', bottom: '12px', zIndex: 99999,
      background: 'rgba(15,23,42,0.92)', color: '#fff', font: '600 15px/1.35 system-ui, sans-serif',
      padding: '10px 12px', borderRadius: '10px', boxShadow: '0 4px 16px rgba(0,0,0,.35)', pointerEvents: 'none'});
    document.body.appendChild(el);
  }
  el.textContent = text;
  el.style.display = text ? 'block' : 'none';
}
"""


TTS_DIR = OUT / "_tts"
VOICE = "Microsoft Zira Desktop"
T0 = 0.0                                     # wall-clock time the video started
SPOKEN: list[tuple[float, Path]] = []        # (seconds into the video, wav) for each caption shown
# how captions should be pronounced (the on-screen text stays unchanged)
SAY = [(r"(\d(?:\.\d)?)x\b", r"\1 times"), (r"(\d)\+", r"\1 or more"), (r"\bDPDP\b", "D P D P"),
       (r"\bAUC\b", "A U C"), (r"\bKYC\b", "K Y C"), (r"\bGSTIN\b", "G S T I N"), (r"\bAI\b", "A I"),
       (r"\bK(\d\d)\b", r"K \1"), (r"\bFAIL\b", "fail"), (r"\bUPI\b", "U P I")]


def spoken(text: str) -> str:
    for pattern, repl in SAY:
        text = re.sub(pattern, repl, text)
    return text


def wav_for(text: str) -> Path:
    return TTS_DIR / (hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] + ".wav")


def synthesise_captions() -> dict[str, float]:
    """Read every caption literal in this file, synthesise it once, return its spoken length in seconds."""
    src = Path(__file__).read_text(encoding="utf-8")
    texts = sorted(set(re.findall(r'caption\(page, "([^"]+)"', src) + re.findall(r'kyc_case\(page, "K\d+", "([^"]+)"', src)
                       + re.findall(r'while_reading="([^"]+)"', src)))
    texts = [t for t in texts if "[^" not in t]
    TTS_DIR.mkdir(exist_ok=True)
    todo = [t for t in texts if not wav_for(t).exists()]
    if todo:
        lines = ["Add-Type -AssemblyName System.Speech",
                 "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer", f"$s.SelectVoice('{VOICE}')", "$s.Rate = 3"]
        for t in todo:
            safe = spoken(t).replace("'", "''")
            lines += [f"$s.SetOutputToWaveFile('{wav_for(t)}')", f"$s.Speak('{safe}')"]
        lines.append("$s.SetOutputToNull()")
        script = TTS_DIR / "speak.ps1"
        script.write_text("\n".join(lines), encoding="utf-8-sig")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], check=True)
    lengths = {}
    for t in texts:
        with wave.open(str(wav_for(t))) as w:
            lengths[t] = w.getnframes() / w.getframerate()
    return lengths


DURATION: dict[str, float] = {}
FAST: list[tuple[float, float]] = []         # silent waits (model replying, documents being read) to fast-forward
SPEEDUP = 4.0
_narration_end = 0.0


def now() -> float:
    return time.time() - T0


def fast_wait(wait) -> None:
    """Run a blocking wait; the part of it after the narration has finished is fast-forwarded in the edit."""
    start = max(now(), _narration_end) + 0.3
    wait()
    end = now() - 0.3
    if end - start > 1.5:
        FAST.append((start, end))


def caption(page: Page, text: str, hold: float = 2.5, block: bool = True) -> None:
    global _narration_end
    page.evaluate(CAPTION_JS, text)
    if text in DURATION:                     # stay on screen until the narration has finished
        SPOKEN.append((now(), wav_for(text)))
        _narration_end = now() + DURATION[text]
        hold = max(hold, DURATION[text] + 0.4)
    if block:                                # block=False narrates over a wait (e.g. documents being read)
        time.sleep(hold)


def scroll(page: Page, pixels: int, steps: int = 6, pause: float = 0.25) -> None:
    for _ in range(steps):
        page.mouse.wheel(0, pixels / steps)
        time.sleep(pause)


def title_card(page: Page) -> None:
    page.set_content("""
      <body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
                   background:#0d4c80;color:#fff;font-family:system-ui,sans-serif;text-align:center">
        <div style="padding:24px">
          <div style="font-size:30px;font-weight:800">Accel Business<br>Udyam Digital</div>
          <p style="font-size:17px;line-height:1.5;opacity:.9">Only 7 in 100 small-business leads activate today,
          after 18 days and 3 chasing calls. 59% of drops are our own process.</p>
          <p style="font-size:17px;line-height:1.5"><b>One sitting, on a phone, in Hindi or English.</b></p>
          <p style="font-size:12px;opacity:.7">Prototype for a fictional operator. All data is synthetic.</p>
        </div></body>""")
    time.sleep(4)


def advisor(page: Page) -> None:
    page.goto(BASE)
    page.evaluate("sessionStorage.clear()")
    page.goto(BASE)
    caption(page, "One chat, one price, instant KYC and a tracker. No sales visit.", 3)
    page.get_by_role("button", name="Start with the advisor").click()
    expect(page.get_by_placeholder("Type in English, हिंदी or Hinglish…")).to_be_enabled(timeout=20000)
    caption(page, "The AI only talks, in English, Hindi or Hinglish. A rule engine picks products and prices.", 3)
    box = page.get_by_placeholder("Type in English, हिंदी or Hinglish…")
    box.click()
    box.type("Chennai mein electronics ki dukaan hai, 4 log kaam karte hain, ek hi shop, GST hai. "
             "Mujhe 1 Gbps fibre aur WhatsApp Business chahiye.", delay=25)
    page.get_by_role("button", name="Send").click()
    caption(page, "The customer asks in Hinglish for 1 Gbps and WhatsApp.", 1)
    fast_wait(lambda: expect(page.get_by_role("button", name="Continue to quote")).to_be_visible(timeout=90000))
    time.sleep(1)
    # show the start of the reply, where the exclusion is explained
    page.locator(".bubble.assistant").last.evaluate("el => el.scrollIntoView({block: 'start', behavior: 'smooth'})")
    time.sleep(1)
    reply = page.locator(".bubble.assistant").last.inner_text()
    if "1G" in reply or "1 Gbps" in reply:
        caption(page, "1 Gbps needs 5+ staff, so it is excluded with the reason, and 300 Mbps is offered.", 6)
    else:
        caption(page, "The reply comes in Hinglish, with reasons and one monthly price.", 5)
    scroll(page, 500)
    caption(page, "Every line has a reason. One monthly total.", 4)
    scroll(page, 900)
    time.sleep(1.5)


def quote_and_checkout(page: Page) -> None:
    page.get_by_role("button", name="Continue to quote").click()
    expect(page.get_by_role("button", name="Proceed to checkout")).to_be_visible(timeout=20000)
    caption(page, "Optional items and add-ons switch on or off.", 3)
    wifi = page.locator("li", has_text="Secure Wi-Fi").locator("label.switch").first
    if wifi.count():
        wifi.scroll_into_view_if_needed()
        caption(page, "Add customer Wi-Fi: the server reprices instantly.", 1.5)
        wifi.click()
        time.sleep(2.5)
    page.get_by_role("button", name="Proceed to checkout").scroll_into_view_if_needed()
    time.sleep(1)
    page.get_by_role("button", name="Proceed to checkout").click()
    expect(page.get_by_text("Order summary")).to_be_visible(timeout=20000)
    caption(page, "Mock payment. Typing FAIL shows a declined payment.", 2)
    page.get_by_label("Business name").fill("Star Electronics")
    page.get_by_label("Contact name").fill("Arun Kumar")
    page.get_by_label("Mobile number").type("9840012345", delay=40)
    page.get_by_label("UPI ID").type("arun@okbank", delay=40)
    time.sleep(1)
    page.get_by_role("button", name="place order").click()
    expect(page.get_by_text("Order placed")).to_be_visible(timeout=20000)
    caption(page, "Order placed, with an expected activation date.", 3.5)


def kyc_case(page: Page, applicant: str, note: str, while_reading: str = "") -> None:
    expect(page.get_by_text("Before we look at any document")).to_be_visible(timeout=20000)
    page.locator("label.card.consent.required input[type=checkbox]").check()
    time.sleep(0.8)
    page.get_by_role("button", name="I agree, continue to documents").click()
    expect(page.get_by_text("Upload your documents")).to_be_visible(timeout=20000)
    page.locator(".sample-row select").select_option(applicant)
    caption(page, note, 2.5)
    while True:
        btn = page.get_by_role("button", name=f"Use sample {applicant}")
        if btn.count() == 0:
            break
        btn.first.scroll_into_view_if_needed()
        btn.first.click()
        if while_reading:
            caption(page, while_reading, block=False)
            while_reading = ""
        fast_wait(lambda: expect(page.get_by_role("button", name="Reading…")).to_have_count(0, timeout=60000))
        time.sleep(0.6)
    result = page.get_by_role("button", name="See verification result")
    result.scroll_into_view_if_needed()
    result.click()
    time.sleep(1.5)


def kyc(page: Page) -> None:
    page.get_by_role("button", name="Verify my business (KYC)").click()
    caption(page, "Consent comes first, under DPDP. Only verification is required.", 0)
    expect(page.get_by_text("Before we look at any document")).to_be_visible(timeout=20000)
    scroll(page, 600, pause=0.35)
    time.sleep(1.2)
    scroll(page, -600, steps=2)
    # 1) a planted problem: stale electricity bill
    kyc_case(page, "K11", "Applicant K11.",
             while_reading="Claude vision reads each photo. We keep the fields, never the image.")
    caption(page, "K11 fails: the electricity bill is 257 days old. Every check is explained.", 5)
    scroll(page, 700, pause=0.35)
    caption(page, "15 checks in all. Identifiers are masked.", 4)
    # 2) a clean applicant for this order
    page.goto(f"{BASE}/kyc")
    kyc_case(page, "K12", "Now applicant K12, a clean set.",
             while_reading="Registry, checksum, names, signatory, address and dates are all checked.")
    caption(page, "K12 is verified, and the order updates by itself.", 4)


def tracker(page: Page) -> None:
    page.get_by_role("button", name="Track my installation").click()
    expect(page.get_by_role("button", name="Demo: simulate next step")).to_be_visible(timeout=20000)
    caption(page, "Every step has an expected date, so no chasing calls.", 3.5)
    for _ in range(2):
        page.get_by_role("button", name="Demo: simulate next step").click()
        time.sleep(2)
    time.sleep(1.2)


def partner(page: Page) -> None:
    page.goto(f"{BASE}/partner")
    expect(page.get_by_role("button", name="Handoffs")).to_be_visible(timeout=20000)
    caption(page, "Partners get the leads the advisor could not close, by territory, with a summary.", 3)
    page.locator("select").first.select_option("Maharashtra")
    time.sleep(1.5)
    head = page.locator(".lead-head").first
    if head.count():
        head.click()
        time.sleep(1)
        scroll(page, 400)
        time.sleep(1.2)
    page.get_by_role("button", name="Who to call").click()
    time.sleep(1.5)
    caption(page, "Who to call: the top 10% of this list converts at 2.2x the average.", 4)
    scroll(page, 600, pause=0.35)
    page.get_by_role("button", name="Assisted").click()
    time.sleep(1)
    caption(page, "Assisted mode: partners fill the journey on the owner's phone.", 4)


def end_card(page: Page) -> None:
    page.set_content("""
      <body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
                   background:#0d4c80;color:#fff;font-family:system-ui,sans-serif;text-align:center">
        <div style="padding:24px;font-size:17px;line-height:1.6">
          <div style="font-size:26px;font-weight:800;margin-bottom:12px">Tested, not just demoed</div>
          25/25 live advisor scenarios<br>12/12 KYC applicants match the answer key<br>
          368 historical bundles replayed through the rule engine<br>160 automated tests
          <p style="font-size:13px;opacity:.75;margin-top:18px">docker compose up · http://localhost:3000</p>
        </div></body>""")
    time.sleep(4)


def edited_time(t: float) -> float:
    """Where moment t of the raw recording lands after the silent waits are fast-forwarded."""
    saved = sum((min(t, b) - a) * (1 - 1 / SPEEDUP) for a, b in FAST if t > a)
    return t - saved


def mux_audio(video: Path, mp4: Path) -> None:
    import imageio_ffmpeg
    args = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video)]
    # video: normal segments at 1x, recorded waits at SPEEDUP x, joined back together
    cuts, last = [], 0.0
    for a, b in sorted(FAST):
        cuts += [(last, a, 1.0), (a, b, SPEEDUP)]
        last = b
    cuts.append((last, None, 1.0))
    chains = []
    for i, (a, b, k) in enumerate(cuts):
        end = f":end={b:.3f}" if b is not None else ""
        chains.append(f"[0:v]trim=start={a:.3f}{end},setpts=(PTS-STARTPTS)/{k}[v{i}]")
    chains.append("".join(f"[v{i}]" for i in range(len(cuts))) + f"concat=n={len(cuts)}:v=1:a=0[vout]")
    labels = []
    for n, (at, wav) in enumerate(SPOKEN, start=1):
        args += ["-i", str(wav)]
        ms = max(0, int(edited_time(at) * 1000))
        chains.append(f"[{n}:a]adelay={ms}|{ms}[a{n}]")
        labels.append(f"[a{n}]")
    graph = ";".join(chains) + ";" + "".join(labels) + f"amix=inputs={len(labels)}:normalize=0[aout]"
    args += ["-filter_complex", graph, "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(mp4)]
    subprocess.run(args, check=True)


def main() -> int:
    global T0
    DURATION.update(synthesise_captions())
    print(f"narration ready: {len(DURATION)} captions, {sum(DURATION.values()):.0f} s of speech")
    raw = OUT / "_raw"
    shutil.rmtree(raw, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport=VIEW, device_scale_factor=2,
                                  record_video_dir=str(raw), record_video_size=VIEW)
        page = ctx.new_page()
        T0 = time.time()
        page.set_default_timeout(30000)
        try:
            title_card(page)
            advisor(page)
            quote_and_checkout(page)
            kyc(page)
            tracker(page)
            partner(page)
            end_card(page)
        except Exception:
            page.screenshot(path=str(OUT / "failure.png"))
            raise
        finally:
            video = page.video
            ctx.close()
            browser.close()
        src = Path(video.path())
    webm = OUT / "udyam_digital_demo.webm"
    shutil.move(str(src), webm)
    shutil.rmtree(raw, ignore_errors=True)
    print("wrote", webm)
    mp4 = OUT / "udyam_digital_demo.mp4"
    mux_audio(webm, mp4)
    webm.unlink()
    print("wrote", mp4, f"with {len(SPOKEN)} narrated captions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
