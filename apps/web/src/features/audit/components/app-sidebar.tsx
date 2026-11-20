"use client";

import { Badge, Button, Separator } from "@medv/ui";
import {
  Activity,
  ExternalLink,
  FileSearch,
  FileText,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";

interface AppSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  activeStage?: string;
  onSelectStage?: (stageId: string) => void;
}

export function AppSidebar({
  isOpen,
  onClose,
  activeStage = "stage-1",
  onSelectStage,
}: AppSidebarProps) {
  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-xs lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar container */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border bg-card transition-transform duration-200 ease-in-out lg:static lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand header */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-xs">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <span className="text-base font-bold tracking-tight text-foreground">MedVigil</span>
              <p className="text-[11px] font-medium text-muted-foreground leading-none">
                Clinical AI Platform
              </p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden h-8 w-8"
            onClick={onClose}
            aria-label="Close sidebar"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Navigation list */}
        <div className="flex-1 overflow-y-auto px-4 py-5 space-y-6">
          <div>
            <p className="px-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              Clinical Pipelines
            </p>
            <div className="mt-2 space-y-1.5">
              {/* STAGE 1 BUTTON */}
              <button
                type="button"
                onClick={() => {
                  onSelectStage?.("stage-1");
                  onClose();
                }}
                className={`w-full flex items-start gap-3 rounded-xl p-3 text-left transition-all ${
                  activeStage === "stage-1"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "hover:bg-muted text-foreground"
                }`}
              >
                <div
                  className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                    activeStage === "stage-1"
                      ? "bg-primary-foreground/20 text-primary-foreground"
                      : "bg-muted text-primary"
                  }`}
                >
                  <FileSearch className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-wider opacity-80">
                      Stage 1
                    </span>
                    <Badge
                      variant="outline"
                      className={`text-[10px] px-1.5 py-0 font-medium ${
                        activeStage === "stage-1"
                          ? "border-primary-foreground/30 text-primary-foreground bg-primary-foreground/10"
                          : ""
                      }`}
                    >
                      Active
                    </Badge>
                  </div>
                  <p className="font-semibold text-sm leading-tight mt-0.5">
                    Medical Gap Analyzer
                  </p>
                  <p className="text-[11px] opacity-75 line-clamp-1 mt-0.5">
                    Rubric audit & evidence extraction
                  </p>
                </div>
              </button>

              {/* Stage 2 - Upcoming */}
              <div className="w-full flex items-start gap-3 rounded-xl p-3 text-left opacity-55 cursor-not-allowed">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <FileText className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                      Stage 2
                    </span>
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 text-muted-foreground">
                      Soon
                    </Badge>
                  </div>
                  <p className="font-semibold text-sm leading-tight mt-0.5 text-muted-foreground">
                    Prior-Auth Drafter
                  </p>
                  <p className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">
                    Automated clinical packet generation
                  </p>
                </div>
              </div>

              {/* Stage 3 - Upcoming */}
              <div className="w-full flex items-start gap-3 rounded-xl p-3 text-left opacity-55 cursor-not-allowed">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <Send className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                      Stage 3
                    </span>
                    <Badge variant="outline" className="text-[9px] px-1.5 py-0 text-muted-foreground">
                      Soon
                    </Badge>
                  </div>
                  <p className="font-semibold text-sm leading-tight mt-0.5 text-muted-foreground">
                    Appeal Letter Drafter
                  </p>
                  <p className="text-[11px] text-muted-foreground line-clamp-1 mt-0.5">
                    Denial reversal rationale builder
                  </p>
                </div>
              </div>
            </div>
          </div>

          <Separator />

          <div>
            <p className="px-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
              Developer & Engine
            </p>
            <div className="mt-2 space-y-1">
              <a
                href="/docs"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
              >
                <span className="flex items-center gap-2">
                  <Activity className="h-3.5 w-3.5" />
                  API Documentation
                </span>
                <ExternalLink className="h-3 w-3 opacity-60" />
              </a>
              <div className="flex items-center justify-between rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground">
                <span className="flex items-center gap-2">
                  <Sparkles className="h-3.5 w-3.5" />
                  Provider Mode
                </span>
                <span className="font-mono text-[11px] text-foreground">Active</span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer status */}
        <div className="border-t border-border bg-muted/20 p-4 space-y-2 shrink-0">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground font-medium">FastAPI Engine</span>
            <Badge
              variant="outline"
              className="gap-1 border-emerald-500/30 bg-emerald-500/10 text-emerald-700 text-[10px] py-0.5"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Connected
            </Badge>
          </div>
          <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono">
            <span>Version</span>
            <span>v0.1.0</span>
          </div>
        </div>
      </aside>
    </>
  );
}
