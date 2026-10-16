"use client";

import { useEffect, useRef, useState } from "react";
import { post, loadSegments, streamBriefing } from "../lib/api";
import { narrate } from "../lib/narrate";
import { speakInBrowser, stopBrowserVoice } from "../lib/speech";
import Login from "./components/Login";
import InterestInput from "./components/InterestInput";
import Steps from "./components/Steps";
import Player from "./components/Player";
import Transcript from "./components/Transcript";
import RunLog from "./components/RunLog";
import Activity from "./components/Activity";

const AUDIO_TIMEOUT_MS = 45000;
const LANGUAGES = ["English", "Spanish", "French", "German", "Portuguese", "Italian", "Hindi", "Arabic", "Chinese", "Japanese"];

const cleanTopic = (text) => text.replace(/,/g, "").trim();

export default function Home() {
  const [auth, setAuth] = useState("checking");
  const [interests, setInterests] = useState([]);
  const [draft, setDraft] = useState("");
  const [language, setLanguage] = useState("English");
  const [stepState, setStepState] = useState("idle");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [briefing, setBriefing] = useState(null);
  const [activeLine, setActiveLine] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [activity, setActivity] = useState([]);

  const inputRef = useRef(null);
  const audioRef = useRef(null);
  const lineStarts = useRef([]);
  const rowRefs = useRef([]);
  const audioUrl = useRef(null);

  useEffect(() => {
    fetch("/api/auth/session").then((r) => setAuth(r.ok ? "in" : "out")).catch(() => setAuth("out"));
  }, []);

  useEffect(() => {
    if (activeLine < 0 || document.activeElement === inputRef.current) return;
    rowRefs.current[activeLine]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [activeLine]);

  function pendingTopics() {
    const extra = cleanTopic(draft);
    return extra && !interests.includes(extra) ? [...interests, extra] : interests;
  }

  function commitDraft() {
    const next = pendingTopics();
    setInterests(next);
    setDraft("");
    return next;
  }

  async function login(username, password) {
    await post("/api/auth/login", { username, password });
    setAuth("in");
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    location.reload();
  }

  function startBrowserVoice(data, lang) {
    return speakInBrowser(data.script, lang, { onLine: setActiveLine, onDone: () => setActiveLine(-1) });
  }

  async function recordAudio(data, lang) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), AUDIO_TIMEOUT_MS);
    try {
      const { segments } = await post("/api/briefing/audio", data, controller.signal);
      const { url, starts } = await loadSegments(segments);
      if (audioUrl.current) URL.revokeObjectURL(audioUrl.current);
      audioUrl.current = url;
      lineStarts.current = starts;
      audioRef.current.src = url;
      audioRef.current.play().catch(() => {});
    } catch (err) {
      const reason = err.name === "AbortError" ? "took too long" : err.message;
      setNote(`Server voice unavailable (${reason}). Playing with browser voice.`);
      await startBrowserVoice(data, lang);
    } finally {
      clearTimeout(timer);
    }
  }

  async function generate(e) {
    e.preventDefault();
    if (running) return;
    const topics = commitDraft();
    if (!topics.length) {
      inputRef.current?.focus();
      return;
    }
    stopBrowserVoice();
    setError("");
    setNote("");
    setBriefing(null);
    setActiveLine(-1);
    setPlaying(false);
    setActivity([]);
    lineStarts.current = [];
    audioRef.current?.removeAttribute("src");
    setStepState("script");
    setRunning(true);
    try {
      const data = await streamBriefing({ user_interests: topics, language }, (ev) => {
        const line = narrate(ev);
        if (line) setActivity((items) => [...items, line]);
      });
      setBriefing({ ...data, language, topics });
      setStepState("audio");
      await recordAudio(data, language);
      setStepState("done");
    } catch (err) {
      if (err.status === 401) setAuth("out");
      setStepState("idle");
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  function toggleBrowserVoice() {
    if (speechSynthesis.speaking) {
      stopBrowserVoice();
      setActiveLine(-1);
      return;
    }
    if (briefing) startBrowserVoice(briefing, briefing.language).catch((err) => setNote(err.message));
  }

  function handleTimeUpdate() {
    const t = audioRef.current.currentTime;
    setActiveLine(lineStarts.current.reduce((idx, s, i) => (t >= s ? i : idx), -1));
  }

  function handleEnded() {
    setPlaying(false);
    setActiveLine(-1);
  }

  if (auth === "checking") return null;

  return (
    <>
      {auth === "out" && <Login onLogin={login} />}
      <div className="wrap">
        <header>
          <span className="badge"><span className="dot" /> Live news &middot; AI powered</span>
          <h1>Daily <span className="ai-red">AI</span> Briefing</h1>
          <p className="sub">Pick your topics. Listen to today's news while you work.</p>
          {auth === "in" && (
            <button className="btn ghost" type="button" id="logout" onClick={logout}>Sign out</button>
          )}
        </header>

        <div className="card">
          <form onSubmit={generate}>
            <div className="input-row">
              <InterestInput
                interests={interests}
                setInterests={setInterests}
                draft={draft}
                setDraft={setDraft}
                inputRef={inputRef}
                onCommit={commitDraft}
              />
              <select className="lang" value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Briefing language">
                {LANGUAGES.map((l) => <option key={l}>{l}</option>)}
              </select>
              <button className="btn" type="submit" id="go" aria-disabled={running || pendingTopics().length === 0}>
                {running ? "Working..." : "Generate briefing"}
              </button>
            </div>
            <p className="hint">Press Enter or comma to add a topic. Each briefing uses search, language model and voice credits.</p>
          </form>

          <Steps state={stepState} />
          <Activity items={activity} running={running} />
          {error && <div className="error show">{error}</div>}

          <div className={`result${briefing ? " show" : ""}`}>
            <Player
              audioRef={audioRef}
              playing={playing}
              title={briefing?.title}
              meta={briefing ? `${briefing.script.length} lines \u00b7 ${briefing.topics.join(" \u00b7 ")}` : ""}
              note={note}
              onTimeUpdate={handleTimeUpdate}
              onEnded={handleEnded}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
            >
              <button className="btn ghost" type="button" id="browser-btn" disabled={!briefing} onClick={toggleBrowserVoice}>
                Browser voice
              </button>
            </Player>
            <h2>Transcript</h2>
            <Transcript script={briefing?.script ?? []} activeLine={activeLine} rowRefs={rowRefs} />
            <RunLog entries={briefing?.run_log ?? []} stopReason={briefing?.stop_reason} />
          </div>
        </div>
      </div>
    </>
  );
}
