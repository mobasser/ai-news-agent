"use client";

function toneOf(e) {
  if (e.action === "plan") return "plan";
  if (e.action === "decide") return "decide";
  if (e.action === "finish_research") return "finish";
  if (e.action === "search_news") {
    return e.observation.startsWith("No relevant") || e.observation.startsWith("All ") ? "miss" : "search";
  }
  return "other";
}

function labelOf(e) {
  if (e.action === "plan") return `${e.observation.split(" | ").length} queries`;
  if (e.action === "decide") return e.observation.replace("Coverage: ", "").split(". Offered")[0];
  if (e.action === "finish_research") return e.input?.reason ?? "";
  return e.input?.query ?? "";
}

export default function RunLog({ entries, stopReason }) {
  if (!entries.length) return null;
  return (
    <div className="runlog">
      <div className="runlog-title">Agent actions</div>
      <div className="labels">
        {entries.map((e, i) => (
          <span key={i} className={`label ${toneOf(e)}`} title={e.observation}>
            <b>{e.action === "finish_research" ? "finish" : e.action === "search_news" ? "search" : e.action}</b>
            <span>{labelOf(e)}</span>
          </span>
        ))}
      </div>
      {stopReason && <div className="stop-label">Stopped: {stopReason}</div>}
    </div>
  );
}
