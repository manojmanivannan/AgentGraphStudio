import type { ProviderProfileId, ProviderSettingsForm } from "@/types";

export interface ProviderProfile {
  id: ProviderProfileId;
  label: string;
  description: string;
  /** Omitted for "custom", which keeps whatever is already in the form. */
  defaults?: Omit<ProviderSettingsForm, "profile">;
}

export const PROVIDER_PROFILES: ProviderProfile[] = [
  {
    id: "external_ollama",
    label: "Ollama (external)",
    description: "An Ollama server running on your host or LAN.",
    defaults: {
      llm_provider_type: "ollama",
      llm_base_url: "http://localhost:11434",
      llm_model: "ollama_chat/llama3.1",
      mem0_llm_model: "llama3.1",
      mem0_embedder_model: "nomic-embed-text:latest",
      mem0_embedder_dimensions: 768,
    },
  },
  {
    id: "docker_ollama",
    label: "Ollama (Docker)",
    description: "The bundled ollama service from docker-compose.",
    defaults: {
      llm_provider_type: "ollama",
      llm_base_url: "http://ollama:11434",
      llm_model: "ollama_chat/llama3.1",
      mem0_llm_model: "llama3.1",
      mem0_embedder_model: "nomic-embed-text:latest",
      mem0_embedder_dimensions: 768,
    },
  },
  {
    id: "openai",
    label: "OpenAI",
    description: "api.openai.com — requires an API key.",
    defaults: {
      llm_provider_type: "openai",
      llm_base_url: "https://api.openai.com/v1",
      llm_model: "gpt-4o-mini",
      mem0_llm_model: "gpt-4o-mini",
      mem0_embedder_model: "text-embedding-3-small",
      mem0_embedder_dimensions: 1536,
    },
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    description: "OpenAI-compatible gateway to many hosted models.",
    defaults: {
      llm_provider_type: "openai",
      llm_base_url: "https://openrouter.ai/api/v1",
      llm_model: "openrouter/google/gemma-3-27b-it:free",
      mem0_llm_model: "google/gemma-3-27b-it:free",
      mem0_embedder_model: "text-embedding-3-small",
      mem0_embedder_dimensions: 1536,
    },
  },
  {
    id: "custom",
    label: "Custom",
    description: "Any other OpenAI-compatible endpoint.",
  },
];

export function applyProfile(
  profile: ProviderProfileId,
  current: ProviderSettingsForm
): ProviderSettingsForm {
  const preset = PROVIDER_PROFILES.find((p) => p.id === profile);
  if (!preset?.defaults) return { ...current, profile };
  return { ...current, ...preset.defaults, profile };
}

/** Profiles whose endpoints are meaningless without a key. */
export function profileRequiresApiKey(profile: ProviderProfileId): boolean {
  return profile === "openai" || profile === "openrouter";
}
