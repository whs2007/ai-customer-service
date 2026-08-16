/**
 * 事件流 SSE 客户端（开发文档 02 §5）。
 *
 * EventSource 无法携带 Authorization 头，因此使用 fetch 流式读取 +
 * 手动断线重连（等价自动重连）；event_id 幂等去重，重连成功后回调
 * onReconnect 由页面全量重拉列表兜底（11 §9.3）。
 */

import { getAccessToken } from '../api/token';
import { getUserAccessToken } from '../api/token';

interface EventStreamOptions {
  onOpen?: () => void;
  onError?: (err: unknown) => void;
  onReconnect?: () => void;
  reconnectDelayMs?: number;
  /** 显式指定 token（用户端传 user token，管理端/客服端传管理 token）。 */
  token?: string | null;
}

export function connectEventStream(
  url: string,
  handlers: Record<string, (data: Record<string, unknown>) => void>,
  opts: EventStreamOptions = {},
): () => void {
  let stopped = false;
  let controller: AbortController | null = null;
  let attempt = 0;
  const seenEventIds = new Set<string>();
  const MAX_DEDUP = 500;

  // 【修复 H1】按 scope 判断端侧，而非 URL 路径子串（scope=user 不含 "/user/"）
  const token =
    opts.token ?? (url.includes('scope=user') ? getUserAccessToken() : getAccessToken());

  async function run() {
    let firstConnect = true;
    while (!stopped) {
      controller = new AbortController();
      try {
        const resp = await fetch(url, {
          headers: { Authorization: `Bearer ${token ?? ''}` },
          signal: controller.signal,
        });
        if (!resp.ok || !resp.body) {
          throw new Error(`事件流连接失败（HTTP ${resp.status}）`);
        }
        attempt = 0;
        if (firstConnect) {
          opts.onOpen?.();
          firstConnect = false;
        } else {
          opts.onReconnect?.();
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let eventName = '';
        while (!stopped) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() ?? '';
          for (const part of parts) {
            for (const line of part.split('\n')) {
              const trimmed = line.trim();
              if (trimmed.startsWith(':')) continue; // 心跳注释行
              if (trimmed.startsWith('event:')) {
                eventName = trimmed.slice(6).trim();
              } else if (trimmed.startsWith('data:')) {
                try {
                  const data = JSON.parse(trimmed.slice(5).trim()) as Record<string, unknown>;
                  const eventId = data.event_id as string | undefined;
                  if (eventId && seenEventIds.has(eventId)) continue;
                  if (eventId) {
                    seenEventIds.add(eventId);
                    if (seenEventIds.size > MAX_DEDUP) {
                      const first = seenEventIds.values().next().value;
                      if (first) seenEventIds.delete(first);
                    }
                  }
                  handlers[eventName]?.(data);
                } catch {
                  // 忽略无法解析的数据行
                }
              }
            }
          }
        }
      } catch (err) {
        if (!stopped) opts.onError?.(err);
      }
      if (!stopped) {
        // 【修复 L5】指数退避 + 随机抖动，上限 30s，避免断线风暴
        const base = Math.min(30000, (opts.reconnectDelayMs ?? 2000) * 2 ** attempt);
        const delay = base / 2 + Math.random() * (base / 2);
        attempt += 1;
        await new Promise((resolve) => setTimeout(resolve, delay));
      }
    }
  }

  void run();
  return () => {
    stopped = true;
    controller?.abort();
  };
}
