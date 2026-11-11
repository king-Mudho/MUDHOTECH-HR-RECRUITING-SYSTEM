import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/components/login-form";
import { RegisterForm } from "@/features/auth/components/register-form";
import { ForgotPasswordForm } from "@/features/auth/components/password-reset";
import messages from "../messages/en.json";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams("next=/hr/jobs"),
  usePathname: () => "/login",
}));

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NextIntlClientProvider locale="en" messages={messages}>
        {ui}
      </NextIntlClientProvider>
    </QueryClientProvider>,
  );
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const fetchMock = vi.fn();
beforeEach(() => {
  document.cookie = "csrftoken=test-token";
  fetchMock.mockReset();
  replace.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe("LoginForm", () => {
  it("shows field errors without calling the API", async () => {
    wrap(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Please fix the following:")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/Email address/)).toHaveAttribute("aria-invalid", "true");
  });

  it("ends an existing session and signs in again when already signed in (409)", async () => {
    fetchMock
      .mockResolvedValueOnce(json({ status: 409, errors: [{ code: "conflict" }] }, 409))
      .mockResolvedValueOnce(json({ status: 401, data: { flows: [] }, meta: {} }, 401))
      .mockResolvedValueOnce(json({ status: 200, meta: { is_authenticated: true } }))
      .mockResolvedValueOnce(
        json({ id: "u2", memberships: [{ role: "hr_manager" }], platform_role: "none" }),
      );
    wrap(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/Email address/), "hr@example.test");
    await userEvent.type(screen.getByLabelText(/^Password/), "a long passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(replace).toHaveBeenCalled());
    const methods = fetchMock.mock.calls.map(
      ([u, i]) => `${(i as RequestInit)?.method ?? "GET"} ${String(u)}`,
    );
    expect(methods.slice(0, 3)).toEqual([
      "POST /api/v1/auth/browser/v1/auth/login",
      "DELETE /api/v1/auth/browser/v1/auth/session",
      "POST /api/v1/auth/browser/v1/auth/login",
    ]);
    expect(screen.queryByText("Please fix the following:")).not.toBeInTheDocument();
  });

  it("walks through the MFA step and redirects to next", async () => {
    fetchMock
      .mockResolvedValueOnce(
        json(
          {
            status: 401,
            data: { flows: [{ id: "mfa_authenticate", is_pending: true }] },
            meta: {},
          },
          401,
        ),
      )
      .mockResolvedValueOnce(json({ status: 200, meta: { is_authenticated: true } }))
      .mockResolvedValueOnce(
        json({ id: "u1", memberships: [{ role: "recruiter" }], platform_role: "none" }),
      );
    wrap(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/Email address/), "hr@example.test");
    await userEvent.type(screen.getByLabelText(/^Password/), "a long passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByRole("heading", { name: "Two-factor authentication" }),
    ).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Verification code/), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/hr/jobs"));
    const mfaCall = fetchMock.mock.calls[1];
    expect(mfaCall[0]).toBe("/api/v1/auth/browser/v1/auth/2fa/authenticate");
    expect(JSON.parse(mfaCall[1].body)).toEqual({ code: "123456" });
  });

  it("shows the generic error for bad credentials", async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        {
          status: 400,
          errors: [
            {
              code: "email_password_mismatch",
              message: "The email address and/or password you specified are not correct.",
            },
          ],
        },
        400,
      ),
    );
    wrap(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/Email address/), "x@example.test");
    await userEvent.type(screen.getByLabelText(/^Password/), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText(/not correct/)).toBeInTheDocument();
  });

  it("explains pending email verification", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ status: 401, data: { flows: [{ id: "verify_email", is_pending: true }] } }, 401),
    );
    wrap(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/Email address/), "new@example.test");
    await userEvent.type(screen.getByLabelText(/^Password/), "a long passphrase");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(
      await screen.findByRole("heading", { name: "Confirm your email first" }),
    ).toBeInTheDocument();
  });
});

describe("RegisterForm", () => {
  it("shows the same 'check your inbox' outcome after signup (no enumeration)", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ status: 401, data: { flows: [{ id: "verify_email", is_pending: true }] } }, 401),
    );
    wrap(<RegisterForm />);
    await userEvent.type(screen.getByLabelText(/Email address/), "Someone@Example.test");
    await userEvent.type(screen.getByLabelText(/^Password/), "a long passphrase");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "a long passphrase");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: "Check your inbox" })).toBeInTheDocument();
    expect(screen.getByText(/someone@example.test/)).toBeInTheDocument();
  });

  it("maps a breached-password error to the password field", async () => {
    fetchMock.mockResolvedValueOnce(
      json(
        {
          status: 400,
          errors: [
            {
              code: "password_breached",
              message: "This password has appeared in a data breach.",
              param: "password",
            },
          ],
        },
        400,
      ),
    );
    wrap(<RegisterForm />);
    await userEvent.type(screen.getByLabelText(/Email address/), "a@example.test");
    await userEvent.type(screen.getByLabelText(/^Password/), "password123");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "password123");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findAllByText(/data breach/)).not.toHaveLength(0);
    expect(screen.getByLabelText(/^Password/)).toHaveAttribute("aria-invalid", "true");
  });
});

describe("ForgotPasswordForm", () => {
  it("always shows the generic confirmation", async () => {
    fetchMock.mockResolvedValueOnce(json({ status: 200 }));
    wrap(<ForgotPasswordForm />);
    await userEvent.type(screen.getByLabelText(/Email address/), "nobody@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText(/If an account exists/)).toBeInTheDocument();
  });
});
