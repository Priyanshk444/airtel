import { NavLink, Route, Routes } from "react-router-dom";
import Home from "./pages/Home";
import Advisor from "./pages/Advisor";
import Placeholder from "./pages/Placeholder";
import Quote from "./pages/Quote";
import Checkout from "./pages/Checkout";
import Kyc from "./pages/Kyc";
import Track from "./pages/Track";
import Partner from "./pages/Partner";

export default function App() {
  return (
    <div className="app">
      <header className="topbar">
        <NavLink to="/" className="brand">
          <span className="brand-mark">A</span>
          <span>
            <strong>Accel Business</strong>
            <small>Udyam Digital</small>
          </span>
        </NavLink>
        <nav className="topnav">
          <NavLink to="/advisor">Advisor</NavLink>
          <NavLink to="/track">Track</NavLink>
          <NavLink to="/partner">Partner</NavLink>
        </nav>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/advisor" element={<Advisor />} />
          <Route path="/quote" element={<Quote />} />
          <Route path="/checkout" element={<Checkout />} />
          <Route path="/kyc" element={<Kyc />} />
          <Route path="/track" element={<Track />} />
          <Route path="/partner" element={<Partner />} />
        </Routes>
      </main>
    </div>
  );
}
