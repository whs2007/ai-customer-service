/** 应用评测页（09 §3–4 / evaluation.html）：评测集 / 评测任务 / 回流候选 三个 Tab。 */

import {
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  EyeOutlined,
  ImportOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Badge,
  Button,
  Card,
  Empty,
  Modal,
  Pagination,
  Progress,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '../../api/client';
import {
  confirmCandidate,
  deleteEvalSet,
  deleteTask,
  listCandidates,
  listEvalSets,
  listSamples,
  listTasks,
  rejectCandidate,
  rerunTask,
  type EvalCandidate,
  type EvalSet,
  type EvalTask,
} from '../../api/evaluation';
import EvalSetModal from './EvalSetModal';
import SampleModal from './SampleModal';
import TaskModal from './TaskModal';

const SOURCE_TAG: Record<string, { color: string; label: string }> = {
  manual: { color: 'gray', label: '手动' },
  public: { color: 'blue', label: '公开样例' },
  feedback: { color: 'orange', label: '反馈回流' },
};

const TASK_STATUS: Record<string, { color: string; label: string }> = {
  pending: { color: 'gray', label: '待执行' },
  running: { color: 'blue', label: '运行中' },
  completed: { color: 'green', label: '已完成' },
  failed: { color: 'red', label: '失败' },
};

export default function EvaluationPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [setModalOpen, setSetModalOpen] = useState(false);
  const [editingSet, setEditingSet] = useState<EvalSet | null>(null);
  const [sampleModal, setSampleModal] = useState<{ open: boolean; setId: string }>({ open: false, setId: '' });
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [viewSamples, setViewSamples] = useState<EvalSet | null>(null);
  const [samplesPage, setSamplesPage] = useState(1);
  const [confirmTarget, setConfirmTarget] = useState<EvalCandidate | null>(null);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['eval-sets'] });
    queryClient.invalidateQueries({ queryKey: ['eval-tasks'] });
    queryClient.invalidateQueries({ queryKey: ['eval-candidates'] });
  };

  const { data: evalSets = [], isLoading: setsLoading } = useQuery({
    queryKey: ['eval-sets'],
    queryFn: listEvalSets,
  });
  const { data: tasksPage, isLoading: tasksLoading } = useQuery({
    queryKey: ['eval-tasks'],
    queryFn: () => listTasks({ page: 1, page_size: 50 }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return items.some((t) => t.status === 'pending' || t.status === 'running') ? 2000 : false;
    },
  });
  const { data: candidates = [] } = useQuery({
    queryKey: ['eval-candidates'],
    queryFn: listCandidates,
  });
  const { data: samplesPageData, isLoading: samplesLoading } = useQuery({
    queryKey: ['eval-samples', viewSamples?.id, samplesPage],
    queryFn: () =>
      viewSamples
        ? listSamples(viewSamples.id, { page: samplesPage, page_size: 10 })
        : Promise.resolve({ items: [], total: 0, page: 1, page_size: 10 }),
    enabled: Boolean(viewSamples),
  });

  const runMutation = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      message.success('操作成功');
      invalidate();
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '操作失败'),
  });

  const confirmDeleteSet = (set: EvalSet) => {
    Modal.confirm({
      title: '删除评测集',
      content: `将删除「${set.name}」及其全部样本与任务，且不可恢复。确定删除吗？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => runMutation.mutateAsync(() => deleteEvalSet(set.id)),
    });
  };
  const confirmDeleteTask = (task: EvalTask) => {
    Modal.confirm({
      title: '删除评测任务',
      content: `确定删除任务（${task.eval_set_name}）及其报告吗？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => runMutation.mutateAsync(() => deleteTask(task.id)),
    });
  };

  const setColumns: ColumnsType<EvalSet> = [
    { title: '名称', dataIndex: 'name' },
    { title: '样本数', dataIndex: 'sample_count', width: 90, render: (v: number) => <span className="num">{v}</span> },
    {
      title: '来源',
      dataIndex: 'source',
      width: 110,
      render: (s: string) => <Tag color={SOURCE_TAG[s]?.color}>{SOURCE_TAG[s]?.label ?? s}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170, render: (v: string) => v.slice(0, 16).replace('T', ' ') },
    {
      title: '操作',
      key: 'actions',
      width: 300,
      render: (_, set) => (
        <Space size="small">
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => { setSamplesPage(1); setViewSamples(set); }}>
            查看样本
          </Button>
          <Button type="link" size="small" icon={<ImportOutlined />} onClick={() => setSampleModal({ open: true, setId: set.id })}>
            导入样本
          </Button>
          <Button
            type="link"
            size="small"
            disabled={set.sample_count === 0}
            title={set.sample_count === 0 ? '请先导入样本' : ''}
            onClick={() => setTaskModalOpen(true)}
          >
            创建评测任务
          </Button>
          <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => confirmDeleteSet(set)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const taskColumns: ColumnsType<EvalTask> = [
    { title: '评测集', dataIndex: 'eval_set_name' },
    { title: '对话模型', dataIndex: 'model_name', render: (v: string) => v || '默认' },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => <Tag color={TASK_STATUS[s]?.color}>{TASK_STATUS[s]?.label ?? s}</Tag>,
    },
    {
      title: '进度',
      key: 'progress',
      width: 160,
      render: (_, t) => (
        <Space size={8}>
          <Progress percent={t.total ? Math.round((t.progress / t.total) * 100) : 0} size="small" style={{ width: 100 }} />
          <span className="num" style={{ fontSize: 12, color: '#6B7280' }}>{t.progress}/{t.total}</span>
        </Space>
      ),
    },
    {
      title: '平均分',
      dataIndex: 'score_avg',
      width: 90,
      render: (v: number | null) => (v == null ? '—' : <b className="num">{v}%</b>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 210,
      render: (_, t) => (
        <Space size="small">
          {t.status === 'completed' && (
            <Button type="link" size="small" onClick={() => navigate(`/evaluation/tasks/${t.id}/report`)}>
              查看报告
            </Button>
          )}
          {t.status === 'failed' && (
            <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => runMutation.mutate(() => rerunTask(t.id))}>
              重试
            </Button>
          )}
          <Button type="link" size="small" danger onClick={() => confirmDeleteTask(t)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  const candidateColumns: ColumnsType<EvalCandidate> = [
    { title: '问题', dataIndex: 'question', ellipsis: true },
    { title: '期望答案', dataIndex: 'expected_answer', ellipsis: true },
    {
      title: '来源',
      dataIndex: 'source',
      width: 100,
      render: (s: string) => <Tag color={s === 'feedback' ? 'orange' : 'blue'}>{s === 'feedback' ? '引用反馈' : '人工标注'}</Tag>,
    },
    { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => v.slice(0, 16).replace('T', ' ') },
    {
      title: '操作',
      key: 'actions',
      width: 160,
      render: (_, c) => (
        <Space size="small">
          <Button type="link" size="small" icon={<CheckOutlined />} onClick={() => setConfirmTarget(c)}>
            确认加入
          </Button>
          <Button type="link" size="small" danger icon={<CloseOutlined />} onClick={() => runMutation.mutate(() => rejectCandidate(c.id))}>
            拒绝
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <h1 className="page-title">应用评测</h1>
      <p className="page-sub">
        评测集 → 评测任务 → 指标报告；引用反馈与人工标注可回流评测集（09_应用评测.md）
      </p>
      <div style={{ marginTop: 16 }}>
        <Tabs
          items={[
            {
              key: 'sets',
              label: '评测集',
              children: (
                <Card style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                    <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditingSet(null); setSetModalOpen(true); }}>
                      创建评测集
                    </Button>
                  </div>
                  <Table<EvalSet>
                    rowKey="id"
                    loading={setsLoading}
                    columns={setColumns}
                    dataSource={evalSets}
                    pagination={false}
                    locale={{ emptyText: <Empty description="暂无评测集，请先创建" /> }}
                  />
                </Card>
              ),
            },
            {
              key: 'tasks',
              label: '评测任务',
              children: (
                <Card style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      disabled={!evalSets.some((s) => s.sample_count > 0)}
                      title={!evalSets.some((s) => s.sample_count > 0) ? '请先导入样本' : ''}
                      onClick={() => setTaskModalOpen(true)}
                    >
                      创建评测任务
                    </Button>
                  </div>
                  <Table<EvalTask>
                    rowKey="id"
                    loading={tasksLoading}
                    columns={taskColumns}
                    dataSource={tasksPage?.items ?? []}
                    pagination={false}
                    locale={{ emptyText: <Empty description="暂无评测任务" /> }}
                  />
                  {tasksPage && tasksPage.total > 50 && (
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
                      <Pagination total={tasksPage.total} pageSize={50} showTotal={(t) => `共 ${t} 条`} />
                    </div>
                  )}
                </Card>
              ),
            },
            {
              key: 'candidates',
              label: (
                <Badge count={candidates.length} size="small">
                  <span style={{ paddingRight: 8 }}>回流候选</span>
                </Badge>
              ),
              children: (
                <Card style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
                  <Table<EvalCandidate>
                    rowKey="id"
                    columns={candidateColumns}
                    dataSource={candidates}
                    pagination={false}
                    locale={{ emptyText: <Empty description="暂无回流候选" /> }}
                  />
                </Card>
              ),
            },
          ]}
        />
      </div>

      <EvalSetModal
        open={setModalOpen}
        editing={editingSet}
        submitting={runMutation.isPending}
        onCancel={() => setSetModalOpen(false)}
        onSubmit={(values) =>
          runMutation.mutate(
            async () => {
              if (editingSet) {
                const { updateEvalSet } = await import('../../api/evaluation');
                await updateEvalSet(editingSet.id, values);
              } else {
                const { createEvalSet } = await import('../../api/evaluation');
                await createEvalSet(values);
              }
            },
            { onSuccess: () => setSetModalOpen(false) },
          )
        }
      />
      <SampleModal
        open={sampleModal.open}
        setId={sampleModal.setId}
        onCancel={() => setSampleModal({ open: false, setId: '' })}
        onDone={() => {
          setSampleModal({ open: false, setId: '' });
          invalidate();
        }}
      />
      <TaskModal
        open={taskModalOpen}
        submitting={runMutation.isPending}
        onCancel={() => setTaskModalOpen(false)}
        onSubmit={(values) =>
          runMutation.mutate(
            async () => {
              const { createTask } = await import('../../api/evaluation');
              await createTask(values);
            },
            { onSuccess: () => setTaskModalOpen(false) },
          )
        }
      />

      {/* 查看样本 */}
      <Modal
        title={`样本列表 · ${viewSamples?.name ?? ''}`}
        open={Boolean(viewSamples)}
        onCancel={() => setViewSamples(null)}
        footer={null}
        width={720}
      >
        <Table
          rowKey="id"
          size="small"
          loading={samplesLoading}
          dataSource={samplesPageData?.items ?? []}
          pagination={false}
          columns={[
            { title: '问题', dataIndex: 'question', ellipsis: true },
            { title: '期望答案', dataIndex: 'expected_answer', ellipsis: true },
            { title: '来源', dataIndex: 'source', width: 100, render: (s: string) => <Tag>{s}</Tag> },
          ]}
        />
        {(samplesPageData?.total ?? 0) > 10 && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 12 }}>
            <Pagination
              current={samplesPage}
              total={samplesPageData?.total ?? 0}
              pageSize={10}
              onChange={setSamplesPage}
              showTotal={(t) => `共 ${t} 条`}
            />
          </div>
        )}
      </Modal>

      {/* 确认候选加入评测集 */}
      <Modal
        title="确认候选加入评测集"
        open={Boolean(confirmTarget)}
        onCancel={() => setConfirmTarget(null)}
        footer={null}
        width={480}
      >
        <Select
          style={{ width: '100%' }}
          placeholder="选择目标评测集"
          options={evalSets.map((s) => ({ value: s.id, label: `${s.name}（${s.sample_count} 条）` }))}
          onChange={(value) => {
            if (confirmTarget) {
              runMutation.mutate(
                async () => confirmCandidate(confirmTarget.id, value),
                { onSuccess: () => setConfirmTarget(null) },
              );
            }
          }}
        />
      </Modal>
    </div>
  );
}
