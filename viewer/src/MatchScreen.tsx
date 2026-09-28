import { useEffect, useMemo, useRef, useState } from "react";
import { Bulb } from "./Bulb";
import { History } from "./History";
import { InsightPanel } from "./InsightPanel";
import { bulbOf, shownCards } from "./insights";
import {
  breakBetween,
  breakLabel,
  type Fact,
  formatClock,
  type Goal,
  periodLabel,
  type Segment,
  type Timeline,
  timelineOf,
  visibleAt,
} from "./replay";
import type { RegistaReplayExport } from "./replayTypes";

const SPEEDS = [1, 10, 60] as const;
type Speed = (typeof SPEEDS)[number];
type View = "live" | "history";
// Ten updates a second keep the clock smooth at 60x without busy rendering.
const TICK_MILLISECONDS = 100;

export function MatchScreen({ exported }: { exported: RegistaReplayExport }) {
  const timeline = useMemo(() => timelineOf(exported.periods), [exported]);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(10);
  const [view, setView] = useState<View>("live");
  // The break playback stopped at; cleared as soon as the position moves on.
  const [breakAt, setBreakAt] = useState<Segment | null>(null);
  usePlayback(playing, speed, timeline, position, setPosition, (segment) => {
    setPlaying(false);
    setBreakAt(segment);
    setView("history");
  });
  const [showExperimental, setShowExperimental] = useExperimentalPreference();
  const [readIds, setReadIds] = useState<ReadonlySet<string>>(new Set());
  const [openId, setOpenId] = useState<string | null>(null);

  const visible = visibleAt(exported, timeline, position);
  const { home, away } = exported.match;
  const teamName = (teamId: number) => (teamId === home.id ? home.name : away.name);
  const finished = position >= timeline.total;
  const shown = shownCards(visible.cards, showExperimental);
  const bulb = bulbOf(shown, readIds);
  // A card hidden again (scrubbed back past it, or toggled off) closes the panel.
  const openIndex = shown.findIndex((card) => card.id === openId);
  const atBreak = breakAt !== null && position === breakAt.offset + breakAt.length ? breakAt : null;

  // Everything listed in the history counts as seen.
  const shownKey = shown.map((card) => card.id).join(",");
  useEffect(() => {
    if (view !== "history" || shownKey === "") {
      return;
    }
    setReadIds((read) => new Set([...read, ...shownKey.split(",")]));
  }, [view, shownKey]);

  const open = (cardId: string | undefined) => {
    if (cardId === undefined) {
      return;
    }
    setView("live");
    setOpenId(cardId);
    setReadIds((read) => new Set(read).add(cardId));
  };

  const togglePlay = () => {
    if (finished) {
      setPosition(0);
      setBreakAt(null);
    }
    if (!playing) {
      setView("live");
    }
    setPlaying(!playing);
  };

  const scrub = (next: number) => {
    setBreakAt(null);
    setPosition(next);
  };

  return (
    <section className="match">
      <div className="scoreboard">
        <span className="team home">{home.name}</span>
        <span className="score">
          {visible.score.home} – {visible.score.away}
        </span>
        <span className="team away">{away.name}</span>
        <div className="clock-row">
          <span className="clock">
            {atBreak !== null
              ? breakLabel(atBreak, timeline)
              : `${periodLabel(visible.clock.period)} · ${formatClock(visible.clock)}`}
          </span>
          <Bulb bulb={bulb} onOpen={() => open(bulb.opens?.id)} />
        </div>
      </div>

      {view === "live" && openIndex >= 0 && (
        <InsightPanel
          cards={shown}
          index={openIndex}
          teamName={teamName}
          homeName={home.name}
          awayName={away.name}
          onStep={(index) => open(shown[index]?.id)}
          onClose={() => setOpenId(null)}
        />
      )}

      <div className="controls">
        <button type="button" className="play" onClick={togglePlay}>
          {playing ? "Pause" : finished ? "Replay" : "Play"}
        </button>
        <fieldset className="speeds">
          <legend className="visually-hidden">Playback speed</legend>
          {SPEEDS.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={speed === option}
              onClick={() => setSpeed(option)}
            >
              {option}×
            </button>
          ))}
        </fieldset>
        <label className="toggle">
          <input
            type="checkbox"
            checked={showExperimental}
            onChange={(event) => setShowExperimental(event.target.checked)}
          />
          Show experimental insights
        </label>
      </div>

      <Scrubber timeline={timeline} position={position} onChange={scrub} />

      <div className="tabs" role="tablist" aria-label="Match views">
        <button
          type="button"
          role="tab"
          aria-selected={view === "live"}
          onClick={() => setView("live")}
        >
          Live
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "history"}
          onClick={() => setView("history")}
        >
          Insights so far ({shown.length})
        </button>
      </div>

      {view === "live" ? (
        <SoFar goals={visible.goals} facts={visible.facts} teamName={teamName} />
      ) : (
        <History
          cards={shown}
          hiddenExperimental={visible.cards.length - shown.length}
          breakTitle={atBreak === null ? null : breakLabel(atBreak, timeline)}
          score={visible.score}
          teamName={teamName}
          homeName={home.name}
          awayName={away.name}
          onContinue={
            atBreak === null || finished
              ? null
              : () => {
                  setView("live");
                  setPlaying(true);
                }
          }
        />
      )}
    </section>
  );
}

