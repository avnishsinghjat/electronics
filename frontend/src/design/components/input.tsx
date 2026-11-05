import * as React from "react";

import { cn } from "@/lib/utils";

import { controlClasses, useFieldControl } from "./field";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...rest }, ref) => {
    const props = useFieldControl(rest);
    return <input ref={ref} type={type} className={cn(controlClasses, "h-9", className)} {...props} />;
  },
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, rows = 4, ...rest }, ref) => {
  const props = useFieldControl(rest);
  return <textarea ref={ref} rows={rows} className={cn(controlClasses, "min-h-[72px] py-2 leading-5", className)} {...props} />;
});
Textarea.displayName = "Textarea";
