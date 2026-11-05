import * as DialogPrimitive from "@radix-ui/react-dialog";
import { ChevronLeft, ChevronRight, ImageOff, UploadCloud, X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import { MonoText } from "./badge";

/* ---------------------------------------------------------------- FileDropzone */

export interface FileDropzoneProps {
  onFiles: (files: File[]) => void;
  accept?: string[];
  maxSizeBytes?: number;
  multiple?: boolean;
  disabled?: boolean;
  /** "environment" opens the rear camera directly on tablets (QC photo capture). */
  capture?: "environment" | "user";
  label?: string;
  hint?: string;
  error?: string;
}

function matches(file: File, accept: string[]): boolean {
  return accept.some((a) => {
    if (a.startsWith(".")) return file.name.toLowerCase().endsWith(a.toLowerCase());
    if (a.endsWith("/*")) return file.type.startsWith(a.slice(0, -1));
    return file.type === a;
  });
}

export function FileDropzone({
  onFiles,
  accept,
  maxSizeBytes,
  multiple = true,
  disabled,
  capture,
  label = "Drop files here or browse",
  hint,
  error,
}: FileDropzoneProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);
  const [rejected, setRejected] = React.useState<string | null>(null);
  const id = React.useId();

  const handle = (list: FileList | null) => {
    if (!list || disabled) return;
    const files = Array.from(list);
    const bad: string[] = [];
    const ok = files.filter((f) => {
      if (accept && !matches(f, accept)) {
        bad.push(`${f.name}: type not allowed`);
        return false;
      }
      if (maxSizeBytes && f.size > maxSizeBytes) {
        bad.push(`${f.name}: larger than ${Math.round(maxSizeBytes / 1024 / 1024)} MB`);
        return false;
      }
      return true;
    });
    setRejected(bad.length ? bad.join("; ") : null);
    if (ok.length) onFiles(multiple ? ok : ok.slice(0, 1));
  };

  const message = error ?? rejected;
  return (
    <div>
      <label
        htmlFor={id}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handle(e.dataTransfer.files);
        }}
        aria-disabled={disabled || undefined}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-neutral-300 bg-neutral-25 px-6 py-8 text-center transition-colors hover:border-accent-400 hover:bg-accent-50/40",
          dragging && "border-accent-600 bg-accent-50",
          message && "border-status-red-border",
          disabled && "cursor-not-allowed opacity-60 hover:border-neutral-300 hover:bg-neutral-25",
        )}
      >
        <span className="flex size-10 items-center justify-center rounded-lg border bg-white shadow-xs">
          <UploadCloud className="size-5 text-neutral-500" aria-hidden="true" />
        </span>
        <span className="text-sm font-medium text-neutral-800">{label}</span>
        {hint && <span className="text-xs text-neutral-500">{hint}</span>}
        <input
          ref={inputRef}
          id={id}
          type="file"
          className="sr-only"
          multiple={multiple}
          accept={accept?.join(",")}
          capture={capture}
          disabled={disabled}
          onChange={(e) => {
            handle(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
      {message && (
        <p role="alert" className="mt-1.5 text-xs text-status-red-fg">
          {message}
        </p>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- PhotoGrid + lightbox */

export interface Photo {
  id: string;
  src: string;
  thumbSrc?: string;
  alt: string;
  caption?: string;
  /** Evidence chain shown in the lightbox, e.g. who, when, which checklist item. */
  meta?: { label: string; value: string; mono?: boolean }[];
}

export function PhotoGrid({ photos, loading, emptyText = "No photos yet", className }: {
  photos: Photo[];
  loading?: boolean;
  emptyText?: string;
  className?: string;
}) {
  const [index, setIndex] = React.useState<number | null>(null);
  const current = index === null ? null : photos[index];

  const go = React.useCallback(
    (dir: 1 | -1) => setIndex((i) => (i === null ? i : (i + dir + photos.length) % photos.length)),
    [photos.length],
  );

  if (loading) {
    return (
      <div className={cn("grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3", className)} aria-busy="true">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="skeleton-shimmer aspect-[4/3] rounded-md" />
        ))}
      </div>
    );
  }
  if (photos.length === 0) {
    return (
      <div className={cn("flex items-center gap-2 rounded-md border border-dashed px-4 py-6 text-sm text-neutral-500", className)}>
        <ImageOff className="size-4" aria-hidden="true" /> {emptyText}
      </div>
    );
  }
  return (
    <>
      <ul className={cn("grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3", className)}>
        {photos.map((p, i) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => setIndex(i)}
              className="group block w-full overflow-hidden rounded-md border bg-neutral-50 shadow-xs focus-visible:shadow-focus focus-visible:outline-none"
              aria-label={`Open photo: ${p.alt}`}
            >
              <img src={p.thumbSrc ?? p.src} alt={p.alt} loading="lazy" className="aspect-[4/3] w-full object-cover transition-transform group-hover:scale-[1.02]" />
            </button>
            {p.caption && <p className="mt-1 truncate text-xs text-neutral-600">{p.caption}</p>}
          </li>
        ))}
      </ul>
      <DialogPrimitive.Root open={current !== null} onOpenChange={(o) => !o && setIndex(null)}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay className="fixed inset-0 z-overlay bg-neutral-900/80" />
          <DialogPrimitive.Content
            className="fixed inset-0 z-modal flex flex-col focus:outline-none"
            aria-describedby={undefined}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") go(1);
              if (e.key === "ArrowLeft") go(-1);
            }}
          >
            {current && (
              <>
                <div className="flex items-center justify-between px-4 py-3 text-white">
                  <DialogPrimitive.Title className="text-sm font-medium">
                    {current.alt} <span className="text-white/60 tabular-nums">({(index ?? 0) + 1} / {photos.length})</span>
                  </DialogPrimitive.Title>
                  <DialogPrimitive.Close aria-label="Close" className="rounded-md p-1.5 hover:bg-white/10">
                    <X className="size-5" />
                  </DialogPrimitive.Close>
                </div>
                <div className="relative flex min-h-0 flex-1 items-center justify-center px-14">
                  <img src={current.src} alt={current.alt} className="max-h-full max-w-full rounded object-contain" />
                  {photos.length > 1 && (
                    <>
                      <button type="button" aria-label="Previous photo" onClick={() => go(-1)} className="absolute left-3 rounded-full bg-white/10 p-2 text-white hover:bg-white/20">
                        <ChevronLeft className="size-5" />
                      </button>
                      <button type="button" aria-label="Next photo" onClick={() => go(1)} className="absolute right-3 rounded-full bg-white/10 p-2 text-white hover:bg-white/20">
                        <ChevronRight className="size-5" />
                      </button>
                    </>
                  )}
                </div>
                {current.meta && (
                  <dl className="flex flex-wrap gap-x-6 gap-y-1 px-4 py-3 text-xs text-white/80">
                    {current.meta.map((m) => (
                      <div key={m.label} className="flex gap-1.5">
                        <dt className="text-white/50">{m.label}</dt>
                        <dd>{m.mono ? <MonoText>{m.value}</MonoText> : m.value}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </>
            )}
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </>
  );
}
