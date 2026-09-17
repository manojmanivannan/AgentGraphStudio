import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownMessage } from "./MarkdownMessage";

describe("MarkdownMessage", () => {
  it("renders bold markdown as <strong>", () => {
    render(<MarkdownMessage content="**Current weather:** 9.8°C" />);
    expect(screen.getByText("Current weather:").tagName).toBe("STRONG");
    expect(screen.getByText(/9\.8°C/)).toBeInTheDocument();
  });

  it("renders unordered lists as <ul>/<li>", () => {
    render(<MarkdownMessage content={"- floor(9.8) = 9\n- round(9.8) = 10"} />);
    expect(screen.getByRole("list")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/floor\(9\.8\) = 9/)).toBeInTheDocument();
  });

  it("renders ordered lists as <ol>/<li>", () => {
    render(<MarkdownMessage content={"1. first\n2. second"} />);
    expect(screen.getByRole("list").tagName).toBe("OL");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("renders headings", () => {
    render(<MarkdownMessage content="## For reference" />);
    expect(screen.getByRole("heading", { name: "For reference" })).toBeInTheDocument();
  });

  it("renders fenced code blocks as <pre><code>", () => {
    render(<MarkdownMessage content={"```python\nprint(9.8)\n```"} />);
    const code = screen.getByText(/print\(9\.8\)/);
    expect(code.tagName).toBe("CODE");
    expect(code.closest("pre")).toBeInTheDocument();
  });

  it("renders inline code", () => {
    render(<MarkdownMessage content="run `npm test` now" />);
    expect(screen.getByText("npm test").tagName).toBe("CODE");
  });

  it("renders GFM tables", () => {
    render(
      <MarkdownMessage
        content={"| City | Temp |\n| --- | --- |\n| Paris | 9.8 |"}
      />
    );
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "City" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Paris" })).toBeInTheDocument();
  });

  it("renders links with target=_blank and rel=noopener", () => {
    render(<MarkdownMessage content="[docs](https://example.com)" />);
    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("resolves relative image URLs against the API origin", () => {
    render(<MarkdownMessage content="![plot](/api/attachments/abc)" />);
    const img = screen.getByRole("img", { name: "plot" });
    expect(img).toHaveAttribute("src", "http://localhost:8000/api/attachments/abc");
  });

  it("leaves absolute image URLs untouched", () => {
    render(<MarkdownMessage content="![plot](https://cdn.example.com/x.png)" />);
    expect(screen.getByRole("img", { name: "plot" })).toHaveAttribute(
      "src",
      "https://cdn.example.com/x.png"
    );
  });

  it("escapes raw HTML instead of executing it", () => {
    render(<MarkdownMessage content={'<img src=x onerror="alert(1)">' } />);
    // react-markdown skips raw HTML by default — no <img> element is created.
    expect(document.querySelector("img[src='x']")).toBeNull();
  });

  it("renders plain text with newlines as separate paragraphs", () => {
    render(<MarkdownMessage content={"line one\n\nline two"} />);
    expect(screen.getByText("line one").tagName).toBe("P");
    expect(screen.getByText("line two").tagName).toBe("P");
  });

  it("renders nothing for empty content", () => {
    const { container } = render(<MarkdownMessage content="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("applies the small variant class for step messages", () => {
    render(<MarkdownMessage content="step detail" small />);
    expect(screen.getByText("step detail").closest(".chat-markdown--sm")).not.toBeNull();
  });
});