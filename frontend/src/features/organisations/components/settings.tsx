"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { useForm } from "react-hook-form";

import { ConfirmDialog } from "@/components/forms/confirm-dialog";
import { ErrorSummary, SelectField, TextField } from "@/components/forms/form-field";
import { EmptyState, ErrorState, ForbiddenState } from "@/components/states/states";
import { PageSkeleton } from "@/components/states/page-skeleton";
import { StatusBadge } from "@/components/states/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { applyServerErrors } from "@/features/auth/form-errors";
import { ApiError } from "@/lib/api-client";

import { orgApi, type Membership, type Role } from "../api";
import {
  ROLES,
  can,
  orgKeys,
  useActiveMembership,
  useDepartments,
  useInvitations,
  useLocations,
  useMembers,
  useOrganisation,
  usePolicy,
} from "../hooks";
import { inviteSchema, policySchema, type InviteValues, type PolicyValues } from "../schemas";
import { OrganisationForm } from "./organisation-form";

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <h2 className="text-lg font-semibold">{title}</h2>
        </CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-4">{children}</CardContent>
    </Card>
  );
}

function useOrgContext() {
  const { membership, isPending } = useActiveMembership();
  return { orgId: membership?.organisation_id, role: membership?.role ?? null, isPending };
}

function errorMessage(err: unknown): string | null {
  if (!err) return null;
  return err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
}

// ------------------------------------------------------------------------ profile
export function OrganisationProfileSettings() {
  const t = useTranslations("organisations.settings");
  const { orgId, role, isPending } = useOrgContext();
  const org = useOrganisation(orgId);
  const client = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const logo = useMutation({
    mutationFn: (file: File) => orgApi.uploadLogo(orgId!, file),
    onSuccess: (data) => client.setQueryData(orgKeys.org(orgId!), data),
  });

  if (isPending || org.isPending) return <PageSkeleton rows={4} />;
  if (org.isError) return <ErrorState error={org.error} onRetry={() => org.refetch()} />;
  const editable = can(role, "org.update");
  const o = org.data;
  return (
    <div className="flex flex-col gap-6">
      {o.status !== "active" ? (
        <Alert>
          <AlertDescription>
            {o.status === "pending_verification" ? t("pendingVerification") : t("suspended")}
          </AlertDescription>
        </Alert>
      ) : null}
      <Section title={t("logoTitle")} description={t("logoHelp")}>
        <div className="flex items-center gap-4">
          {o.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- short-lived presigned URL
            <img
              src={o.logo_url}
              alt={t("logoAlt", { name: o.name })}
              width={64}
              height={64}
              className="rounded border"
            />
          ) : (
            <div
              aria-hidden="true"
              className="bg-muted grid size-16 place-items-center rounded border text-xl font-bold"
            >
              {o.name.slice(0, 1)}
            </div>
          )}
          {editable ? (
            <div className="flex flex-col gap-1">
              <Label htmlFor="logo-file">{t("chooseLogo")}</Label>
              <input
                id="logo-file"
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="text-sm"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) logo.mutate(file);
                }}
              />
              {logo.isPending ? (
                <p role="status" className="text-sm">
                  {t("uploading")}
                </p>
              ) : null}
              {logo.isError ? (
                <p role="alert" className="text-destructive text-sm">
                  {errorMessage(logo.error)}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </Section>
      <Section title={t("profileTitle")} description={<StatusBadge status={o.status} />}>
        <OrganisationForm
          readOnly={!editable}
          initial={{
            name: o.name,
            legal_name: o.legal_name ?? "",
            registration_number: o.registration_number ?? "",
            industry: o.industry ?? "",
            size_band: (o.size_band ?? "") as "",
            country: o.country ?? "ZW",
            city: o.city ?? "",
            website: o.website ?? "",
            description: o.description ?? "",
          }}
          submitLabel={t("save")}
          onSubmit={async (values) => {
            const updated = await orgApi.update(orgId!, values);
            client.setQueryData(orgKeys.org(orgId!), updated);
          }}
        />
      </Section>
    </div>
  );
}

