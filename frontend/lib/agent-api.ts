export type AppMode = 'demo' | 'local';

export type PlannerMode = 'deterministic' | 'llm';

export type ProviderName = 'openai' | 'anthropic' | 'gemini' | 'ollama';

export type WorkflowStatus =
  | 'received'
  | 'plan_generated'
  | 'running'
  | 'waiting_for_approval'
  | 'finalizing'
  | 'completed'
  | 'rejected'
  | 'failed';

export type StepStatus =
  | 'pending'
  | 'ready'
  | 'running'
  | 'waiting_for_approval'
  | 'approved'
  | 'rejected'
  | 'completed'
  | 'failed'
  | 'skipped';

export type ApprovalDecision = 'approved' | 'rejected';

export type ServiceErrorCode =
  | 'task_not_found'
  | 'invalid_task_request'
  | 'approval_required'
  | 'invalid_approval'
  | 'planner_unavailable'
  | 'provider_unavailable'
  | 'workflow_execution_error';

export type TaskId = `TASK-${string}`;

export interface Health {
  status: 'ok';
}

export interface ProviderCapability {
  name: ProviderName;
  default_model: string;
  requires_api_key: boolean;
}

export interface ToolCapability {
  name: string;
  description: string;
  requires_approval: boolean;
}

export interface Capabilities {
  app_mode: AppMode;
  planner_modes: PlannerMode[];
  providers: ProviderCapability[];
  tools: ToolCapability[];
  approval_required_tools: string[];
}

export interface PlannerConfiguration {
  app_mode: AppMode;
  planner_mode: PlannerMode;
  provider: ProviderName | null;
  effective_provider: ProviderName | null;
  requested_model: string | null;
  effective_model: string | null;
  requires_api_key: boolean;
}

export interface StartTaskRequest {
  user_request: string;
  planner_mode?: PlannerMode;
  provider?: ProviderName | null;
  model?: string | null;
}

export interface ResumeApprovalRequest {
  decision: ApprovalDecision;
  reviewer_note?: string | null;
}

export interface WorkflowStatusDetail {
  status: WorkflowStatus;
  current_step_id: string | null;
  is_terminal: boolean;
  waiting_for_approval: boolean;
}

export interface PlanStep {
  step_id: string;
  tool_name: string;
  description: string;
  reason: string;
  inputs: Record<string, unknown>;
  depends_on: string[];
  requires_approval: boolean;
  status: StepStatus;
}

export interface ExecutionPlan {
  task_type: string;
  planner_mode: PlannerMode;
  summary: string;
  steps: PlanStep[];
}

export interface ToolExecutionResult {
  step_id: string | null;
  tool_name: string;
  status: StepStatus;
  payload: Record<string, unknown>;
  latency_ms: number | null;
  error_message: string | null;
}

export interface PendingApproval {
  task_id: TaskId;
  step_id: string;
  tool_name: string;
  description: string;
  reason: string;
  recommended_action: string | null;
}

export interface ApprovalRecord {
  id: number | null;
  task_id: TaskId;
  step_id: string;
  decision: ApprovalDecision;
  reviewer_note: string | null;
  decided_at: string;
}

export interface AuditEvent {
  id: number | null;
  task_id: TaskId;
  step_id: string | null;
  event_type: string;
  detail: string | null;
  created_at: string;
}

export interface StructuredApiError {
  code: ServiceErrorCode;
  message: string;
  task_id: TaskId | null;
  retryable: boolean;
}

export interface ApiErrorResponse {
  error: StructuredApiError;
}

export interface TaskSummary {
  task_id: TaskId;
  user_request: string;
  planner_mode: PlannerMode;
  provider: ProviderName | null;
  status: WorkflowStatus;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  tools_used: number;
  requested_planner: string | null;
  executed_planner: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  case_id: string | null;
  customer_id: string | null;
  refund_amount: string | null;
  approval_status: ApprovalDecision | null;
}

export interface TaskDetail {
  task_id: TaskId;
  user_request: string;
  planner_mode: PlannerMode;
  provider: ProviderName | null;
  model: string | null;
  workflow: WorkflowStatusDetail;
  plan: ExecutionPlan | null;
  tool_results: ToolExecutionResult[];
  pending_approval: PendingApproval | null;
  approvals: ApprovalRecord[];
  events: AuditEvent[];
  approval_status: ApprovalDecision | null;
  approval_reason: string | null;
  recommended_action: string | null;
  final_response: string | null;
  generated_report_path: string | null;
  customer_response: string | null;
  requested_planner: string;
  executed_planner: string;
  fallback_used: boolean;
  fallback_reason: string | null;
  planning_notice: string | null;
  unsupported_actions: string[];
  error: StructuredApiError | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface TaskHistoryQuery {
  status?: WorkflowStatus | null;
  case_id?: string | null;
  customer_id?: string | null;
  keyword?: string | null;
  limit?: number;
}

export interface AgentApiRequestOptions {
  providerApiKey?: string;
  signal?: AbortSignal;
}

export type AgentApiErrorKind = 'network_unavailable' | 'http_error';

export class AgentApiError extends Error {
  readonly kind: AgentApiErrorKind;
  readonly status: number | null;
  readonly backendError: StructuredApiError | null;

