"use client";

export default function InterestInput({ interests, setInterests, draft, setDraft, inputRef, onCommit }) {
  function onKeyDown(e) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      onCommit();
    }
    if (e.key === "Backspace" && !draft && interests.length) setInterests(interests.slice(0, -1));
  }

  return (
    <div className="chips" onClick={() => inputRef.current?.focus()}>
      {interests.map((topic, i) => (
        <span className="chip" key={topic}>
          {topic}
          <button type="button" onClick={() => setInterests(interests.filter((_, j) => j !== i))}>{"\u00d7"}</button>
        </span>
      ))}
      <input
        ref={inputRef}
        id="interest-input"
        type="text"
        placeholder="Add a topic and press Enter (e.g. AI, climate)"
        autoComplete="off"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={onCommit}
      />
    </div>
  );
}
