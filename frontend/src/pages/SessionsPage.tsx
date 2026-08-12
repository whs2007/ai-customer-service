/** 会话记录列表（10 §4.1）：筛选（时间/意图/状态/是否转人工/关键词/标注）+ 分页。 */

import { useQuery } from '@tanstack/react-query';
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Input,
  Pagination,
  Select,
  Space,
  Table,
  Tag,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { INTENT_LABELS, listSessions, type SessionListItem } from '../api/sessions';

const STATUS_LABELS: Record<string, string> = {
  active: '进行中',
  closed: '已结束',
  transferred: '已转人工',
};

export default function SessionsPage() {
  const navigate = useNavigate();
  const [keyword, setKeyword] = useState('');
  const [debounced, setDebounced] = useState('');
  const [intent, setIntent] = useState<string | undefined>();
  const [status, setStatus] = useState<string | undefined>();
  const [transferred, setTransferred] = useState<boolean | undefined>();
  const [annotated, setAnnotated] = useState<boolean | undefined>();
  const [dates, setDates] = useState<[string, string] | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(keyword.trim()), 300);
    return () => clearTimeout(t);
  }, [keyword]);

  const { data, isLoading } = useQuery({
    queryKey: ['sessions-list', debounced, intent, status, transferred, annotated, dates, page, pageSize],
    queryFn: () =>
      listSessions({
        keyword: debounced || undefined,
        intent,
        status,
        transferred,
        annotated,
        start_date: dates?.[0],
        end_date: dates?.[1],
        page,
        page_size: pageSize,
      }),
    placeholderData: (prev) => prev,
  });

  const columns: ColumnsType<SessionListItem> = [
    {
      title: '会话 ID',
      dataIndex: 'id',
      width: 150,
      render: (v: string) => <span className="num">{v.slice(0, 8)}…</span>,
    },
    {
      title: '开始时间',
      dataIndex: 'created_at',
      width: 160,
      render: (v: string) => v.replace('T', ' ').slice(0, 16),
    },
    {
      title: '意图',
      dataIndex: 'intent',
      width: 120,
      render: (v: string | null) =>
        v ? (
          <Tag color={v === 'complaint' || v === 'transfer' ? 'orange' : 'blue'}>
            {INTENT_LABELS[v] ?? v}
          </Tag>
        ) : (
          '—'
        ),
    },
    {
      title: '消息数',
      dataIndex: 'message_count',
      width: 80,
      render: (v: number) => <span className="num">{v}</span>,
    },
    {
      title: '是否转人工',
      dataIndex: 'transferred',
      width: 100,
      render: (v: boolean) => (v ? <Tag color="red">是</Tag> : <Tag color="gray">否</Tag>),
    },
    {
      title: '关联工单',
      dataIndex: 'ticket_no',
      width: 200,
      render: (v: string | null) =>
        v ? <span className="num" style={{ color: '#2563EB' }}>{v}</span> : '—',
    },
    {
      title: '标注状态',
      dataIndex: 'annotated',
      width: 90,
      render: (v: boolean) => (v ? <Tag color="green">已标注</Tag> : <Tag color="gray">未标注</Tag>),
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_, s) => (
        <Button type="link" size="small" onClick={() => navigate(`/sessions/${s.id}`)}>
          查看
        </Button>
      ),
    },
  ];

  return (
    <div>
      <h1 className="page-title">会话记录</h1>
      <p className="page-sub">统一查阅会话消息、知识引用与调用链路；支持人工标注并回流评测集（10_会话记录.md）</p>
      <Card style={{ marginTop: 16, borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
        <Space wrap style={{ marginBottom: 16 }}>
          <DatePicker.RangePicker
            onChange={(vals) =>
              setDates(vals && vals[0] && vals[1] ? [vals[0].format('YYYY-MM-DD'), vals[1].format('YYYY-MM-DD')] : null)
            }
          />
          <Select
            allowClear
            placeholder="意图"
            style={{ width: 130 }}
            value={intent}
            onChange={(v) => {
              setIntent(v);
              setPage(1);
            }}
            options={Object.entries(INTENT_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 120 }}
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
            options={Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <Select
            allowClear
            placeholder="是否转人工"
            style={{ width: 130 }}
            value={transferred}
            onChange={(v) => {
              setTransferred(v);
              setPage(1);
            }}
            options={[
              { value: true, label: '已转人工' },
              { value: false, label: '未转人工' },
            ]}
          />
          <Select
            allowClear
            placeholder="标注状态"
            style={{ width: 130 }}
            value={annotated}
            onChange={(v) => {
              setAnnotated(v);
              setPage(1);
            }}
            options={[
              { value: true, label: '已标注' },
              { value: false, label: '未标注' },
            ]}
          />
          <Input.Search
            placeholder="搜索会话 ID / 消息内容"
            allowClear
            style={{ width: 240 }}
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
          />
        </Space>
        <Table<SessionListItem>
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={data?.items ?? []}
          pagination={false}
          onRow={(s) => ({
            onClick: () => navigate(`/sessions/${s.id}`),
            style: { cursor: 'pointer' },
          })}
          locale={{ emptyText: <Empty description="暂无会话记录" /> }}
        />
        {(data?.total ?? 0) > 0 && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={data?.total ?? 0}
              showTotal={(t) => `共 ${t} 条`}
              showSizeChanger
              pageSizeOptions={[10, 20, 50]}
              onChange={(p, ps) => {
                setPage(p);
                setPageSize(ps);
              }}
            />
          </div>
        )}
      </Card>
    </div>
  );
}
