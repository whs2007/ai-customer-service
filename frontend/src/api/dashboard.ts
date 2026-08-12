/** 工作台统计接口（B5）。 */

import { request } from './client';

export interface DashboardStats {
  stat_date: string;
  today_sessions: number;
  ai_solved_count: number;
  ai_solved_rate: number;
  transfer_count: number;
  kb_hit_rate: number;
  intent_distribution: Record<string, number>;
}

export interface TrendPoint {
  date: string;
  sessions: number;
}

export interface IntentItem {
  intent: string;
  count: number;
}

export function getStats(): Promise<DashboardStats> {
  return request({ url: '/dashboard/stats', method: 'GET' });
}

export function getTrend(days = 7): Promise<TrendPoint[]> {
  return request({ url: '/dashboard/trend', method: 'GET', params: { days } });
}

export function getIntents(days = 7): Promise<{ items: IntentItem[]; total: number }> {
  return request({ url: '/dashboard/intents', method: 'GET', params: { days } });
}

