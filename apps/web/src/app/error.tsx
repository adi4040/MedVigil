"use client";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@medv/ui";
import { AlertCircle, RotateCcw } from "lucide-react";

export default function GlobalError({ reset }: { reset: () => void }) {
  return (
    <main className="grid min-h-screen place-items-center bg-background px-6">
      <Card className="max-w-md border-border shadow-md">
        <CardHeader className="text-center pb-2">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive mb-3">
            <AlertCircle className="h-6 w-6" />
          </div>
          <CardTitle className="text-2xl font-bold">Application Error</CardTitle>
          <CardDescription className="text-sm text-muted-foreground mt-1">
            The clinical audit workspace encountered an unexpected issue and could not be loaded.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-4 flex justify-center">
          <Button onClick={reset} type="button" className="w-full sm:w-auto font-medium">
            <RotateCcw className="mr-2 h-4 w-4" />
            Try again
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
