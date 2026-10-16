"use client";

import { useState } from "react";

export default function Login({ onLogin }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    setError("");
    setBusy(true);
    try {
      await onLogin(form.get("username"), form.get("password"));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form className="card login-card" onSubmit={submit}>
        <h2 className="login-title">Daily <span className="ai-red">AI</span> Briefing</h2>
        <p className="login-desc">Pick your topics and listen to today's news while you work.</p>
        <input name="username" type="text" placeholder="Username" autoComplete="username" required autoFocus />
        <input name="password" type="password" placeholder="Password" autoComplete="current-password" required />
        <button className="btn" type="submit" disabled={busy}>Enter</button>
        {error && <div className="error show">{error}</div>}
      </form>
    </div>
  );
}
