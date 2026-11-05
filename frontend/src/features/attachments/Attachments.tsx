import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Eye, FileText, Image as ImageIcon, Paperclip, Trash2 } from "lucide-react";
import * as React from "react";

import { Button, Dialog, DialogContent, EmptyState, FileDropzone, MonoText, Skeleton, toast } from "@/design/components";
import { useCan } from "@/features/auth/AuthContext";
import { formatBytes } from "@/features/system/format";
import { ApiError, apiBlob, apiDelete, apiGet, apiPost, qs } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

export interface Attachment {
  id: string;
  ref_type: string;
  ref_id: string;
  original_name: string;
  mime: string;
  size_bytes: number;
  sha256: string;
  uploaded_by: string | null;
  uploaded_by_name: string | null;
  created_at: string;
  previewable: boolean;
  row_version: number;
}

export const attachmentKey = (refType: string, refId: string) => ["files", refType, refId] as const;

export function useAttachments(refType: string, refId: string | null) {
  return useQuery({
    queryKey: attachmentKey(refType, refId ?? ""),
    queryFn: ({ signal }) => apiGet<Attachment[]>(`/files${qs({ ref_type: refType, ref_id: refId })}`, signal),
    enabled: refId !== null,
  });
}

export async function uploadAttachment(refType: string, refId: string, file: File): Promise<Attachment> {
  const body = new FormData();
  body.append("ref_type", refType);
  body.append("ref_id", refId);
  body.append("file", file);
  return apiPost<Attachment>("/files", body);
}

export async function downloadAttachment(file: Attachment): Promise<void> {
  const blob = await apiBlob(`/files/${file.id}/content`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = file.original_name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function Preview({ file, onClose }: { file: Attachment | null; onClose: () => void }) {
  const [url, setUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!file) return;
    let objectUrl: string | null = null;
    const controller = new AbortController();
    apiBlob(`/files/${file.id}/content?disposition=inline`, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) setError(err instanceof ApiError ? err.message : "Could not load the file");
      });
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setUrl(null);
      setError(null);
    };
  }, [file]);
  const isPdf = file?.mime === "application/pdf";
  return (
    <Dialog open={file !== null} onOpenChange={(o) => !o && onClose()}>
      <DialogContent
        size="xl"
        title={file?.original_name ?? ""}
        description={file ? `${formatBytes(file.size_bytes)} · SHA-256 ${file.sha256.slice(0, 12)}…` : undefined}
        footer={
          file && (
            <>
              {isPdf && url && (
                <Button asChild variant="secondary">
                  <a href={url} target="_blank" rel="noreferrer">
                    Open in new tab
                  </a>
                </Button>
              )}
              <Button onClick={() => void downloadAttachment(file)}>
                <Download /> Download
              </Button>
            </>
          )
        }
      >
        {error && <p role="alert" className="text-sm text-status-red-fg">{error}</p>}
        {!error && !url && <Skeleton className="h-[60vh] w-full" />}
        {url && !isPdf && <img src={url} alt={file?.original_name} className="mx-auto max-h-[65vh] rounded border object-contain" />}
        {url && isPdf && <iframe src={url} title={`Preview of ${file?.original_name ?? "file"}`} className="h-[65vh] w-full rounded border" />}
      </DialogContent>
    </Dialog>
  );
}

/** Drag-and-drop attachments for any record: list, preview images/PDF, download, delete. */
export function Attachments({ refType, refId, title = "Files", onChanged }: {
  refType: string;
  refId: string;
  title?: string;
  onChanged?: () => void;
}) {
  const canUpload = useCan("files:upload");
  const canDelete = useCan("files:delete");
  const qc = useQueryClient();
  const files = useAttachments(refType, refId);
  const [preview, setPreview] = React.useState<Attachment | null>(null);
  const [confirm, setConfirm] = React.useState<Attachment | null>(null);
  const changed = () => {
    void qc.invalidateQueries({ queryKey: attachmentKey(refType, refId) });
    void qc.invalidateQueries({ queryKey: ["projects", "history"] });
    onChanged?.();
  };
  const upload = useMutation({
    mutationFn: async (list: File[]) => {
      for (const f of list) await uploadAttachment(refType, refId, f);
      return list.length;
    },
    onSuccess: (n) => {
      toast.success(`${n} file${n === 1 ? "" : "s"} attached`);
      changed();
    },
    onError: (err) => {
      toast.error(err instanceof ApiError ? err.message : "Upload failed");
      changed();
    },
  });
  const remove = useMutation({
    mutationFn: (f: Attachment) => apiDelete(`/files/${f.id}?row_version=${f.row_version}`),
    onSuccess: () => {
      toast.success("File deleted");
      changed();
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Could not delete"),
    onSettled: () => setConfirm(null),
  });

  return (
    <section aria-label={title} className="space-y-3">
      {canUpload && (
        <FileDropzone onFiles={(f) => upload.mutate(f)} disabled={upload.isPending} label={upload.isPending ? "Uploading…" : "Drop files here or browse"} hint="Drawings, specs, photos, Gerbers, KiCad zips · up to 100 MB each" />
      )}
      {files.isPending ? (
        <Skeleton className="h-20" />
      ) : files.isError ? (
        <p role="alert" className="text-sm text-status-red-fg">{files.error.message}</p>
      ) : files.data.length === 0 ? (
        <EmptyState icon={Paperclip} title="No files yet" description={canUpload ? "Drop drawings, specifications or photos above." : "Nothing has been attached."} className="py-6" />
      ) : (
        <ul className="divide-y rounded-lg border bg-white" aria-label={`${title} list`}>
          {files.data.map((f) => {
            const Icon = f.mime.startsWith("image/") ? ImageIcon : FileText;
            return (
              <li key={f.id} className="flex items-center gap-3 px-3 py-2">
                <Icon className="size-4 shrink-0 text-neutral-500" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-neutral-900">{f.original_name}</p>
                  <p className="text-xs text-neutral-500">
                    {formatBytes(f.size_bytes)} · {f.uploaded_by_name ?? "System"} · {fmtDateTime(f.created_at)} · <MonoText>{f.sha256.slice(0, 8)}</MonoText>
                  </p>
                </div>
                {f.previewable && (
                  <Button size="icon-sm" variant="ghost" aria-label={`Preview ${f.original_name}`} onClick={() => setPreview(f)}>
                    <Eye />
                  </Button>
                )}
                <Button size="icon-sm" variant="ghost" aria-label={`Download ${f.original_name}`} onClick={() => void downloadAttachment(f).catch(() => toast.error("Download failed"))}>
                  <Download />
                </Button>
                {canDelete && (
                  <Button size="icon-sm" variant="ghost" aria-label={`Delete ${f.original_name}`} onClick={() => setConfirm(f)}>
                    <Trash2 />
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <Preview file={preview} onClose={() => setPreview(null)} />
      <Dialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent
          size="sm"
          title="Delete file?"
          description="It disappears from this record; the deletion is recorded in the history."
          footer={
            <>
              <Button variant="secondary" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              <Button variant="danger" loading={remove.isPending} onClick={() => confirm && remove.mutate(confirm)}>
                Delete
              </Button>
            </>
          }
        >
          <p className="text-sm text-neutral-700">{confirm?.original_name}</p>
        </DialogContent>
      </Dialog>
    </section>
  );
}
