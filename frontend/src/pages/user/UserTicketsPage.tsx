/** 用户端我的工单（12 §4.1）：状态筛选 + 列表 + 实时刷新。 */

import { Table, Tabs, Tag, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { listUserTickets, type UserTicket } from '../../api/user';
import { getUserAccessToken } from '../../api/token';
import { connectEventStream } from '../../utils/eventStream';

const STATUS_LABELS: Record<string, string> = {
  open: '待处理',
  processing: '处理中',
  closed: '已关闭',
};

const PRIORITY_COLORS: Record<string, string> = {
  high: 'red',
  medium: 'orange',
  low: 'default',
};

export default function UserTicketsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['user-tickets'],
    queryFn: () => listUserTickets({ page: 1, page_size: 50 }),
  });

  useEffect(() => {
    const off = connectEventStream(
      '/api/stream/events?scope=user',
      {
        'ticket.created': () => void queryClient.invalidateQueries({ queryKey: ['user-tickets'] }),
        'ticket.claimed': () => void queryClient.invalidateQueries({ queryKey: ['user-tickets'] }),
        'ticket.closed': () => void queryClient.invalidateQueries({ queryKey: ['user-tickets'] }),
        'ticket.updated': () => void queryClient.invalidateQueries({ queryKey: ['user-tickets'] }),
      },
      {
        token: getUserAccessToken(),
        onError: () => message.warning('实时连接断开，正在重连…'),
        onReconnect: () => void queryClient.invalidateQueries({ queryKey: ['user-tickets'] }),
      },
    );
    return off;
  }, [queryClient]);

  const filterTickets = (status?: string) =>
    (data?.items ?? []).filter((t) => !status || t.status === status);

  return (
    <div style={{ maxWidth: 960, margin: '24px auto', padding: '0 16px' }}>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        我的工单
      </Typography.Title>
      <Tabs
        items={[
          { key: 'all', label: '全部', children: <TicketTable loading={isLoading} tickets={filterTickets()} onRow={navigate} /> },
          { key: 'open', label: '待处理', children: <TicketTable loading={isLoading} tickets={filterTickets('open')} onRow={navigate} /> },
          { key: 'processing', label: '处理中', children: <TicketTable loading={isLoading} tickets={filterTickets('processing')} onRow={navigate} /> },
          { key: 'closed', label: '已关闭', children: <TicketTable loading={isLoading} tickets={filterTickets('closed')} onRow={navigate} /> },
        ]}
      />
    </div>
  );
}

function TicketTable({
  tickets,
  loading,
  onRow,
}: {
  tickets: UserTicket[];
  loading: boolean;
  onRow: (id: string) => void;
}) {
  return (
    <Table<UserTicket>
      rowKey="id"
      size="middle"
      loading={loading}
      dataSource={tickets}
      columns={[
        { title: '工单号', dataIndex: 'ticket_no' },
        {
          title: '状态',
          dataIndex: 'status',
          width: 100,
          render: (v: string) => (
            <Tag color={v === 'closed' ? 'default' : v === 'processing' ? 'blue' : 'orange'}>
              {STATUS_LABELS[v]}
            </Tag>
          ),
        },
        {
          title: '优先级',
          dataIndex: 'priority',
          width: 90,
          render: (v: string) => <Tag color={PRIORITY_COLORS[v]}>{v === 'high' ? '高' : v === 'medium' ? '中' : '低'}</Tag>,
        },
        {
          title: '最后更新时间',
          dataIndex: 'updated_at',
          width: 180,
          render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
        },
      ]}
      onRow={(record) => ({
        onClick: () => onRow(`/user/tickets/${record.id}`),
        style: { cursor: 'pointer' },
      })}
      pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
    />
  );
}
