import { createParser } from "eventsource-parser";

import {
  type AuditRequest,
  type StreamChunk,
  streamChunkSchema,
} from "./schemas";

export class AuditHttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AuditHttpError";
  }
}

export interface AuditStreamHandlers {
  onEvent: (event: StreamChunk) => void;
}

export interface AuditStreamOptions {
  endpoint?: string;
  signal?: AbortSignal;
}

function parseErrorBody(body: string, fallback: string): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return "The audit request is invalid.";
  } catch {
    // Fall through to the status-based message.
  }
  return fallback;
}

export async function streamAudit(
  request: AuditRequest,
  handlers: AuditStreamHandlers,
  options: AuditStreamOptions = {},
): Promise<void> {
  const response = await fetch(
    options.endpoint ?? "/api/v1/audit/evaluate/stream",
    {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
      cache: "no-store",
      signal: options.signal,
    },
  );

  if (!response.ok) {
    const body = await response.text();
    throw new AuditHttpError(
      parseErrorBody(body, `Audit request failed with HTTP ${response.status}.`),
      response.status,
    );
  }

  if (!response.headers.get("content-type")?.includes("text/event-stream")) {
    throw new Error("The audit service returned a non-streaming response.");
  }

  if (!response.body) {
    throw new Error("The audit service returned an empty response body.");
  }

  let terminalEventReceived = false;
  const parser = createParser({
    onEvent(message) {
      const raw = JSON.parse(message.data) as unknown;
      const event = streamChunkSchema.parse(raw);

      if (message.event && message.event !== event.event) {
        throw new Error("SSE event name does not match its JSON payload.");
      }

      if (event.event === "done" || event.event === "error") {
        terminalEventReceived = true;
      }
      handlers.onEvent(event);
    },
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
    parser.feed(decoder.decode());
  } finally {
    reader.releaseLock();
  }

  if (!terminalEventReceived) {
    throw new Error("The audit stream ended before a final report was received.");
  }
}
