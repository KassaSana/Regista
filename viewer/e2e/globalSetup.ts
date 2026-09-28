import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { syntheticExport } from "../src/fixtures/syntheticExport";

/** Write the synthetic export and its index where the test's dev server serves them. */
export default async function globalSetup(): Promise<void> {
  const directory = resolve(import.meta.dirname, ".exports");
  await mkdir(directory, { recursive: true });
  const { match } = syntheticExport;
  await writeFile(resolve(directory, `${match.id}.json`), JSON.stringify(syntheticExport));
  await writeFile(
    resolve(directory, "index.json"),
    JSON.stringify([
      {
        id: match.id,
        date: match.date,
        competition: match.competition,
        home: match.home.name,
        away: match.away.name,
      },
    ]),
  );
}