  constructor({
    message,
    kind,
    status = null,
    backendError = null,
  }: {
    message: string;
    kind: AgentApiErrorKind;
    status?: number | null;
    backendError?: StructuredApiError | null;
  }) {
    super(message);
    this.name = 'AgentApiError';
    this.kind = kind;
    this.status = status;
    this.backendError = backendError;
  }

  get code(): ServiceErrorCode | null {
    return this.backendError?.code ?? null;
  }

  get taskId(): TaskId | null {
    return this.backendError?.task_id ?? null;
  }

  get retryable(): boolean {
    return this.backendError?.retryable ?? this.kind === 'network_unavailable';
  }
}

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

const HTTP_ERROR_MESSAGES: Readonly<Record<number, string>> = {
  400: 'The agent API rejected the request.',
  404: 'The requested agent resource was not found.',
  409: 'The task cannot perform that operation in its current state.',
  422: 'The agent API could not validate the request.',
  500: 'The agent workflow failed while processing the request.',
  503: 'The requested provider is currently unavailable.',
};

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, '');
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function parseStructuredError(value: unknown): StructuredApiError | null {
  if (!isRecord(value) || !isRecord(value.error)) return null;

  const error = value.error;
  if (typeof error.code !== 'string' || typeof error.message !== 'string') {
    return null;
  }

  return {
    code: error.code as ServiceErrorCode,
    message: error.message,
    task_id: typeof error.task_id === 'string' ? (error.task_id as TaskId) : null,
    retryable: error.retryable === true,
  };
}

function taskPath(taskId: TaskId): string {
  return `/tasks/${encodeURIComponent(taskId)}`;
}

export class AgentApiClient {
  readonly baseUrl: string;

  constructor(baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL) {
    this.baseUrl = normalizeBaseUrl(baseUrl || DEFAULT_API_BASE_URL);
  }

  getHealth(options?: AgentApiRequestOptions): Promise<Health> {
    return this.request('/health', { options });
  }

  getCapabilities(options?: AgentApiRequestOptions): Promise<Capabilities> {
    return this.request('/capabilities', { options });
  }

  startTask(
    task: StartTaskRequest,
    options?: AgentApiRequestOptions,
  ): Promise<TaskDetail> {
    return this.request('/tasks', { method: 'POST', body: task, options });
  }

  listTasks(
    query: TaskHistoryQuery = {},
    options?: AgentApiRequestOptions,
  ): Promise<TaskSummary[]> {
    const search = new URLSearchParams();

    if (query.status) search.set('status', query.status);
    if (query.case_id) search.set('case_id', query.case_id);
    if (query.customer_id) search.set('customer_id', query.customer_id);
    if (query.keyword) search.set('keyword', query.keyword);
    if (query.limit !== undefined) search.set('limit', String(query.limit));

    const suffix = search.size > 0 ? `?${search.toString()}` : '';
    return this.request(`/tasks${suffix}`, { options });
  }

  getTask(
    taskId: TaskId,
    options?: AgentApiRequestOptions,
  ): Promise<TaskDetail> {
    return this.request(taskPath(taskId), { options });
  }

  getPendingApproval(
    taskId: TaskId,
    options?: AgentApiRequestOptions,
  ): Promise<PendingApproval> {
    return this.request(`${taskPath(taskId)}/approval`, { options });
  }

  decideApproval(
    taskId: TaskId,
    approval: ResumeApprovalRequest,
    options?: AgentApiRequestOptions,
  ): Promise<TaskDetail> {
    return this.request(`${taskPath(taskId)}/approval`, {
      method: 'POST',
      body: approval,
      options,
    });
  }

  getTaskSteps(
    taskId: TaskId,
    options?: AgentApiRequestOptions,
  ): Promise<PlanStep[]> {
    return this.request(`${taskPath(taskId)}/steps`, { options });
  }

  getTaskEvents(
    taskId: TaskId,
    options?: AgentApiRequestOptions,
  ): Promise<AuditEvent[]> {
    return this.request(`${taskPath(taskId)}/events`, { options });
  }

  getTaskApprovals(
    taskId: TaskId,
    options?: AgentApiRequestOptions,
  ): Promise<ApprovalRecord[]> {
    return this.request(`${taskPath(taskId)}/approvals`, { options });
  }

  private async request<T>(
    path: string,
    {
      method = 'GET',
      body,
      options,
    }: {
      method?: 'GET' | 'POST';
      body?: object;
      options?: AgentApiRequestOptions;
    },
  ): Promise<T> {
    const headers = new Headers({ Accept: 'application/json' });

    if (body !== undefined) headers.set('Content-Type', 'application/json');
    if (options?.providerApiKey) {
      headers.set('X-Provider-API-Key', options.providerApiKey);
    }

    let response: Response;

    try {
      response = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: options?.signal,
      });
    } catch {
      throw new AgentApiError({
        message: 'Unable to reach the agent API.',
        kind: 'network_unavailable',
      });
    }

    const responseText = await response.text();
    let responseBody: unknown = null;

    if (responseText) {
      try {
        responseBody = JSON.parse(responseText) as unknown;
      } catch {
        responseBody = null;
      }
    }

    if (!response.ok) {
      const backendError = parseStructuredError(responseBody);
      throw new AgentApiError({
        message:
          backendError?.message ??
          HTTP_ERROR_MESSAGES[response.status] ??
          `The agent API returned HTTP ${response.status}.`,
        kind: 'http_error',
        status: response.status,
        backendError,
      });
    }

    return responseBody as T;
  }
}

export const agentApi = new AgentApiClient();
