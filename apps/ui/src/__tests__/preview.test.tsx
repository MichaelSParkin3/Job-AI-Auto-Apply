import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "../App";
import { usePreviewStore } from "../store/preview-store";

const mockPreviewResponse = {
  runId: "demo123",
  status: "review",
  dryRun: true,
  preview: {
    screenshotUrl: "data:image/png;base64,preview",
    summary: "Queue demo summary",
    notes: "Manual overrides enabled.",
  },
  metadata: {
    profileId: "demo",
    profileLabel: "Demo profile",
    startedAt: "2025-01-01T00:00:00Z",
    limit: 3,
  },
};

const baseQueueSnapshot = {
  mode: "review" as const,
  pending: [
    {
      id: "cand-1",
      posting: { title: "Frontend Developer", company: "Acme" },
      state: "awaiting_decision" as const,
    },
    {
      id: "cand-2",
      posting: { title: "Backend Engineer", company: "Globex" },
      state: "awaiting_decision" as const,
    },
  ],
  escalated: [
    {
      id: "cand-3",
      posting: { title: "Data Analyst", company: "Initech" },
      state: "awaiting_decision" as const,
    },
  ],
  decided: [],
  lastUpdated: "2025-01-01T00:00:00Z",
};

type FetchMock = ReturnType<typeof vi.fn> & typeof fetch;

function mockResponse<T>(data: T, init?: { ok?: boolean; status?: number }) {
  const ok = init?.ok ?? true;
  const status = init?.status ?? (ok ? 200 : 400);
  return {
    ok,
    status,
    json: async () => data,
    text: async () => JSON.stringify(data),
  } as Response;
}

function mockError(message: string, status = 400) {
  const payload = { error: { message } };
  return {
    ok: false,
    status,
    json: async () => payload,
    text: async () => JSON.stringify(payload),
  } as Response;
}

async function closeQueueDrawer(user: ReturnType<typeof userEvent.setup>) {
  const hideButton = await screen.findByRole("button", {
    name: /Close queue drawer/i,
  });
  await user.click(hideButton);
  await waitFor(() =>
    expect(
      screen.queryByRole("dialog", { name: /Review Queue/i })
    ).not.toBeInTheDocument()
  );
}

