"use client";

import { startTransition, useCallback, useEffect, useReducer, useRef, useState } from "react";

import { type AuditRequest, streamAudit } from "@medv/api-client";

import { auditReducer, initialAuditState } from "./audit-reducer";

export function useAuditStream() {
  const [state, dispatch] = useReducer(auditReducer, initialAuditState);
  const [elapsedMs, setElapsedMs] = useState(0);
  const controllerRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef<number | null>(null);

  const active = state.phase === "connecting" || state.phase === "streaming";

  useEffect(() => {
    if (!active || startedAtRef.current === null) return;
    const timer = window.setInterval(() => {
      setElapsedMs(performance.now() - (startedAtRef.current ?? performance.now()));
    }, 100);
    return () => window.clearInterval(timer);
  }, [active]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const start = useCallback(async (request: AuditRequest) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    startedAtRef.current = performance.now();
    setElapsedMs(0);
    dispatch({ type: "start" });
    let firstTokenSeen = false;

    try {
      await streamAudit(
        request,
        {
          onEvent(event) {
            if (event.event === "status" && event.message) {
              dispatch({
                type: "status",
                message: event.message,
                retries: event.retries ?? 0,
              });
              return;
            }

            if (event.event === "token" && event.text) {
              const ttftMs = firstTokenSeen
                ? undefined
                : performance.now() - (startedAtRef.current ?? performance.now());
              firstTokenSeen = true;
              startTransition(() => dispatch({ type: "token", text: event.text!, ttftMs }));
              return;
            }

            if (event.event === "done" && event.report) {
              dispatch({
                type: "done",
                report: event.report,
                retries: event.retries ?? 0,
              });
              return;
            }

            if (event.event === "error") {
              dispatch({ type: "error", message: event.error ?? "Audit stream failed." });
            }
          },
        },
        { signal: controller.signal },
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        dispatch({ type: "cancel" });
      } else {
        dispatch({
          type: "error",
          message: error instanceof Error ? error.message : "Unexpected audit failure.",
        });
      }
    } finally {
      setElapsedMs(performance.now() - (startedAtRef.current ?? performance.now()));
      if (controllerRef.current === controller) controllerRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => controllerRef.current?.abort(), []);
  const reset = useCallback(() => dispatch({ type: "reset" }), []);

  return { state, elapsedMs, active, start, cancel, reset };
}
