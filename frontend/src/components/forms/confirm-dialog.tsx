"use client";

import { useTranslations } from "next-intl";
import { useId, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

/** Confirmation for consequential actions, optionally collecting a reason (docs/08 §1). */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = false,
  reason = "none",
  onConfirm,
  pending = false,
  error,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  confirmLabel: string;
  destructive?: boolean;
  reason?: "none" | "optional" | "required";
  onConfirm: (reason: string) => void;
  pending?: boolean;
  error?: string | null;
}) {
  const t = useTranslations("forms");
  const id = useId();
  const [value, setValue] = useState("");
  const missing = reason === "required" && value.trim().length < 5;
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setValue("");
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {reason !== "none" ? (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={id}>
              {t("reason")}
              {reason === "required" ? ` ${t("requiredMark")}` : ""}
            </Label>
            <textarea
              id={id}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              rows={3}
              maxLength={500}
              className="border-input bg-background focus-visible:ring-ring/50 rounded-md border p-2 text-sm"
            />
            <p className="text-muted-foreground text-xs">{t("reasonHelp")}</p>
          </div>
        ) : null}
        {error ? (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" className="min-h-10" onClick={() => onOpenChange(false)}>
            {t("cancel")}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            className="min-h-10"
            disabled={pending || missing}
            onClick={() => onConfirm(value.trim())}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
