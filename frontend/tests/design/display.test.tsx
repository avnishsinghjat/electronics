import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  Badge,
  Breadcrumb,
  Button,
  Card,
  CardContent,
  CardHeader,
  Dialog,
  DialogContent,
  DialogTrigger,
  Drawer,
  DrawerContent,
  DrawerTrigger,
  EmptyState,
  FileDropzone,
  MonoText,
  PageHeader,
  PhotoGrid,
  ProgressBar,
  Skeleton,
  StatCard,
  StatusPill,
  Stepper,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Timeline,
  Tooltip,
  toast,
} from "@/design/components";
import type { StatusTone } from "@/design/tokens";

import { renderUi } from "../utils";

describe("Badge, StatusPill, MonoText", () => {
  it("renders the five semantic status tones", () => {
    const tones: StatusTone[] = ["grey", "blue", "amber", "green", "red"];
    renderUi(
      <>
        {tones.map((t) => (
          <StatusPill key={t} tone={t}>
            {t}
          </StatusPill>
        ))}
      </>,
    );
    for (const t of tones) {
      const pill = screen.getByText(t);
      expect(pill).toHaveAttribute("data-tone", t);
      expect(pill.className).toContain(`bg-status-${t}-bg`);
    }
  });

  it("renders badges and mono text", () => {
    renderUi(
      <>
        <Badge tone="teal">Clear to build</Badge>
        <MonoText>STM32F407VGT6</MonoText>
      </>,
    );
    expect(screen.getByText("Clear to build").className).toContain("bg-teal-50");
    expect(screen.getByText("STM32F407VGT6").className).toContain("font-mono");
  });
});