// ---------------------------------------------------------------------- structure
function NameAdder({
  label,
  onAdd,
  pending,
}: {
  label: string;
  onAdd: (name: string) => Promise<unknown>;
  pending: boolean;
}) {
  const t = useTranslations("organisations.settings");
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!value.trim()) return;
    setError(null);
    try {
      await onAdd(value.trim());
      setValue("");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (Object.values(err.fieldErrors())[0]?.[0] ?? err.message)
          : t("genericError"),
      );
    }
  };
  const id = `add-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <form method="post" onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={id}>{label}</Label>
        <Input
          id={id}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="h-10 w-64"
        />
      </div>
      <Button type="submit" className="min-h-10" disabled={pending || !value.trim()}>
        {t("add")}
      </Button>
      {error ? (
        <p role="alert" className="text-destructive w-full text-sm">
          {error}
        </p>
      ) : null}
    </form>
  );
}

export function StructureSettings() {
  const t = useTranslations("organisations.settings");
  const { orgId, role, isPending } = useOrgContext();
  const client = useQueryClient();
  const departments = useDepartments(orgId);
  const locations = useLocations(orgId);
  const manage = can(role, "structure.manage");
  const refresh = (key: readonly unknown[]) => client.invalidateQueries({ queryKey: key });
  const addDep = useMutation({
    mutationFn: (name: string) => orgApi.createDepartment(orgId!, name),
    onSuccess: () => refresh(orgKeys.departments(orgId!)),
  });
  const delDep = useMutation({
    mutationFn: (id: string) => orgApi.deleteDepartment(orgId!, id),
    onSuccess: () => refresh(orgKeys.departments(orgId!)),
  });
  const addLoc = useMutation({
    mutationFn: (name: string) =>
      orgApi.createLocation(orgId!, { name, city: name, workplace_type_default: "on_site" }),
    onSuccess: () => refresh(orgKeys.locations(orgId!)),
  });
  const delLoc = useMutation({
    mutationFn: (id: string) => orgApi.deleteLocation(orgId!, id),
    onSuccess: () => refresh(orgKeys.locations(orgId!)),
  });

  if (isPending || departments.isPending || locations.isPending) return <PageSkeleton rows={4} />;
  if (departments.isError)
    return <ErrorState error={departments.error} onRetry={() => departments.refetch()} />;
  if (locations.isError)
    return <ErrorState error={locations.error} onRetry={() => locations.refetch()} />;

  const list = (
    items: { id: string; name: string; extra?: string }[],
    onDelete: (id: string) => void,
    emptyText: string,
  ) =>
    items.length === 0 ? (
      <EmptyState title={emptyText} className="py-6" />
    ) : (
      <ul className="divide-y rounded-md border">
        {items.map((item) => (
          <li key={item.id} className="flex items-center justify-between gap-2 p-3">
            <span>
              {item.name}
              {item.extra ? (
                <span className="text-muted-foreground text-sm"> · {item.extra}</span>
              ) : null}
            </span>
            {manage ? (
              <Button
                variant="ghost"
                size="icon"
                className="size-10"
                aria-label={t("deleteItem", { name: item.name })}
                onClick={() => onDelete(item.id)}
              >
                <Trash2 aria-hidden="true" />
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    );

  return (
    <div className="flex flex-col gap-6">
      <Section title={t("departmentsTitle")}>
        {list(departments.data.results, (id) => delDep.mutate(id), t("noDepartments"))}
        {manage ? (
          <NameAdder
            label={t("newDepartment")}
            onAdd={(n) => addDep.mutateAsync(n)}
            pending={addDep.isPending}
          />
        ) : null}
      </Section>
      <Section title={t("locationsTitle")}>
        {list(
          locations.data.results.map((l) => ({ id: l.id, name: l.name, extra: l.city })),
          (id) => delLoc.mutate(id),
          t("noLocations"),
        )}
        {manage ? (
          <NameAdder
            label={t("newLocation")}
            onAdd={(n) => addLoc.mutateAsync(n)}
            pending={addLoc.isPending}
          />
        ) : null}
      </Section>
    </div>
  );
}

// --------------------------------------------------------------------------- team
export function TeamSettings() {
  const t = useTranslations("organisations.team");
  const tr = useTranslations("roles");
  const { orgId, role, isPending } = useOrgContext();
  const client = useQueryClient();
  const canView = can(role, "members.view");
  const manage = can(role, "members.manage");
  const canInvite = can(role, "invitations.manage");
  const members = useMembers(orgId, canView);
  const invitations = useInvitations(orgId, canInvite);
  const [deactivating, setDeactivating] = useState<Membership | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const invalidate = () => {
    client.invalidateQueries({ queryKey: orgKeys.members(orgId!) });
    client.invalidateQueries({ queryKey: orgKeys.invitations(orgId!) });
  };
  const changeRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) => orgApi.changeRole(orgId!, id, role),
    onSuccess: invalidate,
  });
  const deactivate = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      orgApi.deactivate(orgId!, id, reason),
    onSuccess: (result) => {
      setDeactivating(null);
      setNotice(t("deactivated", { count: result.needs_reassignment.length }));
      invalidate();
    },
  });
  const resend = useMutation({
    mutationFn: (id: string) => orgApi.resendInvitation(orgId!, id),
    onSuccess: invalidate,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => orgApi.revokeInvitation(orgId!, id),
    onSuccess: invalidate,
  });

  const [inviteError, setInviteError] = useState<string | null>(null);
  const inviteForm = useForm<InviteValues>({
    resolver: zodResolver(inviteSchema),
    defaultValues: { email: "", role: "recruiter" },
  });
  const onInvite = inviteForm.handleSubmit(async (values) => {
    setInviteError(null);
    try {
      await orgApi.invite(orgId!, { ...values, allow_any_email: false });
      inviteForm.reset({ email: "", role: values.role });
      setNotice(t("invited", { email: values.email }));
      invalidate();
    } catch (err) {
      setInviteError(applyServerErrors(err, inviteForm.setError, { email: "email", role: "role" }));
    }
  });

  if (isPending) return <PageSkeleton rows={5} />;
  if (!canView) return <ForbiddenState description={t("forbidden")} />;
  if (members.isPending) return <PageSkeleton rows={5} />;
  if (members.isError)
    return <ErrorState error={members.error} onRetry={() => members.refetch()} />;
  const roleOptions = ROLES.map((r) => ({ value: r, label: tr(r) }));

  return (
    <div className="flex flex-col gap-6">
      {notice ? (
        <p role="status" className="text-sm">
          {notice}
        </p>
      ) : null}
      {changeRole.isError ? (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(changeRole.error)}</AlertDescription>
        </Alert>
      ) : null}
      <Section title={t("membersTitle")}>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{t("membersTitle")}</caption>
            <thead>
              <tr className="border-b">
                <th scope="col" className="py-2 pr-3">
                  {t("name")}
                </th>
                <th scope="col" className="py-2 pr-3">
                  {t("role")}
                </th>
                <th scope="col" className="py-2 pr-3">
                  {t("mfa")}
                </th>
                <th scope="col" className="py-2 pr-3">
                  {t("status")}
                </th>
                <th scope="col" className="py-2">
                  <span className="sr-only">{t("actions")}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {members.data.results.map((m) => (
                <tr key={m.id} className="border-b last:border-0">
                  <td className="py-2 pr-3">
                    <div className="font-medium">{m.user.display_name}</div>
                    <div className="text-muted-foreground text-xs">{m.user.email}</div>
                  </td>
                  <td className="py-2 pr-3">
                    {manage && m.status === "active" ? (
                      <select
                        aria-label={t("roleFor", { name: m.user.display_name })}
                        value={m.role}
                        disabled={changeRole.isPending}
                        onChange={(e) =>
                          changeRole.mutate({ id: m.id, role: e.target.value as Role })
                        }
                        className="border-input bg-background h-9 rounded-md border px-2"
                      >
                        {roleOptions.map((o) => (
                          <option key={o.value} value={o.value}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      tr(m.role)
                    )}
                  </td>
                  <td className="py-2 pr-3">{m.mfa_enabled ? t("mfaOn") : t("mfaOff")}</td>
                  <td className="py-2 pr-3">
                    <StatusBadge status={m.status} />
                  </td>
                  <td className="py-2 text-right">
                    {manage && m.status === "active" ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="min-h-8"
                        onClick={() => setDeactivating(m)}
                      >
                        {t("deactivate")}
                      </Button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {canInvite ? (
        <Section title={t("invitationsTitle")} description={t("invitationsHelp")}>
          <form
            method="post"
            onSubmit={onInvite}
            noValidate
            className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end"
          >
            <ErrorSummary
              errors={inviteForm.formState.errors}
              formError={inviteError}
              labels={{ email: t("email"), role: t("role") }}
              submitCount={inviteForm.formState.submitCount}
            />
            <TextField
              label={t("email")}
              type="email"
              required
              error={inviteForm.formState.errors.email}
              {...inviteForm.register("email")}
            />
            <SelectField
              label={t("role")}
              options={roleOptions}
              error={inviteForm.formState.errors.role}
              {...inviteForm.register("role")}
            />
            <Button type="submit" className="min-h-10" disabled={inviteForm.formState.isSubmitting}>
              {t("sendInvite")}
            </Button>
          </form>
          {invitations.isPending ? null : invitations.isError ? (
            <ErrorState error={invitations.error} onRetry={() => invitations.refetch()} />
          ) : invitations.data.results.length === 0 ? (
            <p className="text-muted-foreground text-sm">{t("noPending")}</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {invitations.data.results.map((inv) => (
                <li key={inv.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                  <div>
                    <div className="font-medium">{inv.email}</div>
                    <div className="text-muted-foreground text-xs">
                      {tr(inv.role)} ·{" "}
                      {t("expires", { date: new Date(inv.expires_at).toLocaleDateString() })}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="min-h-8"
                      onClick={() => resend.mutate(inv.id)}
                    >
                      {t("resend")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="min-h-8"
                      onClick={() => revoke.mutate(inv.id)}
                    >
                      {t("revoke")}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>
      ) : null}

      <ConfirmDialog
        open={deactivating !== null}
        onOpenChange={(open) => !open && setDeactivating(null)}
        title={t("deactivateTitle", { name: deactivating?.user.display_name ?? "" })}
        description={t("deactivateBody")}
        confirmLabel={t("deactivate")}
        destructive
        reason="optional"
        pending={deactivate.isPending}
        error={errorMessage(deactivate.error)}
        onConfirm={(reason) => deactivating && deactivate.mutate({ id: deactivating.id, reason })}
      />
    </div>
  );
}

// ------------------------------------------------------------------------- policies
const BOOLEAN_POLICIES = [
  "ai_enabled",
  "llm_enabled",
  "blind_review_default",
  "hide_ai_from_panelists",
  "shortlist_dual_control",
  "rubric_dual_control",
] as const;

export function PolicySettings() {
  const t = useTranslations("organisations.policies");
  const { orgId, role, isPending } = useOrgContext();
  const canView = can(role, "policy.view");
  const editable = can(role, "policy.update");
  const policy = usePolicy(orgId, canView);
  const client = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const form = useForm<PolicyValues>({
    resolver: zodResolver(policySchema),
    values: policy.data as PolicyValues | undefined,
  });

  if (isPending) return <PageSkeleton rows={6} />;
  if (!canView) return <ForbiddenState description={t("forbidden")} />;
  if (policy.isPending) return <PageSkeleton rows={6} />;
  if (policy.isError) return <ErrorState error={policy.error} onRetry={() => policy.refetch()} />;

  const submit = form.handleSubmit(async (values) => {
    setFormError(null);
    setSaved(false);
    try {
      const updated = await orgApi.updatePolicy(orgId!, {
        ...values,
        lock_version: policy.data.version,
      });
      client.setQueryData(orgKeys.policy(orgId!), updated);
      setSaved(true);
    } catch (err) {
      if (err instanceof ApiError && err.code === "conflict.stale_version") {
        setFormError(t("stale"));
        await policy.refetch();
        return;
      }
      setFormError(applyServerErrors(err, form.setError));
    }
  });
  const e = form.formState.errors;
  const num = { setValueAs: (v: string) => (v === "" ? undefined : Number(v)) };
  return (
    <form method="post" onSubmit={submit} noValidate className="flex flex-col gap-6">
      <ErrorSummary
        errors={e}
        formError={formError}
        labels={{
          retention_months: t("retention_months"),
          notification_delay_minutes: t("notification_delay_minutes"),
          rights_request_sla_days: t("rights_request_sla_days"),
        }}
        submitCount={form.formState.submitCount}
      />
      <fieldset disabled={!editable} className="flex flex-col gap-6">
        <Section title={t("aiTitle")} description={t("aiHelp")}>
          {BOOLEAN_POLICIES.map((key) => (
            <div key={key} className="flex items-start gap-2">
              <input
                id={`field-${key}`}
                type="checkbox"
                className="mt-1 size-4"
                {...form.register(key)}
              />
              <div>
                <label htmlFor={`field-${key}`} className="text-sm font-medium">
                  {t(key)}
                </label>
                <p className="text-muted-foreground text-xs">{t(`${key}_help`)}</p>
              </div>
            </div>
          ))}
        </Section>
        <Section title={t("dataTitle")}>
          <div className="grid gap-4 sm:grid-cols-3">
            <TextField
              label={t("retention_months")}
              type="number"
              min={1}
              max={120}
              error={e.retention_months}
              {...form.register("retention_months", num)}
            />
            <TextField
              label={t("notification_delay_minutes")}
              type="number"
              min={0}
              max={1440}
              error={e.notification_delay_minutes}
              {...form.register("notification_delay_minutes", num)}
            />
            <TextField
              label={t("rights_request_sla_days")}
              type="number"
              min={1}
              max={90}
              error={e.rights_request_sla_days}
              {...form.register("rights_request_sla_days", num)}
            />
          </div>
          <SelectField
            label={t("duplicate_policy")}
            options={["one_active", "allow_resubmit_replace", "allow_multiple"].map((v) => ({
              value: v,
              label: t(`duplicate_${v}`),
            }))}
            {...form.register("duplicate_policy")}
          />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="field-privacy_notice">{t("privacy_notice")}</Label>
            <textarea
              id="field-privacy_notice"
              rows={6}
              className="border-input bg-background rounded-md border p-2 text-sm"
              {...form.register("privacy_notice")}
            />
          </div>
        </Section>
      </fieldset>
      {saved ? (
        <p role="status" className="text-success text-sm">
          {t("saved")}
        </p>
      ) : null}
      {editable ? (
        <Button
          type="submit"
          className="min-h-10 self-start"
          disabled={form.formState.isSubmitting}
        >
          {t("save")}
        </Button>
      ) : (
        <p className="text-muted-foreground text-sm">{t("readOnly")}</p>
      )}
    </form>
  );
}
