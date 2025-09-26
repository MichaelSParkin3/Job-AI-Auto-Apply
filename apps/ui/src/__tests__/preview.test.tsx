import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import App from "../App";

const mockPreviewResponse = {
  runId: "demo123",
  status: "review",
  dryRun: true,
  preview: {
    screenshotUrl: "data:image/png;base64,preview",
    summary: "Placeholder summary for testing",
    notes: "Keyboard shortcuts active.",
  },
};

type FetchMock = ReturnType<typeof vi.fn> & typeof fetch;

function mockResponse<T>(data: T) {
  return {
    ok: true,
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as Response;
}

describe("Preview App", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders preview data, screenshot, and handles approve action", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse({ ok: true }));

    // @ts-expect-error setting global fetch for jsdom
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getByText(/Preview Submission/)).toBeInTheDocument()
    );
    expect(screen.getByText(/Dry Run Mode is active/i)).toBeInTheDocument();
    expect(
      screen.getByAltText(/Preview screenshot before submission/)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Approve/i }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/run/demo123/approve", {
        method: "POST",
      })
    );
  });

  it("fires approve with A shortcut", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse({ ok: true }));

    // @ts-expect-error setting global fetch for jsdom
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getByText(/Keyboard shortcuts/)).toBeInTheDocument()
    );

    fireEvent.keyDown(window, { key: "a" });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/run/demo123/approve", {
        method: "POST",
      })
    );
  });

  it("fires abort with Escape shortcut", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse({ ok: true }));

    // @ts-expect-error setting global fetch for jsdom
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getByText(/Keyboard shortcuts/)).toBeInTheDocument()
    );

    fireEvent.keyDown(window, { key: "Escape" });

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith("/api/run/demo123/abort", {
        method: "POST",
      })
    );
  });

  it("opens edit dialog with E shortcut", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      mockResponse(mockPreviewResponse)
    );

    // @ts-expect-error setting global fetch for jsdom
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getByText(/Preview Submission/)).toBeInTheDocument()
    );

    fireEvent.keyDown(window, { key: "e" });

    await waitFor(() =>
      expect(
        screen.getByRole("dialog", { name: /request edit/i })
      ).toBeInTheDocument()
    );
  });
});
