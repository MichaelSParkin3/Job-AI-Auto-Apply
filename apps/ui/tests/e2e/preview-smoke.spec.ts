import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..", "..", "..", "..");
const uiRoot = path.resolve(__dirname, "..", "..");

async function runCommand(command: string, args: string[], cwd: string) {
  return new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.on("error", (error) => reject(error));
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`${command} ${args.join(" ")} exited with code ${code}`));
      }
    });
  });
}

async function waitForServer(url: string, timeoutMs = 20_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url, { method: "GET" });
      if (response.ok) {
        return;
      }
    } catch (error) {
      // Retry until the server comes up or timeout is reached.
    }
    await delay(500);
  }
  throw new Error(`Timed out waiting for ${url}`);
}

let serverProcess: ReturnType<typeof spawn> | undefined;
let serverExit: Promise<void> | undefined;

test.beforeAll(async () => {
  await runCommand("npm", ["run", "build"], uiRoot);

  const pythonLauncher = process.platform === "win32" ? "py" : "python3";
  serverProcess = spawn(
    pythonLauncher,
    ["-m", "apps.cli.main", "preview", "demo", "--no-browser", "--port", "4951"],
    {
      cwd: repoRoot,
      stdio: "inherit",
      shell: process.platform === "win32",
    }
  );

  serverExit = new Promise<void>((resolve) => {
    serverProcess?.once("exit", (code) => {
      if (code && code !== 0) {
        console.error(`Preview server exited unexpectedly with code ${code}`);
      }
      resolve();
    });
  });

  await waitForServer("http://127.0.0.1:4951/ui");
});

test.afterAll(async () => {
  if (serverProcess && serverProcess.pid && serverProcess.exitCode === null) {
    serverProcess.kill(process.platform === "win32" ? "SIGINT" : "SIGTERM");
    await serverExit;
  }
  serverProcess = undefined;
  serverExit = undefined;
});

test("preview smoke shows key controls", async ({ page }) => {
  await page.goto("/ui");
  await expect(page.getByRole("heading", { name: "Review & Approve" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve/i })).toBeVisible();
  await expect(page.getByText(/Dry Run Mode is active/i)).toBeVisible();
});
