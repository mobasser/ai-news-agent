const ITEMS = [
  { key: "script", label: "Researching and writing" },
  { key: "audio", label: "Recording voices" },
];

export default function Steps({ state }) {
  if (state === "idle") return null;
  const current = ITEMS.findIndex((s) => s.key === state);
  return (
    <div className="steps show">
      {ITEMS.map((s, i) => {
        let cls = "step";
        if (state === "done" || i < current) cls += " done";
        else if (i === current) cls += " active";
        return (
          <div className={cls} key={s.key}>
            <span className="ico">{i + 1}</span>
            {s.label}
          </div>
        );
      })}
    </div>
  );
}
