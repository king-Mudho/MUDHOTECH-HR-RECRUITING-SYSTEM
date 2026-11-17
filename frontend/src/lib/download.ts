/** Download a file from a staff endpoint that needs the organisation header (`X-Org-Id`). */
export async function downloadWithOrg(
  url: string,
  orgId: string,
  filename: string,
): Promise<boolean> {
  const res = await fetch(url, { credentials: "same-origin", headers: { "X-Org-Id": orgId } });
  if (!res.ok) return false;
  const href = URL.createObjectURL(await res.blob());
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(href);
  return true;
}
