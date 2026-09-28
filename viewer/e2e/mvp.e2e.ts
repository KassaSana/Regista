import { expect, type Page, test } from "@playwright/test";

/**
 * The whole MVP flow on the synthetic export (src/fixtures/syntheticExport.ts):
 * pick a match, watch the bulb stay quiet and then light at a card's clock,
 * open the insight and its evidence, reveal the experimental card, stop at half
 * time and full time, and read the history.
 *
 * Replay positions in seconds: the first half runs 0:00-47:00 (2,820 s), the
 * side-shift card fires at 24:14 (1,454), the experimental burst at 80:00 in
 * the second half (2,820 + 35 * 60 = 4,920), and full time is 5,700.
 */

async function scrubTo(page: Page, position: number): Promise<void> {
  await page.getByRole("slider", { name: "Replay position" }).evaluate((input, value) => {
    const range = input as HTMLInputElement;
    const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setValue?.call(range, String(value));
    range.dispatchEvent(new Event("input", { bubbles: true }));
  }, position);
}

test("a fan follows a match with Regista from kickoff to full time", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  page.on("pageerror", (error) => errors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Pick a match" })).toBeVisible();
  await expect(page.getByText("Data: StatsBomb")).toBeVisible();
  await page.getByRole("button", { name: /Home v Away/ }).click();

  const clock = page.locator(".clock");
  const score = page.locator(".score");
  const bulb = page.locator(".bulb");
  await expect(clock).toHaveText("1st half · 00:00");
  await expect(score).toHaveText("0 – 0");
  await expect(bulb).toBeDisabled();
  await expect(bulb).toHaveAccessibleName("No insight yet");

  // Quiet until the card's own clock, then one new insight.
  await scrubTo(page, 1453);
  await expect(bulb).toHaveAccessibleName("No insight yet");
  await scrubTo(page, 1454);
  await expect(clock).toHaveText("1st half · 24:14");
  await expect(score).toHaveText("1 – 0");
  await expect(bulb).toHaveAccessibleName("1 new insight");

  await bulb.click();
  const panel = page.getByRole("article", { name: "Insight" });
  await expect(panel.locator(".insight-kind")).toHaveText("Attacking side");
  await expect(panel.locator(".badge")).toHaveCount(0);
  await expect(panel.getByText("Synthetic side_shift card.")).toBeVisible();
  await expect(panel.locator(".insight-meta")).toContainText("Home 1–0 Away");
  await expect(panel.getByText("Data: StatsBomb")).toBeVisible();
  await panel.getByText("Why this insight?").click();
  await expect(panel.locator(".pitch line.mark")).toHaveCount(3);
  await expect(bulb).toHaveAccessibleName("Insights so far");

  // Play at 60x into half time: playback stops there and shows the history.
  await page.getByRole("button", { name: "60×" }).click();
  await scrubTo(page, 2810);
  await page.getByRole("button", { name: "Play" }).click();
  await expect(clock).toHaveText("Half time");
  const history = page.getByRole("region", { name: "Insight history" });
  await expect(history.locator(".break-summary")).toContainText("Home 2–0 Away");
  await expect(history.getByText("Regista noticed 1 thing so far.")).toBeVisible();
  await expect(history.locator(".history-item")).toHaveCount(1);

  // Continue into the second half.
  await history.getByRole("button", { name: "Continue" }).click();
  await expect(clock).toContainText("2nd half");
  await page.getByRole("button", { name: "Pause" }).click();

  // The burst is experimental: hidden until the viewer asks for it.
  await scrubTo(page, 4930);
  await expect(bulb).toHaveAccessibleName("Insights so far");
  await page.getByLabel("Show experimental insights").check();
  await expect(bulb).toHaveAccessibleName("1 new insight");
  await bulb.click();
  await expect(panel.locator(".insight-kind")).toHaveText("Attacking burst");
  await expect(panel.locator(".badge")).toHaveText("Experimental");
  await expect(panel.locator(".insight-meta")).toContainText("Home 2–1 Away");
  await panel.getByText("Why this insight?").click();
  await expect(panel.locator(".pitch circle.mark")).toHaveCount(2);

  // Play through full time: playback stops and the history lists both insights.
  await scrubTo(page, 5690);
  await page.getByRole("button", { name: "Play" }).click();
  await expect(clock).toHaveText("Full time");
  await expect(page.getByRole("button", { name: "Replay" })).toBeVisible();
  await expect(history.locator(".break-summary")).toContainText("Home 2–1 Away");
  await expect(history.getByRole("button", { name: "Continue" })).toHaveCount(0);
  await expect(history.locator(".history-item")).toHaveCount(2);
  await page.screenshot({ path: "test-results/full-time-history.png", fullPage: true });

  // Scrubbing back never shows a later insight.
  await scrubTo(page, 100);
  await expect(page.getByRole("tab", { name: "Insights so far (0)" })).toBeVisible();

  expect(errors).toEqual([]);
});

test("a match with nothing noteworthy stays quiet", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Home v Away/ }).click();
  await scrubTo(page, 1000);
  await page.getByRole("tab", { name: /Insights so far/ }).click();
  await expect(page.getByText("Nothing stood out so far.", { exact: false })).toBeVisible();
  await expect(page.locator(".bulb")).toBeDisabled();
});
