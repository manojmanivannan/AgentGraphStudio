/**
 * Mock for @monaco-editor/react.
 * Renders a <textarea> in jsdom so ToolEditor tests work without WebGL/Canvas.
 * Usage in test files: vi.mock('@monaco-editor/react', () => import('@/test/mocks/monaco'))
 */
import React from "react";

interface MockEditorProps {
  value?: string;
  onChange?: (value: string | undefined) => void;
  height?: string | number;
  defaultLanguage?: string;
  options?: Record<string, unknown>;
  theme?: string;
  wrapperProps?: Record<string, unknown>;
  [key: string]: unknown;
}

function MockMonacoEditor({ value, onChange }: MockEditorProps) {
  return React.createElement("textarea", {
    "data-testid": "tool-code-editor",
    value: value ?? "",
    onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) =>
      onChange?.(e.target.value),
  });
}

export default MockMonacoEditor;
