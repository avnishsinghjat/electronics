import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import {
  Button,
  Checkbox,
  Combobox,
  type ComboboxOption,
  DatePicker,
  Field,
  Input,
  NumberInput,
  Select,
  Switch,
  Textarea,
} from "@/design/components";

import { renderUi } from "../utils";

describe("Button", () => {
  it("renders every variant and fires clicks", async () => {
    const onClick = vi.fn();
    renderUi(
      <>
        <Button onClick={onClick}>Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger">Danger</Button>
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Primary" }));
    expect(onClick).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Danger" }).className).toContain("bg-[#D92D20]");
  });

  it("is disabled and busy while loading", async () => {
    const onClick = vi.fn();
    renderUi(<Button loading onClick={onClick}>Saving</Button>);
    const btn = screen.getByRole("button", { name: "Saving" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
    await userEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("supports disabled and asChild", () => {
    renderUi(
      <>
        <Button disabled>Off</Button>
        <Button asChild>
          <a href="/x">Link button</a>
        </Button>
      </>,
    );
    expect(screen.getByRole("button", { name: "Off" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Link button" })).toHaveAttribute("href", "/x");
  });
});

describe("Field, Input, Textarea", () => {
  it("wires label, hint and required", () => {
    renderUi(
      <Field label="Project name" htmlFor="pn" hint="Shown on reports" required>
        <Input />
      </Field>,
    );
    const input = screen.getByLabelText(/Project name/);
    expect(input).toHaveAttribute("aria-required", "true");
    expect(input).toHaveAccessibleDescription("Shown on reports");
  });

  it("shows an error state", () => {
    renderUi(
      <Field label="Client PO" htmlFor="po" error="Client PO is required">
        <Input />
      </Field>,
    );
    const input = screen.getByLabelText("Client PO");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Client PO is required");
    expect(screen.getByRole("alert")).toHaveTextContent("Client PO is required");
  });

  it("supports disabled inputs and textareas", () => {
    renderUi(
      <>
        <Input aria-label="code" disabled defaultValue="PRJ-2026-0001" />
        <Textarea aria-label="notes" disabled />
      </>,
    );
    expect(screen.getByLabelText("code")).toBeDisabled();
    expect(screen.getByLabelText("notes")).toBeDisabled();
  });
});

describe("NumberInput", () => {
  function Harness(props: { min?: number; max?: number; precision?: number; disabled?: boolean }) {
    const [v, setV] = React.useState<number | null>(10);
    return (
      <>
        <NumberInput aria-label="qty" value={v} onValueChange={setV} unit="pcs" step={5} {...props} />
        <output data-testid="value">{String(v)}</output>
      </>
    );
  }

  it("shows the unit and steps with buttons and arrow keys", async () => {
    renderUi(<Harness />);
    expect(screen.getByText("pcs")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Increase" }));
    expect(screen.getByTestId("value")).toHaveTextContent("15");
    const input = screen.getByLabelText("qty");
    input.focus();
    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    expect(screen.getByTestId("value")).toHaveTextContent("5");
  });

  it("clamps typed values to min/max and rounds to precision", async () => {
    renderUi(<Harness min={0} max={100} precision={2} />);
    const input = screen.getByLabelText("qty");
    await userEvent.clear(input);
    await userEvent.type(input, "1,234.567{Enter}");
    expect(screen.getByTestId("value")).toHaveTextContent("100");
    await userEvent.clear(input);
    await userEvent.type(input, "3.14159{Enter}");
    expect(screen.getByTestId("value")).toHaveTextContent("3.14");
    expect(input).toHaveValue("3.14");
  });

  it("rejects non-numeric text and supports disabled", async () => {
    renderUi(<Harness disabled />);
    expect(screen.getByLabelText("qty")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Increase" })).toBeDisabled();
  });

  it("restores the last value on garbage input", async () => {
    renderUi(<Harness />);
    const input = screen.getByLabelText("qty");
    await userEvent.clear(input);
    await userEvent.type(input, "abc{Enter}");
    expect(screen.getByTestId("value")).toHaveTextContent("10");
    expect(input).toHaveValue("10");
  });
});

describe("Select", () => {
  it("opens, selects and respects disabled options", async () => {
    const onChange = vi.fn();
    renderUi(
      <Select
        aria-label="Category"
        value={undefined}
        onValueChange={onChange}
        options={[
          { value: "ic", label: "IC" },
          { value: "pcb", label: "PCB", disabled: true },
        ]}
      />,
    );
    const trigger = screen.getByRole("combobox", { name: "Category" });
    expect(trigger).toHaveTextContent("Select…");
    await userEvent.click(trigger);
    expect(screen.getByRole("option", { name: "PCB" })).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(screen.getByRole("option", { name: "IC" }));
    expect(onChange).toHaveBeenCalledWith("ic");
  });

  it("can be disabled", () => {
    renderUi(<Select aria-label="Category" value="ic" onValueChange={() => undefined} options={[{ value: "ic", label: "IC" }]} disabled />);
    expect(screen.getByRole("combobox", { name: "Category" })).toBeDisabled();
  });
});

describe("Combobox (async search)", () => {
  const options: ComboboxOption[] = [
    { value: "a", label: "STM32F407VGT6", description: "STMicroelectronics" },
    { value: "b", label: "TPS54331DR", description: "Texas Instruments" },
  ];

  it("searches through loadOptions with the typed query and selects", async () => {
    const load = vi.fn(async (q: string) => options.filter((o) => o.label.toLowerCase().includes(q.toLowerCase())));
    const onChange = vi.fn();
    renderUi(<Combobox aria-label="Part" value={null} onChange={onChange} loadOptions={load} debounceMs={0} />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(await screen.findByText("STM32F407VGT6")).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText("Search…"), "tps");
    await waitFor(() => expect(load).toHaveBeenLastCalledWith("tps", expect.any(AbortSignal)));
    await waitFor(() => expect(screen.queryByText("STM32F407VGT6")).not.toBeInTheDocument());
    await userEvent.click(screen.getByText("TPS54331DR"));
    expect(onChange).toHaveBeenCalledWith(options[1]);
  });

  it("shows the empty and error states", async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error("Server unreachable")).mockResolvedValue([]);
    renderUi(<Combobox aria-label="Part" value={null} onChange={() => undefined} loadOptions={load} debounceMs={0} />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Server unreachable");
    await userEvent.type(screen.getByPlaceholderText("Search…"), "x");
    expect(await screen.findByText("No matches")).toBeInTheDocument();
  });

  it("can be disabled", () => {
    renderUi(<Combobox value={null} onChange={() => undefined} loadOptions={async () => []} disabled />);
    expect(screen.getByRole("combobox")).toBeDisabled();
  });
});

describe("DatePicker", () => {
  function Harness() {
    const [d, setD] = React.useState<Date | null>(new Date(2026, 10, 30));
    return (
      <>
        <DatePicker aria-label="Due date" value={d} onChange={setD} />
        <output data-testid="iso">{d ? d.toDateString() : "none"}</output>
      </>
    );
  }

  it("formats, parses typed dates and clears", async () => {
    renderUi(<Harness />);
    const input = screen.getByLabelText("Due date");
    expect(input).toHaveValue("30 Nov 2026");
    await userEvent.clear(input);
    await userEvent.type(input, "2027-01-15{Enter}");
    expect(screen.getByTestId("iso")).toHaveTextContent("Fri Jan 15 2027");
    expect(input).toHaveValue("15 Jan 2027");
    await userEvent.clear(input);
    await userEvent.type(input, "not a date{Enter}");
    expect(input).toHaveValue("15 Jan 2027");
    await userEvent.clear(input);
    await userEvent.tab();
    expect(screen.getByTestId("iso")).toHaveTextContent("none");
  });

  it("picks from the calendar", async () => {
    renderUi(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "Open calendar" }));
    const grid = await screen.findByRole("grid");
    await userEvent.click(within(grid).getByText("12"));
    expect(screen.getByTestId("iso")).toHaveTextContent("Thu Nov 12 2026");
  });
});

describe("Checkbox and Switch", () => {
  it("toggle and support disabled", async () => {
    const onCheck = vi.fn();
    const onSwitch = vi.fn();
    renderUi(
      <>
        <Checkbox aria-label="DNP" onCheckedChange={onCheck} />
        <Checkbox aria-label="Locked" disabled />
        <Switch aria-label="Air-gap" onCheckedChange={onSwitch} />
        <Switch aria-label="Off" disabled />
      </>,
    );
    await userEvent.click(screen.getByRole("checkbox", { name: "DNP" }));
    await userEvent.click(screen.getByRole("switch", { name: "Air-gap" }));
    expect(onCheck).toHaveBeenCalledWith(true);
    expect(onSwitch).toHaveBeenCalledWith(true);
    expect(screen.getByRole("checkbox", { name: "Locked" })).toBeDisabled();
    expect(screen.getByRole("switch", { name: "Off" })).toBeDisabled();
  });

  it("renders the indeterminate state", () => {
    renderUi(<Checkbox aria-label="Some" checked="indeterminate" />);
    expect(screen.getByRole("checkbox", { name: "Some" })).toHaveAttribute("aria-checked", "mixed");
  });
});
