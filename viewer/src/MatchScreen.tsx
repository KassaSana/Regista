import { useEffect, useMemo, useRef, useState } from "react";
import { Bulb } from "./Bulb";
import { InsightPanel } from "./InsightPanel";
import { bulbOf, shownCards } from "./insights";
import {
  type Fact,
  formatClock,
  type Goal,
  periodLabel,
  type Timeline,
  timelineOf,
  visibleAt,
} from "./replay";
import type { RegistaReplayExport } from "./replayTypes";

const SPEEDS = [1, 10, 60] as const;
type Speed = (typeof SPEEDS)[number];

export function MatchScreen({ exported }: { exported: RegistaReplayExport }) {
  const timeline = useMemo(() => timelineOf(exported.periods), [exported]);
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<Speed>(10);
  usePlayback(playing, speed, timeline.total, position, setPosition, () => setPlaying(false));
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

  const open = (cardId: string | undefined) => {
    if (cardId === undefined) {
      return;
    }
    setOpenId(cardId);
    setReadIds((read) => new Set(read).add(cardId));
  };

  const togglePlay = () => {
    if (finished) {
      setPosition(0);
    }
    setPlaying(!playing);
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
            {periodLabel(visible.clock.period)} · {formatClock(visible.clock)}
          </span>
          <Bulb bulb={bulb} onOpen={() => open(bulb.opens?.id)} />
        </div>
      </div>

      {openIndex >= 0 && (
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

      <Scrubber timeline={timeline} position={position} onChange={setPosition} />

      <SoFar goals={visible.goals} facts={visible.facts} teamName={teamName} />
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

/** Advance the replay position in real time while playing, then stop at full time. */
function usePlayback(
  playing: boolean,
  speed: Speed,
  total: number,
  position: number,
  setPosition: (position: number) => void,
  onFinished: () => void,
) {
  const finishedRef = useRef(onFinished);
  finishedRef.current = onFinished;
  // The loop reads the latest position (including scrubbing) without restarting.
  const positionRef = useRef(position);
  positionRef.current = position;
  useEffect(() => {
    if (!playing) {
      return;
    }
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const elapsed = (now - last) / 1000;
      last = now;
      const next = Math.min(positionRef.current + elapsed * speed, total);
      positionRef.current = next;
      setPosition(next);
      if (next >= total) {
        finishedRef.current();
        return;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, total, setPosition]);
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
