/**
 * A pitch drawn in the acting team's attacking frame (120 x 80, attacking left
 * to right). Low y is the team's left (pinned on the Python side by
 * test_low_y_is_the_acting_teams_left); with SVG y pointing down, the team's
 * left is at the top. Only a card's own evidence is drawn.
 */

import { useId } from "react";
import type { Card } from "./replayTypes";

const LENGTH = 120;
const WIDTH = 80;
const FINAL_THIRD_X = 80;
const CHANNEL_LINES = [WIDTH / 3, (2 * WIDTH) / 3];

export function Pitch({ card }: { card: Card }) {
  const marker = useId();
  const sideShift = card.kind === "side_shift";
  return (
    <svg
      className="pitch"
      viewBox={`-2 -6 ${LENGTH + 4} ${WIDTH + 12}`}
      role="img"
      aria-label={`${card.evidence.length} evidence events on a pitch, attacking to the right`}
    >
      <defs>
        <marker
          id={marker}
          viewBox="0 0 6 6"
          refX="5"
          refY="3"
          markerWidth="4"
          markerHeight="4"
          orient="auto-start-reverse"
        >
          <path d="M0,0 L6,3 L0,6 z" className="arrow-head" />
        </marker>
      </defs>
      <g className="markings">
        <rect x={0} y={0} width={LENGTH} height={WIDTH} />
        <line x1={LENGTH / 2} y1={0} x2={LENGTH / 2} y2={WIDTH} />
        <circle cx={LENGTH / 2} cy={WIDTH / 2} r={10} />
        <rect x={0} y={18} width={18} height={44} />
        <rect x={LENGTH - 18} y={18} width={18} height={44} />
        <rect x={0} y={30} width={6} height={20} />
        <rect x={LENGTH - 6} y={30} width={6} height={20} />
        <circle className="spot" cx={12} cy={WIDTH / 2} r={0.5} />
        <circle className="spot" cx={LENGTH - 12} cy={WIDTH / 2} r={0.5} />
      </g>
      <g className="guides">
        <line x1={FINAL_THIRD_X} y1={0} x2={FINAL_THIRD_X} y2={WIDTH} />
        {sideShift &&
          CHANNEL_LINES.map((y) => <line key={y} x1={FINAL_THIRD_X} y1={y} x2={LENGTH} y2={y} />)}
      </g>
      {sideShift && (
        <g className="channel-labels">
          <text x={LENGTH - 2} y={WIDTH / 6 + 1}>
            left
          </text>
          <text x={LENGTH - 2} y={WIDTH / 2 + 1}>
            center
          </text>
          <text x={LENGTH - 2} y={(5 * WIDTH) / 6 + 1}>
            right
          </text>
        </g>
      )}
      <g className="evidence">
        {card.evidence.map((item) => {
          if (item.start === null) {
            return null;
          }
          if (item.end === null) {
            return (
              <circle
                key={item.event_id}
                className={`mark ${item.role}`}
                cx={item.start.x}
                cy={item.start.y}
                r={1.3}
              />
            );
          }
          return (
            <line
              key={item.event_id}
              className={`mark ${item.role}`}
              x1={item.start.x}
              y1={item.start.y}
              x2={item.end.x}
              y2={item.end.y}
              markerEnd={`url(#${marker})`}
            />
          );
        })}
      </g>
      <text className="direction" x={LENGTH / 2} y={-1.5}>
        attacking →
      </text>
    </svg>
  );
}
