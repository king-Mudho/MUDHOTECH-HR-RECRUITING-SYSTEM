import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { isActive } from "@/components/layout/sidebar-nav";
import { NotificationBell, OrgSwitcher } from "@/components/layout/top-bar-actions";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { STATUS_TONES, StatusBadge } from "@/components/states/status-badge";
import { ApiError } from "@/lib/api-client";
import messages from "../messages/en.json";

function wrap(ui: ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={messages}>
      {ui}
    </NextIntlClientProvider>,
  );
}

describe("StatusBadge", () => {
  it("renders a text label (never colour only)", () => {
    wrap(<StatusBadge status="not_selected" />);
    const badge = screen.getByText("Not selected");
    expect(badge.closest("[data-status]")).toHaveAttribute("data-tone", "neutral");
  });

  it("never uses the word 'rejected'", () => {
    expect(JSON.stringify(messages).toLowerCase()).not.toContain("rejected");
    expect(Object.keys(STATUS_TONES)).not.toContain("rejected");
  });

  it("falls back gracefully for unknown statuses", () => {
    wrap(<StatusBadge status="some_new_state" />);
    expect(screen.getByText("some new state")).toBeInTheDocument();
  });
});

describe("state primitives", () => {
  it("EmptyState shows default title and action", () => {
    wrap(<EmptyState action={<button type="button">Create job</button>} />);
    expect(screen.getByRole("heading", { name: "Nothing here yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create job" })).toBeInTheDocument();
  });

  it("ErrorState surfaces the request id and retries", async () => {
    const onRetry = vi.fn();
    const err = new ApiError(500, "internal_error", "Server problem.", {}, "req_XYZ");
    wrap(<ErrorState error={err} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Server problem.");
    expect(screen.getByTestId("request-id")).toHaveTextContent("Reference: req_XYZ");
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("ErrorState without ApiError uses generic copy and no retry", () => {
    wrap(<ErrorState />);
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't load this.");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("ForbiddenState renders permission message", () => {
    wrap(<ForbiddenState />);
    expect(screen.getByRole("alert")).toHaveTextContent("You don't have access to this");
  });

  it("PageSkeleton announces loading", () => {
    wrap(<PageSkeleton rows={2} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });
});

describe("shell pieces", () => {
  it("isActive matches exact and nested paths only", () => {
    expect(isActive("/hr/jobs", "/hr/jobs")).toBe(true);
    expect(isActive("/hr/jobs/123", "/hr/jobs")).toBe(true);
    expect(isActive("/hr/jobsx", "/hr/jobs")).toBe(false);
  });

  it("top bar controls have accessible names", () => {
    wrap(
      <>
        <OrgSwitcher />
        <NotificationBell unread={150} />
      </>,
    );
    expect(screen.getByRole("button", { name: "Switch organisation" })).toBeInTheDocument();
    const bell = screen.getByRole("button", { name: "Notifications" });
    expect(bell).toHaveTextContent("99+");
  });
});
