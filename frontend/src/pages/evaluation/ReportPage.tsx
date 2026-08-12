/** 评测任务报告页（09 §4.4 / evaluation.html）：3 指标卡 + 样本明细 + CSV 导出 + 人工调通过。 */

import { ArrowLeftOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import { Button, Card, Descriptions, Switch, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '../../api/client';
import { getReport, updateResultPassed, type EvalResult } from '../../api/evaluation';

function exportCsv(report: { task: { id: string }; results: EvalResult[] }) {
  const header = ['序号', '问题', '模型回答', '期望答案', '回答准确性', '通过'];
  const rows = report.results.map((r, i) => [
    i + 1,
    r.question,
    r.answer,
    r.expected_answer,
    r.scores.accuracy ?? '',
    r.passed ? '通过' : '未通过',
  ]);
  const escape = (v: string | number) => `"${String(v).split('"').join('""')}"`;
  const csv = [header, ...rows].map((row) => row.map(escape).join(',')).join('\n');
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `评测报告_${report.task.id.slice(0, 8)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function MetricCard({ title, value, extra, status }: { title: string; value: string; extra: string; status: 'done' | 'pending' }) {
  return (
    <Card style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
      <div style={{ fontSize: 13, color: '#6B7280' }}>
        {title} <Tag color={status === 'done' ? 'green' : 'gray'}>{status === 'done' ? '已实现' : '预留'}</Tag>
      </div>
      <div style={{ fontSize: 30, fontWeight: 700, marginTop: 6 }}>{value}</div>
      <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>{extra}</div>
    </Card>
  );
}

export default function ReportPage() {
  const { taskId = '' } = useParams();
  const navigate = useNavigate();
  const { data: report, isLoading, refetch } = useQuery({
    queryKey: ['eval-report', taskId],
    queryFn: () => getReport(taskId),
    enabled: Boolean(taskId),
  });

  const togglePass = async (result: EvalResult, passed: boolean) => {
    try {
      await updateResultPassed(result.id, passed);
      message.success('通过状态已更新');
      await refetch();
    } catch (err) {
      message.error(err instanceof ApiError ? err.message : '更新失败');
    }
  };

  const columns: ColumnsType<EvalResult> = [
    { title: '问题', dataIndex: 'question', width: 220, ellipsis: true },
    {
      title: '模型回答',
      dataIndex: 'answer',
      ellipsis: true,
      render: (v: string) => <span title={v}>{v || '—'}</span>,
    },
    {
      title: '期望答案',
      dataIndex: 'expected_answer',
      ellipsis: true,
      render: (v: string) => <span title={v}>{v}</span>,
    },
    {
      title: '引用',
      dataIndex: 'citations',
      width: 90,
      render: (v: unknown[]) => <Tag>{v.length} 条</Tag>,
    },
    {
      title: '回答准确性',
      dataIndex: ['scores', 'accuracy'],
      width: 110,
      render: (v: number | null) => (v == null ? '—' : `${v}%`),
    },
    {
      title: '通过',
      dataIndex: 'passed',
      width: 90,
      render: (passed: boolean, result) => (
        <Switch checked={passed} onChange={(v) => void togglePass(result, v)} size="small" />
      ),
    },
  ];

  const metrics = report?.metrics;
  const accuracy = metrics?.accuracy;
  const passRate = metrics?.pass_rate;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/evaluation')}>
          返回任务列表
        </Button>
        <Typography.Title level={4} style={{ margin: 0 }}>
          评测报告
        </Typography.Title>
        {report && (
          <Tag color={report.task.status === 'completed' ? 'green' : 'orange'}>
            {report.task.status}
          </Tag>
        )}
        <div style={{ flex: 1 }} />
        {report && (
          <Button onClick={() => exportCsv(report)}>导出 CSV</Button>
        )}
      </div>

      {report && (
        <Descriptions size="small" column={3} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="评测集">{report.task.eval_set_name}</Descriptions.Item>
          <Descriptions.Item label="对话模型">
            {report.task.model_name || '默认'}
          </Descriptions.Item>
          <Descriptions.Item label="通过率">
            {report.passed_count}/{report.total}（{passRate ?? 0}%）
          </Descriptions.Item>
        </Descriptions>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 16 }}>
        <MetricCard
          title="回答准确性"
          value={accuracy == null ? '—' : `${accuracy}%`}
          extra="LLM-as-judge · 先行实现"
          status="done"
        />
        <MetricCard title="问题相关性" value="—" extra="预留" status="pending" />
        <MetricCard title="语义准确性" value="—" extra="预留" status="pending" />
      </div>

      <Card title="样本明细" style={{ borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
        <Table<EvalResult>
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={report?.results ?? []}
          pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
        />
      </Card>
    </div>
  );
}
