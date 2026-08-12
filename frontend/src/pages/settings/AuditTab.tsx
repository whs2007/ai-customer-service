/** 日志审计 Tab（07 §2）：操作日志 + 对话日志（跳转会话详情）。 */

import { useQuery } from '@tanstack/react-query';
import { Button, Select, Space, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { listAuditLogs, type AuditLog } from '../../api/admin';
import { listSessions } from '../../api/sessions';

export default function AuditTab() {
  const navigate = useNavigate();
  const [action, setAction] = useState<string | undefined>();
  const { data: logs } = useQuery({
    queryKey: ['audit-logs', action],
    queryFn: () => listAuditLogs({ action, page: 1, page_size: 20 }),
  });
  const { data: sessions } = useQuery({
    queryKey: ['sessions-audit'],
    queryFn: () => listSessions({ page: 1, page_size: 10 }),
  });

  const logColumns: ColumnsType<AuditLog> = [
    {
      title: '动作',
      dataIndex: 'action',
      width: 170,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    { title: '目标', dataIndex: 'target_id', width: 220, render: (v: string | null) => <span className="num">{v ?? '—'}</span> },
    { title: 'IP', dataIndex: 'ip', width: 130, render: (v: string | null) => v ?? '—' },
    { title: '时间', dataIndex: 'created_at', render: (v: string) => v.replace('T', ' ').slice(0, 19) },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <strong>操作日志</strong>
          <Select
            allowClear
            placeholder="按动作过滤"
            style={{ width: 180 }}
            value={action}
            onChange={setAction}
            options={[
              { value: 'login', label: '登录' },
              { value: 'login_failed', label: '登录失败' },
              { value: 'user_create', label: '创建用户' },
              { value: 'user_update', label: '更新用户' },
              { value: 'user_password_reset', label: '重置密码' },
              { value: 'delete_knowledge_base', label: '删除知识库' },
              { value: 'delete_document', label: '删除文档' },
              { value: 'ticket_start', label: '工单开始处理' },
              { value: 'ticket_close', label: '工单关闭' },
            ]}
          />
        </div>
        <Table<AuditLog> rowKey="id" size="small" columns={logColumns} dataSource={logs?.items ?? []} pagination={false} />
      </div>
      <div>
        <strong>对话日志</strong>
        <div style={{ fontSize: 12, color: '#9CA3AF', margin: '4px 0 8px' }}>
          会话详情含消息、引用与链路 trace，点击查看
        </div>
        <Table
          rowKey="id"
          size="small"
          dataSource={sessions?.items ?? []}
          pagination={false}
          columns={[
            { title: '会话 ID', dataIndex: 'id', width: 150, render: (v: string) => <span className="num">{v.slice(0, 8)}…</span> },
            { title: '开始时间', dataIndex: 'created_at', render: (v: string) => v.replace('T', ' ').slice(0, 16) },
            { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <Tag>{v}</Tag> },
            {
              title: '操作',
              key: 'actions',
              width: 100,
              render: (_, s) => (
                <Button type="link" size="small" onClick={() => navigate(`/sessions/${s.id}`)}>
                  查看链路
                </Button>
              ),
            },
          ]}
        />
      </div>
    </Space>
  );
}

