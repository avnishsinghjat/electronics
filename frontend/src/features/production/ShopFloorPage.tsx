import jsQR from "jsqr";
import { ArrowLeft, Camera, Factory, ScanLine, X } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { Button, MonoText, Skeleton, StatusPill } from "@/design/components";
import { useAuth } from "@/features/auth/AuthContext";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { LotStageActions, UnitStageActions } from "./StageActions";
import { STAGE_STATUS, type ScanResult, UNIT_STATUS, WO_STATUS, scanSerial, useUnits, useWorkOrder, useWorkOrders } from "./api";

/** Camera QR reader, decoded locally with jsQR (no network). Needs a secure context
 *  (HTTPS or localhost); otherwise the typed / handheld-scanner input is used. */
function CameraScanner({ onCode, onClose }: { onCode: (code: string) => void; onClose: () => void }) {
  const video = React.useRef<HTMLVideoElement>(null);
  const canvas = React.useRef<HTMLCanvasElement>(null);
  const [error, setError] = React.useState<string | null>(
    window.isSecureContext && "mediaDevices" in navigator ? null : "The camera needs a secure (HTTPS) connection. Type the serial or use a handheld scanner.",
  );
  React.useEffect(() => {
    if (error) return;
    let stream: MediaStream | null = null;
    let frame = 0;
    let done = false;
    const tick = () => {
      const v = video.current;
      const c = canvas.current;
      if (done || !v || !c) return;
      if (v.readyState === v.HAVE_ENOUGH_DATA) {
        c.width = v.videoWidth;
        c.height = v.videoHeight;
        const ctx = c.getContext("2d", { willReadFrequently: true });
        if (ctx) {
          ctx.drawImage(v, 0, 0, c.width, c.height);
          const img = ctx.getImageData(0, 0, c.width, c.height);
          const found = jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" });
          if (found?.data) {
            done = true;
            onCode(found.data.trim());
            return;
          }
        }
      }
      frame = requestAnimationFrame(tick);
    };
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then((s) => {
        stream = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play();
          frame = requestAnimationFrame(tick);
        }
      })
      .catch(() => setError("The camera could not be opened. Allow camera access, or type the serial."));
    return () => {
      done = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [error, onCode]);
  return (
    <div role="dialog" aria-label="Scan a serial label" className="fixed inset-0 z-modal flex flex-col items-center justify-center bg-neutral-900/90 p-6">
      {error ? (
        <p role="alert" className="max-w-md rounded-lg bg-white p-6 text-center text-lg text-neutral-800">{error}</p>
      ) : (
        <div className="relative w-full max-w-xl overflow-hidden rounded-xl bg-black">
          <video ref={video} className="w-full" playsInline muted />
          <div className="pointer-events-none absolute inset-[18%] rounded-lg border-4 border-white/80" aria-hidden="true" />
        </div>
      )}
      <canvas ref={canvas} className="hidden" />
      <Button size="lg" variant="secondary" className="mt-6 h-14 text-lg" onClick={onClose}><X /> Close camera</Button>
    </div>
  );
}

function UnitCard({ result, onRefresh }: { result: ScanResult; onRefresh: () => void }) {
  const unit = UNIT_STATUS[result.unit_status];
  const stageStatus = result.stage?.status ?? (result.stage_id ? "not_started" : null);
  return (
    <section aria-label={`Unit ${result.serial_number}`} className="rounded-2xl border-2 bg-white p-6 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <MonoText className="text-2xl font-semibold">{result.serial_number}</MonoText>
        <StatusPill tone={unit.tone}>{unit.label}</StatusPill>
        <Link to={`/production/work-orders/${result.work_order_id}`} className="ml-auto font-mono text-accent-700 hover:underline">{result.work_order_number}</Link>
      </div>
      {result.stage_name ? (
        <div className="mt-6">
          <p className="text-sm uppercase tracking-wide text-neutral-500">Current stage</p>
          <p className="mt-1 flex flex-wrap items-center gap-3 text-3xl font-semibold text-neutral-900">
            {result.stage_name}
            {stageStatus && <StatusPill tone={STAGE_STATUS[stageStatus].tone}>{STAGE_STATUS[stageStatus].label}</StatusPill>}
            {result.stage_requires_qc && <StatusPill tone="amber">QC required</StatusPill>}
          </p>
          <div className="mt-6">
            {result.next_action && result.stage_id ? (
              <UnitStageActions
                large
                stageId={result.stage_id}
                unitId={result.serial_unit_id}
                serial={result.serial_number}
                action={result.next_action}
                requiresQc={result.stage_requires_qc}
                onDone={onRefresh}
              />
            ) : (
              <p className="text-lg text-neutral-600">{result.unit_status === "failed" ? "This unit failed a stage: hand it to QC." : "No action here: the work order is not released."}</p>
            )}
          </div>
        </div>
      ) : (
        <p className="mt-6 text-xl text-status-green-fg">All stages complete.</p>
      )}
    </section>
  );
}

function OrderTile({ id, onPick }: { id: string; onPick: (code: string) => void }) {
  const wo = useWorkOrder(id);
  const units = useUnits(id, !!wo.data?.track_serials);
  if (!wo.data) return <Skeleton className="h-40" />;
  const w = wo.data;
  const current = w.stages.find((s) => s.status !== "completed");
  return (
    <section aria-label={`Work order ${w.number}`} className="rounded-2xl border bg-white p-5">
      <div className="flex items-center gap-3">
        <MonoText className="text-lg font-semibold">{w.number}</MonoText>
        <StatusPill tone={WO_STATUS[w.status].tone}>{WO_STATUS[w.status].label}</StatusPill>
      </div>
      <p className="mt-1 text-sm text-neutral-600">{w.assembly_label} · {w.build_qty} boards</p>
      {w.track_serials ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {(units.data ?? []).filter((u) => u.status === "in_production").map((u) => (
            <button
              key={u.id}
              type="button"
              onClick={() => onPick(u.serial_number)}
              className="min-h-12 rounded-lg border-2 px-3 py-2 text-left hover:border-accent-600 focus-visible:shadow-focus focus-visible:outline-none"
            >
              <MonoText className="block text-sm">{u.serial_number.split("-").slice(-1)[0]}</MonoText>
              <span className="text-xs text-neutral-500">{u.current_stage}</span>
            </button>
          ))}
          {units.data && !units.data.length && <p className="text-sm text-neutral-500">No serials yet: generate them on the work order.</p>}
        </div>
      ) : current ? (
        <div className="mt-4 space-y-2">
          <p className="text-lg font-medium">{current.name} <span className="text-sm text-neutral-500">({current.units_done}/{current.units_in})</span></p>
          <LotStageActions stageId={current.id} status={current.status} unitsIn={current.units_in} requiresQc={current.requires_qc} stageName={current.name} />
        </div>
      ) : null}
    </section>
  );
}

