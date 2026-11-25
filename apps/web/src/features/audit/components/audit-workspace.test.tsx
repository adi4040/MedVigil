import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AuditWorkspace } from "./audit-workspace";

afterEach(() => {
  cleanup();
});

describe("AuditWorkspace", () => {
  it("renders the synthetic case without placing report HTML into the document", () => {
    render(<AuditWorkspace />);

    expect(screen.getByRole("heading", { name: /test the record/i })).toBeInTheDocument();
    expect((screen.getByLabelText("Clinical note") as HTMLTextAreaElement).value).toContain(
      "lower-back pain for eight weeks",
    );
    expect(screen.getByRole("button", { name: /start clinical audit/i })).toBeEnabled();
    expect(screen.getByText(/evidence before inference/i)).toBeInTheDocument();
  });

  it("switches to Stage 2 Renal Safety Auditor from the sidebar", () => {
    render(<AuditWorkspace />);

    const stage2Button = screen.getByRole("button", { name: /renal safety auditor/i });
    fireEvent.click(stage2Button);

    expect(screen.getByRole("heading", { name: /verify renal dosing safety/i })).toBeInTheDocument();
    expect(screen.getByLabelText("Discharge JSON")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run renal safety audit/i })).toBeEnabled();
    expect(screen.getByText(/renal audit report/i)).toBeInTheDocument();
  });

  it("collapses and expands the desktop sidebar as a vertical icon rail", () => {
    render(<AuditWorkspace />);

    const collapseBtn = screen.getByRole("button", { name: /collapse sidebar/i });
    fireEvent.click(collapseBtn);

    const sidebar = screen.getByRole("complementary", { name: /primary sidebar/i });
    expect(sidebar.className).toContain("lg:w-16");

    const expandBtn = screen.getByRole("button", { name: /expand sidebar/i });
    fireEvent.click(expandBtn);
    expect(sidebar.className).toContain("lg:w-72");
  });
});
