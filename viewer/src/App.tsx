import { useEffect, useState } from "react";
import { Attribution } from "./Attribution";
import { type ExportIndexEntry, loadExport, loadIndex } from "./exports";
import { MatchScreen } from "./MatchScreen";
import type { RegistaReplayExport } from "./replayTypes";

export function App() {
  const [index, setIndex] = useState<ExportIndexEntry[] | null>(null);
  const [match, setMatch] = useState<RegistaReplayExport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadIndex().then(setIndex);
  }, []);

  const open = (matchId: number) => {
    setError(null);
    loadExport(matchId)
      .then(setMatch)
      .catch((reason: unknown) => setError(String(reason)));
  };

  return (
    <div className="app">
      <header className="app-header">
        <button type="button" className="brand" onClick={() => setMatch(null)}>
          Regista
        </button>
        <span className="tagline">match replay companion</span>
      </header>
      <main>
        {match === null ? (
          <MatchList index={index} onOpen={open} />
        ) : (
          <MatchScreen key={match.match.id} exported={match} />
        )}
        {error !== null && <p className="error">{error}</p>}
      </main>
      <Attribution />
    </div>
  );
}

function MatchList({
  index,
  onOpen,
}: {
  index: ExportIndexEntry[] | null;
  onOpen: (matchId: number) => void;
}) {
  if (index === null) {
    return <p className="muted">Loading matches…</p>;
  }
  if (index.length === 0) {
    return (
      <div className="empty">
        <p>No exported matches yet.</p>
        <p className="muted">
          Run <code>uv run regista export --match &lt;id&gt;</code> for a development match, then
          reload.
        </p>
      </div>
    );
  }
  return (
    <section>
      <h1>Pick a match</h1>
      <ul className="match-list">
        {index.map((entry) => (
          <li key={entry.id}>
            <button type="button" onClick={() => onOpen(entry.id)}>
              <span className="teams">
                {entry.home} v {entry.away}
              </span>
              <span className="muted">
                {entry.competition} · {entry.date}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
