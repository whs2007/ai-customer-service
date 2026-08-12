/** 系统管理接口（B6a）：审计日志 / 重建向量 / 导出。 */

import { getAccessToken } from './token';
import { request } from './client';

export interface AuditLog {
  id: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

export function listAuditLogs(params: {
  action?: string;
  page: number;
  page_size: number;
}): Promise<{ items: AuditLog[]; total: number; page: number; page_size: number }> {
  return request({ url: '/audit-logs', method: 'GET', params });
}

export function rebuildVectors(): Promise<{ total: number; succeeded: number; failed: number }> {
  return request({ url: '/admin/rebuild-vectors', method: 'POST' });
}

export async function exportKnowledgeBases(): Promise<void> {
  const resp = await fetch('/api/admin/export', {
    headers: { Authorization: `Bearer ${getAccessToken() ?? ''}` },
  });
  if (!resp.ok) throw new Error(`导出失败（HTTP ${resp.status}）`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'knowledge_bases_export.json';
  a.click();
  URL.revokeObjectURL(url);
}

