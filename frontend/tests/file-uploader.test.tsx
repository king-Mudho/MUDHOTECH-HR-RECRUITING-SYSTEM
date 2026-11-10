import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FileUploader } from "@/features/documents/components/file-uploader";
import messages from "../messages/en.json";

type Doc = { id: string; original_filename: string; scan_status: string; rejected_reason: string };
const doc = (over: Partial<Doc> = {}): Doc => ({
  id: "d1",
  original_filename: "cv.pdf",
  scan_status: "clean",
  rejected_reason: "",
  ...over,
});

/** XMLHttpRequest stand-in: reports progress then succeeds, or fails with a network error. */
let xhrMode: "ok" | "network" = "ok";
class FakeXhr {
  upload: {
    onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null;
  } = {
    onprogress: null,
  };
  status = 0;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  open() {}
  setRequestHeader() {}
  abort() {
    this.onabort?.();
  }
  send() {
    queueMicrotask(() => {
      if (xhrMode === "network") return this.onerror?.();
      this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 });
      this.status = 200;
      this.onload?.();
    });
  }
}

const fetchMock = vi.fn();
function respond(routes: Record<string, unknown | (() => unknown)>) {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const hit = Object.entries(routes).find(([k]) => key.startsWith(k));
    if (!hit)
      return new Response(
        JSON.stringify({ error: { code: "nf", message: "nf", details: {}, request_id: null } }),
        { status: 404 },
      );
    const body = typeof hit[1] === "function" ? (hit[1] as () => unknown)() : hit[1];
    return new Response(JSON.stringify(body), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    });
  });
}

const SESSION = {
  id: "s1",
  url: "https://storage.example/put",
  method: "PUT",
  headers: { "Content-Type": "application/pdf" },
  expires_at: "",
  filename: "cv.pdf",
};

function renderUploader(onUploaded = vi.fn()) {
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <FileUploader purpose="cv" label="Your CV" onUploaded={onUploaded} />
    </NextIntlClientProvider>,
  );
  return onUploaded;
}

const pdf = (size = 10) => new File([new Uint8Array(size)], "cv.pdf", { type: "application/pdf" });

beforeEach(() => {
  xhrMode = "ok";
  document.cookie = "csrftoken=t";
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("FileUploader", () => {
  it("uploads via presigned PUT, confirms and reports a clean document", async () => {
    respond({
      "POST /api/v1/documents/upload-sessions/s1/complete/": doc(),
      "POST /api/v1/documents/upload-sessions/": SESSION,
    });
    const onUploaded = renderUploader();
    await userEvent.upload(screen.getByLabelText("Your CV"), pdf());
    await waitFor(() =>
      expect(onUploaded).toHaveBeenCalledWith(expect.objectContaining({ id: "d1" })),
    );
    expect(screen.getByRole("status")).toHaveTextContent("cv.pdf is ready.");
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("direct-upload"))).toBe(false);
  });

  it("falls back to the direct upload when storage is unreachable", async () => {
    xhrMode = "network";
    respond({
      "POST /api/v1/documents/upload-sessions/": SESSION,
      "POST /api/v1/documents/direct-upload/": doc({ id: "d2" }),
    });
    const onUploaded = renderUploader();
    await userEvent.upload(screen.getByLabelText("Your CV"), pdf());
    await waitFor(() =>
      expect(onUploaded).toHaveBeenCalledWith(expect.objectContaining({ id: "d2" })),
    );
  });

  it("polls the security scan until it finishes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let checks = 0;
    respond({
      "POST /api/v1/documents/upload-sessions/s1/complete/": doc({ scan_status: "pending" }),
      "POST /api/v1/documents/upload-sessions/": SESSION,
      "GET /api/v1/documents/d1/": () => doc({ scan_status: ++checks >= 2 ? "clean" : "pending" }),
    });
    const onUploaded = renderUploader();
    await userEvent.upload(screen.getByLabelText("Your CV"), pdf());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Checking cv.pdf"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4500);
    });
    await waitFor(() =>
      expect(onUploaded).toHaveBeenCalledWith(expect.objectContaining({ scan_status: "clean" })),
    );
  });

  it("explains a rejected file and does not offer a pointless retry", async () => {
    respond({
      "POST /api/v1/documents/upload-sessions/s1/complete/": doc({
        scan_status: "rejected",
        rejected_reason: "type_mismatch",
      }),
      "POST /api/v1/documents/upload-sessions/": SESSION,
    });
    const onUploaded = renderUploader();
    await userEvent.upload(screen.getByLabelText("Your CV"), pdf());
    expect(await screen.findByRole("alert")).toHaveTextContent("doesn't match its type");
    expect(onUploaded).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("refuses files over the size limit before uploading", async () => {
    renderUploader();
    await userEvent.upload(screen.getByLabelText("Your CV"), pdf(11 * 1024 * 1024));
    expect(await screen.findByRole("alert")).toHaveTextContent("larger than 10 MB");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("offers retry after a network failure", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    renderUploader();
    await userEvent.upload(screen.getByLabelText("Your CV"), pdf());
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
