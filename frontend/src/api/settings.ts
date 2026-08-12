/** 系统设置接口（B6a）：模型配置 / Prompt / 客服规则 / 分块参数。 */

import { request } from './client';
import type { ModelProfile } from './chat';

export interface PromptConfig {
  system_prompt: string;
  fallback_text: string;
  escalation_rule_text: string;
}

export interface EscalationConfig {
  threshold: number;
  priority_rules: Record<string, string>;
}

export interface ChunkingConfig {
  chunk_size: number;
  overlap: number;
}

export interface IntentRules {
  keywords: Record<string, string[]>;
  order_no_pattern: string;
}

// ---------- 模型配置 ----------

export function listModelProfiles(): Promise<ModelProfile[]> {
  return request({ url: '/settings/model-profiles', method: 'GET' });
}

export function createModelProfile(
  data: Omit<ModelProfile, 'id' | 'api_key'> & { api_key?: string },
): Promise<ModelProfile> {
  return request({ url: '/settings/model-profiles', method: 'POST', data });
}

export function updateModelProfile(
  id: string,
  data: Partial<Omit<ModelProfile, 'id' | 'api_key'> & { api_key?: string }>,
): Promise<ModelProfile> {
  return request({ url: `/settings/model-profiles/${id}`, method: 'PUT', data });
}

export function deleteModelProfile(id: string): Promise<null> {
  return request({ url: `/settings/model-profiles/${id}`, method: 'DELETE' });
}

export function testModelProfile(id: string): Promise<{ ok: boolean; latency_ms: number | null; message: string }> {
  return request({ url: `/settings/model-profiles/${id}/test`, method: 'POST' });
}

export function activateModelProfile(id: string): Promise<null> {
  return request({ url: `/settings/model-profiles/${id}/activate`, method: 'PUT' });
}

// ---------- Prompt / 客服规则 / 分块 ----------

export function getPromptConfig(): Promise<PromptConfig> {
  return request({ url: '/settings/prompt', method: 'GET' });
}

export function updatePromptConfig(data: PromptConfig): Promise<PromptConfig> {
  return request({ url: '/settings/prompt', method: 'PUT', data });
}

export function getEscalationConfig(): Promise<EscalationConfig> {
  return request({ url: '/settings/escalation', method: 'GET' });
}

export function updateEscalationConfig(data: EscalationConfig): Promise<EscalationConfig> {
  return request({ url: '/settings/escalation', method: 'PUT', data });
}

export function getChunkingConfig(): Promise<ChunkingConfig> {
  return request({ url: '/settings/chunking', method: 'GET' });
}

export function updateChunkingConfig(data: ChunkingConfig): Promise<ChunkingConfig> {
  return request({ url: '/settings/chunking', method: 'PUT', data });
}

export function getIntentRules(): Promise<IntentRules> {
  return request({ url: '/settings/intent', method: 'GET' });
}

export function updateIntentRules(data: { keywords?: Record<string, string[]>; order_no_pattern?: string }): Promise<null> {
  return request({ url: '/settings/intent', method: 'PUT', data });
}

