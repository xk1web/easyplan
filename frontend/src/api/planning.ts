import type { PlanningRequest, PlanningResponse } from "../types/planning";

type ErrorPayload = {
  detail?: string;
};

const API_BASE_URL = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const getBaseUrl = () => {
  const base = API_BASE_URL;
  return base.endsWith("/") ? base.slice(0, -1) : base;
};

const buildUrl = (path: string) => {
  const base = getBaseUrl();
  return `${base}${path}`;
};

const parseErrorMessage = async (response: Response) => {
  try {
    const data = (await response.json()) as ErrorPayload;
    if (typeof data?.detail === "string") {
      return data.detail;
    }
  } catch {
    // ignore JSON parse errors
  }
  return `HTTP ${response.status} ${response.statusText}`.trim();
};

export const generatePlanning = async (
  payload: PlanningRequest,
): Promise<PlanningResponse> => {
  const response = await fetch(buildUrl("/generate-planning"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const message = await parseErrorMessage(response);
    throw new Error(message);
  }

  return (await response.json()) as PlanningResponse;
};
