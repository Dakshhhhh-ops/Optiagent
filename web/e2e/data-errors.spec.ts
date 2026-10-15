import { expect, test } from "@playwright/test";

const file = (name: string, text: string) => ({
  name,
  mimeType: "text/csv",
  buffer: Buffer.from(text),
});

test("a cost table that mixes currencies is rejected with a clear message", async ({ page }) => {
  await page.goto("/problems/new");
  await page.getByRole("radio", { name: /Transportation/ }).click();
  await page.locator('input[type="file"]').setInputFiles([
    file("routes.csv", "from,to,cost\nA,X,₹40\nA,Y,$3\nB,X,₹55\nB,Y,₹20"),
    file("plants.csv", "plant,supply\nA,10\nB,10"),
    file("stores.csv", "store,demand\nX,8\nY,7"),
  ]);
  await expect(page.getByText("Your tables")).toBeVisible();
  await page.getByRole("button", { name: /Map columns manually/ }).click();

  await expect(page.getByText(/values mix currencies/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Review model/ })).toBeDisabled();
});

test("a non-numeric cell is reported by row, not silently ignored", async ({ page }) => {
  await page.goto("/problems/new");
  await page.getByRole("radio", { name: /Transportation/ }).click();
  await page.locator('input[type="file"]').setInputFiles([
    file("routes.csv", "from,to,cost\nA,X,4\nA,Y,6\nB,X,5\nB,Y,3"),
    file("plants.csv", "plant,supply\nA,about ten\nB,10\nC,12"),
    file("stores.csv", "store,demand\nX,8\nY,7"),
  ]);
  await expect(page.getByText("Your tables")).toBeVisible();
  await page.getByRole("button", { name: /Map columns manually/ }).click();

  await expect(page.getByText(/'about ten' is not a number/)).toBeVisible();
});
