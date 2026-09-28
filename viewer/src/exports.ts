/** Loading exports written by `uv run regista export` (served in development only). */

import type { RegistaReplayExport } from "./replayTypes";

/** One row of out/exports/index.json. */
export interface ExportIndexEntry {
  id: number;
  date: string;
  competition: string;
  home: string;
  away: string;
}

async function getJson(path: string): Promise<unknown> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path}: ${response.status}`);
  }
  return response.json();
}

/** The exported matches, or an empty list when nothing has been exported yet. */
export async function loadIndex(): Promise<ExportIndexEntry[]> {
  try {
    return (await getJson("/exports/index.json")) as ExportIndexEntry[];
  } catch {
    return [];
  }
}

export async function loadExport(matchId: number): Promise<RegistaReplayExport> {
  const exported = (await getJson(`/exports/${matchId}.json`)) as RegistaReplayExport;
  if (exported.schema_version !== 1) {
    throw new Error(`match ${matchId}: unsupported export version ${exported.schema_version}`);
  }
  return exported;
}
