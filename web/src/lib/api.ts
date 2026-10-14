export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

// Mirrors optiagent_api.routers.system.SystemStatus
export interface OllamaStatus {
  reachable: boolean;
  base_url: string;
  models: string[];
  configured_model: string;
  configured_model_available: boolean;
  error: string | null;
}

export interface ServiceStatus {
  name: string;
  reachable: boolean;
  detail: string | null;
}

export interface SystemStatus {
  version: string;
  ollama: OllamaStatus;
  services: ServiceStatus[];
}
