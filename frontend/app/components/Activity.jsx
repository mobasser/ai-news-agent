"use client";

import { useEffect, useRef } from "react";

export default function Activity({ items, running }) {
  const listRef = useRef(null);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [items]);

  if (!items.length) return null;
  return (
    <div className="activity">
      <div className="activity-title">
        Live activity {running && <span className="dot" />}
      </div>
      <ul ref={listRef}>
        {items.map((it, i) => (
          <li key={i} className={it.tone}>{it.text}</li>
        ))}
      </ul>
    </div>
  );
}
