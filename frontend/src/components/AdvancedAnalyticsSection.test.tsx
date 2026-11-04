import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PrizeScope } from "../types/gdb";
import { makeSnapshot } from "../test/fixtures";
import { AdvancedAnalyticsSection } from "./AdvancedAnalyticsSection";

vi.mock("./charts/GapChart", () => ({
  GapChart: ({ scope }: { scope: PrizeScope }) => (
    <div role="img" aria-label={`Gap ${scope}`} />
  ),
}));

vi.mock("./charts/HistoryScatterChart", () => ({
  HistoryScatterChart: ({ scope }: { scope: PrizeScope }) => (
    <div role="img" aria-label={`Scatter ${scope}`} />
  ),
}));

vi.mock("./charts/TransitionMatrixChart", () => ({
  TransitionMatrixChart: ({ scope }: { scope: PrizeScope }) => (
    <div role="img" aria-label={`Transition ${scope}`} />
  ),
}));

describe("AdvancedAnalyticsSection", () => {
  it("initially keeps every advanced chart unmounted", () => {
    render(
      <AdvancedAnalyticsSection
        records={makeSnapshot(30, 1).data}
        scope="all"
        scopeLabel="Tất cả giải"
        theme="light"
      />,
    );

    const button = screen.getByRole("button", { name: "Mở phân tích" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls");
    expect(screen.getByRole("heading", { name: "Phân tích nâng cao · Tất cả giải" }))
      .toBeInTheDocument();
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });

  it("opens and closes all three charts", async () => {
    const user = userEvent.setup();
    render(
      <AdvancedAnalyticsSection
        records={makeSnapshot(30, 1).data}
        scope="all"
        scopeLabel="Tất cả giải"
        theme="light"
      />,
    );

    await user.click(screen.getByRole("button", { name: "Mở phân tích" }));

    expect(screen.getAllByRole("img").map((item) => item.getAttribute("aria-label")))
      .toEqual(["Gap all", "Scatter all", "Transition all"]);
    expect(screen.getByRole("button", { name: "Đóng phân tích" }))
      .toHaveAttribute("aria-expanded", "true");

    await user.click(screen.getByRole("button", { name: "Đóng phân tích" }));
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });

  it("updates every open chart when scope changes", async () => {
    const user = userEvent.setup();
    const records = makeSnapshot(30, 1).data;
    const { rerender } = render(
      <AdvancedAnalyticsSection
        records={records}
        scope="all"
        scopeLabel="Tất cả giải"
        theme="light"
      />,
    );
    await user.click(screen.getByRole("button", { name: "Mở phân tích" }));

    rerender(
      <AdvancedAnalyticsSection
        records={records}
        scope="g7"
        scopeLabel="Giải bảy"
        theme="light"
      />,
    );

    expect(screen.getByRole("heading", { name: "Phân tích nâng cao · Giải bảy" }))
      .toBeInTheDocument();
    expect(screen.getAllByRole("img").map((item) => item.getAttribute("aria-label")))
      .toEqual(["Gap g7", "Scatter g7", "Transition g7"]);
    expect(screen.queryByLabelText(/ all$/)).not.toBeInTheDocument();
  });
});