describe("Preview App queue workflow", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    window.sessionStorage.clear();
    usePreviewStore.getState().reset();
  });

  it("renders queue drawer with counts and candidate details", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse(baseQueueSnapshot));

    // @ts-expect-error set global fetch for tests
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getAllByText(/Frontend Developer/i).length).toBeGreaterThan(0)
    );
    expect(
      screen.getByRole("heading", { name: /Review Queue/i })
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Pending count 2/i)).toHaveTextContent("2");
    expect(screen.getByLabelText(/Escalated count 1/i)).toHaveTextContent("1");
    const activeSection = screen.getByText(/Active Candidate/i).closest("section");
    expect(activeSection).not.toBeNull();
    if (activeSection) {
      expect(within(activeSection).getByText(/Frontend Developer/i)).toBeInTheDocument();
      expect(within(activeSection).getByText(/Acme/i)).toBeInTheDocument();
    }
  });

  it("navigates with J shortcut and approves once while busy", async () => {
    const user = userEvent.setup();
    const updatedQueue = {
      ...baseQueueSnapshot,
      pending: [baseQueueSnapshot.pending[0]],
      decided: [
        {
          decisionId: "d-1",
          candidateId: "cand-2",
          outcome: "approve",
          mode: "human",
          confidence: 0.9,
          timestamp: "2025-01-01T00:00:05Z",
        },
      ],
    };

    let resolveDecision: (() => void) | undefined;

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse(baseQueueSnapshot))
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveDecision = () => resolve(mockResponse({}));
          })
      )
      .mockResolvedValueOnce(mockResponse(updatedQueue));

    // @ts-expect-error set global fetch for tests
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getAllByText(/Frontend Developer/i).length).toBeGreaterThan(0)
    );

    await closeQueueDrawer(user);

    fireEvent.keyDown(window, { key: "j" });

    await waitFor(() => {
      const activeSection = screen.getByText(/Active Candidate/i).closest("section");
      expect(activeSection).not.toBeNull();
      if (activeSection) {
        expect(within(activeSection).getByText(/Backend Engineer/i)).toBeInTheDocument();
      }
    });

    const approveButton = await screen.findByRole("button", { name: /Approve/i });

    fireEvent.keyDown(window, { key: "A", shiftKey: true });
    fireEvent.keyDown(window, { key: "A", shiftKey: true });

    expect(approveButton).toBeDisabled();
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) => url === "/api/queue/demo123/decision").length
      ).toBe(1)
    );

    const decisionCall = fetchMock.mock.calls.find(
      ([url]) => url === "/api/queue/demo123/decision"
    );
    expect(decisionCall).toBeDefined();
    const decisionBody = JSON.parse((decisionCall?.[1] as RequestInit).body as string);
    expect(decisionBody.candidateId).toBe("cand-2");
    expect(decisionBody.outcome).toBe("approve");

    resolveDecision?.();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    await waitFor(() => expect(approveButton).not.toBeDisabled());
  });

  it("rolls back optimistic decision on error and surfaces message", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse(baseQueueSnapshot))
      .mockResolvedValueOnce(mockError("Queue conflict"));

    // @ts-expect-error set global fetch for tests
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getAllByText(/Frontend Developer/i).length).toBeGreaterThan(0)
    );

    await closeQueueDrawer(user);

    fireEvent.keyDown(window, { key: "A", shiftKey: true });

    const errorMessages = await screen.findAllByText(/Queue conflict/i);
    expect(errorMessages.length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Frontend Developer/i).length).toBeGreaterThan(0);
  });

  it("toggles shortcut legend with Shift+?", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse(baseQueueSnapshot));

    // @ts-expect-error set global fetch for tests
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getAllByText(/Frontend Developer/i).length).toBeGreaterThan(0)
    );

    expect(screen.queryByRole("dialog", { name: /Keyboard Shortcuts/i })).not.toBeInTheDocument();
    fireEvent.keyDown(window, { key: "?", shiftKey: true });
    await waitFor(() =>
      expect(
        screen.getByRole("dialog", { name: /Keyboard Shortcuts/i })
      ).toBeInTheDocument()
    );
  });

  it("submits escalate decision with Shift+X", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse(baseQueueSnapshot))
      .mockResolvedValueOnce(mockResponse({}))
      .mockResolvedValueOnce(mockResponse(baseQueueSnapshot));

    // @ts-expect-error set global fetch for tests
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    await waitFor(() =>
      expect(screen.getAllByText(/Frontend Developer/i).length).toBeGreaterThan(0)
    );

    await closeQueueDrawer(user);

    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /Escalate/i })
      ).toBeInTheDocument()
    );
    fireEvent.keyDown(window, { key: "X", shiftKey: true });

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.filter(([url]) => url === "/api/queue/demo123/decision").length
      ).toBe(1)
    );

    const decisionCall = fetchMock.mock.calls.find(
      ([url]) => url === "/api/queue/demo123/decision"
    );
    expect(decisionCall).toBeDefined();
    const decisionBody = JSON.parse((decisionCall?.[1] as RequestInit).body as string);
    expect(decisionBody.outcome).toBe("needs_review");
  });

  it("traps focus within queue drawer and closes with Escape", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockResponse(mockPreviewResponse))
      .mockResolvedValueOnce(mockResponse(baseQueueSnapshot));

    // @ts-expect-error set global fetch for tests
    global.fetch = fetchMock as FetchMock;

    render(<App />);

    const drawer = await screen.findByRole("dialog", { name: /Review Queue/i });
    expect(drawer).toBeInTheDocument();

    const closeButton = await screen.findByRole("button", {
      name: /Close queue drawer/i,
    });

    await waitFor(() => expect(closeButton).toHaveFocus());

    await user.tab();
    const firstCandidate = await screen.findByRole("button", {
      name: /Frontend Developer/i,
    });
    expect(firstCandidate).toHaveFocus();

    await user.tab({ shift: true });
    expect(closeButton).toHaveFocus();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(usePreviewStore.getState().drawerOpen).toBe(false));
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: /Review Queue/i })
      ).not.toBeInTheDocument()
    );
    expect(
      screen.getByRole("button", { name: /Show Queue/i })
    ).toBeInTheDocument();
  });
});
