import createClient from "openapi-fetch";

import type { components, paths } from "@/lib/api-types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const client = createClient<paths>({ baseUrl: API_URL });

type Schemas = components["schemas"];
export type SystemStatus = Schemas["SystemStatus"];
export type SampleDataset = Schemas["SampleDataset"];
export type DatasetDetail = Schemas["DatasetDetail"];
export type TableProfile = Schemas["TableProfile"];
export type ColumnProfile = Schemas["ColumnProfile"];
export type Suggestion = Schemas["Suggestion"];
export type TransportationMapping = Schemas["TransportationMapping"];
export type AssignmentMapping = Schemas["AssignmentMapping"];
export type Mapping = TransportationMapping | AssignmentMapping;
export type LongLayout = Schemas["LongLayout"];
export type MatrixLayout = Schemas["MatrixLayout"];
export type KeyValue = Schemas["KeyValue"];
export type BuildResponse = Schemas["BuildResponse"];
export type DataIssue = Schemas["DataIssue"];
export type Problem = Schemas["TransportationProblem"] | Schemas["AssignmentProblem"];
export type SolveReport = Schemas["SolveReport"];
export type Check = Schemas["Check"];
export type ProblemKind = Problem["kind"];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Turn FastAPI's error body (string detail or validation list) into a readable message. */
function describe(error: unknown, status: number): string {
  if (error && typeof error === "object" && "detail" in error) {
    const detail = (error as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) =>
          [d.loc?.slice(1).join("."), d.msg].filter(Boolean).join(": "),
        )
        .join("; ");
    }
  }
  return `Request failed (${status})`;
}

/** Unwrap an openapi-fetch result, throwing ApiError on failure. */
export async function unwrap<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result;
  try {
    result = await request;
  } catch {
    throw new ApiError(0, `Could not reach the API at ${API_URL}. Is it running?`);
  }
  if (result.error !== undefined || result.data === undefined) {
    throw new ApiError(result.response.status, describe(result.error, result.response.status));
  }
  return result.data;
}

export type Analysis = Schemas["Analysis"];
export type AnalyzeResponse = Schemas["AnalyzeResponse"];
export type ExtractResponse = Schemas["ExtractResponse"];
export type Answer = Schemas["Answer"];
export type Formulation = Schemas["Formulation"];
export type Ungrounded = Schemas["Ungrounded"];
export type Trace = Schemas["Trace"];
export type AuditReport = Schemas["AuditReport"];
export type Finding = Schemas["Finding"];
export type Review = Schemas["Review"];
export type RequirementCheck = Schemas["RequirementCheck"];
