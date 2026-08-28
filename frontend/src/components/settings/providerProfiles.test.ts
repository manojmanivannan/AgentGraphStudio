import { describe, expect, it } from "vitest";
import { PROVIDER_PROFILES, applyProfile, profileRequiresApiKey } from "./providerProfiles";
import type { ProviderSettingsForm } from "@/types";

const current: ProviderSettingsForm = {
  profile: "custom",
  llm_provider_type: "ollama",
  llm_base_url: "http://old",
  llm_model: "old-model",
  mem0_embedder_model: "old-embed",
  mem0_embedder_dimensions: 512,
};

describe("providerProfiles", () => {
  it("exposes the five documented profiles", () => {
    expect(PROVIDER_PROFILES.map((p) => p.id)).toEqual([
      "external_ollama",
      "docker_ollama",
      "openai",
      "openrouter",
      "custom",
    ]);
  });

  it("applies OpenAI defaults including its embedding dimension", () => {
    const next = applyProfile("openai", current);
    expect(next.profile).toBe("openai");
    expect(next.llm_base_url).toBe("https://api.openai.com/v1");
    expect(next.llm_provider_type).toBe("openai");
    expect(next.mem0_embedder_dimensions).toBe(1536);
  });

  it("points the docker profile at the compose service host", () => {
    expect(applyProfile("docker_ollama", current).llm_base_url).toBe(
      "http://ollama:11434"
    );
  });

  it("keeps existing values when switching to custom", () => {
    const next = applyProfile("custom", current);
    expect(next).toEqual({ ...current, profile: "custom" });
  });

  it("marks hosted providers as requiring an API key", () => {
    expect(profileRequiresApiKey("openai")).toBe(true);
    expect(profileRequiresApiKey("openrouter")).toBe(true);
    expect(profileRequiresApiKey("external_ollama")).toBe(false);
  });
});
