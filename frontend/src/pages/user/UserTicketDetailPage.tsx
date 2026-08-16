/** 用户端工单详情（12 §4.2）：对话流 + 状态流转 + 满意度评价。 */

import { Button, Card, Input, Rate, Space, Tag, Timeline, Typography, message } from 'antd';
import dayjs from 'dayjs';
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import ChatConversation from '../../components/chat/ChatConversation';
import { ApiError } from '../../api/client';
import { getUserTicket, rateUserTicket } from '../../api/user';

const STATUS_LABELS: Record<string, string> = {
  open: '待处理',
  processing: '处理中',
  closed: '已关闭',
};

export default function UserTicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [score, setScore] = useState(5);
  const [comment, setComment] = useState('');
  const [rateOpen, setRateOpen] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['user-ticket', id],
    queryFn: () => getUserTicket(id!),
    enabled: Boolean(id),
  });

  const rateMutation = useMutation({
    mutationFn: () => rateUserTicket(id!, { score, comment: comment || undefined }),
    onSuccess: () => {
      message.success('评价已提交');
      setRateOpen(false);
      void queryClient.invalidateQueries({ queryKey: ['user-ticket', id] });
    },
    onError: (err) => message.error(err instanceof ApiError ? err.message : '评价失败'),
  });

  if (isLoading || !data) return <div style={{ padding: 40, textAlign: 'center' }}>加载中…</div>;

  const { ticket, messages, rating, can_rate } = data;
  const timelineItems = [
    { label: '创建', time: ticket.created_at },
    ...(ticket.claimed_at ? [{ label: '客服认领', time: ticket.claimed_at }] : []),
    ...(ticket.closed_at ? [{ label: '已关闭', time: ticket.closed_at }] : []),
  ];

  return (
    <div style={{ maxWidth: 900, margin: '24px auto', padding: '0 16px' }}>
      <Card
        title={
          <Space>
            <span>{ticket.ticket_no}</span>
            <Tag color={ticket.status === 'closed' ? 'default' : ticket.status === 'processing' ? 'blue' : 'orange'}>
              {STATUS_LABELS[ticket.status]}
            </Tag>
            <Tag color={ticket.priority === 'high' ? 'red' : ticket.priority === 'medium' ? 'orange' : 'default'}>
              {ticket.priority === 'high' ? '高' : ticket.priority === 'medium' ? '中' : '低'}
            </Tag>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Timeline
          items={timelineItems.map((item) => ({
            children: `${item.label}：${dayjs(item.time).format('YYYY-MM-DD HH:mm')}`,
          }))}
        />
        {rating ? (
          <div>
            <Typography.Text strong>我的评价：</Typography.Text>
            <Rate disabled value={rating.score} />
            {rating.comment && <Typography.Paragraph style={{ marginTop: 8 }}>{rating.comment}</Typography.Paragraph>}
          </div>
        ) : (
          can_rate && (
            <Button type="primary" onClick={() => setRateOpen(true)}>
              评价本次服务
            </Button>
          )
        )}
      </Card>

      <Card title="完整对话" style={{ minHeight: 400 }}>
        <ChatConversation
          messages={messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            created_at: m.created_at,
          }))}
        />
      </Card>

      {rateOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.35)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
          onClick={() => setRateOpen(false)}
        >
          <Card title="满意度评价" style={{ width: 420 }} onClick={(e) => e.stopPropagation()}>
            <div style={{ textAlign: 'center', margin: '12px 0' }}>
              <Rate value={score} onChange={setScore} />
            </div>
            <InputArea value={comment} onChange={setComment} />
            <Space style={{ marginTop: 12, justifyContent: 'flex-end', width: '100%' }}>
              <Button onClick={() => setRateOpen(false)}>取消</Button>
              <Button type="primary" loading={rateMutation.isPending} onClick={() => rateMutation.mutate()}>
                提交评价
              </Button>
            </Space>
          </Card>
        </div>
      )}
    </div>
  );
}

function InputArea({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return <Input.TextArea value={value} onChange={(e) => onChange(e.target.value.slice(0, 500))} placeholder="评价内容（可选）" maxLength={500} rows={3} />;
}