export default function ShopFloorPage() {
  const { user } = useAuth();
  const orders = useWorkOrders({ status: "released,in_progress" });
  const [code, setCode] = React.useState("");
  const [result, setResult] = React.useState<ScanResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [camera, setCamera] = React.useState(false);
  const input = React.useRef<HTMLInputElement>(null);

  const lookup = React.useCallback(async (serial: string) => {
    setCamera(false);
    setError(null);
    if (!serial.trim()) return;
    // Clear the box either way: the next scan from a handheld scanner must not be
    // appended to a code that was not found.
    setCode("");
    try {
      setResult(await scanSerial(serial.trim()));
    } catch (e) {
      setResult(null);
      setError(e instanceof ApiError ? e.message : "Lookup failed");
    }
    input.current?.focus();
  }, []);

  return (
    <div className="app-canvas min-h-screen">
      <header className="flex items-center gap-3 border-b bg-white px-5 py-3">
        <Button asChild variant="ghost" size="lg" className="h-12"><Link to="/production"><ArrowLeft /> Production</Link></Button>
        <Factory className="size-6 text-accent-700" aria-hidden="true" />
        <h1 className="text-xl font-semibold">Shop floor</h1>
        <span className="ml-auto text-sm text-neutral-600">{user?.full_name}</span>
      </header>
      <main className="mx-auto max-w-5xl space-y-6 p-5">
        <form
          className="flex flex-wrap gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void lookup(code);
          }}
        >
          <label htmlFor="sf-serial" className="sr-only">Serial number</label>
          <input
            id="sf-serial"
            ref={input}
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Scan or type a serial number"
            autoComplete="off"
            className="h-16 min-w-0 flex-1 rounded-xl border-2 border-neutral-300 bg-white px-5 font-mono text-2xl focus:border-accent-600 focus:outline-none"
          />
          <Button type="submit" size="lg" className="h-16 px-6 text-lg"><ScanLine /> Find</Button>
          <Button type="button" size="lg" variant="secondary" className="h-16 px-6 text-lg" onClick={() => setCamera(true)}><Camera /> Camera</Button>
        </form>
        {error && <p role="alert" className="rounded-xl border-2 border-status-red-border bg-status-red-bg p-4 text-lg text-status-red-fg">{error}</p>}
        {result && <UnitCard result={result} onRefresh={() => void lookup(result.serial_number)} />}
        <section aria-label="Work orders on the floor" className="space-y-3">
          <h2 className="text-lg font-semibold text-neutral-800">On the floor</h2>
          <div className={cn("grid gap-4", "md:grid-cols-2")}>
            {(orders.data ?? []).map((w) => <OrderTile key={w.id} id={w.id} onPick={(sn) => void lookup(sn)} />)}
          </div>
          {orders.data && !orders.data.length && <p className="text-neutral-500">No released work orders.</p>}
        </section>
      </main>
      {camera && <CameraScanner onCode={(c) => void lookup(c)} onClose={() => setCamera(false)} />}
    </div>
  );
}