const EXPERIMENTAL_KEY = "regista.showExperimental";

/** A per-viewer convenience; storage can be missing or blocked, so it never fails. */
function useExperimentalPreference(): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => {
    try {
      return localStorage.getItem(EXPERIMENTAL_KEY) === "true";
    } catch {
      return false;
    }
  });
  const update = (next: boolean) => {
    setValue(next);
    try {
      localStorage.setItem(EXPERIMENTAL_KEY, String(next));
    } catch {
      // Keep the choice for this session only.
    }
  };
  return [value, update];
}

/**
 * Advance the replay position in real time while playing. Playback stops at
 * every period end (half time, full time) so the history can be read at breaks.
 *
 * A timer measured against wall-clock time drives it rather than animation
 * frames, which browsers stop in hidden tabs: a companion often sits in a
 * background tab beside the match, and must keep time there too.
 */
function usePlayback(
  playing: boolean,
  speed: Speed,
  timeline: Timeline,
  position: number,
  setPosition: (position: number) => void,
  onBreak: (segment: Segment) => void,
) {
  const breakRef = useRef(onBreak);
  breakRef.current = onBreak;
  // The loop reads the latest position (including scrubbing) without restarting.
  const positionRef = useRef(position);
  positionRef.current = position;
  useEffect(() => {
    if (!playing) {
      return;
    }
    let last = performance.now();
    const tick = () => {
      const now = performance.now();
      const elapsed = (now - last) / 1000;
      last = now;
      const from = positionRef.current;
      const next = Math.min(from + elapsed * speed, timeline.total);
      const crossed = breakBetween(from, next, timeline);
      const stop = crossed === undefined ? next : crossed.offset + crossed.length;
      positionRef.current = stop;
      setPosition(stop);
      if (crossed !== undefined) {
        window.clearInterval(timer);
        breakRef.current(crossed);
      }
    };
    const timer = window.setInterval(tick, TICK_MILLISECONDS);
    return () => window.clearInterval(timer);
  }, [playing, speed, timeline, setPosition]);
}

function Scrubber({
  timeline,
  position,
  onChange,
}: {
  timeline: Timeline;
  position: number;
  onChange: (position: number) => void;
}) {
  return (
    <div className="scrubber">
      <input
        type="range"
        min={0}
        max={timeline.total}
        step={1}
        value={Math.floor(position)}
        aria-label="Replay position"
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <div className="period-markers" aria-hidden="true">
        {timeline.segments.map((segment) => (
          <span
            key={segment.period}
            style={{
              left: `${(segment.offset / timeline.total) * 100}%`,
              width: `${(segment.length / timeline.total) * 100}%`,
            }}
          >
            {periodLabel(segment.period)}
          </span>
        ))}
      </div>
    </div>
  );
}

function SoFar({
  goals,
  facts,
  teamName,
}: {
  goals: Goal[];
  facts: Fact[];
  teamName: (teamId: number) => string;
}) {
  const changes = facts.filter((fact) => fact.kind !== "lineup");
  return (
    <div className="so-far">
      <div>
        <h2>Goals</h2>
        {goals.length === 0 ? (
          <p className="muted">None yet.</p>
        ) : (
          <ul>
            {goals.map((goal) => (
              <li key={goal.event_id}>
                <span className="when">{formatClock(goal.clock)}</span>
                {teamName(goal.team_id)}
                {goal.penalty && " (penalty)"}
                {goal.own_goal && " (own goal)"}
                <span className="muted">
                  {" "}
                  {goal.score.home}–{goal.score.away}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <h2>Changes</h2>
        {changes.length === 0 ? (
          <p className="muted">None yet.</p>
        ) : (
          <ul>
            {changes.map((fact) => (
              <li key={fact.event_id}>
                <span className="when">{formatClock(fact.clock)}</span>
                {fact.sentence}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
