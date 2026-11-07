import { expect, test } from "@playwright/test";

test("streams an audit and renders only the validated report", async ({ page }) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/audit");
  const streamResponse = page.waitForResponse((response) =>
    response.url().includes("/api/v1/audit/evaluate/stream"),
  );
  await page.getByRole("button", { name: "Start clinical audit" }).click();

  const response = await streamResponse;
  expect(await response.text()).toContain("event: status");
  await expect(page.getByTestId("audit-report")).toBeVisible();
  await expect(page.getByText("MRI_PA_001", { exact: true })).toBeVisible();
  expect(pageErrors).toEqual([]);
});
