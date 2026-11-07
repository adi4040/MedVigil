import { afterEach, describe, expect, it, vi } from "vitest";

import { streamAudit, type StreamChunk } from "@medv/api-client";

const request = {
  clinical_note: "Back pain for eight weeks.",
  policy_rubric: "RUBRIC ID: TEST\n1. Symptoms and Duration",
  temperature: 0,
};

function streamingResponse(parts: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const part of parts) controller.enqueue(encoder.encode(part));
        controller.close();
      },
    }),
    {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    },
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("streamAudit", () => {
  it("parses SSE frames split across arbitrary response chunks", async () => {
    const status = 'event: status\ndata: {"event":"status","message":"Evaluating","retries":0}\n\n';
    const done =
      'event: done\ndata: {"event":"done","report":{"rubric_id":"TEST","evaluations":[],"missing_or_unclear_summary":[]},"retries":0}\n\n';
    const wire = status + done;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(streamingResponse([wire.slice(0, 17), wire.slice(17, 61), wire.slice(61)])),
    );
    const events: StreamChunk[] = [];

    await streamAudit(request, { onEvent: (event) => events.push(event) });

    expect(events.map((event) => event.event)).toEqual(["status", "done"]);
    expect(events[1]?.report?.rubric_id).toBe("TEST");
  });

  it("rejects a stream that closes without a terminal event", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        streamingResponse(['event: token\ndata: {"event":"token","text":"partial"}\n\n']),
      ),
    );

    await expect(streamAudit(request, { onEvent: () => undefined })).rejects.toThrow(
      "ended before a final report",
    );
  });
});
