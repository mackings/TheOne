/** What the console needs from the outside world. Infrastructure implements these; pages only ever see the interfaces. */
import type { AssistantStatus, ChatMessage, ChatReply, LiveEvent } from "@/domain/assistant";
import type {
  CompleteResult,
  ContinuousSession,
  Customer,
  DuressEnrolResult,
  EnrolmentSession,
  Health,
  IrisCaptureExtra,
  IrisEnrolResult,
  IrisVerifyResult,
  Language,
  NewCustomer,
  Sample,
  VerificationEvent,
  VerifyResult,
} from "@/domain/identity";
import type {
  AccountBrief,
  AccountDetail,
  Backtest,
  BankAction,
  BankSync,
  Evaluation,
  FlaggedAccount,
  ImportJob,
  ImportOptions,
  ImportResult,
  LabelsSummary,
  LearningRefresh,
  LearningView,
  NetAlert,
  NetDecision,
  NetSummary,
  RiskModel,
  RingActionKind,
  RingActionResult,
  RingDetail,
  RingListItem,
  SafeLimit,
  SimulationResult,
  StatementImport,
  StatementReport,
  TraceResult,
  TraceRow,
} from "@/domain/network";

export interface NetworkGateway {
  summary(): Promise<NetSummary>;
  analyse(): Promise<NetSummary>;
  evaluation(): Promise<Evaluation>;
  simulate(seed: number, customers: number, rings: number): Promise<SimulationResult>;

  rings(): Promise<RingListItem[]>;
  ring(id: string): Promise<RingDetail>;
  ringAction(id: string, action: RingActionKind, actor: string, accountIds?: string[], note?: string): Promise<RingActionResult>;
  traceRing(id: string, actor: string): Promise<TraceResult>;
  ringTraces(id: string): Promise<TraceRow[]>;

  search(q: string): Promise<AccountBrief[]>;
  flagged(): Promise<FlaggedAccount[]>;
  accounts(flagged: boolean, limit?: number): Promise<FlaggedAccount[]>;
  account(id: string): Promise<AccountDetail>;
  syncAccount(id: string): Promise<BankSync>;
  safeLimit(id: string): Promise<SafeLimit>;
  setSafeLimit(id: string, limitKobo: number): Promise<SafeLimit>;
  linkCustomer(accountId: string, customerId: string): Promise<{ account_id: string }>;

  decide(source: AccountBrief, beneficiary: AccountBrief, amountKobo: number): Promise<NetDecision>;
  decisions(limit?: number): Promise<NetDecision[]>;
  reviewDecision(id: string, outcome: "release" | "block", actor: string, note?: string): Promise<NetDecision>;

  alerts(): Promise<NetAlert[]>;
  allAlerts(): Promise<NetAlert[]>;
  ackAlert(id: string, actor: string): Promise<NetAlert>;

  importFile(fmt: string, file: File, opts: ImportOptions): Promise<ImportResult>;
  startImportJob(fmt: string, file: File, opts: ImportOptions, onUpload: (fraction: number) => void): Promise<ImportJob>;
  importJob(id: string): Promise<ImportJob>;
  checkStatement(text: string): Promise<StatementReport>;
  checkStatementFile(file: File, password?: string): Promise<StatementReport & { text: string }>;
  importStatement(text: string, bankCode: string): Promise<StatementImport>;

  bankActions(): Promise<BankAction[]>;
  retryBankAction(id: string): Promise<BankAction>;
  backtest(days: number, stepHours: number, capacityPerDay: number): Promise<Backtest>;
  learning(): Promise<LearningView>;
  refreshLearning(): Promise<LearningRefresh>;
  labelsSummary(): Promise<LabelsSummary>;
  model(): Promise<RiskModel>;
  trainModel(): Promise<RiskModel>;
}

export interface IdentityGateway {
  health(): Promise<Health>;
  languages(): Promise<Language[]>;

  listCustomers(): Promise<Customer[]>;
  getCustomer(id: string): Promise<Customer>;
  createCustomer(body: NewCustomer): Promise<Customer>;
  listEvents(id: string): Promise<VerificationEvent[]>;
  revokeTemplate(id: string): Promise<void>;
  revokeIrisTemplate(id: string): Promise<void>;

  createSession(customerId: string, language?: string): Promise<EnrolmentSession>;
  getSession(id: string): Promise<EnrolmentSession>;
  uploadSample(sessionId: string, step: number, audio: Blob): Promise<Sample>;
  completeSession(id: string): Promise<CompleteResult>;

  verify(customerId: string, audio: Blob, context?: string): Promise<VerifyResult>;
  startContinuous(customerId: string, context?: string): Promise<ContinuousSession>;
  sendChunk(id: string, audio: Blob): Promise<ContinuousSession>;
  endContinuous(id: string): Promise<ContinuousSession>;

  irisEnrol(customerId: string, frames: Blob[], extra?: IrisCaptureExtra): Promise<IrisEnrolResult>;
  irisDuressEnrol(customerId: string, frames: Blob[], extra?: IrisCaptureExtra): Promise<DuressEnrolResult>;
  irisVerify(customerId: string, frames: Blob[], resolvesEventId?: string, context?: string, extra?: IrisCaptureExtra): Promise<IrisVerifyResult>;
}

/** One live voice conversation with the assistant. */
export interface LiveSession {
  readonly open: boolean;
  readonly level: number;
  start(): Promise<void>;
  sendText(text: string): void;
  stop(): void;
}

export interface AssistantGateway {
  status(): Promise<AssistantStatus>;
  chat(messages: ChatMessage[]): Promise<ChatReply>;
  live(onEvent: (e: LiveEvent) => void): LiveSession;
}

/** Pages and files the API serves, opened in a new tab or saved (a plain link cannot carry the API key). */
export interface DocumentGateway {
  readonly apiUrl: string;
  open(path: string, download?: string): Promise<void>;
}

export interface Gateways {
  network: NetworkGateway;
  identity: IdentityGateway;
  assistant: AssistantGateway;
  documents: DocumentGateway;
}
