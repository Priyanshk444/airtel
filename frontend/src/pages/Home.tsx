import { useNavigate } from "react-router-dom";

const STARTERS = [
  { label: "English", text: "Hi, I want internet and a few mobile lines for my shop." },
  { label: "हिंदी", text: "नमस्ते, मुझे अपनी दुकान के लिए इंटरनेट चाहिए।" },
  { label: "Hinglish", text: "Namaste, mujhe apni dukaan ke liye internet aur WhatsApp chahiye." },
];

export default function Home() {
  const navigate = useNavigate();
  const start = (text?: string) => {
    sessionStorage.removeItem("udyam_session");
    if (text) sessionStorage.setItem("udyam_first_message", text);
    navigate("/advisor");
  };
  return (
    <div className="page home">
      <section className="hero">
        <h1>Everything your business needs. One bill. One chat.</h1>
        <p>
          Internet, mobile lines, WhatsApp, billing, CCTV and more, bundled for your shop, clinic or unit,
          in about three minutes, in your language.
        </p>
        <button className="btn primary big" onClick={() => start()}>
          Start with the advisor
        </button>
        <div className="chips">
          {STARTERS.map((s) => (
            <button key={s.label} className="chip" onClick={() => start(s.text)}>
              {s.label}
            </button>
          ))}
        </div>
      </section>
      <section className="steps">
        <div className="step"><span>1</span><div><strong>Tell us about your business</strong><p>A few short questions, no sales visit.</p></div></div>
        <div className="step"><span>2</span><div><strong>See one clear monthly price</strong><p>Toggle add-ons, nothing hidden.</p></div></div>
        <div className="step"><span>3</span><div><strong>Verify in minutes</strong><p>GST or Udyam, with your consent, documents checked instantly.</p></div></div>
        <div className="step"><span>4</span><div><strong>Track activation</strong><p>Know the date, no follow-up calls.</p></div></div>
      </section>
      <p className="fineprint">Prototype for a fictional operator, Accel Business. All data is synthetic.</p>
    </div>
  );
}
