import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "@/test/mocks/server";
import { ProviderSection } from "./ProviderSection";

const API = "http://localhost:8000/api";

const savedSettings = {
  profile: "external_ollama",
  llm_provider_type: "ollama",
  llm_base_url: "http://localhost:11434",
  llm_model: "ollama_chat/llama3.1",
  mem0_embedder_model: "nomic-embed-text:latest",
  mem0_embedder_dimensions: 768,
  api_key_set: false,
  source: "database",
};

function renderSection() {
  return render(<ProviderSection />);
}

beforeEach(() => {
  server.use(
    http.get(`${API}/settings/provider`, () => HttpResponse.json(savedSettings))
  );
});

describe("ProviderSection", () => {
  it("loads the stored provider settings into the form", async () => {
    renderSection();
    expect(await screen.findByLabelText(/base url/i)).toHaveValue(
      "http://localhost:11434"
    );
    expect(screen.getByLabelText(/^chat model$/i)).toHaveValue("ollama_chat/llama3.1");
    expect(screen.getByLabelText(/embedding dimensions/i)).toHaveValue(768);
  });

  it("fills the form when a profile is selected", async () => {
    const user = userEvent.setup();
    renderSection();
    await screen.findByLabelText(/base url/i);

    await user.click(screen.getByRole("radio", { name: /^openai$/i }));

    expect(screen.getByLabelText(/base url/i)).toHaveValue(
      "https://api.openai.com/v1"
    );
    expect(screen.getByLabelText(/embedding dimensions/i)).toHaveValue(1536);
  });

  it("shows a per-check result for the connection test", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${API}/settings/provider/test`, () =>
        HttpResponse.json({
          ok: false,
          checks: [
            { name: "chat", ok: true, detail: "OK", latency_ms: 120 },
            {
              name: "embedding",
              ok: false,
              detail: "404 Not Found",
              latency_ms: 30,
            },
          ],
        })
      )
    );

    renderSection();
    await screen.findByLabelText(/base url/i);
    await user.click(screen.getByRole("button", { name: /test connection/i }));

    const results = await screen.findByLabelText(/connection test results/i);
    expect(results).toHaveTextContent(/chat model/i);
    expect(results).toHaveTextContent(/404 Not Found/i);
  });

  it("saves without confirmation when the embedding dimension is unchanged", async () => {
    const user = userEvent.setup();
    const bodies: any[] = [];
    server.use(
      http.put(`${API}/settings/provider`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(savedSettings);
      })
    );

    renderSection();
    await screen.findByLabelText(/base url/i);
    await user.clear(screen.getByLabelText(/^chat model$/i));
    await user.type(screen.getByLabelText(/^chat model$/i), "ollama_chat/qwen3");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0].llm_model).toBe("ollama_chat/qwen3");
    expect(bodies[0].confirm_reindex).toBe(false);
    expect(bodies[0].api_key).toBeNull();
    expect(await screen.findByText(/provider settings saved/i)).toBeInTheDocument();
  });

  it("requires confirmation before saving a changed embedding dimension", async () => {
    const user = userEvent.setup();
    const bodies: any[] = [];
    server.use(
      http.put(`${API}/settings/provider`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...savedSettings, mem0_embedder_dimensions: 1536 });
      })
    );

    renderSection();
    await screen.findByLabelText(/base url/i);
    await user.click(screen.getByRole("radio", { name: /^openai$/i }));
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    const dialog = await screen.findByRole("dialog", {
      name: /clear stored embeddings/i,
    });
    expect(dialog).toHaveTextContent(/768/);
    expect(dialog).toHaveTextContent(/1536/);
    expect(bodies).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: /clear and save/i }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0].confirm_reindex).toBe(true);
  });

  it("sends the typed API key and keeps the stored one when left blank", async () => {
    const user = userEvent.setup();
    const bodies: any[] = [];
    server.use(
      http.get(`${API}/settings/provider`, () =>
        HttpResponse.json({ ...savedSettings, api_key_set: true })
      ),
      http.put(`${API}/settings/provider`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ ...savedSettings, api_key_set: true });
      })
    );

    renderSection();
    await screen.findByLabelText(/base url/i);
    await user.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0].api_key).toBeNull();

    await user.type(screen.getByLabelText(/^api key$/i), "sk-new");
    await user.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1].api_key).toBe("sk-new");
  });
});