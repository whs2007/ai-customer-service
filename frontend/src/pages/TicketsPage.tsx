/** 客服工单页（06 / sessions.html 联动）：筛选、列表、详情抽屉、状态流转。 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Pagination,
  Select,
  Space,
  Table,
  Tag,
  Timeline,
  Tooltip,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '../api/client';
import { getTicket, listTickets, ticketAction, type TicketItem } from '../api/tickets';

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  open: { color: 'orange', label: '待处理' },
  processing: { color: 'blue', label: '处理中' },
  closed: { color: 'gray', label: '已关闭' },
};
const PRIORITY_TAG: Record<string, { color: string; label: string }> = {
  high: { color: 'red', label: '高' },
  medium: { color: 'orange', label: '中' },
  low: { color: 'green', label: '低' },
};

export default function TicketsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState('');
  const [debounced, setDebounced] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [priority, setPriority] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [note, setNote] = useState('');

  useEffect(() => {
    const t = setTimeout(() => setDebounced(keyword.trim()), 300);
    return () => clearTimeout(t);
  }, [keyword]);

  const { data, isLoading } = useQuery({
    queryKey: ['tickets', status, priority, debounced, page, pageSize],
    queryFn: () =>
      listTickets({
        status,
        priority,
        keyword: debounced || undefined,
        page,
        page_size: pageSize,
      }),
    placeholderData: (prev) => prev,
  });
  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ['ticket', detailId],
    queryFn: () => (detailId ? getTicket(detailId) : Promise.resolve(null)),
    enabled: Boolean(detailId),
  });

  const actionMutation = useMutation({
    mutationFn: (action: 'start' | 'close') => {
      if (!detailId) throw new Error('缺少工单');
      return ticketAction(detailId, { action, note });
    },
    onSuccess: () => {
      message.success('操作成功');
      setNote('');
      queryClient.invalidateQueries({ queryKey: ['tickets'] });
      queryClient.invalidateQueries({ queryKey: ['ticket', detailId] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '操作失败'),
  });

  const columns: ColumnsType<TicketItem> = [
    {
      title: '工单编号',
      dataIndex: 'ticket_no',
      width: 220,
      render: (v: string) => <span className="num">{v}</span>,
    },
    { title: '类型', dataIndex: 'type', width: 120, render: (v: string) => <Tag>{v}</Tag> },
    {
      title: '内容',
      dataIndex: 'content',
      ellipsis: true,
      render: (v: string) => <Tooltip title={v}>{v || '—'}</Tooltip>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (s: string) => <Tag color={STATUS_TAG[s]?.color}>{STATUS_TAG[s]?.label ?? s}</Tag>,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      width: 90,
      render: (p: string) => <Tag color={PRIORITY_TAG[p]?.color}>{PRIORITY_TAG[p]?.label ?? p}</Tag>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 170,
      render: (v: string) => v.replace('T', ' ').slice(0, 19),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_, t) => (
        <Button type="link" size="small" onClick={() => setDetailId(t.id)}>
          查看/处理
        </Button>
      ),
    },
  ];

  return (
    <div>
      <h1 className="page-title">客服工单</h1>
      <p className="page-sub">AI 转人工产生的工单自动出现在这里（06_客服工单.md）</p>
      <Card style={{ marginTop: 16, borderRadius: 14, boxShadow: '0 1px 3px rgba(0,0,0,.06)' }}>
        <Space wrap style={{ marginBottom: 16 }}>
          <Input.Search
            placeholder="搜索工单编号/内容"
            allowClear
            style={{ width: 260 }}
            value={keyword}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
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
            options={Object.entries(STATUS_TAG).map(([value, cfg]) => ({
              value,
              label: cfg.label,
            }))}
          />
          <Select
            allowClear
            placeholder="优先级"
            style={{ width: 120 }}
            value={priority}
            onChange={(v) => {
              setPriority(v);
              setPage(1);
            }}
            options={Object.entries(PRIORITY_TAG).map(([value, cfg]) => ({
              value,
              label: cfg.label,
            }))}
          />
        </Space>
        <Table<TicketItem>
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={data?.items ?? []}
          pagination={false}
          locale={{
            emptyText: (
              <Empty description={debounced ? '未找到匹配的工单' : '暂无工单，AI 转人工后自动出现'} />
            ),
          }}
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

      <Drawer
        title={detail ? detail.ticket_no : '工单详情'}
        width={560}
        open={Boolean(detailId)}
        onClose={() => setDetailId(null)}
      >
        {detailLoading || !detail ? (
          <Empty description="加载中" />
        ) : (
          <>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="状态">
                <Tag color={STATUS_TAG[detail.status]?.color}>{STATUS_TAG[detail.status]?.label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="优先级">
                <Tag color={PRIORITY_TAG[detail.priority]?.color}>{PRIORITY_TAG[detail.priority]?.label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="类型">{detail.type}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{detail.created_at.replace('T', ' ').slice(0, 19)}</Descriptions.Item>
              <Descriptions.Item label="来源会话" span={2}>
                <Button
                  type="link"
                  size="small"
                  onClick={() => navigate(`/sessions/${detail.session_id}`)}
                >
                  {detail.session_id.slice(0, 8)}…（查看会话记录）
                </Button>
              </Descriptions.Item>
              <Descriptions.Item label="诉求内容" span={2}>
                <span style={{ whiteSpace: 'pre-wrap' }}>{detail.content}</span>
              </Descriptions.Item>
            </Descriptions>

            <div style={{ marginTop: 16, fontWeight: 600 }}>知识库命中片段（{detail.citations.length}）</div>
            {detail.citations.length === 0 ? (
              <div style={{ color: '#9CA3AF', fontSize: 13, marginTop: 8 }}>无命中片段</div>
            ) : (
              detail.citations.map((c) => (
                <div
                  key={c.chunk_id}
                  style={{ border: '1px solid #E5E7EB', borderRadius: 10, padding: 10, marginTop: 8 }}
                >
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{c.question}</div>
                  <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>{c.answer}</div>
                  <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
                    {c.document_name}
                    {c.row ? ` 行 ${c.row}` : ''}
                  </div>
                </div>
              ))
            )}

            <div style={{ marginTop: 16, fontWeight: 600 }}>处理记录</div>
            <Timeline
              style={{ marginTop: 12 }}
              items={detail.notes.map((n) => ({
                children: (
                  <div>
                    <div>
                      {n.operator || '系统'}
                      {n.status_from && n.status_to
                        ? `：${STATUS_TAG[n.status_from]?.label ?? n.status_from} → ${STATUS_TAG[n.status_to]?.label ?? n.status_to}`
                        : ''}
                    </div>
                    {n.note && <div style={{ color: '#4B5563', marginTop: 2 }}>{n.note}</div>}
                    <div style={{ fontSize: 12, color: '#9CA3AF' }}>
                      {n.created_at.replace('T', ' ').slice(0, 19)}
                    </div>
                  </div>
                ),
              }))}
            />

            {detail.status !== 'closed' && (
              <div style={{ marginTop: 16 }}>
                <Input.TextArea
                  rows={3}
                  placeholder="备注 / 处理结果"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  maxLength={500}
                />
                <Space style={{ marginTop: 12 }}>
                  {detail.status === 'open' && (
                    <Button
                      type="primary"
                      loading={actionMutation.isPending}
                      onClick={() => actionMutation.mutate('start')}
                    >
                      开始处理
                    </Button>
                  )}
                  {detail.status === 'processing' && (
                    <Button
                      type="primary"
                      danger
                      loading={actionMutation.isPending}
                      onClick={() => actionMutation.mutate('close')}
                    >
                      关闭工单
                    </Button>
                  )}
                </Space>
              </div>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
}
