import { z } from "zod";

/** Mirrors the backend policy (FR-M01-06): min 10 chars, no composition rules. */
export const PASSWORD_MIN = 10;

const email = z.string().trim().min(1, "required").email("invalidEmail");
const password = z.string().min(PASSWORD_MIN, "passwordTooShort");

export const loginSchema = z.object({
  email,
  password: z.string().min(1, "required"),
});

export const registerSchema = z
  .object({
    email,
    password,
    confirmPassword: z.string().min(1, "required"),
    acceptTerms: z.literal(true, { message: "mustAcceptTerms" }),
  })
  .refine((v) => v.password === v.confirmPassword, {
    path: ["confirmPassword"],
    message: "passwordsDoNotMatch",
  });

export const forgotPasswordSchema = z.object({ email });

export const resetPasswordSchema = z
  .object({ password, confirmPassword: z.string().min(1, "required") })
  .refine((v) => v.password === v.confirmPassword, {
    path: ["confirmPassword"],
    message: "passwordsDoNotMatch",
  });

export const changePasswordSchema = z
  .object({
    currentPassword: z.string().min(1, "required"),
    newPassword: password,
    confirmPassword: z.string().min(1, "required"),
  })
  .refine((v) => v.newPassword === v.confirmPassword, {
    path: ["confirmPassword"],
    message: "passwordsDoNotMatch",
  });

export const changeEmailSchema = z.object({ email });

export const codeSchema = z.object({
  code: z
    .string()
    .trim()
    .min(6, "invalidCode")
    .max(20, "invalidCode")
    .regex(/^[A-Za-z0-9-]+$/, "invalidCode"),
});

export const reauthSchema = z.object({ password: z.string().min(1, "required") });

export type LoginValues = z.infer<typeof loginSchema>;
export type RegisterValues = z.infer<typeof registerSchema>;
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;
export type ChangePasswordValues = z.infer<typeof changePasswordSchema>;
export type ChangeEmailValues = z.infer<typeof changeEmailSchema>;
export type CodeValues = z.infer<typeof codeSchema>;
export type ReauthValues = z.infer<typeof reauthSchema>;
