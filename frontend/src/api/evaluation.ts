/** 应用评测接口（B4.5）。 */

import { request } from './client';

export interface EvalSet {
  id: string;
  name: string;
  description: string;
  source: string;
  sample_count: number;
  created_at: string;
  updated_at: string;
}

export interface EvalSample {
  id: string;
  eval_set_id: string;
  question: string;
  expected_answer: string;
  expected_chunks: string[];
  source: string;
  created_at: string;
}

export interface EvalTask {
  id: string;
  eval_set_id: string;
  eval_set_name: string;
  model_profile_id: string | null;
  model_name: string;
  kb_ids: string[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  total: number;
  score_avg: number | null;
  metrics: { accuracy?: number; pass_rate?: number; passed_count?: number } | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvalResult {
  id: string;
  sample_id: string;
  question: string;
  expected_answer: string;
  answer: string;
  citations: Array<Record<string, unknown>>;
  scores: { accuracy: number | null; relevancy: number | null; semantic: number | null };
  passed: boolean;
}

export interface EvalReport {
  task: EvalTask;
  score_avg: number | null;
  pass_rate: number;
  total: number;
  passed_count: number;
  metrics: { accuracy?: number; pass_rate?: number; passed_count?: number } | null;
  results: EvalResult[];
}

export interface EvalCandidate {
  id: string;
  question: string;
  expected_answer: string;
  source: string;
  source_id: string | null;
  message_id: string | null;
  status: string;
  created_at: string;
}

export interface PageResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------- 评测集 ----------

export function listEvalSets(): Promise<EvalSet[]> {
  return request({ url: '/evaluations/sets', method: 'GET' });
}

export function createEvalSet(data: { name: string; description: string }): Promise<EvalSet> {
  return request({ url: '/evaluations/sets', method: 'POST', data });
}

export function updateEvalSet(
  id: string,
  data: { name: string; description: string },
): Promise<EvalSet> {
  return request({ url: `/evaluations/sets/${id}`, method: 'PUT', data });
}

export function deleteEvalSet(id: string): Promise<null> {
  return request({ url: `/evaluations/sets/${id}`, method: 'DELETE' });
}

// ---------- 样本 ----------

export function listSamples(
  setId: string,
  params: { page: number; page_size: number },
): Promise<PageResult<EvalSample>> {
  return request({ url: `/evaluations/sets/${setId}/samples`, method: 'GET', params });
}

export function addSample(
  setId: string,
  data: { question: string; expected_answer: string; expected_chunks?: string[] },
): Promise<EvalSample> {
  return request({ url: `/evaluations/sets/${setId}/samples`, method: 'POST', data });
}

export function importSamples(
  setId: string,
  items: { question: string; expected_answer: string; expected_chunks?: string[] }[],
): Promise<null> {
  return request({ url: `/evaluations/sets/${setId}/samples/import`, method: 'POST', data: { items } });
}

export function importPublicSamples(setId: string): Promise<null> {
  return request({ url: `/evaluations/sets/${setId}/samples/import-public`, method: 'POST' });
}

// ---------- 任务 ----------

export function listTasks(params: { page: number; page_size: number }): Promise<PageResult<EvalTask>> {
  return request({ url: '/evaluations/tasks', method: 'GET', params });
}

export function createTask(data: {
  eval_set_id: string;
  model_profile_id?: string | null;
  kb_ids: string[];
}): Promise<EvalTask> {
  return request({ url: '/evaluations/tasks', method: 'POST', data });
}

export function getTask(id: string): Promise<EvalTask> {
  return request({ url: `/evaluations/tasks/${id}`, method: 'GET' });
}

export function rerunTask(id: string): Promise<EvalTask> {
  return request({ url: `/evaluations/tasks/${id}/rerun`, method: 'POST' });
}

export function deleteTask(id: string): Promise<null> {
  return request({ url: `/evaluations/tasks/${id}`, method: 'DELETE' });
}

export function getReport(id: string): Promise<EvalReport> {
  return request({ url: `/evaluations/tasks/${id}/report`, method: 'GET' });
}

export function updateResultPassed(id: string, passed: boolean): Promise<null> {
  return request({ url: `/evaluations/results/${id}/passed`, method: 'PUT', data: { passed } });
}

// ---------- 回流候选 ----------

export function listCandidates(): Promise<EvalCandidate[]> {
  return request({ url: '/evaluations/candidates', method: 'GET' });
}

export function confirmCandidate(id: string, evalSetId: string): Promise<null> {
  return request({ url: `/evaluations/candidates/${id}/confirm`, method: 'POST', data: { eval_set_id: evalSetId } });
}

export function rejectCandidate(id: string): Promise<null> {
  return request({ url: `/evaluations/candidates/${id}/reject`, method: 'POST' });
}

