import { describe, expect, it } from "vitest";

import { addDays, groupByDay, weekStart, type Interview } from "@/features/interviews/api";
import {
  acceptSchema,
  canRespond,
  openSlots,
  type CandidateInterview,
} from "@/features/candidates/components/hiring";
import { offerActions } from "@/features/offers/api";

function iv(id: string, starts_at: string | null): Interview {
  return {
    id,
    application_id: "a",
    reference: "R",
    job_id: "j",
    job_title: "Developer",
    stage: "Technical",
    mode: "video",
    location: "",
    video_link: "",
    duration_minutes: 45,
    starts_at,
    ends_at: null,
    timezone: "Africa/Harare",
    status: starts_at ? "scheduled" : "proposed",
    status_reason: "",
    instructions: "",
    scorecard_template_id: null,
    sequence: 0,
    slots: [],
    panel: [],
  } as Interview;
}

describe("interview calendar helpers", () => {
  it("weeks start on Monday", () => {
    const thursday = new Date(2026, 10, 19, 15, 30); // Thu 19 Nov 2026
    const start = weekStart(thursday);
    expect(start.getDay()).toBe(1);
    expect(start.getDate()).toBe(16);
    expect(weekStart(new Date(2026, 10, 22)).getDate()).toBe(16); // Sunday belongs to that week
    expect(addDays(start, 7).getDate()).toBe(23);
  });

  it("groups by local day, unscheduled last", () => {
    const groups = groupByDay([
      iv("b", new Date(2026, 10, 20, 9).toISOString()),
      iv("c", null),
      iv("a", new Date(2026, 10, 19, 14).toISOString()),
      iv("d", new Date(2026, 10, 20, 8).toISOString()),
    ]);
    expect(groups.map((g) => g.day)).toEqual(["2026-11-19", "2026-11-20", null]);
    expect(groups[1]!.items.map((i) => i.id)).toEqual(["d", "b"]);
  });
});

describe("offer actions by role and state", () => {
  it("only approvers approve, give back, withdraw and record hires", () => {
    const pending = { status: "pending_approval", hire_recorded: false };
    expect(offerActions(pending, "recruiter").approve).toBe(false);
    expect(offerActions(pending, "hr_manager").approve).toBe(true);
    expect(offerActions({ status: "accepted", hire_recorded: false }, "hr_manager").hire).toBe(
      true,
    );
    expect(offerActions({ status: "accepted", hire_recorded: true }, "hr_manager").hire).toBe(
      false,
    );
    expect(offerActions({ status: "accepted", hire_recorded: false }, "recruiter").hire).toBe(
      false,
    );
  });

  it("issuing needs an approved offer (EC-OFF-01 in the UI too)", () => {
    for (const status of ["draft", "pending_approval", "issued"]) {
      expect(offerActions({ status, hire_recorded: false }, "recruiter").issue).toBe(false);
    }
    expect(offerActions({ status: "approved", hire_recorded: false }, "recruiter").issue).toBe(
      true,
    );
    expect(offerActions({ status: "approved", hire_recorded: false }, "hiring_manager").issue).toBe(
      false,
    );
  });
});

describe("candidate interview and offer helpers", () => {
  const now = new Date("2026-11-19T10:00:00Z");

  it("only free future slots of a proposed interview can be picked, earliest first", () => {
    const base = iv("x", null) as unknown as CandidateInterview;
    const interview = {
      ...base,
      slots: [
        {
          id: "late",
          starts_at: "2026-11-21T09:00:00Z",
          ends_at: "2026-11-21T10:00:00Z",
          booked: false,
        },
        {
          id: "past",
          starts_at: "2026-11-18T09:00:00Z",
          ends_at: "2026-11-18T10:00:00Z",
          booked: false,
        },
        {
          id: "taken",
          starts_at: "2026-11-20T09:00:00Z",
          ends_at: "2026-11-20T10:00:00Z",
          booked: true,
        },
        {
          id: "soon",
          starts_at: "2026-11-20T08:00:00Z",
          ends_at: "2026-11-20T09:00:00Z",
          booked: false,
        },
      ],
    };
    expect(openSlots(interview, now).map((s) => s.id)).toEqual(["soon", "late"]);
    expect(openSlots({ ...interview, status: "scheduled" }, now)).toEqual([]);
  });

  it("an offer can be answered only while issued and not expired", () => {
    expect(canRespond({ status: "issued", expires_at: "2026-11-20T00:00:00Z" }, now)).toBe(true);
    expect(canRespond({ status: "issued", expires_at: "2026-11-19T09:59:00Z" }, now)).toBe(false);
    expect(canRespond({ status: "accepted", expires_at: "2026-11-20T00:00:00Z" }, now)).toBe(false);
  });

  it("acceptance needs a typed name and the ticked statement", () => {
    const empty = acceptSchema.safeParse({ typed_name: " ", agree: false, counter_offer_note: "" });
    expect(empty.success).toBe(false);
    const paths = empty.error!.issues.map((i) => i.path[0]);
    expect(paths).toEqual(expect.arrayContaining(["typed_name", "agree"]));
    expect(
      acceptSchema.safeParse({ typed_name: "Tariro Moyo", agree: true, counter_offer_note: "" })
        .success,
    ).toBe(true);
  });
});
