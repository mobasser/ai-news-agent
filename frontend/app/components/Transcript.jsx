"use client";

export default function Transcript({ script, activeLine, rowRefs }) {
  return (
    <div>
      {script.map((line, i) => {
        const isAnna = line.speaker === "Anna";
        return (
          <div
            key={i}
            ref={(el) => { rowRefs.current[i] = el; }}
            className={`line ${isAnna ? "a" : "b"}${i === activeLine ? " now" : ""}`}
            style={{ animationDelay: `${Math.min(i * 40, 600)}ms` }}
          >
            <div className="avatar">{isAnna ? "A" : "S"}</div>
            <div>
              <div className="who">{line.speaker}</div>
              <div className="text">{line.text}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
