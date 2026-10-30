import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { AdminOperations } from "./AdminOperations";
import { StaleWarning } from "./Alerts";
import { HistoryTable } from "./HistoryTable";
import { StatusBadge } from "./StatusBadge";
import { DashboardHeader } from "../features/dashboard/DashboardHeader";
import { makeSnapshot } from "../test/fixtures";

const operationMocks = vi.hoisted(() => ({
  manual: {
    refresh: vi.fn(async (_token: string) => undefined),
    status: "idle",
    isRefreshing: false,
    isError: false,
    message: null as string | null,
  },
  telegram: {
    send: vi.fn(async (_token: string) => undefined),
    status: "idle",
    isSending: false,
    isError: false,
    message: null as string | null,
  },
}));

vi.mock("../hooks/useManualRefresh", () => ({
  useManualRefresh: () => operationMocks.manual,
}));

vi.mock("../hooks/useSendAbsenceNotification", () => ({
  useSendAbsenceNotification: () => operationMocks.telegram,
}));

describe("AdminOperations", () => {
  beforeEach(() => {
    operationMocks.manual.refresh.mockClear();
    operationMocks.telegram.send.mockClear();
    Object.assign(operationMocks.manual, {
      status: "idle",
      isRefreshing: false,
      isError: false,
      message: null,
    });
    Object.assign(operationMocks.telegram, {
      status: "idle",
      isSending: false,
      isError: false,
      message: null,
    });
  });

  it("owns one in-memory token for both cloud operations without persisting it", async () => {
    const user = userEvent.setup();
    const storageSpy = vi.spyOn(Storage.prototype, "setItem");
    const { unmount } = render(<AdminOperations />);

    const token = screen.getByLabelText("Khóa quản trị");
    await user.type(token, "  admin-secret  ");
    await user.click(screen.getByRole("button", { name: "Làm mới dữ liệu" }));
    await user.click(screen.getByRole("button", { name: "Gửi Telegram ngay" }));

    expect(operationMocks.manual.refresh).toHaveBeenCalledWith("admin-secret");
    expect(operationMocks.telegram.send).toHaveBeenCalledWith("admin-secret");
    expect(storageSpy).not.toHaveBeenCalled();
    expect(screen.getByText(/gửi lại sẽ tạo thêm một tin nhắn Telegram/i)).toBeInTheDocument();

    unmount();
    render(<AdminOperations />);
    expect(screen.getByLabelText("Khóa quản trị")).toHaveValue("");
  });

  it.each([
    ["queued", "Đã xếp hàng"],
    ["running", "Đang chạy trên cloud"],
    ["succeeded", "Đã hoàn tất"],
    ["failed", "Thất bại"],
  ])("shows the %s operation state", (status, label) => {
    Object.assign(operationMocks.manual, {
      status,
      isRefreshing: status === "queued" || status === "running",
      isError: status === "failed",
      message: status === "failed" ? "Khóa quản trị không đúng." : "Thông báo an toàn",
    });
    render(<AdminOperations />);
    expect(screen.getByText(label)).toBeInTheDocument();
    if (status === "failed") {
      expect(screen.getByText("Khóa quản trị không đúng.")).toBeInTheDocument();
    }
  });
});

describe("cloud freshness UI", () => {
  it("uses the approved text labels instead of realtime connection copy", () => {
    const { rerender } = render(<StatusBadge status="current" />);
    expect(screen.getByText("Dữ liệu hiện tại")).toBeInTheDocument();
    expect(screen.queryByText("Trực tuyến")).not.toBeInTheDocument();

    rerender(<StatusBadge status="delayed" />);
    expect(screen.getByText("Chậm cập nhật")).toBeInTheDocument();
  });

  it("shows the generated timestamp and latest source date", () => {
    const snapshot = makeSnapshot(30, 1);
    snapshot.meta.generatedAt = "2026-10-29T11:25:02Z";
    render(
      <DashboardHeader
        meta={snapshot.meta}
        freshness="current"
        sourceReferenceDate="2026-10-29"
        days={30}
        onDaysChange={vi.fn()}
      />,
    );

    expect(screen.getByText("Cập nhật lúc").parentElement).toHaveTextContent("29/10/2026");
    expect(screen.getByText("Kỳ dữ liệu gần nhất").parentElement).toHaveTextContent(
      "29/10/2026",
    );
  });

  it("keeps yesterday's stored history visible while current sync is delayed", () => {
    const snapshot = makeSnapshot(30, 1);
    snapshot.meta.freshnessStatus = "delayed";
    const yesterday = snapshot.data[0]!;
    snapshot.data[0] = {
      ...yesterday,
      date: "2026-10-29",
      dateLabel: "29-10",
      dayName: "Thứ Năm",
    };

    render(
      <>
        <StaleWarning meta={snapshot.meta} />
        <HistoryTable records={snapshot.data} scope="all" />
      </>,
    );

    expect(screen.getByText(/chậm cập nhật/i)).toBeInTheDocument();
    expect(screen.getByText(/29\/10\/2026/)).toBeInTheDocument();
  });
});