describe("Card and StatCard", () => {
  it("renders header, content and actions", () => {
    renderUi(
      <Card>
        <CardHeader title="Tracker" description="All BOQ lines" actions={<Button>Export</Button>} />
        <CardContent>Body</CardContent>
      </Card>,
    );
    expect(screen.getByRole("heading", { name: "Tracker" })).toBeInTheDocument();
    expect(screen.getByText("Body")).toBeInTheDocument();
  });

  it("colours the delta by whether an increase is good", () => {
    renderUi(
      <>
        <StatCard label="Received" value="86%" delta={4} />
        <StatCard label="Overdue" value="7" delta={3} positiveIsGood={false} />
        <StatCard label="Flat" value="2" delta={0} />
      </>,
    );
    const [good, bad, flat] = screen.getAllByTestId("stat-delta");
    expect(good?.className).toContain("text-status-green-fg");
    expect(good).toHaveTextContent("+4");
    expect(bad?.className).toContain("text-status-red-fg");
    expect(flat?.className).toContain("text-neutral-500");
  });

  it("shows a skeleton while loading", () => {
    renderUi(<StatCard label="Yield" value="98%" loading />);
    expect(screen.queryByText("98%")).not.toBeInTheDocument();
    expect(screen.getByText("Yield").closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
  });
});

describe("EmptyState, Skeleton, ProgressBar", () => {
  it("renders an empty state with its next action", () => {
    renderUi(<EmptyState title="No POs yet" description="Create one" action={<Button>New PO</Button>} />);
    expect(screen.getByRole("heading", { name: "No POs yet" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New PO" })).toBeInTheDocument();
  });

  it("renders skeleton and clamps progress", () => {
    const { container } = renderUi(
      <>
        <Skeleton className="h-4" />
        <ProgressBar label="Procurement" value={150} />
        <ProgressBar label="QC" value={1} max={4} tone="green" />
      </>,
    );
    expect(container.querySelector(".skeleton-shimmer")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("progressbar", { name: "Procurement" })).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });
});

describe("Breadcrumb and PageHeader", () => {
  it("links all but the last crumb and marks the current page", () => {
    renderUi(
      <PageHeader
        title="Tracker"
        breadcrumb={[{ label: "Home", to: "/" }, { label: "Projects", to: "/projects" }, { label: "PRJ-2026-0001" }]}
        primaryAction={<Button>New PO</Button>}
      />,
    );
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Home", "Projects"]);
    expect(within(nav).getByText("PRJ-2026-0001")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("heading", { level: 1, name: "Tracker" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New PO" })).toBeInTheDocument();
  });

  it("standalone breadcrumb", () => {
    renderUi(<Breadcrumb items={[{ label: "Only" }]} />);
    expect(screen.getByText("Only")).toHaveAttribute("aria-current", "page");
  });
});

describe("Tabs, Stepper, Timeline", () => {
  it("switches tabs and skips disabled ones", async () => {
    renderUi(
      <Tabs defaultValue="a">
        <TabsList aria-label="Sections">
          <TabsTrigger value="a">A</TabsTrigger>
          <TabsTrigger value="b">B</TabsTrigger>
          <TabsTrigger value="c" disabled>
            C
          </TabsTrigger>
        </TabsList>
        <TabsContent value="a">Panel A</TabsContent>
        <TabsContent value="b">Panel B</TabsContent>
      </Tabs>,
    );
    expect(screen.getByText("Panel A")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "B" }));
    expect(screen.getByText("Panel B")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "C" })).toBeDisabled();
  });

  it("stepper marks the current and blocked stages", () => {
    renderUi(
      <Stepper
        steps={[
          { id: "1", label: "Kitting", state: "complete" },
          { id: "2", label: "Reflow", state: "current" },
          { id: "3", label: "THT", state: "blocked" },
        ]}
      />,
    );
    const items = screen.getAllByRole("listitem");
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("(blocked)")).toBeInTheDocument();
  });

  it("timeline shows events with actors", () => {
    renderUi(<Timeline events={[{ id: "1", title: "BOQ released", timestamp: "2026-11-02T10:24:00+05:30", actor: "Priya", tone: "green" }]} />);
    expect(screen.getByText("BOQ released")).toBeInTheDocument();
    expect(screen.getByText("Priya")).toBeInTheDocument();
    expect(screen.getByRole("listitem").querySelector("time")).toHaveAttribute("dateTime", "2026-11-02T10:24:00+05:30");
  });
});

describe("Dialog, Drawer, Tooltip, Toast", () => {
  it("opens and closes a dialog with title and footer", async () => {
    renderUi(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Open</Button>
        </DialogTrigger>
        <DialogContent title="Release revision?" description="Rev A becomes read-only" footer={<Button>Release</Button>}>
          Body
        </DialogContent>
      </Dialog>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    const dialog = screen.getByRole("dialog", { name: "Release revision?" });
    expect(dialog).toHaveAccessibleDescription("Rev A becomes read-only");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens a drawer and closes with the close button", async () => {
    renderUi(
      <Drawer>
        <DrawerTrigger asChild>
          <Button>Edit line</Button>
        </DrawerTrigger>
        <DrawerContent title="BOQ line 12">Fields</DrawerContent>
      </Drawer>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Edit line" }));
    expect(screen.getByRole("dialog", { name: "BOQ line 12" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a tooltip on focus", async () => {
    renderUi(
      <Tooltip content="Includes 2% attrition">
        <Button>Required</Button>
      </Tooltip>,
    );
    await userEvent.tab();
    expect((await screen.findAllByText("Includes 2% attrition")).length).toBeGreaterThan(0);
  });

  it("shows success and error toasts", async () => {
    renderUi(<span />);
    act(() => {
      toast.success("GRN posted");
      toast.error("Could not post GRN");
    });
    expect(await screen.findByText("GRN posted")).toBeInTheDocument();
    expect(await screen.findByText("Could not post GRN")).toBeInTheDocument();
  });
});

describe("FileDropzone", () => {
  const png = new File(["x"], "board.png", { type: "image/png" });
  const exe = new File(["x"], "virus.exe", { type: "application/x-msdownload" });
  const big = new File([new Uint8Array(3 * 1024 * 1024)], "big.png", { type: "image/png" });

  it("accepts allowed files from the picker and rejects others with a message", async () => {
    const onFiles = vi.fn();
    const { container } = renderUi(<FileDropzone onFiles={onFiles} accept={["image/*"]} maxSizeBytes={2 * 1024 * 1024} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, [png, big], { applyAccept: false });
    expect(onFiles).toHaveBeenCalledWith([png]);
    expect(screen.getByRole("alert")).toHaveTextContent("big.png: larger than 2 MB");
    fireEvent.drop(input.closest("label") as HTMLElement, { dataTransfer: { files: [exe] } });
    expect(screen.getByRole("alert")).toHaveTextContent("virus.exe: type not allowed");
    expect(onFiles).toHaveBeenCalledTimes(1);
  });

  it("does nothing when disabled and shows an external error", () => {
    const onFiles = vi.fn();
    const { container } = renderUi(<FileDropzone onFiles={onFiles} disabled error="Upload failed: disk full" capture="environment" />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeDisabled();
    expect(input).toHaveAttribute("capture", "environment");
    fireEvent.drop(input.closest("label") as HTMLElement, { dataTransfer: { files: [png] } });
    expect(onFiles).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Upload failed: disk full");
  });
});

describe("PhotoGrid", () => {
  const photos = [
    { id: "1", src: "data:image/png;base64,AA==", alt: "Reflow top", meta: [{ label: "Serial", value: "SN-1", mono: true }] },
    { id: "2", src: "data:image/png;base64,AB==", alt: "AOI U3" },
  ];

  it("opens the lightbox, navigates and shows evidence metadata", async () => {
    renderUi(<PhotoGrid photos={photos} />);
    await userEvent.click(screen.getByRole("button", { name: "Open photo: Reflow top" }));
    const dlg = screen.getByRole("dialog");
    expect(within(dlg).getByText("SN-1")).toBeInTheDocument();
    expect(within(dlg).getByText("(1 / 2)")).toBeInTheDocument();
    await userEvent.click(within(dlg).getByRole("button", { name: "Next photo" }));
    expect(within(screen.getByRole("dialog")).getByText("(2 / 2)")).toBeInTheDocument();
    await userEvent.keyboard("{ArrowRight}");
    expect(within(screen.getByRole("dialog")).getByText("(1 / 2)")).toBeInTheDocument();
  });

  it("renders loading and empty states", () => {
    const { rerender } = renderUi(<PhotoGrid photos={[]} loading />);
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument();
    rerender(<PhotoGrid photos={[]} emptyText="No evidence yet" />);
    expect(screen.getByText("No evidence yet")).toBeInTheDocument();
  });
});
