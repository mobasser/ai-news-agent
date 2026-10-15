"use client";

export default function Player({ audioRef, playing, title, meta, note, onTimeUpdate, onEnded, onPlay, onPause, children }) {
  return (
    <div className={`player${playing ? " playing" : ""}`}>
      <div className="orb" />
      <div className="player-meta">
        <div className="t">{title}</div>
        <div className="s">{meta}</div>
        <audio ref={audioRef} controls onTimeUpdate={onTimeUpdate} onEnded={onEnded} onPlay={onPlay} onPause={onPause} />
        <div className="note">{note}</div>
        {children}
      </div>
    </div>
  );
}
