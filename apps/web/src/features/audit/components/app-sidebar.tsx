"use client";

import { Badge, Button, Separator } from "@medv/ui";
import {
  Activity,
  ExternalLink,
  FileSearch,
  FlaskConical,
  PanelLeftClose,
  PanelLeftOpen,
  Send,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";

interface AppSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  activeStage?: string;
  onSelectStage?: (stageId: string) => void;
}

export function AppSidebar({
  isOpen,
  onClose,
  isCollapsed = false,
  onToggleCollapse,
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
        aria-label="Primary sidebar"
        className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r border-border bg-card transition-all duration-200 ease-in-out lg:static lg:translate-x-0 ${
          isOpen ? "translate-x-0 w-72" : "-translate-x-full w-72"
        } ${isCollapsed ? "lg:w-16" : "lg:w-72"}`}
      >
        {/* Brand header */}
        <div
          className={`flex h-16 shrink-0 items-center border-b border-border ${
            isCollapsed ? "lg:justify-center lg:px-2 px-5 justify-between" : "justify-between px-5"
          }`}
        >
          <div className="flex items-center gap-3 min-w-0">
            {!isCollapsed && (
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-xs">
                <ShieldCheck className="h-5 w-5" />
              </div>
            )}
            <div className={`min-w-0 ${isCollapsed ? "lg:hidden" : ""}`}>
              <span className="text-base font-bold tracking-tight text-foreground">MedVigil</span>
              <p className="text-[11px] font-medium text-muted-foreground leading-none truncate">
                Clinical AI Platform
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            {onToggleCollapse && (
              <Button
                variant="ghost"
                size="icon"
                className="hidden lg:inline-flex h-8 w-8"
                onClick={onToggleCollapse}
                aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {isCollapsed ? (
                  <PanelLeftOpen className="h-4 w-4" />
                ) : (
                  <PanelLeftClose className="h-4 w-4" />
                )}
              </Button>
            )}
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
        </div>

        {/* Navigation list */}
        <div className={`flex-1 overflow-y-auto py-5 space-y-6 ${isCollapsed ? "lg:px-2 px-4" : "px-4"}`}>
          <div>
            <p
              className={`px-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground ${
                isCollapsed ? "lg:hidden" : ""
              }`}
            >
              Clinical Pipelines
            </p>
            <div className="mt-2 space-y-1.5">
              {/* Medical Gap Analyzer */}
              <button
                type="button"
                title="Medical Gap Analyzer"
                aria-label="Medical Gap Analyzer"
                onClick={() => {
                  onSelectStage?.("stage-1");
                  onClose();
                }}
                className={`w-full flex items-center gap-3 rounded-xl p-2.5 text-left transition-all ${
                  isCollapsed ? "lg:justify-center lg:p-2" : ""
                } ${
                  activeStage === "stage-1"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "hover:bg-muted text-foreground"
                }`}
              >
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                    activeStage === "stage-1"
                      ? "bg-primary-foreground/20 text-primary-foreground"
                      : "bg-muted text-primary"
                  }`}
                >
                  <FileSearch className="h-4 w-4" />
                </div>
                <span className={`flex-1 min-w-0 font-semibold text-sm leading-tight truncate ${isCollapsed ? "lg:hidden" : ""}`}>
                  Medical Gap Analyzer
                </span>
              </button>

              {/* Renal Safety Auditor */}
              <button
                type="button"
                title="Renal Safety Auditor"
                aria-label="Renal Safety Auditor"
                onClick={() => {
                  onSelectStage?.("stage-2");
                  onClose();
                }}
                className={`w-full flex items-center gap-3 rounded-xl p-2.5 text-left transition-all ${
                  isCollapsed ? "lg:justify-center lg:p-2" : ""
                } ${
                  activeStage === "stage-2"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "hover:bg-muted text-foreground"
                }`}
              >
                <div
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                    activeStage === "stage-2"
                      ? "bg-primary-foreground/20 text-primary-foreground"
                      : "bg-muted text-primary"
                  }`}
                >
                  <FlaskConical className="h-4 w-4" />
                </div>
                <span className={`flex-1 min-w-0 font-semibold text-sm leading-tight truncate ${isCollapsed ? "lg:hidden" : ""}`}>
                  Renal Safety Auditor
                </span>
              </button>

              {/* Appeal Letter Drafter - Upcoming */}
              <div
                title="Appeal Letter Drafter (Soon)"
                aria-label="Appeal Letter Drafter (Soon)"
                className={`w-full flex items-center gap-3 rounded-xl p-2.5 text-left opacity-55 cursor-not-allowed ${
                  isCollapsed ? "lg:justify-center lg:p-2" : ""
                }`}
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                  <Send className="h-4 w-4" />
                </div>
                <div className={`flex-1 min-w-0 flex items-center justify-between gap-2 ${isCollapsed ? "lg:hidden" : ""}`}>
                  <span className="font-semibold text-sm leading-tight text-muted-foreground truncate">
                    Appeal Letter Drafter
                  </span>
                  <Badge variant="outline" className="text-[9px] px-1.5 py-0 text-muted-foreground shrink-0">
                    Soon
                  </Badge>
                </div>
              </div>
            </div>
          </div>

          <Separator />

          <div>
            <p
              className={`px-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground ${
                isCollapsed ? "lg:hidden" : ""
              }`}
            >
              Developer & Engine
            </p>
            <div className="mt-2 space-y-1">
              <a
                href="/docs"
                target="_blank"
                rel="noreferrer"
                title="API Documentation"
                aria-label="API Documentation"
                className={`flex items-center rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors ${
                  isCollapsed ? "lg:justify-center lg:px-2" : "justify-between"
                }`}
              >
                <span className="flex items-center gap-2">
                  <Activity className="h-3.5 w-3.5 shrink-0" />
                  <span className={isCollapsed ? "lg:hidden" : ""}>API Documentation</span>
                </span>
                <ExternalLink className={`h-3 w-3 opacity-60 ${isCollapsed ? "lg:hidden" : ""}`} />
              </a>
              <div
                title="Provider Mode: Active"
                className={`flex items-center rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground ${
                  isCollapsed ? "lg:justify-center lg:px-2" : "justify-between"
                }`}
              >
                <span className="flex items-center gap-2">
                  <Sparkles className="h-3.5 w-3.5 shrink-0" />
                  <span className={isCollapsed ? "lg:hidden" : ""}>Provider Mode</span>
                </span>
                <span className={`font-mono text-[11px] text-foreground ${isCollapsed ? "lg:hidden" : ""}`}>
                  Active
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Footer status */}
        <div
          className={`border-t border-border bg-muted/20 p-4 space-y-2 shrink-0 ${
            isCollapsed ? "lg:flex lg:justify-center lg:p-3" : ""
          }`}
        >
          <div className="flex items-center justify-between text-xs">
            <span className={`text-muted-foreground font-medium ${isCollapsed ? "lg:hidden" : ""}`}>
              FastAPI Engine
            </span>
            <Badge
              variant="outline"
              title="FastAPI Engine: Connected"
              className={`gap-1 border-emerald-500/30 bg-emerald-500/10 text-emerald-700 text-[10px] py-0.5 ${
                isCollapsed ? "lg:px-1.5" : ""
              }`}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className={isCollapsed ? "lg:hidden" : ""}>Connected</span>
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
