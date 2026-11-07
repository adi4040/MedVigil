import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AuditWorkspace } from "./audit-workspace";

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
});
