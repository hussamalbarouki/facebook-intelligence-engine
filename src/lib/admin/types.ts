export const CONTENT_CATEGORIES = [
  'local-news',
  'central-operations',
  'intelligence-reports',
  'facebook-news',
] as const;

export type ContentCategory = (typeof CONTENT_CATEGORIES)[number];
export type ContentStatus = 'draft' | 'published' | 'archived';
export type ContentPriority = 'normal' | 'important' | 'urgent' | 'critical';
export type SourceType = 'manual' | 'rss' | 'telegram' | 'facebook';

export const PERMISSIONS = [
  'content.read',
  'content.local.manage',
  'content.operations.manage',
  'content.intelligence.manage',
  'content.facebook.manage',
  'sources.manage',
  'operations.configure',
  'users.manage',
  'security.manage',
  'audit.read',
] as const;

export type Permission = (typeof PERMISSIONS)[number];

export interface Role {
  id: string;
  name: string;
  permissions: Permission[];
  system?: boolean;
}

export interface AdminUser {
  id: string;
  username: string;
  displayName: string;
  passwordSalt: string;
  passwordHash: string;
  roleId: string;
  active: boolean;
  mustChangePassword: boolean;
  totpEnabled: boolean;
  totpSecret?: string;
  pendingTotpSecret?: string;
  failedAttempts: number;
  lockedUntil?: string;
  createdAt: string;
  updatedAt: string;
  lastLoginAt?: string;
}

export interface ManagedContent {
  id: string;
  category: ContentCategory;
  title: string;
  body: string;
  status: ContentStatus;
  priority: ContentPriority;
  pinned: boolean;
  confirmed: boolean;
  sourceType: SourceType;
  sourceName?: string;
  sourceUrl?: string;
  externalId?: string;
  operationType?: string;
  operationArea?: string;
  operationSeverity?: string;
  structuredData?: Record<string, string>;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  publishedAt?: string;
}

export interface ContentSource {
  id: string;
  name: string;
  type: 'rss' | 'telegram' | 'facebook';
  url: string;
  enabled: boolean;
  autoPublish: boolean;
  autoTranslate: boolean;
  maxItems: number;
  lastSyncedAt?: string;
  lastAttemptAt?: string;
  lastError?: string;
  createdAt: string;
  updatedAt: string;
}

export interface TranslationCacheEntry {
  hash: string;
  sourceLanguage?: string;
  translatedText: string;
  characterCount: number;
  createdAt: string;
}

export interface OperationOptions {
  title: string;
  footer: string;
  fields: OperationField[];
  // Kept during the v5 migration so existing installations retain their old lists.
  types: string[];
  areas: string[];
  severities: string[];
  customFields: Array<{ id: string; label: string; required: boolean }>;
}

export interface OperationField {
  id: string;
  label: string;
  choices: string[];
  required: boolean;
}

export type TelegramFlowPermission = 'central-operations' | 'intelligence-reports';

export interface TelegramOperator {
  userId: string;
  name: string;
  permissions: TelegramFlowPermission[];
}

export interface TelegramConversation {
  userId: string;
  chatId: string;
  flow: TelegramFlowPermission;
  step: number;
  draft: Record<string, string>;
  updatedAt: string;
}

export interface PublicationEvent {
  id: string;
  type: 'content.published' | 'content.updated';
  contentId: string;
  category: 'central-operations' | 'intelligence-reports';
  occurredAt: string;
  payload: {
    version: 1;
    title: string;
    body: string;
    priority: ContentPriority;
    publishedAt: string;
    structuredData?: Record<string, string>;
  };
  deliveries: Array<{
    channel: string;
    status: 'pending' | 'sent' | 'failed';
    attempts: number;
    lastAttemptAt?: string;
    externalId?: string;
    error?: string;
  }>;
}

export interface AuditEntry {
  id: string;
  userId?: string;
  username?: string;
  action: string;
  target?: string;
  ip?: string;
  detail?: string;
  createdAt: string;
}

export interface AdminDatabase {
  version: number;
  security: { sessionSecret: string };
  users: AdminUser[];
  roles: Role[];
  content: ManagedContent[];
  sources: ContentSource[];
  translationCache: TranslationCacheEntry[];
  operationOptions: OperationOptions;
  telegramOperators: TelegramOperator[];
  telegramConversations: TelegramConversation[];
  processedTelegramUpdates: number[];
  publicationEvents: PublicationEvent[];
  audit: AuditEntry[];
}

export const CATEGORY_PERMISSION: Record<ContentCategory, Permission> = {
  'local-news': 'content.local.manage',
  'central-operations': 'content.operations.manage',
  'intelligence-reports': 'content.intelligence.manage',
  'facebook-news': 'content.facebook.manage',
};

