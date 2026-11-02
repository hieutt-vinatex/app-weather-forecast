import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GitHubOperationsLinks } from "./GitHubOperationsLinks";

describe("GitHubOperationsLinks", () => {
  it("moves both administrative operations to safe GitHub workflow links", () => {
    render(<GitHubOperationsLinks />);

    const region = screen.getByRole("region", {
      name: "Quản trị qua GitHub Actions",
    });
    expect(within(region).queryByRole("textbox")).not.toBeInTheDocument();
    expect(within(region).queryByRole("button")).not.toBeInTheDocument();

    const refresh = within(region).getByRole("link", {
      name: "Làm mới dữ liệu",
    });
    const telegram = within(region).getByRole("link", {
      name: "Gửi Telegram ngay",
    });
    expect(refresh).toHaveAttribute(
      "href",
      "https://github.com/hieutt-vinatex/app-weather-forecast/actions/workflows/data-sync.yml",
    );
    expect(telegram).toHaveAttribute(
      "href",
      "https://github.com/hieutt-vinatex/app-weather-forecast/actions/workflows/telegram.yml",
    );
    expect(refresh).toHaveAttribute("rel", "noreferrer");
    expect(telegram).toHaveAttribute("rel", "noreferrer");
  });
});
