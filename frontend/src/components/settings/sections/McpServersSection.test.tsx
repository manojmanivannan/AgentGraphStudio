import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { McpServersSection } from "./McpServersSection";

const API = "http://localhost:8000/api";

const context7 = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Context7",
  url: "https://mcp.context7.com/mcp",
  credential_header: "Authorization",
  credential_set: true,
  credential_preview: "••••••••••••3456",
  url_warning: null,
  credential_value: undefined,
};

const localServer = {
  id: "22222222-2222-2222-2222-222222222222",
  name: "Local dev",
  url: "http://localhost:8000/mcp",
  credential_header: null,
  credential_set: false,
  credential_preview: null,
  url_warning: 'URL uses plain "http://". This is permitted (e.g. for localhost dev servers).',
};

function mockList(servers: unknown[]) {
  server.use(http.get(`${API}/mcp/servers`, () => HttpResponse.json({ servers })));
}

beforeEach(() => {
  mockList([]);
});

describe("McpServersSection", () => {
  it("lists the registered MCP servers with credential state", async () => {
    mockList([context7, localServer]);
    render(<McpServersSection />);

    const row = await screen.findByTestId("mcp-server-row-Context7");
    expect(row).toHaveTextContent("Context7");
    expect(row).toHaveTextContent("https://mcp.context7.com/mcp");
    expect(row).toHaveTextContent(/credential stored/i);
    expect(row).toHaveTextContent("••••••••••••3456");

    const localRow = screen.getByTestId("mcp-server-row-Local dev");
    expect(localRow).toHaveTextContent(/no credential/i);
  });

  it("shows the plain-http warning without blocking the server", async () => {
    mockList([localServer]);
    render(<McpServersSection />);
    const row = await screen.findByTestId("mcp-server-row-Local dev");
    expect(row.querySelector(".mcp-url-warning")).toHaveTextContent('plain "http://"');
  });

  it("shows an empty state when no servers are registered", async () => {
    render(<McpServersSection />);
    expect(await screen.findByText(/no mcp servers yet/i)).toBeInTheDocument();
  });

  it("creates a server end-to-end and refreshes the list", async () => {
    const user = userEvent.setup();
    const bodies: any[] = [];
    server.use(
      http.post(`${API}/mcp/servers`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...context7, name: "Fresh", id: "new-1" });
      }),
      http.get(`${API}/mcp/servers`, ({ request }) => {
        const url = new URL(request.url);
        void url;
        return HttpResponse.json({ servers: [{ ...context7, name: "Fresh", id: "new-1" }] });
      })
    );

    render(<McpServersSection />);
    await user.click(await screen.findByRole("button", { name: /add server/i }));
    await user.type(screen.getByLabelText(/^name$/i), "Fresh");
    await user.type(screen.getByLabelText(/^url$/i), "https://mcp.fresh.dev/mcp");
    await user.type(screen.getByLabelText(/credential value/i), "Bearer fresh-secret");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      name: "Fresh",
      url: "https://mcp.fresh.dev/mcp",
      credential_header: "Authorization",
      credential_value: "Bearer fresh-secret",
    });
    expect(await screen.findByTestId("mcp-server-row-Fresh")).toBeInTheDocument();
    expect(await screen.findByText(/mcp server saved/i)).toBeInTheDocument();
  });

  it("sends a null credential when the field is left blank on create", async () => {
    const user = userEvent.setup();
    const bodies: any[] = [];
    server.use(
      http.post(`${API}/mcp/servers`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(context7);
      })
    );

    render(<McpServersSection />);
    await user.click(await screen.findByRole("button", { name: /add server/i }));
    await user.type(screen.getByLabelText(/^name$/i), "NoCred");
    await user.type(screen.getByLabelText(/^url$/i), "https://a.example/mcp");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0].credential_value).toBeNull();
  });

  it("surfaces scheme-rejection errors from the backend", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${API}/mcp/servers`, () =>
        HttpResponse.json(
          { detail: 'Unsupported URL scheme "ftp" for an MCP server: only http:// and https:// endpoints are allowed.' },
          { status: 400 }
        )
      )
    );

    render(<McpServersSection />);
    await user.click(await screen.findByRole("button", { name: /add server/i }));
    await user.type(screen.getByLabelText(/^name$/i), "Bad");
    await user.type(screen.getByLabelText(/^url$/i), "ftp://example.com/mcp");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/scheme/i);
  });

  it("edits a server and keeps the stored credential when the field is blank", async () => {
    const user = userEvent.setup();
    const bodies: any[] = [];
    mockList([context7]);
    server.use(
      http.put(`${API}/mcp/servers/${context7.id}`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...context7, name: "Renamed" });
      }),
      http.get(`${API}/mcp/servers`, () =>
        HttpResponse.json({ servers: [{ ...context7, name: "Renamed" }] })
      )
    );

    render(<McpServersSection />);
    await user.click(await screen.findByRole("button", { name: /edit/i }));
    expect(screen.getByLabelText(/^url$/i)).toHaveValue("https://mcp.context7.com/mcp");
    // Masked state instead of the real credential.
    const credentialInput = screen.getByLabelText(/credential value/i);
    expect(credentialInput).toHaveValue("");
    expect(credentialInput).toHaveAttribute("placeholder", "••••••••");

    await user.clear(screen.getByLabelText(/^name$/i));
    await user.type(screen.getByLabelText(/^name$/i), "Renamed");
    await user.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({
      name: "Renamed",
      url: "https://mcp.context7.com/mcp",
      credential_header: "Authorization",
      credential_value: null,
    });
    expect(await screen.findByTestId("mcp-server-row-Renamed")).toBeInTheDocument();
  });

  it("clears the stored credential only via the explicit clear option", async () => {
    const user = userEvent.setup();
    const bodies: any[] = [];
    mockList([context7]);
    server.use(
      http.put(`${API}/mcp/servers/${context7.id}`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...context7, credential_set: false, credential_preview: null });
      })
    );

    render(<McpServersSection />);
    await user.click(await screen.findByRole("button", { name: /edit/i }));
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0].credential_value).toBeNull();

    await user.click(screen.getByRole("button", { name: /edit/i }));
    await user.click(screen.getByLabelText(/clear stored credential/i));
    await user.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1].credential_value).toBe("");
  });

  it("deletes a server and refreshes the list", async () => {
    const user = userEvent.setup();
    const deletes: string[] = [];
    let deleted = false;
    server.use(
      http.get(`${API}/mcp/servers`, () =>
        HttpResponse.json({ servers: deleted ? [] : [context7] })
      ),
      http.delete(`${API}/mcp/servers/${context7.id}`, () => {
        deletes.push(context7.id);
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      })
    );

    render(<McpServersSection />);
    await user.click(await screen.findByRole("button", { name: /delete/i }));
    await waitFor(() => expect(deletes).toEqual([context7.id]));
    await waitFor(() =>
      expect(screen.queryByTestId(`mcp-server-row-${context7.name}`)).not.toBeInTheDocument()
    );
  });
});