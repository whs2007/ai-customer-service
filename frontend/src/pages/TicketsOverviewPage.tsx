/** 管理端工单看板（13 §3.2）：统计卡片 + 超时未认领 + SSE 实时刷新。 */

import { Button, Card, Col, Row, Statistic, Table, Tag, message } from 'antd';
import dayjs from 'dayjs';
import { useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getTicketsOverview } from '../api/agent';
import { connectEventStream } from '../utils/eventStream';

export default function TicketsOverviewPage() {
  const queryClient = useQueryClient();
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['overview'],
    queryFn: getTicketsOverview,
  });

  useEffect(() => {
    const off = connectEventStream(
      '/api/stream/events?scope=admin',
      {
        'ticket.created': () => void queryClient.invalidateQueries({ queryKey: ['overview'] }),
        'ticket.claimed': () => void queryClient.invalidateQueries({ queryKey: ['overview'] }),
        'ticket.closed': () => void queryClient.invalidateQueries({ queryKey: ['overview'] }),
        'ticket.updated': () => void queryClient.invalidateQueries({ queryKey: ['overview'] }),
      },
      {
        onError: () => message.warning('实时连接断开，正在重连…'),
        onReconnect: () => void queryClient.invalidateQueries({ queryKey: ['overview'] }),
      },
    );
    return off;
  }, [queryClient]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 className="page-title">工单看板</h1>
          <p className="page-sub">待处理 / 处理中 / 今日关闭 / 认领超时提醒（13 §3.2）</p>
        </div>
        <Button onClick={() => void refetch()}>刷新</Button>
      </div>

      <Row gutter={16} style={{ marginTop: 8 }}>
        <Col span={6}>
          <Card><Statistic title="总工单数" value={data?.total ?? 0} loading={isLoading} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="待处理" value={data?.open ?? 0} valueStyle={{ color: '#FA8C16' }} loading={isLoading} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="处理中" value={data?.processing ?? 0} valueStyle={{ color: '#1677FF' }} loading={isLoading} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="今日关闭" value={data?.closed_today ?? 0} valueStyle={{ color: '#52C41A' }} loading={isLoading} /></Card>
        </Col>
      </Row>

      <Card title="认领超时提醒（>30 分钟未认领）" style={{ marginTop: 16 }}>
        <Table
          rowKey="ticket_no"
          loading={isLoading}
          dataSource={data?.stale_open ?? []}
          locale={{ emptyText: '暂无超时未认领工单' }}
          pagination={false}
          columns={[
            { title: '工单号', dataIndex: 'ticket_no', render: (v: string) => <Tag color="red">{v}</Tag> },
            { title: '创建时间', dataIndex: 'created_at', render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm') },
            { title: '已等待', dataIndex: 'minutes', width: 120, render: (v: number) => `${v} 分钟` },
          ]}
        />
      </Card>
    </div>
  );
}
